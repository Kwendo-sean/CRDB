import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

# Initialise Django before importing anything that reaches a model. The quiz
# consumer imports core.models, and under a real ASGI server nothing has called
# django.setup() yet, so importing it any earlier raises AppRegistryNotReady and
# every worker fails to boot. runserver and the test runner set Django up before
# loading this module, which is why the fault appears only under gunicorn.
django_asgi_application = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from core.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
