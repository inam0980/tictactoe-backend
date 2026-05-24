from django.urls import path

from .views import (
    CreateRoomView,
    GameDetailView,
    GameHistoryView,
    JoinRoomView,
    LeaderboardView,
    MakeMoveView,
    OnlinePlayersView,
    StartSoloGameView,
    heartbeat,
)

urlpatterns = [
    path("games/solo/", StartSoloGameView.as_view(), name="start_solo"),
    path("games/<uuid:id>/", GameDetailView.as_view(), name="game_detail"),
    path("games/<uuid:id>/move/", MakeMoveView.as_view(), name="make_move"),
    path("games/history/", GameHistoryView.as_view(), name="history"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("lobby/online/", OnlinePlayersView.as_view(), name="online_players"),
    path("lobby/heartbeat/", heartbeat, name="heartbeat"),
    path("rooms/create/", CreateRoomView.as_view(), name="create_room"),
    path("rooms/join/", JoinRoomView.as_view(), name="join_room"),
]
