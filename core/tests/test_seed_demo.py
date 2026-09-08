from django.core.management import call_command
from django.test import TestCase
from core.models import Experience, Participant, Quiz, Session


class DemoSeedTests(TestCase):
    def test_seed_creates_visible_operational_programme_and_is_idempotent(self):
        call_command("seed_demo")
        call_command("seed_demo")
        self.assertEqual(Participant.objects.filter(staff_id="CRDB-DEMO").count(), 1)
        self.assertGreaterEqual(Session.objects.filter(is_active=True).count(), 5)
        self.assertEqual(Quiz.objects.count(), 4)
        self.assertGreaterEqual(Experience.objects.filter(show_on_dashboard=True).count(), 10)
        self.assertTrue(Session.objects.filter(title__icontains="CONNECTED BANK").exists())
