from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import EventSettings, Participant


class CacheIsolatedTestCase(TestCase):
    """Rate-limit counters live in the shared cache; keep them out of each other."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)


class SelfRegistrationTests(CacheIsolatedTestCase):
    def join(self, **overrides):
        payload = {"step": "register", "full_name": "Grace Mushi", "email": "grace.mushi@crdbbank.co.tz", "department": "Retail Banking"}
        payload.update(overrides)
        return self.client.post(reverse("participant-access"), payload)

    def test_a_new_person_joins_with_an_email_and_a_name(self):
        response = self.join()
        self.assertRedirects(response, reverse("learning-pass"))
        person = Participant.objects.get()
        self.assertEqual(person.email, "grace.mushi@crdbbank.co.tz")
        self.assertEqual(person.department, "Retail Banking")
        self.assertEqual(self.client.session["participant_id"], str(person.id))

    def test_joining_issues_a_pass_number_and_qr_token_immediately(self):
        self.join()
        person = Participant.objects.get()
        self.assertTrue(person.pass_number.startswith("CRDB-LW-"))
        self.assertTrue(person.qr_token)
        self.assertIsNotNone(person.registration_timestamp)
        self.assertContains(self.client.get(reverse("learning-pass")), person.pass_number)

    def test_email_is_normalised_so_case_does_not_create_a_second_person(self):
        self.join(email="  Grace.Mushi@CRDBbank.co.TZ  ")
        self.assertEqual(Participant.objects.get().email, "grace.mushi@crdbbank.co.tz")
        self.client.post(reverse("participant-access"), {"identity": "GRACE.MUSHI@crdbbank.co.tz"})
        self.assertEqual(Participant.objects.count(), 1)

    def test_registering_an_existing_email_is_refused_rather_than_duplicated(self):
        Participant.objects.create(full_name="Grace Mushi", email="grace.mushi@crdbbank.co.tz")
        response = self.join()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already registered", status_code=400)
        self.assertEqual(Participant.objects.count(), 1)

    def test_registering_an_existing_staff_id_is_refused(self):
        Participant.objects.create(full_name="Someone Else", staff_id="CRDB0142")
        response = self.join(staff_id="crdb0142")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Participant.objects.count(), 1)

    def test_a_name_is_required(self):
        response = self.join(full_name="")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Participant.objects.exists())

    def test_a_malformed_email_is_refused(self):
        response = self.join(email="not-an-email")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Participant.objects.exists())

    def test_a_preloaded_person_signs_in_rather_than_registering_again(self):
        person = Participant.objects.create(full_name="Grace Mushi", staff_id="CRDB0142", email="grace.mushi@crdbbank.co.tz")
        response = self.client.post(reverse("participant-access"), {"identity": "grace.mushi@crdbbank.co.tz"})
        self.assertRedirects(response, reverse("learning-pass"))
        self.assertEqual(self.client.session["participant_id"], str(person.id))
        self.assertEqual(Participant.objects.count(), 1)

    def test_a_staff_id_lookup_still_works(self):
        person = Participant.objects.create(full_name="Grace Mushi", staff_id="CRDB0142")
        self.client.post(reverse("participant-access"), {"identity": "crdb0142"})
        self.assertEqual(self.client.session["participant_id"], str(person.id))

    def test_a_deactivated_person_cannot_re_register_around_the_block(self):
        Participant.objects.create(full_name="Grace Mushi", email="grace.mushi@crdbbank.co.tz", is_active=False)
        response = self.join()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Participant.objects.count(), 1)


class DomainRestrictionTests(CacheIsolatedTestCase):
    def setUp(self):
        super().setUp()
        EventSettings.objects.create(allowed_email_domains="crdbbank.co.tz, predictiveanalyticslab.ai")

    def join(self, email):
        return self.client.post(reverse("participant-access"), {"step": "register", "full_name": "Grace Mushi", "email": email, "department": "Retail"})

    def test_an_allowed_domain_joins(self):
        self.assertRedirects(self.join("grace@crdbbank.co.tz"), reverse("learning-pass"))

    def test_a_second_allowed_domain_joins(self):
        self.assertRedirects(self.join("pal@predictiveanalyticslab.ai"), reverse("learning-pass"))

    def test_an_outside_domain_is_refused(self):
        response = self.join("someone@gmail.com")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "open to", status_code=400)
        self.assertFalse(Participant.objects.exists())

    def test_a_lookalike_domain_is_refused(self):
        self.assertEqual(self.join("attacker@notcrdbbank.co.tz").status_code, 400)
        self.assertFalse(Participant.objects.exists())

    def test_blank_setting_accepts_any_address(self):
        EventSettings.objects.update(allowed_email_domains="")
        self.assertRedirects(self.join("guest@example.com"), reverse("learning-pass"))


class RegistrationDisabledTests(CacheIsolatedTestCase):
    def setUp(self):
        super().setUp()
        EventSettings.objects.create(self_registration_enabled=False)

    def test_the_join_form_is_refused_outright(self):
        response = self.client.post(reverse("participant-access"), {"step": "register", "full_name": "Grace", "email": "grace@crdbbank.co.tz"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Participant.objects.exists())

    def test_the_access_page_does_not_advertise_joining(self):
        self.assertNotContains(self.client.get(reverse("participant-access")), "FIRST TIME?")


class OptionalDepartmentTests(CacheIsolatedTestCase):
    def test_department_can_be_dropped_from_the_form(self):
        EventSettings.objects.create(self_registration_collects_department=False)
        response = self.client.get(reverse("participant-access"))
        self.assertNotContains(response, "DEPARTMENT")
        self.client.post(reverse("participant-access"), {"step": "register", "full_name": "Grace Mushi", "email": "grace@crdbbank.co.tz"})
        self.assertEqual(Participant.objects.get().department, "")

    def test_department_is_optional_even_when_asked_for(self):
        self.client.post(reverse("participant-access"), {"step": "register", "full_name": "Grace Mushi", "email": "grace@crdbbank.co.tz"})
        self.assertEqual(Participant.objects.get().department, "")


class SharedGatewayTests(CacheIsolatedTestCase):
    """A venue full of people shares one public IP; limits must not be per-venue."""

    def test_many_people_behind_one_address_can_all_sign_in(self):
        from django.test import Client
        for number in range(40):
            Participant.objects.create(full_name=f"Person {number:03d}", email=f"person{number:03d}@crdbbank.co.tz")
        signed_in = 0
        for number in range(40):
            person_client = Client(REMOTE_ADDR="41.86.0.1")  # one office gateway
            person_client.get(reverse("participant-access"))
            response = person_client.post(
                reverse("participant-access"),
                {"identity": f"person{number:03d}@crdbbank.co.tz"},
                REMOTE_ADDR="41.86.0.1",
            )
            signed_in += response.status_code == 302
        self.assertEqual(signed_in, 40, "the venue gateway must not share one rate-limit bucket")

    def test_one_person_hammering_the_form_is_still_throttled(self):
        from django.test import Client
        attacker = Client(REMOTE_ADDR="41.86.0.9")
        attacker.get(reverse("participant-access"))
        codes = [
            attacker.post(reverse("participant-access"), {"identity": f"guess{n}@crdbbank.co.tz"}, REMOTE_ADDR="41.86.0.9").status_code
            for n in range(30)
        ]
        self.assertIn(429, codes, "a single session must still hit its own limit")

    def test_answer_submissions_are_limited_per_player_not_per_venue(self):
        from core.views import participant_rate_key
        from django.test import RequestFactory
        first, second = RequestFactory().get("/"), RequestFactory().get("/")
        first.session, second.session = {"participant_id": "aaa"}, {"participant_id": "bbb"}
        first.META["REMOTE_ADDR"] = second.META["REMOTE_ADDR"] = "41.86.0.1"
        self.assertNotEqual(participant_rate_key("g", first), participant_rate_key("g", second))
