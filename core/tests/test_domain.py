import uuid
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from core.models import Participant, Session, Attendance, Quiz, Question, AnswerChoice, QuizAttempt, QuizResponse, ScoreTransaction, ScoringRule
from core.services import check_in_participant, submit_quiz_answer, participant_competition_totals, finalize_daily_ranking

class IdentityTests(TestCase):
    def test_participant_requires_staff_id_or_email_and_gets_one_pass(self):
        with self.assertRaises(ValidationError):
            Participant(full_name="No Identity").full_clean()
        p=Participant.objects.create(full_name="Grace Mushi",staff_id=" crdb-0842 ",email="GRACE@CRDB.TZ",department="Risk & Compliance")
        self.assertEqual(p.staff_id,"CRDB-0842")
        self.assertEqual(p.email,"grace@crdb.tz")
        self.assertTrue(p.qr_token)
        self.assertTrue(p.pass_number.startswith("CRDB-LW-"))

class AttendanceTests(TestCase):
    def test_duplicate_check_in_returns_existing_attendance(self):
        p=Participant.objects.create(full_name="Grace",staff_id="G1")
        s=Session.objects.create(day=1,title="Official session",starts_at=timezone.now(),ends_at=timezone.now()+timezone.timedelta(hours=1))
        first,created1=check_in_participant(participant=p,session=s)
        second,created2=check_in_participant(participant=p,session=s)
        self.assertTrue(created1); self.assertFalse(created2); self.assertEqual(first.pk,second.pk)
        self.assertEqual(ScoreTransaction.objects.filter(participant=p,category="attendance").count(),1)
    def test_check_in_uses_configurable_scoring_rule(self):
        ScoringRule.objects.create(code="session_checkin",category="attendance",points=175,is_active=True)
        p=Participant.objects.create(full_name="Grace",staff_id="G2")
        s=Session.objects.create(day=1,title="Official session",starts_at=timezone.now(),ends_at=timezone.now()+timezone.timedelta(hours=1))
        check_in_participant(participant=p,session=s)
        self.assertEqual(ScoreTransaction.objects.get(participant=p).points,175)

class QuizIntegrityTests(TestCase):
    def setUp(self):
        self.p=Participant.objects.create(full_name="Amina",staff_id="A1")
        self.quiz=Quiz.objects.create(day=1,title="Official challenge",sequence=1,state="question_open",prize_eligible=True)
        self.q=Question.objects.create(quiz=self.quiz,number=1,text="Source question",time_limit_seconds=20,base_points=1000,is_open=True,opened_at=timezone.now(),closes_at=timezone.now()+timezone.timedelta(seconds=20))
        self.correct=AnswerChoice.objects.create(question=self.q,number=1,text="Correct",is_correct=True)
        AnswerChoice.objects.create(question=self.q,number=2,text="Wrong")
        AnswerChoice.objects.create(question=self.q,number=3,text="Wrong 2")
        AnswerChoice.objects.create(question=self.q,number=4,text="Wrong 3")
        self.attempt=QuizAttempt.objects.create(participant=self.p,quiz=self.quiz,authorised=True)

    def test_correct_answer_writes_a_traceable_competition_ledger_entry_not_learning_xp(self):
        r=submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=uuid.uuid4(),response_duration_ms=1200)
        self.assertEqual(r.base_points_awarded,1000); self.assertEqual(r.speed_points_awarded,0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.official_score,1000)
        entry=ScoreTransaction.objects.get(participant=self.p,category="competition")
        self.assertEqual(entry.points,0)
        self.assertEqual(entry.competition_points,1000)
        self.assertEqual(entry.source_type,"quiz_response")
        self.assertEqual(entry.source_id,str(r.pk))

    def test_duplicate_question_submission_is_rejected(self):
        submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=uuid.uuid4(),response_duration_ms=1000)
        with self.assertRaises(IntegrityError):
            submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=uuid.uuid4(),response_duration_ms=900)

    def test_same_submission_uuid_replays_without_double_scoring(self):
        submission_id=uuid.uuid4()
        first=submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=submission_id,response_duration_ms=0)
        second=submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=submission_id,response_duration_ms=0)
        self.attempt.refresh_from_db()
        self.assertEqual(first.pk,second.pk)
        self.assertTrue(second._idempotent_replay)
        self.assertEqual(self.attempt.official_score,1000)
        self.assertEqual(ScoreTransaction.objects.filter(category="competition").count(),1)

    def test_response_duration_is_derived_from_server_timestamps(self):
        self.q.opened_at=timezone.now()-timezone.timedelta(seconds=2)
        self.q.closes_at=timezone.now()+timezone.timedelta(seconds=18)
        self.q.save(update_fields=["opened_at","closes_at"])
        response=submit_quiz_answer(attempt=self.attempt,question=self.q,choice=self.correct,submission_id=uuid.uuid4(),response_duration_ms=0)
        self.assertGreaterEqual(response.response_duration_ms,1500)
        self.assertLessEqual(response.response_duration_ms,3000)

    def test_weekly_total_sums_official_attempt_scores(self):
        self.attempt.official_score=8000; self.attempt.correct_count=8; self.attempt.save()
        quiz2=Quiz.objects.create(day=2,title="Second official challenge",sequence=2,prize_eligible=True)
        QuizAttempt.objects.create(participant=self.p,quiz=quiz2,authorised=True,official_score=9000,correct_count=9)
        totals=participant_competition_totals(self.p)
        self.assertEqual(totals["weekly_score"],17000)
        self.assertEqual(totals["correct_count"],17)
        self.assertEqual([row["day"] for row in totals["daily"]],[1,2])
        self.assertEqual(totals["daily"][1]["score"],9000)

class RankingTests(TestCase):
    def test_daily_ranking_uses_score_correct_time_and_stores_rank(self):
        quiz=Quiz.objects.create(day=1,title="Official",sequence=1,state="finished")
        p1=Participant.objects.create(full_name="First",staff_id="R1")
        p2=Participant.objects.create(full_name="Second",staff_id="R2")
        a1=QuizAttempt.objects.create(participant=p1,quiz=quiz,official_score=9000,correct_count=9,total_response_ms=15000)
        a2=QuizAttempt.objects.create(participant=p2,quiz=quiz,official_score=9000,correct_count=9,total_response_ms=16000)
        winners=finalize_daily_ranking(quiz)
        a1.refresh_from_db(); a2.refresh_from_db()
        self.assertEqual([a1.final_daily_rank,a2.final_daily_rank],[1,2])
        self.assertEqual(winners[0].participant,p1)
