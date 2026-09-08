import hashlib, hmac, json, time
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Activity, ActivityCompletion, EventSettings, Participant, Session, SessionRegistration, PALIntegrationResult, ScoreTransaction

class ParticipantWebFlowTests(TestCase):
    def setUp(self): self.p=Participant.objects.create(full_name="Grace Mushi",staff_id="CRDB-0842",email="grace@crdb.tz",department="Risk & Compliance")
    def test_lookup_creates_participant_session_and_opens_pass(self):
        response=self.client.post(reverse("participant-access"),{"identity":" grace@CRDB.TZ "})
        self.assertRedirects(response,reverse("learning-pass"))
        self.assertEqual(str(self.p.id),self.client.session["participant_id"])
        page=self.client.get(reverse("learning-pass"))
        self.assertContains(page,"GRACE MUSHI"); self.assertContains(page,"CRDB LEARNING PASS")
        qr=self.client.get(reverse("learning-pass-qr")); self.assertEqual(qr["Content-Type"],"image/svg+xml")
    def test_unknown_lookup_offers_self_registration(self):
        response=self.client.post(reverse("participant-access"),{"identity":"missing@crdb.tz"})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"JOIN LEARNING WEEK")
        self.assertContains(response,"missing@crdb.tz")
    def test_unknown_lookup_falls_back_to_the_official_form_when_self_registration_is_off(self):
        EventSettings.objects.create(self_registration_enabled=False)
        response=self.client.post(reverse("participant-access"),{"identity":"missing@crdb.tz"})
        self.assertEqual(response.status_code,404); self.assertContains(response,"NOT REGISTERED",status_code=404)
    def test_the_participant_programme_page_is_gone(self):
        session=self.client.session; session["participant_id"]=str(self.p.id); session.save()
        self.assertEqual(self.client.get("/programme/").status_code,404)
    def test_the_quizzes_url_now_leads_to_the_single_hub(self):
        session=self.client.session; session["participant_id"]=str(self.p.id); session.save()
        self.assertRedirects(self.client.get(reverse("quizzes")),reverse("dashboard"))

class StaffApiTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_user("scanner",password="safe-test-pass",is_staff=True)
        self.p=Participant.objects.create(full_name="Grace",staff_id="G1")
        self.s=Session.objects.create(day=1,title="Exact",starts_at=timezone.now(),ends_at=timezone.now()+timezone.timedelta(hours=1))
        self.client.login(username="scanner",password="safe-test-pass")
    def test_scan_is_idempotent(self):
        url=reverse("api-check-in")
        first=self.client.post(url,data=json.dumps({"qr_token":self.p.qr_token,"session_id":self.s.id}),content_type="application/json")
        second=self.client.post(url,data=json.dumps({"qr_token":self.p.qr_token,"session_id":self.s.id}),content_type="application/json")
        self.assertEqual(first.status_code,201); self.assertEqual(second.status_code,200)
        self.assertEqual(second.json()["status"],"already_checked_in")

@override_settings(PAL_CALLBACK_SECRET="test-callback-secret")
class PALTests(TestCase):
    def setUp(self): self.p=Participant.objects.create(full_name="Amina",staff_id="A1")
    def test_launch_contains_no_email_or_staff_id(self):
        session=self.client.session; session["participant_id"]=str(self.p.id); session.save()
        response=self.client.get(reverse("pal-launch"))
        self.assertEqual(response.status_code,302)
        from urllib.parse import parse_qs, urlparse
        from django.core import signing
        token=parse_qs(urlparse(response.url).query)["token"][0]
        payload=signing.loads(token,salt="pal-launch",max_age=300)
        self.assertNotIn("email",payload); self.assertNotIn("staff_id",payload)
        self.assertEqual(payload["sub"],str(self.p.id))
    def test_signed_callback_is_idempotent_and_awards_xp_once(self):
        result=PALIntegrationResult.objects.create(participant=self.p)
        payload={"external_result_id":"pal-1","subject":str(self.p.id),"nonce":str(result.launch_nonce),"status":"complete","career_role":"Risk Analyst","career_hp":82,"skill_gaps":["model governance"]}
        body=json.dumps(payload,separators=(",",":"),sort_keys=True).encode()
        sig=hmac.new(settings.PAL_CALLBACK_SECRET.encode(),body,hashlib.sha256).hexdigest()
        first=self.client.post(reverse("pal-callback"),data=body,content_type="application/json",HTTP_X_PAL_SIGNATURE=sig)
        second=self.client.post(reverse("pal-callback"),data=body,content_type="application/json",HTTP_X_PAL_SIGNATURE=sig)
        self.assertEqual(first.status_code,200); self.assertEqual(second.status_code,200)
        self.assertEqual(ScoreTransaction.objects.filter(participant=self.p,category="pal").count(),1)

class HealthTests(TestCase):
    @override_settings(REDIS_URL="redis://redis:6379/0")
    @patch("redis.Redis.from_url")
    def test_health_checks_database_and_redis(self, redis_from_url):
        redis_from_url.return_value.ping.return_value = True
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "django": "ready", "database": "ready", "redis": "ready"})
