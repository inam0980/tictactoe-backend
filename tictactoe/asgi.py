"""
ASGI config — entry point for both HTTP and WebSocket traffic.

`ProtocolTypeRouter` decides: HTTP requests go to the Django view stack,
WebSocket connections go through JWT auth into our game routing.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tictactoe.settings")

# Initialize Django ASGI app first so AppRegistry is populated before
# we import anything that touches models (like the JWT middleware).
django_asgi_app = get_asgi_application()

from game.routing import websocket_urlpatterns  # noqa: E402
from game.middleware import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
    ),
})
