from django.urls import path

from .consumers import GameConsumer, MatchmakingConsumer

# ws://host/ws/matchmaking/         -> queue up for a random opponent
# ws://host/ws/game/<game_id>/      -> in-game move sync + chat
websocket_urlpatterns = [
    path("ws/matchmaking/", MatchmakingConsumer.as_asgi()),
    path("ws/game/<uuid:game_id>/", GameConsumer.as_asgi()),
]
