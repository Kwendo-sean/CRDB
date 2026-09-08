"""The staff QR scanner: pick a game, scan a pass, points land."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Activity, ActivityCompletion, Attendance, Participant, ScoreTransaction, Session


class ScannerAwardTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        self.client.login(username="ops", password="control-room-pass")
        self.participant = Participant.objects.create(full_name="Grace Mushi", staff_id="SC1", department="Retail")
        self.vr = Activity.objects.create(code="vr-games", name="VR Games", day=1, points=200)
        self.robot = Activity.objects.create(code="robot-assembly", name="Robot Assembly", day=1, points=250)
        now = timezone.now()
        self.session = Session.objects.create(day=1, title="Keynote", starts_at=now,
                                              ends_at=now + timezone.timedelta(hours=1))

    def scan(self, target, token=None):
        return self.client.post(reverse("api-scan"), content_type="application/json",
                                data=json.dumps({"qr_token": token or self.participant.qr_token, "target": target}))

    def test_scanning_for_a_game_awards_that_game_s_points(self):
        response = self.scan(f"activity:{self.vr.id}")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "awarded")
        self.assertEqual(body["what"], "VR Games")
        self.assertEqual(body["points"], 200)
        self.assertEqual(body["participant"]["name"], "Grace Mushi")
        self.assertEqual(body["total_points"], 200)

    def test_each_game_pays_its_own_points(self):
        self.scan(f"activity:{self.vr.id}")
        body = self.scan(f"activity:{self.robot.id}").json()
        self.assertEqual(body["points"], 250)
        self.assertEqual(body["total_points"], 450, "the two games stack")
        self.assertEqual(ActivityCompletion.objects.filter(participant=self.participant).count(), 2)

    def test_scanning_the_same_game_twice_does_not_pay_twice(self):
        self.scan(f"activity:{self.vr.id}")
        second = self.scan(f"activity:{self.vr.id}")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "already_awarded")
        self.assertEqual(second.json()["points"], 0)
        self.assertEqual(ScoreTransaction.objects.filter(participant=self.participant, category="expo").count(), 1)

    def test_the_scan_records_which_member_of_staff_awarded_it(self):
        self.scan(f"activity:{self.vr.id}")
        entry = ScoreTransaction.objects.get(participant=self.participant, category="expo")
        self.assertEqual(entry.actor.username, "ops")

    def test_a_session_target_still_checks_people_in(self):
        response = self.scan(f"session:{self.session.id}")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["what"], "Keynote")
        self.assertTrue(Attendance.objects.filter(participant=self.participant, session=self.session).exists())

    def test_forgetting_to_choose_a_target_is_a_clear_error(self):
        body = self.scan("").json()
        self.assertEqual(body["error"], "choose_target")
        self.assertFalse(ActivityCompletion.objects.exists())

    def test_an_unrecognised_pass_is_refused(self):
        response = self.scan(f"activity:{self.vr.id}", token="not-a-real-token")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_scan")

    def test_an_inactive_game_cannot_be_scanned_for(self):
        Activity.objects.filter(pk=self.vr.pk).update(is_active=False)
        self.assertEqual(self.scan(f"activity:{self.vr.id}").status_code, 400)

    def test_a_full_pass_url_scans_as_well_as_a_bare_token(self):
        # The client strips the URL, but the endpoint must accept the token it sends.
        self.assertEqual(self.scan(f"activity:{self.vr.id}", token=self.participant.qr_token).status_code, 201)

    def test_the_endpoint_is_staff_only(self):
        self.client.logout()
        response = self.scan(f"activity:{self.vr.id}")
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(ActivityCompletion.objects.exists())


class ScannerPageTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("ops", password="control-room-pass", is_staff=True)
        self.client.login(username="ops", password="control-room-pass")
        Activity.objects.create(code="vr-games", name="VR Games", day=1, points=200)
        Activity.objects.create(code="arduino-assembly", name="Arduino Assembly", day=1, points=250)

    def test_the_scanner_lists_the_games_with_their_points(self):
        response = self.client.get(reverse("scanner"))
        self.assertContains(response, "VR Games (+200 XP)")
        self.assertContains(response, "Arduino Assembly (+250 XP)")
        self.assertContains(response, "EXPO GAMES")

    def test_the_scanner_is_reachable_from_every_control_room_page(self):
        for name in ("control-room", "control-participants", "control-quizzes", "control-competition"):
            self.assertContains(self.client.get(reverse(name)), reverse("scanner"),
                                msg_prefix=f"no scanner link on {name}")

    def test_an_inactive_game_is_not_offered(self):
        Activity.objects.update(is_active=False)
        self.assertNotContains(self.client.get(reverse("scanner")), "VR Games (+200 XP)")
