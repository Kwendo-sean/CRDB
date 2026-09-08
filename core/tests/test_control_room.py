from datetime import date, time
from io import BytesIO
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook
from core.models import Activity, AnswerChoice, Experience, Participant, Quiz, QuizAttempt, Session


class ControlRoomWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "event-admin", password="event-pass", is_staff=True
        )
        self.client.login(username="event-admin", password="event-pass")

    def test_control_room_navigation_reaches_every_operational_area(self):
        """Assert destinations, not headings, so the sidebar can be reorganised."""
        response = self.client.get(reverse("control-room"))
        for name in ("control-quizzes", "control-activities", "control-participants",
                     "control-competition", "control-analytics", "control-experiences",
                     "control-experience-create", "control-sessions", "control-rewards",
                     "control-settings", "control-integrations", "control-audit",
                     "scanner", "projector-weekly", "control-logout"):
            self.assertContains(response, f'href="{reverse(name)}"', msg_prefix=f"{name} missing from Control Room")
        self.assertContains(response, "+ CREATE EXPERIENCE")

    def test_control_room_never_links_to_django_admin(self):
        self.assertNotContains(self.client.get(reverse("control-room")), "/admin/")

    def test_admin_creates_session_entirely_in_control_room(self):
        response = self.client.post(
            reverse("control-session-create"),
            {
                "title": "AI Sustainability and Financial Ethics",
                "day": 2,
                "date": "2026-09-08",
                "start_time": "14:00",
                "end_time": "15:30",
                "facilitator": "CRDB Learning Team",
                "format": "hybrid",
                "audience": "All staff",
                "location": "CRDB HQ",
                "capacity": 300,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        session = Session.objects.get(title="AI Sustainability and Financial Ethics")
        self.assertEqual(session.day, 2)
        from django.utils import timezone
        self.assertEqual(timezone.localtime(session.starts_at).hour, 14)

    def test_admin_creates_quiz_question_previews_and_publishes(self):
        response = self.client.post(
            reverse("control-quiz-create"),
            {
                "title": "Data Detective Challenge",
                "internal_description": "Day two challenge",
                "participant_description": "Find the signal. Ignore the noise.",
                "day": 2,
                "event_date": "2026-09-08",
                "start_time": "12:30",
                "end_time": "12:45",
                "prize_eligible": "on",
                "contributes_to_weekly": "on",
                "max_attempts": 1,
                "theme_key": "data",
            },
        )
        self.assertEqual(response.status_code, 302)
        quiz = Quiz.objects.get(title="Data Detective Challenge")
        self.assertTrue(Experience.objects.filter(quiz=quiz, type="quiz").exists())

        response = self.client.post(
            reverse("control-question-create", args=[quiz.id]),
            {
                "text": "Which field contains the strongest anomaly?",
                "time_limit_seconds": 20,
                "base_points": 1000,
                "answer_1": "Field A",
                "answer_2": "Field B",
                "answer_3": "Field C",
                "answer_4": "Field D",
                "correct_answer": 2,
                "host_note": "Field B deviates from the baseline.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(quiz.questions.get().choices.count(), 4)
        self.assertTrue(quiz.questions.get().choices.get(number=2).is_correct)

        preview = self.client.get(reverse("control-quiz-preview", args=[quiz.id]))
        self.assertContains(preview, "Which field contains the strongest anomaly?")
        self.assertEqual(QuizAttempt.objects.count(), 0)

        blocked = self.client.post(
            reverse("control-quiz-publish", args=[quiz.id]), follow=True
        )
        self.assertContains(blocked, "exactly 10 questions")
        quiz.refresh_from_db()
        self.assertEqual(quiz.state, Quiz.State.DRAFT)

    def test_admin_creates_expo_activity_from_experience_flow(self):
        response = self.client.post(
            reverse("control-activity-create"),
            {
                "name": "AIoT Experience Station",
                "code": "aiot-experience-station",
                "description": "Complete the connected-device demonstration.",
                "day": 1,
                "points": 150,
                "show_on_dashboard": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(code="aiot-experience-station")
        self.assertTrue(Experience.objects.filter(activity=activity, type="expo_activity").exists())

    def test_admin_creates_aiot_demo_as_its_own_experience_type(self):
        response = self.client.post(
            reverse("control-activity-create-type", args=["aiot_demo"]),
            {
                "name": "Connected Device Lab",
                "code": "connected-device-lab",
                "description": "Complete the live AIoT demonstration.",
                "day": 1,
                "points": 150,
                "show_on_dashboard": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Experience.objects.get(slug="connected-device-lab").type, Experience.Type.AIOT_DEMO)

    def quiz_workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "day", "challenge_name", "question_number", "question_text",
            "answer_1", "answer_2", "answer_3", "answer_4",
            "correct_answer_number", "time_limit", "points", "host_note",
        ])
        for number in range(1, 11):
            sheet.append([2, "Imported Source Title", number, f"Question {number}", "A", "B", "C", "D", 1, 20, 1000, "Host note"])
        stream = BytesIO()
        workbook.save(stream)
        return SimpleUploadedFile("questions.xlsx", stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_question_import_previews_before_replacing_only_the_selected_quiz(self):
        selected = Quiz.objects.create(day=2, title="Selected Quiz", sequence=1)
        untouched = Quiz.objects.create(day=3, title="Untouched Quiz", sequence=2)

        preview = self.client.post(
            reverse("control-quiz-import", args=[selected.id]),
            {"action": "preview", "workbook": self.quiz_workbook()},
        )
        self.assertContains(preview, "Questions detected: 10")
        self.assertContains(preview, "Valid: 10")
        self.assertEqual(selected.questions.count(), 0)
        self.assertTrue(Quiz.objects.filter(pk=untouched.pk).exists())

        imported = self.client.post(
            reverse("control-quiz-import", args=[selected.id]),
            {"action": "import", "workbook": self.quiz_workbook()},
            follow=True,
        )
        self.assertContains(imported, "IMPORT COMPLETE / 10 QUESTIONS")
        self.assertEqual(selected.questions.count(), 10)
        self.assertTrue(Quiz.objects.filter(pk=untouched.pk).exists())


class ParticipantJourneyTests(TestCase):
    def test_dashboard_shows_quizzes_games_and_a_points_total(self):
        participant = Participant.objects.create(full_name="Grace Mushi", staff_id="GRACE-1")
        quiz = Quiz.objects.create(day=1, title="AI Infrastructure Sprint", sequence=1, state=Quiz.State.LOBBY)
        Experience.objects.create(title=quiz.title, slug="ai-infrastructure-sprint", type="quiz", day=1,
                                  status="scheduled", show_on_dashboard=True, quiz=quiz)
        activity = Activity.objects.create(code="aiot-stand", name="AIoT Smart Branch", day=2, points=150)
        Experience.objects.create(title=activity.name, slug="aiot-smart-branch", type="expo_activity", day=2,
                                  status="scheduled", show_on_dashboard=True, completion_points=150, activity=activity)
        browser_session = self.client.session
        browser_session["participant_id"] = str(participant.id)
        browser_session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "AI Infrastructure Sprint")
        self.assertContains(response, "AIoT Smart Branch")
        self.assertContains(response, "MY TOTAL POINTS")
        self.assertEqual(response.context["points"]["total"], 0)

    def test_dashboard_no_longer_lists_programme_sessions(self):
        participant = Participant.objects.create(full_name="Grace Mushi", staff_id="GRACE-2")
        session = Session.objects.create(day=2, title="AI Sustainability and Financial Ethics",
                                         starts_at="2026-09-08T14:00:00+03:00", ends_at="2026-09-08T15:30:00+03:00")
        Experience.objects.create(title=session.title, slug="ai-sustainability", type="session", day=2,
                                  status="scheduled", show_on_dashboard=True, session=session)
        browser_session = self.client.session
        browser_session["participant_id"] = str(participant.id)
        browser_session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "AI Sustainability and Financial Ethics")
