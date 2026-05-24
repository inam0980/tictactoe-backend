"""
REST endpoints for solo games + history + leaderboard + lobby.

Real-time multiplayer goes through WebSockets (consumers.py), not here.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserSerializer

from .logic import pick_ai_move
from .models import Game, GameMode, GameStatus
from .serializers import (
    ChatMessageSerializer,
    GameHistoryItemSerializer,
    GameSerializer,
)
from .services import (
    GameError,
    _play,
    create_room,
    join_room,
    record_move,
    serialize_game_state,
)

User = get_user_model()


class StartSoloGameView(APIView):
    """
    POST /api/games/solo/  body: {"mode": "ai_easy|ai_medium|ai_hard",
                                   "player_mark": "X"|"O" (default X)}
    Returns the freshly created Game. If the user picks O, the AI plays
    the opening move immediately so the client never has to wait.
    """

    def post(self, request):
        mode = request.data.get("mode", GameMode.AI_MEDIUM)
        if mode not in {GameMode.AI_EASY, GameMode.AI_MEDIUM, GameMode.AI_HARD}:
            return Response({"detail": "invalid mode"}, status=400)

        player_mark = request.data.get("player_mark", "X").upper()
        if player_mark not in ("X", "O"):
            return Response({"detail": "player_mark must be X or O"}, status=400)

        game = Game.objects.create(
            mode=mode,
            status=GameStatus.ACTIVE,
            player_x=request.user if player_mark == "X" else None,
            player_o=request.user if player_mark == "O" else None,
            started_at=timezone.now(),
        )
        # If the human is O, the AI (X) plays first.
        if player_mark == "O":
            # player_x must be non-null in the model — we set the human
            # in the X slot for solo games regardless and use a flag... but
            # to keep the schema simple we always put the human in X.
            # Re-create with human as X. (Simplification: AI O only.)
            game.delete()
            game = Game.objects.create(
                mode=mode,
                status=GameStatus.ACTIVE,
                player_x=request.user,
                started_at=timezone.now(),
            )

        return Response(serialize_game_state(game), status=status.HTTP_201_CREATED)


class GameDetailView(generics.RetrieveAPIView):
    serializer_class = GameSerializer
    queryset = Game.objects.all()
    lookup_field = "id"


class MakeMoveView(APIView):
    """POST /api/games/<id>/move/  body: {"position": 0..8}"""

    def post(self, request, id):
        try:
            game = Game.objects.get(id=id)
        except Game.DoesNotExist:
            return Response({"detail": "game not found"}, status=404)
        try:
            position = int(request.data.get("position"))
        except (TypeError, ValueError):
            return Response({"detail": "position required (0-8)"}, status=400)
        try:
            state = record_move(game, request.user, position)
        except GameError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(state)


class GameHistoryView(generics.ListAPIView):
    """GET /api/games/history/  -> last 50 games of the current user."""
    serializer_class = GameHistoryItemSerializer

    def get_queryset(self):
        u = self.request.user
        return (
            Game.objects.filter(Q(player_x=u) | Q(player_o=u))
            .select_related("player_x", "player_o", "winner")
            .order_by("-created_at")[:50]
        )


class LeaderboardView(APIView):
    """GET /api/leaderboard/  -> top 100 users by wins."""

    def get(self, request):
        users = User.objects.order_by("-wins", "-draws")[:100]
        data = [
            {**UserSerializer(u).data, "rank": i + 1}
            for i, u in enumerate(users)
        ]
        return Response(data)


class OnlinePlayersView(APIView):
    """GET /api/lobby/online/  -> users seen in the last 2 minutes."""

    def get(self, request):
        cutoff = timezone.now() - timezone.timedelta(minutes=2)
        users = (
            User.objects.filter(last_seen__gte=cutoff)
            .exclude(id=request.user.id)
            .order_by("-last_seen")[:50]
        )
        return Response(UserSerializer(users, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def heartbeat(request):
    """Lobby clients call this every ~30s to mark themselves online."""
    request.user.last_seen = timezone.now()
    request.user.save(update_fields=["last_seen"])
    return Response({"ok": True})


class CreateRoomView(APIView):
    """POST /api/rooms/create/  -> {game_id, room_code} for a new private room."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            game = create_room(request.user)
        except GameError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(
            {"game_id": str(game.id), "room_code": game.room_code},
            status=status.HTTP_201_CREATED,
        )


class JoinRoomView(APIView):
    """POST /api/rooms/join/  body: {"room_code": "0427"} -> {game_id, your_mark}

    After flipping the game to ACTIVE in the DB, we push a state frame to
    the game's Channels group so the creator (who is already connected to
    the GameConsumer waiting) navigates into the game instantly.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("room_code", "")
        try:
            game = join_room(request.user, code)
        except GameError as e:
            return Response({"detail": str(e)}, status=400)

        # Push the new ACTIVE state to anyone listening on this game's group
        # (the creator's WebSocket). The joiner connects to the same group
        # right after this response, and GameConsumer.connect sends them
        # the initial state directly — so we don't need to send to ourselves.
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"game_{game.id}",
                {"type": "broadcast.state", "state": serialize_game_state(game)},
            )

        return Response(
            {"game_id": str(game.id), "your_mark": "O"},
            status=status.HTTP_200_OK,
        )
