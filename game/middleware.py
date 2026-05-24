"""
JWT middleware for Channels (WebSocket) connections.

Browsers can't easily send Authorization headers on a WS handshake, so we
accept the token as a query-string param: ws://.../ws/game/?token=...
This middleware pulls it out and resolves it to a User before the
consumer's `connect()` runs.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

User = get_user_model()


@database_sync_to_async
def _user_for_token(raw_token: str):
    try:
        token = UntypedToken(raw_token)
    except (InvalidToken, TokenError):
        return AnonymousUser()
    try:
        user_id = token["user_id"]
        return User.objects.get(id=user_id)
    except (KeyError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope["query_string"].decode())
        raw_token = (query.get("token") or [None])[0]
        scope["user"] = (
            await _user_for_token(raw_token) if raw_token else AnonymousUser()
        )
        return await super().__call__(scope, receive, send)
