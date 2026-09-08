import hmac, json, logging, uuid
from datetime import datetime
from functools import wraps
from io import BytesIO
from django.conf import settings
from django.core.cache import cache

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError,transaction
from django.db.models import Count,Q,Sum
from django.http import HttpResponse,JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.db import connection
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET,require_POST
from django_ratelimit.decorators import ratelimit
import qrcode
import qrcode.image.svg
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .decorators import participant_required
from .control_views import audit,control_required
from .forms import SelfRegistrationForm
from .integrations import apply_pal_callback,build_pal_launch,verify_callback_signature
from .models import Activity,ActivityCompletion,AnswerChoice,Attendance,EventSettings,Experience,Participant,Question,Quiz,QuizAttempt,QuizResponse,ScoreTransaction,Session,SessionRegistration
from .services import award_activity,check_in_participant,derive_live_state,learning_xp,participant_competition_totals,round_runs_until,schedule_round,submit_quiz_answer

logger=logging.getLogger(__name__)

def participant_rate_key(group,request):
    """Rate-limit key that survives a shared corporate gateway.

    A whole venue sits behind one NAT address, so keying on IP alone would put
    2,000 people in a single bucket and lock the room out mid-round. Prefer the
    signed-in Learning Pass, then the browser session, and fall back to IP only
    for a visitor who has neither yet.
    """
    participant_id=request.session.get("participant_id")
    if participant_id: return f"p:{participant_id}"
    if request.session.session_key: return f"s:{request.session.session_key}"
    forwarded=request.META.get("HTTP_X_FORWARDED_FOR","")
    return "i:"+(forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR","") or "unknown")

def _ratelimit(key,rate_setting,method="ALL"):
    """Wrap django-ratelimit so limits stay retunable at run time.

    The rate and the on/off switch are read per request, not at import, so an
    operator can widen a limit mid-event without a code change or a restart.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not settings.RATELIMIT_ENABLE:
                request.limited=False
                return view(request,*args,**kwargs)
            limited=ratelimit(key=key,rate=getattr(settings,rate_setting),method=method,block=False)
            return limited(view)(request,*args,**kwargs)
        return wrapped
    return decorator

def _rate_limited(request):
    return getattr(request,"limited",False)

@require_GET
def health(request):
    state={"status":"ready","django":"ready","database":"ready","redis":"not_configured"}
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1"); cursor.fetchone()
    except Exception:
        state.update(status="degraded",database="unavailable")
    if settings.REDIS_URL:
        try:
            from redis import Redis
            Redis.from_url(settings.REDIS_URL,socket_connect_timeout=1,socket_timeout=1).ping()
            state["redis"]="ready"
        except Exception:
            state.update(status="degraded",redis="unavailable")
    return JsonResponse(state,status=200 if state["status"]=="ready" else 503)

def landing(request):
    sessions=Session.objects.filter(is_active=True).order_by("starts_at")[:5]
    registered=cache.get("landing:registered")
    if registered is None:
        registered=Participant.objects.filter(is_active=True).count()
        cache.set("landing:registered",registered,60)
    return render(request,"core/landing.html",{"registered":registered,"sessions":sessions})

def _sign_in(request,participant):
    request.session.cycle_key(); request.session["participant_id"]=str(participant.id)
    return redirect("learning-pass")

@_ratelimit(participant_rate_key,"RATELIMIT_ACCESS",method="POST")
def access(request):
    """Enter an email address. Known people go straight in; new people give a name and join.

    Pre-loading a roster from a spreadsheet or Google Form still works and takes
    priority: a match on staff ID or email always signs in rather than registering.
    """
    event=EventSettings.load()
    if request.method=="GET":
        # Establish the session here so the submission that follows is rate-limited
        # per person rather than per gateway. A bot that posts without loading the
        # page has no session and correctly falls back to a per-IP limit.
        if not request.session.session_key: request.session.create()
        return render(request,"core/access.html",{"event":event})
    if _rate_limited(request):
        return render(request,"core/access.html",{"event":event,"throttled":True},status=429)

    if request.POST.get("step")=="register":
        if not event.self_registration_enabled:
            return render(request,"core/access.html",{"event":event,"not_found":True},status=403)
        form=SelfRegistrationForm(request.POST,settings_row=event)
        if form.is_valid():
            try:
                participant=form.save()
            except (IntegrityError,ValidationError):
                # Someone registered the same address between validation and save.
                existing=Participant.objects.filter(email=form.cleaned_data["email"],is_active=True).first()
                if existing: return _sign_in(request,existing)
                return render(request,"core/access.html",{"event":event,"form":form,"registering":True},status=409)
            logger.info("Self-registration: %s",participant.pk)
            return _sign_in(request,participant)
        return render(request,"core/access.html",{"event":event,"form":form,"registering":True},status=400)

    identity=request.POST.get("identity","").strip()
    if not identity or len(identity)>254:
        return render(request,"core/access.html",{"event":event,"not_found":True},status=404)
    participant=Participant.objects.filter(Q(staff_id__iexact=identity)|Q(email__iexact=identity),is_active=True).first()
    if participant: return _sign_in(request,participant)
    if not event.self_registration_enabled:
        return render(request,"core/access.html",{"event":event,"not_found":True},status=404)
    # Unknown identity and self-registration is open: carry it into the join form.
    initial={"email":identity} if "@" in identity else {"staff_id":identity}
    return render(request,"core/access.html",{"event":event,"form":SelfRegistrationForm(initial=initial,settings_row=event),"registering":True,"new_here":True})
CLOSED_LABELS={Quiz.State.DRAFT:"NOT READY",Quiz.State.FINISHED:"FINISHED",
               Quiz.State.VERIFIED:"RESULTS VERIFIED",Quiz.State.ARCHIVED:"CLOSED"}

def _quiz_tile(experience,played):
    """A round tile: what it is, whether it can be entered, and what to call it.

    Rounds are listed as they are, without day labels; a scheduled round can be
    entered because auto-run opens its lobby only seconds before question one.
    """
    quiz=experience.quiz
    state,_=derive_live_state(quiz)
    closed=state in CLOSED_LABELS
    live=state in (Quiz.State.QUESTION_OPEN,Quiz.State.REVEAL,Quiz.State.QUESTION_CLOSED)
    return {"experience":experience,"quiz":quiz,"joined":quiz.id in played,
            "questions":quiz.questions.count(),"open":not closed,
            "label":CLOSED_LABELS.get(state,"LIVE NOW" if live else "READY TO JOIN")}

def participant_points(participant):
    """Everything that makes up the number a participant cares about.

    Competition points come from official quiz rounds; Learning XP comes from
    interactive games, stand activities, PAL and session check-in. The total is
    what the dashboard leads with.
    """
    competition=participant_competition_totals(participant)
    xp=learning_xp(participant)
    return {"competition":competition,"xp":xp,"total":competition["weekly_score"]+xp}

@participant_required
def dashboard(request):
    p=request.participant
    points=participant_points(p)
    live=Experience.objects.filter(show_on_dashboard=True).exclude(status=Experience.Status.ARCHIVED)
    quizzes=(live.filter(type=Experience.Type.QUIZ).select_related("quiz").prefetch_related("quiz__questions").order_by("day","start_at"))
    games=(live.filter(type__in=[Experience.Type.EXPO_ACTIVITY,Experience.Type.AIOT_DEMO,Experience.Type.CUSTOM_CHALLENGE,Experience.Type.PAL_CHALLENGE])
           .select_related("activity").order_by("day","title"))
    done=set(p.activity_completions.values_list("activity_id",flat=True))
    played=set(p.quiz_attempts.filter(authorised=True).values_list("quiz_id",flat=True))
    return render(request,"core/dashboard.html",{
        "participant":p,"points":points,"xp":points["xp"],"competition":points["competition"],
        "quizzes":[_quiz_tile(item,played) for item in quizzes if item.quiz_id],
        "games":[{"experience":item,"activity":item.activity,"done":item.activity_id in done} for item in games],
        "badges":p.badge_awards.select_related("badge"),
        "pal":p.pal_results.order_by("-created_at").first()})
@participant_required
def learning_pass(request):
    p=request.participant
    points=participant_points(p)
    return render(request,"core/pass.html",{"participant":p,"points":points,"xp":points["xp"],
        "competition":points["competition"],"games_done":p.activity_completions.count()})
@participant_required
def learning_pass_qr(request):
    payload=request.build_absolute_uri(reverse("scan-token",args=[request.participant.qr_token]))
    image=qrcode.make(payload,image_factory=qrcode.image.svg.SvgPathImage,box_size=12,border=4)
    stream=BytesIO(); image.save(stream)
    return HttpResponse(stream.getvalue(),content_type="image/svg+xml")
def weekly_leaderboard_rows(limit=100):
    """Top weekly standings, cached: every participant hits this page during a live round."""
    key=f"leaderboard:weekly:{limit}"
    rows=cache.get(key)
    if rows is None:
        rows=list(QuizAttempt.objects.filter(authorised=True,quiz__prize_eligible=True,quiz__contributes_to_weekly=True).exclude(state=QuizAttempt.State.VOID)
            .values("participant_id","participant__full_name","participant__department")
            .annotate(score=Sum("official_score"),correct=Sum("correct_count"),response_ms=Sum("total_response_ms"))
            .filter(score__gt=0).order_by("-score","-correct","response_ms","participant_id")[:limit])
        for position,row in enumerate(rows,start=1):
            row["position"]=position
            # Match the Participant.public_name masking: the public board shows
            # "Grace M." rather than a full staff name.
            parts=(row["participant__full_name"] or "").split()
            row["public_name"]=row["participant__full_name"] if len(parts)<2 else f"{parts[0]} {parts[-1][0]}."
            row["department"]=row["participant__department"]
        cache.set(key,rows,settings.LEADERBOARD_CACHE_SECONDS)
    return rows

@participant_required
def leaderboard(request):
    rows=weekly_leaderboard_rows()
    mine=next((row for row in rows if row["participant_id"]==request.participant.id),None)
    return render(request,"core/leaderboard.html",{"leaders":rows,"my_row":mine,"participant":request.participant,
        "points":participant_points(request.participant),"competition":participant_competition_totals(request.participant)})
@participant_required
def pal_launch(request): return redirect(build_pal_launch(request.participant))
@csrf_exempt
@require_POST
def pal_callback(request):
    if not verify_callback_signature(request.body,request.headers.get("X-PAL-Signature")): return JsonResponse({"error":"invalid_signature"},status=401)
    try: result=apply_pal_callback(json.loads(request.body),request.body)
    except (KeyError,ValueError,Participant.DoesNotExist): return JsonResponse({"error":"invalid_payload"},status=400)
    return JsonResponse({"status":result.status,"result_id":result.external_result_id})

def scan_token(request,token):
    participant=get_object_or_404(Participant,qr_token=token,is_active=True)
    if not request.user.is_staff: return redirect(f"{reverse('control-login')}?next={request.path}")
    return render(request,"core/scanner.html",{"scanned_participant":participant,
        "sessions":Session.objects.filter(is_active=True).order_by("starts_at"),
        "activities":Activity.objects.filter(is_active=True).order_by("name")})
@control_required
def scanner(request):
    return render(request,"core/scanner.html",{
        "sessions":Session.objects.filter(is_active=True).order_by("starts_at"),
        "activities":Activity.objects.filter(is_active=True).order_by("name")})
@control_required
@require_POST
def api_scan(request):
    """Award a scanned Learning Pass, either an expo game or a session check-in.

    One endpoint so the stand operator picks what they are scanning for and the
    rest of the flow is identical.
    """
    try:
        data=json.loads(request.body)
        target=str(data.get("target",""))
        kind,_,raw_id=target.partition(":")
        participant=Participant.objects.get(qr_token=data["qr_token"],is_active=True)
        if kind=="activity":
            activity=Activity.objects.get(pk=int(raw_id),is_active=True)
            _,created=award_activity(participant=participant,activity=activity,actor=request.user)
            return JsonResponse({"status":"awarded" if created else "already_awarded",
                "participant":{"name":participant.full_name,"department":participant.department},
                "what":activity.name,"points":activity.points if created else 0,
                "total_points":learning_xp(participant)},status=201 if created else 200)
        if kind=="session":
            session=Session.objects.get(pk=int(raw_id),is_active=True)
            attendance,created=check_in_participant(participant=participant,session=session,actor=request.user)
            return JsonResponse({"status":"awarded" if created else "already_awarded",
                "participant":{"name":participant.full_name,"department":participant.department,
                    "registered":SessionRegistration.objects.filter(participant=participant,session=session).exists()},
                "what":session.title,"points":0,"checked_in_at":attendance.checked_in_at.isoformat(),
                "total_points":learning_xp(participant)},status=201 if created else 200)
        return JsonResponse({"error":"choose_target","detail":"Select a game or session first."},status=400)
    except (KeyError,TypeError,ValueError,json.JSONDecodeError,ValidationError,
            Participant.DoesNotExist,Session.DoesNotExist,Activity.DoesNotExist):
        return JsonResponse({"error":"invalid_scan","detail":"That QR code was not recognised."},status=400)
    except IntegrityError:
        return JsonResponse({"error":"scan_conflict","detail":"Another device scanned this pass at the same moment."},status=409)

@control_required
@require_POST
def api_check_in(request):
    try:
        data=json.loads(request.body); participant=Participant.objects.get(qr_token=data["qr_token"],is_active=True); session=Session.objects.get(pk=data["session_id"],is_active=True)
        attendance,created=check_in_participant(participant=participant,session=session,actor=request.user)
        return JsonResponse({"status":"success" if created else "already_checked_in","participant":{"name":participant.full_name,"department":participant.department,"registered":SessionRegistration.objects.filter(participant=participant,session=session).exists()},"checked_in_at":attendance.checked_in_at.isoformat()},status=201 if created else 200)
    except (KeyError,ValueError,json.JSONDecodeError,ValidationError,Participant.DoesNotExist,Session.DoesNotExist): return JsonResponse({"error":"invalid_scan"},status=400)
    except IntegrityError:
        return JsonResponse({"error":"check_in_conflict","detail":"Another device checked this pass in at the same moment. Refresh to confirm."},status=409)
@control_required
def control_room(request):
    stats={"registered":Participant.objects.count(),"checked_in_today":Attendance.objects.count(),"quiz_participants":QuizAttempt.objects.values("participant_id").distinct().count(),"pal_completed":ScoreTransaction.objects.filter(category="pal").count()}
    return render(request,"core/control_room.html",{"stats":stats,"sessions":Session.objects.all()[:8],"quizzes":Quiz.objects.all()})
@control_required
def prizes(request):
    attempts=QuizAttempt.objects.filter(authorised=True,quiz__prize_eligible=True).select_related("participant","quiz").order_by("quiz__day","-official_score","-correct_count","total_response_ms")
    return render(request,"core/prizes.html",{"attempts":attempts})

@participant_required
def quizzes(request):
    # One hub is easier to navigate than two: the dashboard already lists rounds and games.
    return redirect("dashboard")

@participant_required
def quiz_play(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.prefetch_related("questions"),pk=quiz_id)
    attempt=QuizAttempt.objects.filter(participant=request.participant,quiz=quiz,authorised=True).exclude(state="void").first()
    state,question=derive_live_state(quiz)
    answered=attempt.responses.filter(question=question).exists() if attempt and question else False
    live=bool(question and question.is_live() and state==Quiz.State.QUESTION_OPEN)
    starts_in=None
    if state==Quiz.State.LOBBY and quiz.auto_started_at:
        starts_in=max(0,int((quiz.auto_started_at-timezone.now()).total_seconds()))
    return render(request,"core/quiz_play.html",{"quiz":quiz,"attempt":attempt,"question":question,
        "state":state,"answered":answered,"question_live":live,"starts_in":starts_in,
        "total_questions":quiz.questions.count(),
        "time_up":bool(question and not live and state==Quiz.State.QUESTION_OPEN)})

# Everything except these accepts new players. An auto-run round opens its lobby
# for only a few seconds before question 1, so players must be able to join a
# scheduled round beforehand, and latecomers must be able to join mid-round.
CLOSED_TO_NEW_PLAYERS=(Quiz.State.DRAFT,Quiz.State.FINISHED,Quiz.State.VERIFIED,Quiz.State.ARCHIVED)

@participant_required
@require_POST
def quiz_join(request,quiz_id):
    quiz=get_object_or_404(Quiz,pk=quiz_id)
    existing=QuizAttempt.objects.filter(participant=request.participant,quiz=quiz,authorised=True).exclude(state=QuizAttempt.State.VOID).first()
    if existing is None:
        live_state,_=derive_live_state(quiz)
        if quiz.state in CLOSED_TO_NEW_PLAYERS or live_state==Quiz.State.FINISHED:
            messages.error(request,"This round is not open for entry.")
            return redirect("quiz-play",quiz_id=quiz.id)
        try:
            with transaction.atomic():
                QuizAttempt.objects.create(participant=request.participant,quiz=quiz,authorised=True,state=QuizAttempt.State.ACTIVE)
        except IntegrityError:
            # Double submit or two devices: the unique authorised-attempt constraint
            # already holds the single valid attempt, so this is a successful join.
            pass
    return redirect("quiz-play",quiz_id=quiz.id)

@participant_required
@_ratelimit(participant_rate_key,"RATELIMIT_ANSWER",method="POST")
@require_POST
def quiz_answer(request,quiz_id):
    if _rate_limited(request):
        return JsonResponse({"error":"too_many_submissions"},status=429)
    try:
        data=json.loads(request.body)
        attempt=QuizAttempt.objects.get(participant=request.participant,quiz_id=quiz_id,authorised=True,state=QuizAttempt.State.ACTIVE)
        question=Question.objects.get(pk=data["question_id"],quiz_id=quiz_id)
        choice=AnswerChoice.objects.get(pk=data["choice_id"],question=question)
        response=submit_quiz_answer(attempt=attempt,question=question,choice=choice,submission_id=uuid.UUID(data["submission_id"]),response_duration_ms=int(data["response_duration_ms"]))
        return JsonResponse({"status":"correct" if response.is_correct else "incorrect","competition_points":response.base_points_awarded+response.speed_points_awarded},status=200 if getattr(response,"_idempotent_replay",False) else 201)
    except (KeyError,TypeError,ValueError,json.JSONDecodeError,QuizAttempt.DoesNotExist,Question.DoesNotExist,AnswerChoice.DoesNotExist,ValidationError): return JsonResponse({"error":"invalid_submission"},status=400)
    except (PermissionDenied,IntegrityError): return JsonResponse({"error":"question_closed_or_already_answered"},status=409)

def quiz_public_state(quiz_id):
    """Quiz-wide half of the state payload, identical for every player.

    Caching it turns a 2,000-client poll into one database read per cache window
    instead of one read per client.
    """
    key=f"quiz:schedule:{quiz_id}"
    schedule=cache.get(key)
    if schedule is None:
        quiz=Quiz.objects.prefetch_related("questions__choices").filter(pk=quiz_id).first()
        if quiz is None: return None
        # Cache the whole schedule, not one question. An auto-run round changes on
        # the clock rather than on a host action, so every client can derive the
        # current question itself and the database is read once per cache window.
        schedule={"auto_run":quiz.auto_run,"stored_state":quiz.state,
                  "started":quiz.auto_started_at.isoformat() if quiz.auto_started_at else None,
                  "current_id":quiz.current_question_id,"questions":[
            {"id":q.id,"number":q.number,"text":q.text,
             "opens_at":q.opened_at.isoformat() if q.opened_at else None,
             "closes_at":q.closes_at.isoformat() if q.closes_at else None,
             "is_open":q.is_open,
             "choices":[{"id":c.id,"number":c.number,"text":c.text} for c in q.choices.all()]}
            for q in quiz.questions.all().order_by("number")]}
        cache.set(key,schedule,5)
    return _state_from_schedule(schedule)

def _state_from_schedule(schedule,now=None):
    """Work out the live state from the cached schedule, judged at this instant."""
    now=now or timezone.now()
    questions=schedule["questions"]
    def payload(question):
        return {"id":question["id"],"number":question["number"],"text":question["text"],
                "closes_at":question["closes_at"],"choices":question["choices"]}
    if schedule["auto_run"] and schedule["started"] and questions:
        opens=[datetime.fromisoformat(q["opens_at"]) for q in questions if q["opens_at"]]
        if len(opens)==len(questions):
            if now<opens[0]:
                return {"state":Quiz.State.LOBBY,"question":None,"starts_at":questions[0]["opens_at"]}
            for index,question in enumerate(questions):
                start=datetime.fromisoformat(question["opens_at"]); end=datetime.fromisoformat(question["closes_at"])
                if start<=now<=end:
                    return {"state":Quiz.State.QUESTION_OPEN,"question":payload(question),"starts_at":None}
                following=questions[index+1] if index+1<len(questions) else None
                if following and end<now<datetime.fromisoformat(following["opens_at"]):
                    return {"state":Quiz.State.REVEAL,"question":None,"starts_at":following["opens_at"]}
            return {"state":Quiz.State.FINISHED,"question":None,"starts_at":None}
    # Host-paced round: the stored state governs, still bounded by the deadline.
    current=next((q for q in questions if q["id"]==schedule["current_id"]),None)
    if schedule["stored_state"]==Quiz.State.QUESTION_OPEN and current and current["closes_at"]:
        if now<=datetime.fromisoformat(current["closes_at"]):
            return {"state":Quiz.State.QUESTION_OPEN,"question":payload(current),"starts_at":None}
        return {"state":Quiz.State.QUESTION_CLOSED,"question":None,"starts_at":None}
    return {"state":schedule["stored_state"],"question":None,"starts_at":None}

def invalidate_quiz_state(quiz_id):
    cache.delete(f"quiz:schedule:{quiz_id}")

@participant_required
@_ratelimit(participant_rate_key,"RATELIMIT_STATE",method="GET")
@require_GET
def quiz_state(request,quiz_id):
    if _rate_limited(request):
        return JsonResponse({"error":"too_many_requests"},status=429)
    payload=quiz_public_state(quiz_id)
    if payload is None: return JsonResponse({"error":"not_found"},status=404)
    attempt=QuizAttempt.objects.filter(participant=request.participant,quiz_id=quiz_id,authorised=True).exclude(state=QuizAttempt.State.VOID).only("id","official_score").first()
    question_id=(payload["question"] or {}).get("id")
    answered=bool(attempt and question_id and QuizResponse.objects.filter(attempt=attempt,question_id=question_id).exists())
    return JsonResponse({"state":payload["state"],"server_time":timezone.now().isoformat(),"joined":bool(attempt),
        "answered":answered,"score":attempt.official_score if attempt else 0,
        "question":payload["question"],"starts_at":payload.get("starts_at")})

def close_expired_question(quiz):
    """Close the running question once its timer has run out.

    Kahoot ends a question on the clock, not on a click. Doing the same here also
    removes the state that produced stale question_open rounds: a host who walks
    away no longer leaves answers apparently open but actually refused.

    Called from the host screen, which one person has open, rather than from the
    participant poll, which 2,000 people hit.
    """
    question=quiz.current_question
    if not (quiz.auto_close_questions and question and quiz.state==Quiz.State.QUESTION_OPEN): return False
    if question.is_live(): return False
    Question.objects.filter(pk=question.pk).update(is_open=False)
    quiz.state=Quiz.State.REVEAL
    quiz.save(update_fields=["state","updated_at"])
    invalidate_quiz_state(quiz.id)
    broadcast_quiz_state(quiz)
    return True

def broadcast_quiz_state(quiz):
    try:
        async_to_sync(get_channel_layer().group_send)(f"quiz_{quiz.id}",{"type":"quiz.state","payload":{"state":quiz.state,"question_id":quiz.current_question_id}})
    except Exception:
        # The database stays authoritative and clients fall back to polling /state/,
        # so a channel-layer outage must never block the round.
        logger.exception("Quiz state broadcast failed for quiz %s",quiz.id)

def open_question(quiz,question):
    quiz.questions.update(is_open=False)
    now=timezone.now()
    question.is_open=True; question.opened_at=now
    question.closes_at=now+timezone.timedelta(seconds=question.time_limit_seconds)
    question.save(update_fields=["is_open","opened_at","closes_at","updated_at"])
    quiz.current_question=question
    quiz.state=Quiz.State.QUESTION_OPEN

@control_required
def quiz_control(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.select_related("current_question").prefetch_related("questions"),pk=quiz_id)
    if not quiz.auto_run:
        close_expired_question(quiz)
        quiz.refresh_from_db()
    live_state,live_question=derive_live_state(quiz)
    question=live_question if quiz.auto_run else quiz.current_question
    answer_counts=question.choices.annotate(response_count=Count("responses")).order_by("number") if question else []
    upcoming=quiz.questions.filter(number__gt=question.number).order_by("number").first() if question else quiz.questions.order_by("number").first()
    now=timezone.now()
    runs_until=round_runs_until(quiz) if quiz.auto_started_at else None
    return render(request,"core/quiz_control.html",{"quiz":quiz,"players":quiz.attempts.filter(authorised=True).count(),
        "question":question,"answer_counts":answer_counts,"upcoming":upcoming,
        "total_questions":quiz.questions.count(),"live_state":live_state,
        "running":bool(quiz.auto_run and quiz.auto_started_at and live_state!=Quiz.State.FINISHED),
        "starts_in":max(0,int((quiz.auto_started_at-now).total_seconds())) if quiz.auto_started_at and live_state==Quiz.State.LOBBY else 0,
        "ends_at":runs_until,
        "total_seconds":int((runs_until-quiz.auto_started_at).total_seconds()) if runs_until and quiz.auto_started_at else 0,
        "seconds_left":max(0,int((question.closes_at-now).total_seconds())) if question and question.closes_at and question.is_live(now) else 0,
        "response_count":question.responses.count() if question else 0})

@control_required
@require_POST
def quiz_control_action(request,quiz_id):
    quiz=get_object_or_404(Quiz,pk=quiz_id); action=request.POST.get("action"); before={"state":quiz.state,"question_id":quiz.current_question_id}
    if action=="start_round":
        # One press schedules every question. Nothing has to come back and advance it.
        try:
            schedule_round(quiz)
        except ValidationError as exc:
            messages.error(request," ".join(exc.messages))
            return redirect("quiz-control",quiz_id=quiz.id)
        invalidate_quiz_state(quiz.id)
        audit(request,"quiz.start_round",quiz,before=before,after={"started_at":quiz.auto_started_at.isoformat()})
        broadcast_quiz_state(quiz)
        messages.success(request,f"ROUND RUNNING / {quiz.questions.count()} QUESTIONS WILL PLAY AUTOMATICALLY")
        return redirect("quiz-control",quiz_id=quiz.id)
    if action=="abort_round":
        quiz.auto_started_at=None; quiz.current_question=None; quiz.state=Quiz.State.LOBBY
        quiz.questions.update(is_open=False,opened_at=None,closes_at=None)
    elif action=="open_lobby": quiz.state=Quiz.State.LOBBY
    elif action in ("open_question","next_question"):
        if quiz.state==Quiz.State.DRAFT:
            messages.error(request,"Publish this round before launching a question.")
            return redirect("quiz-control",quiz_id=quiz.id)
        if action=="next_question":
            current=quiz.current_question
            question=(quiz.questions.filter(number__gt=current.number) if current else quiz.questions).order_by("number").first()
            if question is None:
                messages.info(request,"That was the last question. End the round to publish the results.")
                return redirect("quiz-control",quiz_id=quiz.id)
        else:
            question=get_object_or_404(Question,pk=request.POST.get("question_id"),quiz=quiz)
        open_question(quiz,question)
    elif action=="close_question":
        if quiz.current_question_id:
            quiz.current_question.is_open=False; quiz.current_question.save(update_fields=["is_open","updated_at"])
        quiz.state=Quiz.State.QUESTION_CLOSED
    elif action=="show_answer": quiz.state=Quiz.State.REVEAL
    elif action=="show_leaderboard": quiz.state=Quiz.State.LEADERBOARD
    elif action=="end_quiz": quiz.state=Quiz.State.FINISHED
    else: return JsonResponse({"error":"invalid_action"},status=400)
    quiz.save()
    invalidate_quiz_state(quiz.id)
    audit(request,f"quiz.{action}",quiz,before=before,after={"state":quiz.state,"question_id":quiz.current_question_id})
    broadcast_quiz_state(quiz)
    return redirect("quiz-control",quiz_id=quiz.id)

@control_required
def projector_leaderboard(request,quiz_id=None):
    """Top ten for a room-facing screen.

    Daily and weekly boards render one shared row shape so both mask surnames the
    same way the participant leaderboard does. Set PROJECTOR_SHOW_FULL_NAMES=1 to
    show full names instead, e.g. for a prize announcement.
    """
    attempts=QuizAttempt.objects.filter(authorised=True).exclude(state=QuizAttempt.State.VOID)
    title="LEARNING WEEK / FINAL LEADERBOARD"
    if quiz_id:
        quiz=get_object_or_404(Quiz,pk=quiz_id); attempts=attempts.filter(quiz=quiz); title=f"DAY {quiz.day} / {quiz.title}"
    rows=(attempts.values("participant_id","participant__full_name","participant__department")
          .annotate(official_score=Sum("official_score"),correct_count=Sum("correct_count"),total_response_ms=Sum("total_response_ms"))
          .order_by("-official_score","-correct_count","total_response_ms","participant_id")[:10])
    leaders=[]
    for position,row in enumerate(rows,start=1):
        full_name=row["participant__full_name"] or ""
        parts=full_name.split()
        leaders.append({"position":position,
                        "name":full_name if settings.PROJECTOR_SHOW_FULL_NAMES or len(parts)<2 else f"{parts[0]} {parts[-1][0]}.",
                        "department":row["participant__department"],
                        "official_score":row["official_score"] or 0})
    return render(request,"core/projector.html",{"leaders":leaders,"title":title,"weekly":not quiz_id})

@csrf_exempt
@require_POST
@transaction.atomic
def activity_complete(request):
    presented=request.headers.get("X-Activity-Key","")
    if not settings.ACTIVITY_API_KEY or not hmac.compare_digest(presented,settings.ACTIVITY_API_KEY):
        return JsonResponse({"error":"unauthorised"},status=401)
    try:
        data=json.loads(request.body)
        participant=Participant.objects.get(qr_token=data["qr_token"],is_active=True)
        activity=Activity.objects.get(code=data["activity_code"],is_active=True)
        _,created=award_activity(participant=participant,activity=activity,
            external_id=data.get("external_id",""),metadata=data.get("metadata",{}))
        return JsonResponse({"status":"complete" if created else "already_complete","participant":participant.public_name,"activity":activity.name,"points":activity.points},status=201 if created else 200)
    except (KeyError,TypeError,ValueError,json.JSONDecodeError,Participant.DoesNotExist,Activity.DoesNotExist):
        return JsonResponse({"error":"invalid_activity_completion"},status=400)
    except IntegrityError:
        return JsonResponse({"status":"already_complete"},status=200)
