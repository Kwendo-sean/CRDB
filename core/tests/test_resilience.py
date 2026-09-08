"""Regression cover for the failure modes that would surface under event-day load."""

import json
import uuid

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Activity, AnswerChoice, Attendance, Participant, Question, Quiz, QuizAttempt, QuizResponse, Session


class SessionRecoveryTests(TestCase):
    """A Learning Pass cookie can outlive the row it points at."""

    def test_unreadable_participant_id_signs_the_visitor_out_instead_of_erroring(self):
        session = self.client.session
        session["participant_id"] = "not-a-uuid"
        session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("participant-access"))
        self.assertNotIn("participant_id", self.client.session)

    def test_deleted_participant_signs_the_visitor_out(self):
        participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G9")
        session = self.client.session
        session["participant_id"] = str(participant.id)
        session.save()
        participant.delete()
        self.assertRedirects(self.client.get(reverse("learning-pass")), reverse("participant-access"))

    def test_deactivated_participant_cannot_keep_using_an_old_session(self):
        participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G8")
        session = self.client.session
        session["participant_id"] = str(participant.id)
        session.save()
        Participant.objects.filter(pk=participant.pk).update(is_active=False)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("participant-access"))


class QuizJoinTests(TestCase):
    def setUp(self):
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G1")
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1, state=Quiz.State.LOBBY)
        session = self.client.session
        session["participant_id"] = str(self.participant.id)
        session.save()

    def test_joining_twice_does_not_error_and_keeps_one_attempt(self):
        first = self.client.post(reverse("quiz-join", args=[self.quiz.id]))
        second = self.client.post(reverse("quiz-join", args=[self.quiz.id]))
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(QuizAttempt.objects.filter(participant=self.participant, quiz=self.quiz).count(), 1)

    def test_joining_a_closed_round_redirects_with_a_message_rather_than_a_json_error(self):
        self.quiz.state = Quiz.State.DRAFT
        self.quiz.save(update_fields=["state"])
        response = self.client.post(reverse("quiz-join", args=[self.quiz.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not open for entry")
        self.assertFalse(QuizAttempt.objects.exists())

    def test_a_player_who_joined_earlier_can_still_reach_a_finished_round(self):
        QuizAttempt.objects.create(participant=self.participant, quiz=self.quiz)
        self.quiz.state = Quiz.State.FINISHED
        self.quiz.save(update_fields=["state"])
        self.assertRedirects(
            self.client.post(reverse("quiz-join", args=[self.quiz.id])),
            reverse("quiz-play", args=[self.quiz.id]),
        )


class QuizStateCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G2")
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1,
                                        state=Quiz.State.QUESTION_OPEN, auto_run=False)
        self.question = Question.objects.create(
            quiz=self.quiz, number=1, text="Which layer settles payments?", time_limit_seconds=20,
            base_points=1000, is_open=True, opened_at=timezone.now(),
            closes_at=timezone.now() + timezone.timedelta(seconds=20),
        )
        self.choice = AnswerChoice.objects.create(question=self.question, number=1, text="The switch", is_correct=True)
        for number in range(2, 5):
            AnswerChoice.objects.create(question=self.question, number=number, text=f"Option {number}")
        self.quiz.current_question = self.question
        self.quiz.save(update_fields=["current_question"])
        session = self.client.session
        session["participant_id"] = str(self.participant.id)
        session.save()

    def tearDown(self):
        cache.clear()

    def test_the_shared_half_of_the_payload_is_cached_across_players(self):
        self.client.get(reverse("quiz-state", args=[self.quiz.id]))
        self.assertIsNotNone(cache.get(f"quiz:schedule:{self.quiz.id}"))

    def test_a_cached_payload_still_never_reveals_the_correct_answer(self):
        payload = self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()
        self.assertEqual(len(payload["question"]["choices"]), 4)
        for choice in payload["question"]["choices"]:
            self.assertNotIn("is_correct", choice)

    def test_the_answered_flag_stays_per_participant_despite_the_shared_cache(self):
        attempt = QuizAttempt.objects.create(participant=self.participant, quiz=self.quiz)
        self.assertFalse(self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()["answered"])
        QuizResponse.objects.create(
            attempt=attempt, question=self.question, selected_choice=self.choice, submission_id=uuid.uuid4(),
            is_correct=True, base_points_awarded=1000, response_duration_ms=900,
        )
        payload = self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()
        self.assertTrue(payload["answered"])
        self.assertEqual(payload["score"], 0, "score comes from the attempt row, not the shared cache")

    def test_a_host_action_invalidates_the_cache_immediately(self):
        self.client.get(reverse("quiz-state", args=[self.quiz.id]))
        get_user_model().objects.create_user("host", password="control-room-pass", is_staff=True)
        host = self.client.__class__()
        host.login(username="host", password="control-room-pass")
        host.post(reverse("quiz-control-action", args=[self.quiz.id]), {"action": "close_question"})
        self.assertIsNone(cache.get(f"quiz:state:{self.quiz.id}"))
        self.assertEqual(self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()["state"], Quiz.State.QUESTION_CLOSED)

    def test_state_for_an_unknown_round_is_a_404_not_a_crash(self):
        self.assertEqual(self.client.get(reverse("quiz-state", args=[9999])).status_code, 404)


class CheckInResilienceTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        self.client.login(username="ops", password="control-room-pass")
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G3")
        now = timezone.now()
        self.session = Session.objects.create(day=1, title="Keynote", starts_at=now, ends_at=now + timezone.timedelta(hours=1))

    def post(self, payload):
        return self.client.post(reverse("api-check-in"), data=json.dumps(payload), content_type="application/json")

    def test_scanning_the_same_pass_twice_reports_already_checked_in(self):
        first = self.post({"qr_token": self.participant.qr_token, "session_id": self.session.id})
        second = self.post({"qr_token": self.participant.qr_token, "session_id": self.session.id})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "already_checked_in")
        self.assertEqual(Attendance.objects.count(), 1)

    def test_a_malformed_scan_is_a_clean_400(self):
        self.assertEqual(self.post({"qr_token": "rubbish", "session_id": self.session.id}).status_code, 400)
        self.assertEqual(self.post({"session_id": self.session.id}).status_code, 400)


@override_settings(ACTIVITY_API_KEY="stand-device-key")
class ActivityApiTests(TestCase):
    def setUp(self):
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="G4")
        self.activity = Activity.objects.create(code="aiot-demo", name="AIoT Demo", day=2, points=150)

    def post(self, payload, key="stand-device-key"):
        return self.client.post(
            reverse("activity-complete"), data=json.dumps(payload),
            content_type="application/json", headers={"x-activity-key": key},
        )

    def test_a_wrong_key_is_rejected(self):
        self.assertEqual(self.post({"qr_token": self.participant.qr_token, "activity_code": "aiot-demo"}, key="wrong").status_code, 401)

    def test_completion_is_idempotent(self):
        payload = {"qr_token": self.participant.qr_token, "activity_code": "aiot-demo"}
        self.assertEqual(self.post(payload).status_code, 201)
        second = self.post(payload)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "already_complete")

    def test_an_unknown_activity_code_is_a_clean_400(self):
        self.assertEqual(self.post({"qr_token": self.participant.qr_token, "activity_code": "nope"}).status_code, 400)


class ControlRoomScaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        now = timezone.now()
        cls.session = Session.objects.create(day=1, title="Keynote", starts_at=now, ends_at=now + timezone.timedelta(hours=1))
        cls.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1)
        Participant.objects.bulk_create([
            Participant(full_name=f"Person {number:04d}", staff_id=f"S{number:04d}") for number in range(250)
        ])

    def setUp(self):
        self.client.login(username="ops", password="control-room-pass")

    def test_participant_list_is_paginated(self):
        response = self.client.get(reverse("control-participants"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["participants"]), 100)
        self.assertEqual(response.context["total"], 250)
        self.assertTrue(response.context["page"].has_next())

    def test_attendance_and_attempt_counts_are_not_inflated_by_each_other(self):
        person = Participant.objects.first()
        Attendance.objects.create(participant=person, session=self.session, checked_in_at=timezone.now())
        QuizAttempt.objects.create(participant=person, quiz=self.quiz)
        response = self.client.get(reverse("control-participants"), {"q": person.full_name})
        row = response.context["participants"][0]
        self.assertEqual((row.attended, row.attempts), (1, 1))

    def test_overview_does_not_scale_its_queries_with_the_roster(self):
        """It once prefetched every registration and attendance row for all sessions."""
        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("control-room"))
        self.assertLess(len(captured), 15, " | ".join(query["sql"][:100] for query in captured))

    def test_export_streams_every_participant(self):
        response = self.client.get(reverse("control-participants-export"))
        body = b"".join(response.streaming_content).decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body.strip().splitlines()), 251)
        self.assertTrue(body.startswith("staff_id,full_name,email"))

    def test_export_escapes_a_name_containing_a_comma(self):
        Participant.objects.create(full_name='Mushi, Grace "GM"', staff_id="S9999")
        body = b"".join(self.client.get(reverse("control-participants-export")).streaming_content).decode()
        self.assertIn('"Mushi, Grace ""GM"""', body)


