import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from channels.routing import ProtocolTypeRouter,URLRouter
from django.core.asgi import get_asgi_application
from core.routing import websocket_urlpatterns
application=ProtocolTypeRouter({"http":get_asgi_application(),"websocket":AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))})
