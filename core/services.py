from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from .models import ActivityCompletion, Attendance, Question, Quiz, QuizAttempt, QuizResponse, ScoreTransaction, ScoringRule, WinnerRecord

@transaction.atomic
def check_in_participant(*,participant,session,actor=None,override=False,note=""):
    attendance,created=Attendance.objects.get_or_create(participant=participant,session=session,defaults={"checked_in_at":timezone.now(),"checked_in_by":actor,"is_override":override,"override_note":note})
    if created:
        rule=ScoringRule.objects.filter(code="session_checkin",is_active=True).first()
        points=rule.points if rule else 100
        ScoreTransaction.objects.get_or_create(participant=participant,category="attendance",idempotency_key=f"attendance:{attendance.pk}",defaults={"points":points,"learning_xp":points,"source_type":"attendance","source_id":str(attendance.pk),"description":f"Session check-in / {session.title}","actor":actor})
    return attendance,created

@transaction.atomic
def submit_quiz_answer(*,attempt,question,choice,submission_id,response_duration_ms):
    attempt=QuizAttempt.objects.select_for_update().select_related("quiz").get(pk=attempt.pk)
    now=timezone.now()
    if not attempt.authorised or attempt.state!="active": raise PermissionDenied("Attempt is not active.")
    if question.quiz_id!=attempt.quiz_id or choice.question_id!=question.id: raise ValidationError("Question/choice does not belong to this attempt.")
    existing=QuizResponse.objects.filter(submission_id=submission_id).first()
    if existing:
        if existing.attempt_id==attempt.id and existing.question_id==question.id and existing.selected_choice_id==choice.id:
            existing._idempotent_replay=True
            return existing
        raise IntegrityError("Submission identifier was already used for different answer data.")
    if not question.is_live(now): raise PermissionDenied("Question is closed.")
    if QuizResponse.objects.filter(attempt=attempt,question=question).exists(): raise IntegrityError("Duplicate question submission.")
    correct=choice.is_correct
    base=question.base_points if correct else 0
    speed=0
    duration_ms=max(0,int((now-question.opened_at).total_seconds()*1000)) if question.opened_at else 0
    duration_ms=min(duration_ms,question.time_limit_seconds*1000)
    response=QuizResponse.objects.create(attempt=attempt,question=question,selected_choice=choice,submission_id=submission_id,is_correct=correct,base_points_awarded=base,speed_points_awarded=speed,response_duration_ms=duration_ms)
    ScoreTransaction.objects.create(participant=attempt.participant,category="competition",points=0,competition_points=base+speed,learning_xp=0,source_type="quiz_response",source_id=str(response.pk),reason=f"Quiz {attempt.quiz_id} / question {question.number}",idempotency_key=f"quiz_response:{response.pk}",description=f"{attempt.quiz.title} / Q{question.number:02d}")
    attempt.official_score+=base+speed
    attempt.correct_count+=int(correct)
    attempt.total_response_ms+=duration_ms
    attempt.save(update_fields=["official_score","correct_count","total_response_ms","updated_at"])
    return response

def participant_competition_totals(participant):
    attempts=QuizAttempt.objects.filter(participant=participant,authorised=True,quiz__prize_eligible=True,quiz__contributes_to_weekly=True).exclude(state="void").select_related("quiz").order_by("quiz__day","quiz__sequence")
    data=attempts.aggregate(weekly_score=Sum("official_score"),correct_count=Sum("correct_count"),response_ms=Sum("total_response_ms"))
    totals={key:(value or 0) for key,value in data.items()}
    totals["daily"]=[{"day":attempt.quiz.day,"quiz":attempt.quiz.title,"score":attempt.official_score,"correct":attempt.correct_count,"rank":attempt.final_daily_rank,"state":attempt.quiz.state} for attempt in attempts]
    return totals

def learning_xp(participant):
    return ScoreTransaction.objects.filter(participant=participant).aggregate(total=Sum("points"))["total"] or 0

