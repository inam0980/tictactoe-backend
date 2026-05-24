"""
ASGI config — entry point for both HTTP and WebSocket traffic.

`ProtocolTypeRouter` decides: HTTP requests go to the Django view stack,
WebSocket connections go through JWT auth into our game routing.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tictactoe.settings")

# Initialize Django ASGI app first so AppRegistry is populated before
# we import anything that touches models (like the JWT middleware).
django_asgi_app = get_asgi_application()

from game.routing import websocket_urlpatterns  # noqa: E402
from game.middleware import JWTAuthMiddleware  # noqa: E402

# Origin validation intentionally omitted: the Flutter client is a native
# mobile app and does not send an Origin header on the WS handshake. JWT
# auth in JWTAuthMiddleware (token query param) is the actual access check.
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
