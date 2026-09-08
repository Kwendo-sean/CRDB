"""Query-count guards at full event scale.

These do not measure wall-clock speed, which depends on the host. They assert
the thing that actually breaks at 2,000 participants: that a page's query count
stays flat as the roster grows, rather than scaling with it.
"""

import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import AnswerChoice, Participant, Question, Quiz, QuizAttempt, QuizResponse

ROSTER = 2000


@tag("load")
class FullRosterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.quiz = Quiz.objects.create(day=1, title="Systems Online", sequence=1, state=Quiz.State.QUESTION_OPEN)
        cls.question = Question.objects.create(
            quiz=cls.quiz, number=1, text="Which layer settles payments?", time_limit_seconds=20,
            base_points=1000, is_open=True, opened_at=timezone.now(),
            closes_at=timezone.now() + timezone.timedelta(seconds=20),
        )
        cls.choice = AnswerChoice.objects.create(question=cls.question, number=1, text="The switch", is_correct=True)
        for number in range(2, 5):
            AnswerChoice.objects.create(question=cls.question, number=number, text=f"Option {number}")
        cls.quiz.current_question = cls.question
        cls.quiz.save(update_fields=["current_question"])

        Participant.objects.bulk_create([
            Participant(full_name=f"Person {number:04d}", staff_id=f"S{number:04d}",
                        email=f"person{number:04d}@crdbbank.co.tz", department=f"Dept {number % 12}")
            for number in range(ROSTER)
        ])
        people = list(Participant.objects.all())
        QuizAttempt.objects.bulk_create([
            QuizAttempt(participant=person, quiz=cls.quiz, official_score=(index * 37) % 10000,
                        correct_count=index % 11, total_response_ms=5000 + index)
            for index, person in enumerate(people)
        ])
        attempts = list(QuizAttempt.objects.all())
        QuizResponse.objects.bulk_create([
            QuizResponse(attempt=attempt, question=cls.question, selected_choice=cls.choice,
                         submission_id=uuid.uuid4(), is_correct=True, base_points_awarded=1000,
                         response_duration_ms=900)
            for attempt in attempts[:500]
        ])
        cls.participant = people[0]

    def setUp(self):
        cache.clear()
        session = self.client.session
        session["participant_id"] = str(self.participant.id)
        session.save()

    def tearDown(self):
        cache.clear()

    def bounded(self, url, limit, note):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        self.assertLessEqual(len(captured), limit, f"{note}: {len(captured)} queries at {ROSTER} participants")
        return response

    def test_quiz_state_poll_is_a_handful_of_queries_at_full_scale(self):
        self.bounded(reverse("quiz-state", args=[self.quiz.id]), 8, "live poll")

    def test_a_warm_state_cache_removes_the_quiz_read_entirely(self):
        self.client.get(reverse("quiz-state", args=[self.quiz.id]))
        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("quiz-state", args=[self.quiz.id]))
        sql = " ".join(query["sql"] for query in captured)
        self.assertNotIn("core_answerchoice", sql, "choices should come from the shared cache")

    def test_leaderboard_stays_flat(self):
        self.bounded(reverse("leaderboard"), 12, "weekly leaderboard")

    def test_leaderboard_is_served_from_cache_on_the_second_view(self):
        self.client.get(reverse("leaderboard"))
        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("leaderboard"))
        self.assertNotIn("GROUP BY", " ".join(query["sql"] for query in captured).upper())

    def test_leaderboard_publishes_only_the_top_hundred(self):
        rows = self.client.get(reverse("leaderboard")).context["leaders"]
        self.assertEqual(len(rows), 100)
        scores = [row["score"] for row in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_leaderboard_masks_surnames(self):
        row = self.client.get(reverse("leaderboard")).context["leaders"][0]
        self.assertRegex(row["public_name"], r"^Person \d\.$")

    def test_landing_page_stays_flat(self):
        self.client.logout()
        self.bounded(reverse("landing"), 8, "public landing page")

    def test_dashboard_stays_flat(self):
        self.bounded(reverse("dashboard"), 20, "participant dashboard")


@tag("load")
class ControlRoomFullRosterTests(FullRosterTests):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        self.client.login(username="ops", password="control-room-pass")

    def test_quiz_state_poll_is_a_handful_of_queries_at_full_scale(self):
        self.skipTest("participant-facing")

    def test_a_warm_state_cache_removes_the_quiz_read_entirely(self):
        self.skipTest("participant-facing")

    def test_leaderboard_stays_flat(self):
        self.skipTest("participant-facing")

    def test_leaderboard_is_served_from_cache_on_the_second_view(self):
        self.skipTest("participant-facing")

    def test_leaderboard_publishes_only_the_top_hundred(self):
        self.skipTest("participant-facing")

    def test_leaderboard_masks_surnames(self):
        self.skipTest("participant-facing")

    def test_landing_page_stays_flat(self):
        self.skipTest("participant-facing")

    def test_dashboard_stays_flat(self):
        self.skipTest("participant-facing")

    def test_overview_stays_flat(self):
        self.bounded(reverse("control-room"), 15, "control room overview")

    def test_participant_list_stays_flat(self):
        self.bounded(reverse("control-participants"), 15, "participant list")

    def test_participant_search_stays_flat(self):
        self.bounded(reverse("control-participants") + "?q=Person+0500", 15, "participant search")

    def test_host_control_screen_stays_flat(self):
        self.bounded(reverse("quiz-control", args=[self.quiz.id]), 15, "host control screen")

    def test_analytics_stays_flat(self):
        self.bounded(reverse("control-analytics"), 15, "analytics")

    def test_competition_screen_stays_flat(self):
        self.bounded(reverse("control-competition"), 15, "competition standings")