class ProjectorBoardTests(TestCase):
    """Daily and weekly boards must agree on how they present a name."""

    def setUp(self):
        get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        self.client.login(username="ops", password="control-room-pass")
        self.person = Participant.objects.create(full_name="Grace Mushi", staff_id="G7")
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1)
        QuizAttempt.objects.create(participant=self.person, quiz=self.quiz, official_score=1000, correct_count=1)

    def names(self, path):
        return [row["name"] for row in self.client.get(path).context["leaders"]]

    def test_daily_and_weekly_mask_surnames_identically(self):
        weekly = self.names(reverse("projector-weekly"))
        daily = self.names(reverse("projector-daily", args=[self.quiz.id]))
        self.assertEqual(weekly, ["Grace M."])
        self.assertEqual(weekly, daily)

    @override_settings(PROJECTOR_SHOW_FULL_NAMES=True)
    def test_full_names_can_be_switched_on_for_a_prize_announcement(self):
        self.assertEqual(self.names(reverse("projector-weekly")), ["Grace Mushi"])

    def test_a_single_word_name_is_shown_whole(self):
        Participant.objects.filter(pk=self.person.pk).update(full_name="Mushi")
        self.assertEqual(self.names(reverse("projector-weekly")), ["Mushi"])

    def test_void_attempts_are_excluded_from_the_room_facing_board(self):
        QuizAttempt.objects.filter(participant=self.person).update(state=QuizAttempt.State.VOID)
        self.assertEqual(self.names(reverse("projector-weekly")), [])


class PassNumberTests(TestCase):
    """Pass numbers are drawn at random; a collision must not fail a registration."""

    def test_a_collision_is_redrawn_rather_than_failing_the_registration(self):
        first = Participant.objects.create(full_name="Grace Mushi", staff_id="P1")
        # Force the exact clash the random draw can produce at scale.
        second = Participant(full_name="Juma Almasi", staff_id="P2")
        second.pass_number = first.pass_number
        second.save()
        second.refresh_from_db()
        self.assertNotEqual(second.pass_number, first.pass_number)
        self.assertTrue(second.pass_number.startswith("CRDB-LW-"))
        self.assertEqual(Participant.objects.count(), 2)

    def test_the_redraw_does_not_apply_to_an_existing_participant(self):
        first = Participant.objects.create(full_name="Grace Mushi", staff_id="P3")
        second = Participant.objects.create(full_name="Juma Almasi", staff_id="P4")
        # Editing a saved row into a clash is an operator error, not a random draw:
        # it must surface rather than silently reassign someone a new pass.
        second.pass_number = first.pass_number
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises(DjangoValidationError):
            second.save()

    def test_a_genuine_duplicate_email_still_raises(self):
        from django.core.exceptions import ValidationError as DjangoValidationError
        Participant.objects.create(full_name="Grace Mushi", email="grace@crdbbank.co.tz")
        with self.assertRaises(DjangoValidationError):
            Participant.objects.create(full_name="Someone Else", email="grace@crdbbank.co.tz")

    def test_two_thousand_participants_all_get_distinct_passes(self):
        people = [Participant.objects.create(full_name=f"Person {n:04d}", staff_id=f"B{n:04d}") for n in range(2000)]
        passes = {person.pass_number for person in people}
        self.assertEqual(len(passes), 2000)
        self.assertTrue(all(p.startswith("CRDB-LW-") and len(p) == 16 for p in passes))


