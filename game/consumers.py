"""
WebSocket consumers — handle real-time multiplayer game rooms + matchmaking.

A "consumer" in Channels is the async equivalent of a Django view:
each WebSocket connection gets one consumer instance for its whole lifetime.

Architecture:
- MatchmakingConsumer: client connects, waits in a queue. When two clients
  are waiting, we create a Game row and tell both clients the game_id.
  Then both clients connect to GameConsumer for that game.
- GameConsumer: joins a per-game "group" (Channels' pub/sub primitive).
  Receives move messages, validates + writes via services.record_move,
  broadcasts the new state to everyone in the group.
"""

import asyncio
import json
from typing import Optional

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .models import ChatMessage, Game, GameMode, GameStatus
from .services import GameError, record_move, serialize_game_state


# --- In-memory matchmaking queue ---
# Plain Python list because Channels matchmaking is intrinsically tied to
# one process anyway (the connection lives on this worker). For multi-
# worker prod, replace with a Redis-backed queue.
_MATCHMAKING_QUEUE: list[dict] = []
_QUEUE_LOCK = asyncio.Lock()


@database_sync_to_async
def _create_multiplayer_game(player_x, player_o) -> Game:
    return Game.objects.create(
        mode=GameMode.MULTIPLAYER,
        status=GameStatus.ACTIVE,
        player_x=player_x,
        player_o=player_o,
        started_at=timezone.now(),
    )


@database_sync_to_async
def _load_game(game_id) -> Optional[Game]:
    try:
        return Game.objects.select_related(
            "player_x", "player_o", "winner"
        ).get(id=game_id)
    except Game.DoesNotExist:
        return None


@database_sync_to_async
def _record_move(game, user, position) -> dict:
    return record_move(game, user, position)


@database_sync_to_async
def _save_chat(game, sender, text) -> dict:
    msg = ChatMessage.objects.create(game=game, sender=sender, text=text[:200])
    return {
        "id": msg.id,
        "sender": {"id": sender.id, "username": sender.username},
        "text": msg.text,
        "sent_at": msg.sent_at.isoformat(),
    }


@database_sync_to_async
def _refresh_state(game_id) -> Optional[dict]:
    g = Game.objects.select_related("player_x", "player_o", "winner").filter(id=game_id).first()
    return serialize_game_state(g) if g else None


class MatchmakingConsumer(AsyncWebsocketConsumer):
    """
    Client connects to ws://host/ws/matchmaking/?token=JWT.
    Server pairs two waiting clients, creates a Game, and sends each
    client {"type": "matched", "game_id": "...", "your_mark": "X"|"O"}.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        await self._try_match()

    async def disconnect(self, code):
        async with _QUEUE_LOCK:
            _MATCHMAKING_QUEUE[:] = [
                e for e in _MATCHMAKING_QUEUE if e["channel"] != self.channel_name
            ]

    async def _try_match(self):
        async with _QUEUE_LOCK:
            # Don't match a user against themselves (multiple devices).
            opponent = next(
                (e for e in _MATCHMAKING_QUEUE if e["user_id"] != self.user.id),
                None,
            )
            if opponent is None:
                _MATCHMAKING_QUEUE.append({
                    "user_id": self.user.id,
                    "user": self.user,
                    "channel": self.channel_name,
                })
                await self.send(json.dumps({"type": "waiting"}))
                return
            _MATCHMAKING_QUEUE.remove(opponent)

        game = await _create_multiplayer_game(
            player_x=opponent["user"], player_o=self.user
        )
        # Notify the waiting opponent (X).
        await self.channel_layer.send(opponent["channel"], {
            "type": "match.found",
            "game_id": str(game.id),
            "your_mark": "X",
        })
        # Notify ourselves (O).
        await self.send(json.dumps({
            "type": "matched",
            "game_id": str(game.id),
            "your_mark": "O",
        }))

    async def match_found(self, event):
        """Handler invoked by channel_layer.send -> the waiting client."""
        await self.send(json.dumps({
            "type": "matched",
            "game_id": event["game_id"],
            "your_mark": event["your_mark"],
        }))


class GameConsumer(AsyncWebsocketConsumer):
    """
    Client connects to ws://host/ws/game/<game_id>/?token=JWT.

    Message protocol (client -> server, JSON):
      {"type": "move", "position": 0..8}
      {"type": "chat", "text": "..."}
      {"type": "resign"}

    Server -> client:
      {"type": "state", "game": {...}}
      {"type": "chat",  "message": {...}}
      {"type": "error", "detail": "..."}
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.game_id = str(self.scope["url_route"]["kwargs"]["game_id"])
        self.group_name = f"game_{self.game_id}"

        game = await _load_game(self.game_id)
        if game is None:
            await self.close(code=4404)
            return
        # Only the two players may connect.
        if self.user.id not in {game.player_x_id, game.player_o_id}:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Send initial state on connect so a reconnecting client recovers.
        state = await _refresh_state(self.game_id)
        await self.send(json.dumps({"type": "state", "game": state}))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "detail": "invalid JSON"}))
            return

        msg_type = data.get("type")
        if msg_type == "move":
            await self._handle_move(data)
        elif msg_type == "chat":
            await self._handle_chat(data)
        elif msg_type == "resign":
            await self._handle_resign()
        else:
            await self.send(json.dumps({"type": "error", "detail": f"unknown type {msg_type!r}"}))

    async def _handle_move(self, data):
        position = data.get("position")
        if not isinstance(position, int):
            await self.send(json.dumps({"type": "error", "detail": "position must be int 0-8"}))
            return
        game = await _load_game(self.game_id)
        if game is None:
            await self.send(json.dumps({"type": "error", "detail": "game gone"}))
            return
        try:
            state = await _record_move(game, self.user, position)
        except GameError as e:
            await self.send(json.dumps({"type": "error", "detail": str(e)}))
            return
        await self.channel_layer.group_send(self.group_name, {
            "type": "broadcast.state",
            "state": state,
        })

    async def _handle_chat(self, data):
        text = (data.get("text") or "").strip()
        if not text:
            return
        game = await _load_game(self.game_id)
        if game is None:
            return
        msg = await _save_chat(game, self.user, text)
        await self.channel_layer.group_send(self.group_name, {
            "type": "broadcast.chat",
            "message": msg,
        })

    async def _handle_resign(self):
        # Simple resign: just mark abandoned. Stats not updated for resigns
        # to keep the rules forgiving — change here if you want penalties.
        @database_sync_to_async
        def _do():
            g = Game.objects.get(id=self.game_id)
            if g.status == GameStatus.FINISHED:
                return serialize_game_state(g)
            g.status = GameStatus.ABANDONED
            g.ended_at = timezone.now()
            g.save()
            return serialize_game_state(g)
        state = await _do()
        await self.channel_layer.group_send(self.group_name, {
            "type": "broadcast.state",
            "state": state,
        })

    # --- group event handlers (server-to-server via channel_layer) ---

    async def broadcast_state(self, event):
        await self.send(json.dumps({"type": "state", "game": event["state"]}))

    async def broadcast_chat(self, event):
        await self.send(json.dumps({"type": "chat", "message": event["message"]}))
