from django.conf import settings
from .models import EventSettings


def event_settings(request):
    return {
        "OFFICIAL_REGISTRATION_URL": settings.OFFICIAL_REGISTRATION_URL,
        "EVENT": EventSettings.load(),
    }