class ExpiredQuestionTests(TestCase):
    """A question whose timer ran out must stop being offered, not just refused."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="E1")
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1,
                                        state=Quiz.State.QUESTION_OPEN, auto_run=False)
        opened = timezone.now() - timezone.timedelta(minutes=20)
        self.question = Question.objects.create(
            quiz=self.quiz, number=1, text="Expired question", time_limit_seconds=20,
            base_points=1000, is_open=True, opened_at=opened,
            closes_at=opened + timezone.timedelta(seconds=20),
        )
        self.choice = AnswerChoice.objects.create(question=self.question, number=1, text="A", is_correct=True)
        for n in range(2, 5):
            AnswerChoice.objects.create(question=self.question, number=n, text=f"Option {n}")
        self.quiz.current_question = self.question
        self.quiz.save(update_fields=["current_question"])
        QuizAttempt.objects.create(participant=self.participant, quiz=self.quiz)
        session = self.client.session
        session["participant_id"] = str(self.participant.id)
        session.save()

    def test_is_live_is_false_once_the_deadline_passes(self):
        self.assertFalse(self.question.is_live())

    def test_the_state_endpoint_stops_serving_an_expired_question(self):
        payload = self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()
        self.assertIsNone(payload["question"], "an expired question must not be offered")
        self.assertEqual(payload["state"], Quiz.State.QUESTION_CLOSED)

    def test_the_play_page_shows_time_up_instead_of_answer_buttons(self):
        response = self.client.get(reverse("quiz-play", args=[self.quiz.id]))
        self.assertContains(response, "TIME IS UP")
        self.assertNotContains(response, "data-choice=")

    def test_a_deadline_inside_the_cache_window_still_expires_immediately(self):
        """The schedule is cached; the clock reading of it must not be."""
        closes = timezone.now() + timezone.timedelta(seconds=1)
        Question.objects.filter(pk=self.question.pk).update(closes_at=closes)
        self.assertIsNotNone(self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()["question"])
        # Leave the cached schedule in place and let only the wall clock move past it.
        with patch("core.views.timezone.now", return_value=closes + timezone.timedelta(seconds=5)):
            payload = self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()
        self.assertIsNone(payload["question"],
                          "the deadline must be judged per request, not when the schedule was cached")


class HostConsoleTests(TestCase):
    """One press per question, and the timer closes the question by itself."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        get_user_model().objects.create_user("host", password="control-room-pass", is_staff=True)
        self.client.login(username="host", password="control-room-pass")
        # This class covers the host-paced mode; auto-run has its own class below.
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1,
                                        state=Quiz.State.LOBBY, auto_run=False)
        for number in range(1, 4):
            question = Question.objects.create(quiz=self.quiz, number=number, text=f"Q{number}",
                                               time_limit_seconds=20, base_points=1000)
            for n in range(1, 5):
                AnswerChoice.objects.create(question=question, number=n, text=f"A{n}", is_correct=n == 1)

    def press(self, action):
        return self.client.post(reverse("quiz-control-action", args=[self.quiz.id]), {"action": action})

    def current(self):
        self.quiz.refresh_from_db()
        return self.quiz.current_question

    def test_next_question_walks_the_round_with_one_press_each(self):
        self.press("next_question")
        self.assertEqual(self.current().number, 1)
        self.press("next_question")
        self.assertEqual(self.current().number, 2)
        self.press("next_question")
        self.assertEqual(self.current().number, 3)

    def test_next_question_sets_the_deadline_from_the_server_clock(self):
        self.press("next_question")
        question = self.current()
        self.assertTrue(question.is_open)
        self.assertIsNotNone(question.closes_at)
        self.assertAlmostEqual((question.closes_at - question.opened_at).total_seconds(), 20, delta=1)

    def test_only_one_question_is_ever_open(self):
        self.press("next_question")
        self.press("next_question")
        self.assertEqual(Question.objects.filter(quiz=self.quiz, is_open=True).count(), 1)

    def test_running_past_the_last_question_does_not_error(self):
        for _ in range(5):
            response = self.press("next_question")
            self.assertEqual(response.status_code, 302)
        self.assertEqual(self.current().number, 3)

    def test_the_expired_question_closes_itself_when_the_host_screen_loads(self):
        self.press("next_question")
        question = self.current()
        Question.objects.filter(pk=question.pk).update(closes_at=timezone.now() - timezone.timedelta(seconds=1))
        self.client.get(reverse("quiz-control", args=[self.quiz.id]))
        self.quiz.refresh_from_db()
        question.refresh_from_db()
        self.assertFalse(question.is_open, "the timer, not a click, should close the question")
        self.assertEqual(self.quiz.state, Quiz.State.REVEAL)

    def test_auto_close_can_be_switched_off_for_a_manual_round(self):
        Quiz.objects.filter(pk=self.quiz.pk).update(auto_close_questions=False)
        self.press("next_question")
        question = self.current()
        Question.objects.filter(pk=question.pk).update(closes_at=timezone.now() - timezone.timedelta(seconds=1))
        self.client.get(reverse("quiz-control", args=[self.quiz.id]))
        question.refresh_from_db()
        self.assertTrue(question.is_open)

    def test_the_host_screen_offers_a_single_primary_action(self):
        response = self.client.get(reverse("quiz-control", args=[self.quiz.id]))
        self.assertContains(response, "START QUESTION 01")
        self.assertEqual(response.content.count(b'class="button primary big"'), 1)


