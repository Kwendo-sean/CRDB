"""Deployment guards.

These run on every ``manage.py check`` and every container start, so a
misconfiguration that would only show itself under event-day load is caught
before participants arrive rather than during a live round.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register


@register(deploy=False)
def event_day_configuration(app_configs, **kwargs):
    problems = []
    if not settings.IS_PRODUCTION:
        return problems

    if not settings.REDIS_URL:
        problems.append(Error(
            "REDIS_URL is not set, so Channels falls back to an in-process layer.",
            hint="With more than one Gunicorn worker, a live quiz state broadcast would reach only the "
                 "players attached to the worker that sent it, and the shared cache and leaderboard would "
                 "diverge per worker. Set REDIS_URL in .env.",
            id="core.E001",
        ))

    if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"):
        problems.append(Error(
            "The production database is SQLite.",
            hint="SQLite serialises writes and will stall when 2,000 participants submit answers at once. "
                 "Set DATABASE_URL to the PostgreSQL service.",
            id="core.E002",
        ))

    if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "testserver"]:
        problems.append(Error(
            "DJANGO_ALLOWED_HOSTS still holds only local defaults.",
            hint="Set it to the public event domain, or every request will be rejected.",
            id="core.E003",
        ))

    if settings.SECURE_SSL_REDIRECT and not settings.CSRF_TRUSTED_ORIGINS:
        problems.append(Error(
            "HTTPS redirection is on but CSRF_TRUSTED_ORIGINS is empty.",
            hint="Set CSRF_TRUSTED_ORIGINS to https://your-domain, or every Control Room form post "
                 "and every answer submission will be rejected as a CSRF failure.",
            id="core.E004",
        ))

    if not settings.ACTIVITY_API_KEY:
        problems.append(Warning(
            "ACTIVITY_API_KEY is empty, so the expo/AIoT completion endpoint is closed.",
            hint="Set it if stand devices need to mark activities complete.",
            id="core.W001",
        ))

    if settings.PAL_CALLBACK_SECRET == "dev-pal-secret":
        problems.append(Warning(
            "PAL_CALLBACK_SECRET is still the development placeholder.",
            hint="Set a real shared secret before enabling the PAL AI Jobs integration.",
            id="core.W002",
        ))

    if settings.OFFICIAL_REGISTRATION_URL.startswith("#"):
        problems.append(Warning(
            "OFFICIAL_REGISTRATION_URL is unset, so the 'register now' link on the access page goes nowhere.",
            id="core.W003",
        ))

    return problems