@transaction.atomic
def finalize_daily_ranking(quiz):
    attempts=list(QuizAttempt.objects.select_for_update().filter(quiz=quiz,authorised=True).exclude(state="void").select_related("participant").order_by("-official_score","-correct_count","total_response_ms","completed_at","id"))
    WinnerRecord.objects.filter(quiz=quiz,scope="daily").delete()
    winners=[]
    for rank,attempt in enumerate(attempts,start=1):
        attempt.final_daily_rank=rank; attempt.save(update_fields=["final_daily_rank","updated_at"])
        if rank<=3:
            winners.append(WinnerRecord.objects.create(participant=attempt.participant,quiz=quiz,scope="daily",calculated_rank=rank,final_rank=rank,score_snapshot=attempt.official_score,correct_snapshot=attempt.correct_count,response_ms_snapshot=attempt.total_response_ms))
    return winners


@transaction.atomic
def award_activity(*, participant, activity, actor=None, external_id="", metadata=None):
    """Record that someone completed an expo game and give them its points.

    Idempotent: scanning the same pass twice at the same stand reports the
    existing completion instead of paying out again. Shared by the staff QR
    scanner and the stand-device API so both can never diverge.
    """
    completion, created = ActivityCompletion.objects.get_or_create(
        participant=participant, activity=activity,
        defaults={"completed_at": timezone.now(), "external_id": str(external_id or ""), "metadata": metadata or {}},
    )
    if created:
        ScoreTransaction.objects.get_or_create(
            participant=participant, category="expo", idempotency_key=f"activity:{completion.pk}",
            defaults={"points": activity.points, "learning_xp": activity.points,
                      "source_type": "activity_completion", "source_id": str(completion.pk),
                      "description": f"Activity / {activity.name}", "actor": actor},
        )
    return completion, created


@transaction.atomic
def schedule_round(quiz, start_at=None):
    """Launch the whole round at once.

    Every question gets its open and close time written up front, derived from
    one start instant and each question's own time limit. Nothing has to come
    back and advance the round: the clock does it, and every client works out
    where the round is from the same stored schedule.

    Returns the list of questions with their windows set.
    """
    questions = list(quiz.questions.order_by("number"))
    if not questions:
        raise ValidationError("This round has no questions to run.")
    start = start_at or (timezone.now() + timezone.timedelta(seconds=quiz.lobby_seconds))
    cursor = start
    for question in questions:
        question.opened_at = cursor
        question.closes_at = cursor + timezone.timedelta(seconds=question.time_limit_seconds)
        question.is_open = True
        cursor = question.closes_at + timezone.timedelta(seconds=quiz.reveal_seconds)
    Question.objects.bulk_update(questions, ["opened_at", "closes_at", "is_open", "updated_at"])
    quiz.auto_started_at = start
    quiz.current_question = questions[0]
    quiz.state = Quiz.State.QUESTION_OPEN
    quiz.save(update_fields=["auto_started_at", "current_question", "state", "updated_at"])
    return questions


def round_runs_until(quiz):
    """When the last question of a scheduled round closes."""
    last = quiz.questions.order_by("-number").first()
    return last.closes_at if last else None


def derive_live_state(quiz, now=None):
    """Where an auto-run round is right now, worked out purely from the clock.

    Returns (state, question). No database writes, so 2,000 clients asking at
    once cost nothing beyond the read that is already cached.
    """
    now = now or timezone.now()
    if not (quiz.auto_run and quiz.auto_started_at):
        return quiz.state, quiz.current_question
    questions = list(quiz.questions.order_by("number"))
    if not questions:
        return quiz.state, None
    if now < questions[0].opened_at:
        return Quiz.State.LOBBY, None
    for index, question in enumerate(questions):
        if question.opened_at <= now <= question.closes_at:
            return Quiz.State.QUESTION_OPEN, question
        following = questions[index + 1] if index + 1 < len(questions) else None
        if following and question.closes_at < now < following.opened_at:
            # The gap between two questions is where the answer is shown.
            return Quiz.State.REVEAL, question
    return Quiz.State.FINISHED, questions[-1]
