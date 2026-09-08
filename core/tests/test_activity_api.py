import json
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Activity,ActivityCompletion,Participant,ScoreTransaction

@override_settings(ACTIVITY_API_KEY="device-secret")
class ActivityApiTests(TestCase):
 def test_device_completion_is_idempotent_and_awards_configured_points(self):
  participant=Participant.objects.create(full_name="Grace",staff_id="G1")
  activity=Activity.objects.create(code="aiot-station",name="AIoT Station",points=150)
  body=json.dumps({"qr_token":participant.qr_token,"activity_code":activity.code,"external_id":"device-event-1"})
  first=self.client.post(reverse("activity-complete"),body,content_type="application/json",HTTP_X_ACTIVITY_KEY="device-secret")
  second=self.client.post(reverse("activity-complete"),body,content_type="application/json",HTTP_X_ACTIVITY_KEY="device-secret")
  self.assertEqual(first.status_code,201); self.assertEqual(second.status_code,200)
  self.assertEqual(ActivityCompletion.objects.count(),1)
  self.assertEqual(ScoreTransaction.objects.get().points,150)
 def test_device_requires_api_key(self):
  response=self.client.post(reverse("activity-complete"),"{}",content_type="application/json")
  self.assertEqual(response.status_code,401)