class AutoRunRoundTests(TestCase):
    """One press launches every question; the clock does the rest."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        get_user_model().objects.create_user("host", password="control-room-pass", is_staff=True)
        self.host = self.client_class()
        self.host.login(username="host", password="control-room-pass")
        self.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1,
                                        state=Quiz.State.SCHEDULED, auto_run=True,
                                        lobby_seconds=10, reveal_seconds=5)
        for number in range(1, 4):
            question = Question.objects.create(quiz=self.quiz, number=number, text=f"Q{number}",
                                               time_limit_seconds=20, base_points=1000)
            for n in range(1, 5):
                AnswerChoice.objects.create(question=question, number=n, text=f"A{n}", is_correct=n == 1)
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="AR1")
        QuizAttempt.objects.create(participant=self.participant, quiz=self.quiz)
        session = self.client.session
        session["participant_id"] = str(self.participant.id)
        session.save()

    def start(self):
        return self.host.post(reverse("quiz-control-action", args=[self.quiz.id]), {"action": "start_round"})

    def state_at(self, offset_seconds):
        """What a participant polling at start+offset sees."""
        cache.clear()
        moment = self.quiz.auto_started_at + timezone.timedelta(seconds=offset_seconds)
        with patch("core.views.timezone.now", return_value=moment), \
             patch("core.services.timezone.now", return_value=moment):
            return self.client.get(reverse("quiz-state", args=[self.quiz.id])).json()

    def test_one_press_schedules_every_question(self):
        self.start()
        self.quiz.refresh_from_db()
        questions = list(self.quiz.questions.order_by("number"))
        self.assertIsNotNone(self.quiz.auto_started_at)
        for question in questions:
            self.assertIsNotNone(question.opened_at, f"Q{question.number} was not scheduled")
            self.assertIsNotNone(question.closes_at)

    def test_the_questions_run_back_to_back_with_a_reveal_gap(self):
        self.start()
        self.quiz.refresh_from_db()
        first, second, third = self.quiz.questions.order_by("number")
        self.assertEqual((first.closes_at - first.opened_at).total_seconds(), 20)
        self.assertEqual((second.opened_at - first.closes_at).total_seconds(), 5)
        self.assertEqual((third.opened_at - second.closes_at).total_seconds(), 5)

    def test_the_round_walks_itself_with_no_further_host_action(self):
        self.start()
        self.quiz.refresh_from_db()
        # offsets measured from the moment question 1 opens
        self.assertEqual(self.state_at(-5)["state"], Quiz.State.LOBBY)
        self.assertEqual(self.state_at(1)["question"]["number"], 1)
        self.assertEqual(self.state_at(22)["state"], Quiz.State.REVEAL)
        self.assertEqual(self.state_at(26)["question"]["number"], 2)
        self.assertEqual(self.state_at(51)["question"]["number"], 3)
        self.assertEqual(self.state_at(200)["state"], Quiz.State.FINISHED)
        self.assertEqual(self.host.post(reverse("quiz-control-action", args=[self.quiz.id]),
                                        {"action": "start_round"}).status_code, 302)

    def test_answers_are_accepted_only_inside_a_question_window(self):
        from core.services import submit_quiz_answer
        from django.core.exceptions import PermissionDenied
        self.start()
        self.quiz.refresh_from_db()
        attempt = QuizAttempt.objects.get(participant=self.participant, quiz=self.quiz)
        second = self.quiz.questions.get(number=2)
        choice = second.choices.first()
        during_first = self.quiz.auto_started_at + timezone.timedelta(seconds=5)
        with patch("core.services.timezone.now", return_value=during_first):
            with self.assertRaises(PermissionDenied):
                submit_quiz_answer(attempt=attempt, question=second, choice=choice,
                                   submission_id=uuid.uuid4(), response_duration_ms=100)
        during_second = second.opened_at + timezone.timedelta(seconds=3)
        with patch("core.services.timezone.now", return_value=during_second):
            response = submit_quiz_answer(attempt=attempt, question=second, choice=choice,
                                          submission_id=uuid.uuid4(), response_duration_ms=100)
        self.assertTrue(response.is_correct)

    def test_the_host_screen_asks_for_one_press_then_stops_asking(self):
        before = self.host.get(reverse("quiz-control", args=[self.quiz.id]))
        self.assertContains(before, "START THE ROUND")
        self.start()
        self.quiz.refresh_from_db()

        during_lobby = self.host.get(reverse("quiz-control", args=[self.quiz.id]))
        self.assertNotContains(during_lobby, "START THE ROUND")
        self.assertNotContains(during_lobby, 'value="next_question"')
        self.assertContains(during_lobby, "opens automatically")

        mid_round = self.quiz.auto_started_at + timezone.timedelta(seconds=5)
        with patch("core.views.timezone.now", return_value=mid_round),              patch("core.services.timezone.now", return_value=mid_round):
            running = self.host.get(reverse("quiz-control", args=[self.quiz.id]))
        self.assertContains(running, "advancing on its own")
        self.assertNotContains(running, 'value="next_question"')
        self.assertNotContains(running, 'class="button primary big"')

    def test_a_round_with_no_questions_is_refused_clearly(self):
        empty = Quiz.objects.create(day=2, title="Empty", sequence=2, state=Quiz.State.SCHEDULED)
        response = self.host.post(reverse("quiz-control-action", args=[empty.id]),
                                  {"action": "start_round"}, follow=True)
        self.assertContains(response, "no questions")
        empty.refresh_from_db()
        self.assertIsNone(empty.auto_started_at)

    def test_the_round_can_be_stopped_and_reset(self):
        self.start()
        self.host.post(reverse("quiz-control-action", args=[self.quiz.id]), {"action": "abort_round"})
        self.quiz.refresh_from_db()
        self.assertIsNone(self.quiz.auto_started_at)
        self.assertEqual(self.quiz.state, Quiz.State.LOBBY)
        self.assertFalse(self.quiz.questions.filter(is_open=True).exists())

    def test_long_per_question_timers_are_allowed(self):
        Question.objects.filter(quiz=self.quiz).update(time_limit_seconds=300)
        self.start()
        self.quiz.refresh_from_db()
        first = self.quiz.questions.order_by("number").first()
        self.assertEqual((first.closes_at - first.opened_at).total_seconds(), 300)

    def test_players_can_join_before_the_round_starts(self):
        newcomer = Participant.objects.create(full_name="Early Bird", staff_id="AR2")
        client = self.client_class()
        session = client.session
        session["participant_id"] = str(newcomer.id)
        session.save()
        client.post(reverse("quiz-join", args=[self.quiz.id]))
        self.assertTrue(QuizAttempt.objects.filter(participant=newcomer, quiz=self.quiz).exists(),
                        "an auto-run lobby is only seconds long; early joiners must not be locked out")

    def test_latecomers_can_join_a_running_round(self):
        self.start()
        self.quiz.refresh_from_db()
        latecomer = Participant.objects.create(full_name="Late Comer", staff_id="AR3")
        client = self.client_class()
        session = client.session
        session["participant_id"] = str(latecomer.id)
        session.save()
        mid = self.quiz.auto_started_at + timezone.timedelta(seconds=25)
        with patch("core.views.timezone.now", return_value=mid), \
             patch("core.services.timezone.now", return_value=mid):
            client.post(reverse("quiz-join", args=[self.quiz.id]))
        self.assertTrue(QuizAttempt.objects.filter(participant=latecomer, quiz=self.quiz).exists())

    def test_nobody_can_join_after_the_round_has_played_out(self):
        self.start()
        self.quiz.refresh_from_db()
        straggler = Participant.objects.create(full_name="Too Late", staff_id="AR4")
        client = self.client_class()
        session = client.session
        session["participant_id"] = str(straggler.id)
        session.save()
        after = self.quiz.auto_started_at + timezone.timedelta(hours=1)
        with patch("core.views.timezone.now", return_value=after), \
             patch("core.services.timezone.now", return_value=after):
            client.post(reverse("quiz-join", args=[self.quiz.id]))
        self.assertFalse(QuizAttempt.objects.filter(participant=straggler, quiz=self.quiz).exists())
