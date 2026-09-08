from datetime import datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from core.models import Activity, Badge, EventSettings, Experience, ExperienceTheme, Participant, Quiz, ScoringRule, Session, SessionRegistration


class Command(BaseCommand):
    help = "Create an idempotent operational preview using titles supplied in the Learning Week brief."

    def handle(self, *args, **opts):
        participant, _ = Participant.objects.update_or_create(
            staff_id="CRDB-DEMO",
            defaults={"full_name": "Grace Mushi", "email": "grace.demo@crdb.local", "department": "Risk & Compliance", "job_role": "Risk Analyst", "is_active": True},
        )
        EventSettings.objects.update_or_create(
            pk=1,
            defaults={"event_name": "CRDB × Predictive Analytics Lab Learning Week Experience", "start_date": "2026-09-07", "end_date": "2026-09-10", "timezone": "Africa/Dar_es_Salaam", "registration_url": settings.OFFICIAL_REGISTRATION_URL, "programme_visible": True, "leaderboard_visible": True},
        )
        for code, category, points, description in [
            ("session_checkin", "attendance", 100, "Verified session attendance"),
            ("pal_completion", "pal", 500, "PAL AI Jobs completion"),
            ("expo_default", "expo", 150, "Expo or AIoT completion"),
        ]:
            ScoringRule.objects.update_or_create(code=code, defaults={"category": category, "points": points, "description": description, "is_active": True})
        for code, name in [
            ("connected-bank", "CONNECTED BANK"), ("data-detective", "DATA DETECTIVE"),
            ("fraud-hunter", "FRAUD HUNTER"), ("future-ready", "FUTURE READY"),
            ("learning-explorer", "LEARNING EXPLORER"), ("ai-champion", "AI CHAMPION"),
        ]:
            Badge.objects.update_or_create(code=code, defaults={"name": name, "is_active": True})
        themes = {
            "infrastructure": ("INFRASTRUCTURE", "#df1f26", "SYSTEMS ONLINE", "Initialize the banking intelligence stack."),
            "data": ("DATA DETECTIVE", "#48b7ff", "DATASET LOADED", "Find the signal. Ignore the noise."),
            "fraud": ("FORENSICS", "#ff633f", "CASE FILE OPEN", "Can you identify the fraud signal?"),
            "finale": ("GRAND FINALE", "#f0b44d", "THE FINAL MODEL", "Top 10 take the grand prizes."),
        }
        theme_objects = {}
        for key, (name, accent, label, copy) in themes.items():
            theme_objects[key], _ = ExperienceTheme.objects.update_or_create(key=key, defaults={"name": name, "accent": accent, "hero_label": label, "intro_copy": copy})

        session_specs = [
            ("connected-bank-aiot", 1, datetime(2026, 9, 7, 14, 0), datetime(2026, 9, 7, 16, 0), "THE CONNECTED BANK — AI + IoT (AIoT) in Banking Operations", "Pascal Aloo"),
            ("hot-hour-day-1", 1, datetime(2026, 9, 7, 12, 30), datetime(2026, 9, 7, 12, 45), "AI Infrastructure Trivia Sprint", "Predictive Analytics Lab"),
            ("hot-hour-day-2", 2, datetime(2026, 9, 8, 12, 30), datetime(2026, 9, 8, 12, 45), "Data Detective Challenge", "Predictive Analytics Lab"),
            ("hot-hour-day-3", 3, datetime(2026, 9, 9, 12, 30), datetime(2026, 9, 9, 12, 45), "Catch the Fraudster", "Predictive Analytics Lab"),
            ("hot-hour-day-4", 4, datetime(2026, 9, 10, 12, 30), datetime(2026, 9, 10, 13, 0), "Predict & Win — Grand Finale", "Predictive Analytics Lab"),
        ]
        for key, day, start, end, title, facilitator in session_specs:
            session, _ = Session.objects.update_or_create(
                source_key=key,
                defaults={"day": day, "title": title, "facilitator": facilitator, "format": Session.Format.HYBRID, "audience": "CRDB Learning Week participants", "location": "CRDB HQ + Online", "starts_at": timezone.make_aware(start), "ends_at": timezone.make_aware(end), "is_active": True},
            )
            SessionRegistration.objects.get_or_create(participant=participant, session=session, defaults={"source": "demo"})
            Experience.objects.update_or_create(
                session=session,
                defaults={"title": title, "slug": key, "type": Experience.Type.SESSION, "description": "Registered Learning Week session.", "day": day, "start_at": session.starts_at, "end_at": session.ends_at, "status": Experience.Status.SCHEDULED, "visibility": "registered", "location": session.location, "requires_registration": True, "requires_checkin": True, "show_on_dashboard": True},
            )

        quiz_specs = [
            (1, "AI Infrastructure Trivia Sprint", "infrastructure"),
            (2, "Data Detective Challenge", "data"),
            (3, "Catch the Fraudster", "fraud"),
            (4, "Predict & Win — Grand Finale", "finale"),
        ]
        for day, title, theme_key in quiz_specs:
            quiz, _ = Quiz.objects.update_or_create(
                sequence=day,
                defaults={"day": day, "title": title, "participant_description": themes[theme_key][3], "event_date": f"2026-09-{6 + day:02d}", "start_time": "12:30", "end_time": "12:45" if day < 4 else "13:00", "state": Quiz.State.SCHEDULED, "prize_eligible": True, "contributes_to_weekly": True, "speed_bonus_enabled": False, "max_attempts": 1, "theme_key": theme_key},
            )
            start = timezone.make_aware(datetime(2026, 9, 6 + day, 12, 30))
            end = timezone.make_aware(datetime(2026, 9, 6 + day, 12, 45 if day < 4 else 0)) if day < 4 else timezone.make_aware(datetime(2026, 9, 10, 13, 0))
            Experience.objects.update_or_create(
                quiz=quiz,
                defaults={"title": title, "slug": f"day-{day}-{slugify(title)}", "type": Experience.Type.QUIZ, "description": themes[theme_key][3], "day": day, "start_at": start, "end_at": end, "status": Experience.Status.SCHEDULED, "points_enabled": True, "show_on_dashboard": True, "featured": True, "theme": theme_objects[theme_key]},
            )

        activity, _ = Activity.objects.update_or_create(code="aiot-expo", defaults={"name": "AIoT Experience Station", "description": "Complete the connected banking demonstration with your Learning Pass.", "day": 1, "points": 150, "is_active": True})
        Experience.objects.update_or_create(activity=activity, defaults={"title": activity.name, "slug": "aiot-experience-station", "type": Experience.Type.EXPO_ACTIVITY, "description": activity.description, "day": 1, "status": Experience.Status.SCHEDULED, "points_enabled": True, "completion_points": 150, "requires_checkin": True, "show_on_dashboard": True})
        Experience.objects.update_or_create(slug="pal-ai-jobs", defaults={"title": "PAL AI Jobs — AI Career Challenge", "type": Experience.Type.PAL_CHALLENGE, "description": "Discover how AI may change your role and identify your future skill priorities.", "day": 1, "status": Experience.Status.SCHEDULED, "points_enabled": True, "completion_points": 500, "show_on_dashboard": True, "featured": True})
        self.stdout.write(self.style.SUCCESS("Operational preview ready: 5 sessions, 4 challenge rounds, PAL and AIoT. Official question content remains spreadsheet-only."))
