import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
BASE_DIR=Path(__file__).resolve().parent.parent
DEBUG=os.getenv("DJANGO_DEBUG", "1")=="1"
# The test runner forces DEBUG=False, so deployment guards key off the operator's
# declared intent captured here at import time rather than off DEBUG itself.
IS_PRODUCTION=not DEBUG
INSECURE_SECRET="dev-only-change-me"
SECRET_KEY=os.getenv("DJANGO_SECRET_KEY") or INSECURE_SECRET
if not DEBUG and SECRET_KEY==INSECURE_SECRET:
 raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG=0.")
ALLOWED_HOSTS=[x for x in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if x]
CSRF_TRUSTED_ORIGINS=[x for x in os.getenv("CSRF_TRUSTED_ORIGINS","").split(",") if x]
INSTALLED_APPS=["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","rest_framework","channels","core"]
MIDDLEWARE=["django.middleware.security.SecurityMiddleware","whitenoise.middleware.WhiteNoiseMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF="config.urls"
TEMPLATES=[{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR/"templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages","core.context_processors.event_settings"]}}]
WSGI_APPLICATION="config.wsgi.application"
ASGI_APPLICATION="config.asgi.application"
CONN_MAX_AGE=int(os.getenv("DJANGO_CONN_MAX_AGE","60"))
try:
 import dj_database_url
 DATABASES={"default":dj_database_url.config(default=f"sqlite:///{BASE_DIR/'db.sqlite3'}",conn_max_age=CONN_MAX_AGE,conn_health_checks=True)}
except ImportError:
 DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
REDIS_URL=os.getenv("REDIS_URL","")
CHANNEL_LAYERS={"default":{"BACKEND":"channels.layers.InMemoryChannelLayer"}}
CACHES={"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache","LOCATION":"crdb-learning-week"}}
if REDIS_URL:
 CHANNEL_LAYERS={"default":{"BACKEND":"channels_redis.core.RedisChannelLayer","CONFIG":{"hosts":[REDIS_URL],"capacity":2000,"expiry":30}}}
 CACHES={"default":{"BACKEND":"django.core.cache.backends.redis.RedisCache","LOCATION":REDIS_URL,"KEY_PREFIX":"lw","TIMEOUT":300}}
# Sessions read from cache and write through to the database, so 2,000 concurrent
# Learning Pass holders do not turn every page view into a django_session read.
SESSION_ENGINE="django.contrib.sessions.backends.cached_db"
SESSION_CACHE_ALIAS="default"
SESSION_COOKIE_AGE=int(os.getenv("SESSION_COOKIE_AGE",str(60*60*14)))
AUTH_PASSWORD_VALIDATORS=[
 {"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
 {"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator","OPTIONS":{"min_length":12}},
 {"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},
 {"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE="en-us"
TIME_ZONE=os.getenv("TIME_ZONE","Africa/Dar_es_Salaam")
USE_I18N=True
USE_TZ=True
STATIC_URL="static/"
STATIC_ROOT=BASE_DIR/"staticfiles"
STATICFILES_DIRS=[BASE_DIR/"static"]
STORAGES={"staticfiles":{"BACKEND":"django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
# Spreadsheet imports carry a few thousand rows; the default 2.5 MB form ceiling rejects them.
DATA_UPLOAD_MAX_MEMORY_SIZE=int(os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE",str(16*1024*1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE=DATA_UPLOAD_MAX_MEMORY_SIZE
DATA_UPLOAD_MAX_NUMBER_FIELDS=5000
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE="Lax"
CSRF_COOKIE_SAMESITE="Lax"
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_SSL_REDIRECT=os.getenv("DJANGO_SECURE_SSL_REDIRECT","1" if not DEBUG else "0")=="1"
SECURE_HSTS_SECONDS=int(os.getenv("DJANGO_SECURE_HSTS_SECONDS","31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
# Deliberate: this event domain does not assert HTTPS control over every subdomain
# and is not being submitted to the irreversible browser HSTS preload list.
SILENCED_SYSTEM_CHECKS=["security.W005","security.W021"] if not DEBUG else []
SECURE_REFERRER_POLICY="strict-origin-when-cross-origin"
X_FRAME_OPTIONS="DENY"
OFFICIAL_REGISTRATION_URL=os.getenv("OFFICIAL_REGISTRATION_URL", "#registration-link-required")
PAL_LAUNCH_URL=os.getenv("PAL_LAUNCH_URL", "https://aijobs.predictiveanalyticslab.ai/learning-week")
PAL_CALLBACK_SECRET=os.getenv("PAL_CALLBACK_SECRET", "dev-pal-secret")
PAL_ISSUER=os.getenv("PAL_ISSUER", "crdb-learning-week")
PAL_AUDIENCE=os.getenv("PAL_AUDIENCE", "pal-ai-jobs")
ACTIVITY_API_KEY=os.getenv("ACTIVITY_API_KEY", "")
APP_BASE_URL=os.getenv("APP_BASE_URL","http://localhost:8000").rstrip("/")
EMAIL_HOST=os.getenv("EMAIL_HOST","")
EMAIL_PORT=int(os.getenv("EMAIL_PORT","587"))
EMAIL_USE_TLS=os.getenv("EMAIL_USE_TLS","1")=="1"
EMAIL_HOST_USER=os.getenv("EMAIL_USERNAME","")
EMAIL_HOST_PASSWORD=os.getenv("EMAIL_PASSWORD","")
DEFAULT_FROM_EMAIL=os.getenv("DEFAULT_FROM_EMAIL","learningweek@localhost")
CELERY_BROKER_URL=REDIS_URL or "redis://localhost:6379/0"
CELERY_RESULT_BACKEND=REDIS_URL or "redis://localhost:6379/0"
CELERY_TASK_ALWAYS_EAGER=os.getenv("CELERY_TASK_ALWAYS_EAGER","0")=="1"
LOGIN_URL="control-login"
LOGIN_REDIRECT_URL="control-room"
# Rate limits are read at request time so a busy event can be retuned without a code change.
RATELIMIT_ACCESS=os.getenv("RATELIMIT_ACCESS","12/m")
RATELIMIT_ANSWER=os.getenv("RATELIMIT_ANSWER","60/m")
RATELIMIT_STATE=os.getenv("RATELIMIT_STATE","120/m")
RATELIMIT_LOGIN=os.getenv("RATELIMIT_LOGIN","20/m")
RATELIMIT_ENABLE=os.getenv("RATELIMIT_ENABLE","1")=="1"
LEADERBOARD_CACHE_SECONDS=int(os.getenv("LEADERBOARD_CACHE_SECONDS","15"))
# Room-facing boards mask surnames like the participant leaderboard. Set to 1 to
# show full names, e.g. when announcing prize winners from the stage.
PROJECTOR_SHOW_FULL_NAMES=os.getenv("PROJECTOR_SHOW_FULL_NAMES","0")=="1"
LOGGING={
 "version":1,
 "disable_existing_loggers":False,
 "formatters":{"standard":{"format":"%(asctime)s %(levelname)s %(name)s %(message)s"}},
 "handlers":{"console":{"class":"logging.StreamHandler","formatter":"standard"}},
 "root":{"handlers":["console"],"level":os.getenv("DJANGO_LOG_LEVEL","INFO")},
 "loggers":{
  "django.request":{"handlers":["console"],"level":"ERROR","propagate":False},
  "django.security":{"handlers":["console"],"level":"WARNING","propagate":False},
  "core":{"handlers":["console"],"level":os.getenv("DJANGO_LOG_LEVEL","INFO"),"propagate":False},
 },
}
