"""
Service layer — orchestrates DB writes for a move.

Both REST views (solo games) and WebSocket consumers (multiplayer) call
into these functions so the win-detection / stats-update logic lives in
exactly one place.
"""

import secrets

from django.db import transaction
from django.utils import timezone

from .logic import apply_move, check_winner, pick_ai_move
from .models import Game, GameMode, GameResult, GameStatus, Move


class GameError(Exception):
    """Raised for player-visible rule violations (not bugs)."""


@transaction.atomic
def record_move(game: Game, user, position: int) -> dict:
    """Apply `user`'s move to `game`. Returns a state dict for the client.

    For solo (AI) games, also plays the bot's reply move within the same
    transaction so the client sees both moves in one response.
    """
    if game.status == GameStatus.FINISHED:
        raise GameError("game is already finished")

    # Determine which mark the calling user plays.
    if user.id == game.player_x_id:
        my_mark = "X"
    elif game.player_o_id and user.id == game.player_o_id:
        my_mark = "O"
    else:
        raise GameError("you are not a player in this game")

    if game.turn != my_mark:
        raise GameError("not your turn")

    _play(game, user, position, my_mark)

    # If it's a solo game and game is still active, AI replies immediately.
    if game.is_solo and game.status == GameStatus.ACTIVE:
        ai_mark = "O" if my_mark == "X" else "X"
        ai_pos = pick_ai_move(game.board_state, ai_mark, game.mode)
        _play(game, None, ai_pos, ai_mark)

    return serialize_game_state(game)


def _play(game: Game, player, position: int, mark: str) -> None:
    """Apply one move (human or AI) and persist + check for end."""
    try:
        new_board = apply_move(game.board_state, position, mark)
    except ValueError as e:
        raise GameError(str(e))

    game.board_state = new_board
    if game.started_at is None:
        game.started_at = timezone.now()

    move_number = game.moves.count() + 1
    Move.objects.create(
        game=game, player=player, mark=mark,
        position=position, move_number=move_number,
    )

    outcome = check_winner(new_board)
    if outcome is None:
        # Game continues — flip turn.
        game.turn = "O" if mark == "X" else "X"
        game.status = GameStatus.ACTIVE
        game.save()
        return

    # Game ended this move.
    game.status = GameStatus.FINISHED
    game.ended_at = timezone.now()
    if outcome == "draw":
        game.result = GameResult.DRAW
        game.winner = None
    else:
        game.result = GameResult.X_WON if outcome == "X" else GameResult.O_WON
        game.winner = game.player_x if outcome == "X" else game.player_o
    game.save()

    _update_stats(game)


def _update_stats(game: Game) -> None:
    """Bump wins/losses/draws on the player rows. Solo games count too."""
    px, po = game.player_x, game.player_o

    if game.result == GameResult.DRAW:
        px.draws += 1
        px.save(update_fields=["draws"])
        if po:
            po.draws += 1
            po.save(update_fields=["draws"])
        return

    winner = game.winner
    loser = po if winner == px else px
    winner.wins += 1
    winner.save(update_fields=["wins"])
    if loser:  # None for solo games where AI "wins"
        loser.losses += 1
        loser.save(update_fields=["losses"])


def serialize_game_state(game: Game) -> dict:
    """Compact shape used by both REST responses and WS broadcasts."""
    return {
        "id": str(game.id),
        "mode": game.mode,
        "status": game.status,
        "result": game.result,
        "board": game.board_state,
        "turn": game.turn,
        "player_x": _user_brief(game.player_x),
        "player_o": _user_brief(game.player_o) if game.player_o else None,
        "winner": _user_brief(game.winner) if game.winner else None,
    }


def _user_brief(user) -> dict:
    return {"id": user.id, "username": user.username, "avatar_url": user.avatar_url}


# --- Private room (4-digit code) flow ---

_ROOM_CODE_TRIES = 8  # 10k codes, very few active at once → collisions are rare.


def _generate_room_code() -> str:
    """Cryptographically random 4-digit string, zero-padded ("0427")."""
    return f"{secrets.randbelow(10000):04d}"


@transaction.atomic
def create_room(user) -> Game:
    """Create a WAITING multiplayer game with a unique 4-digit room_code.

    Uniqueness is enforced only among currently-WAITING games. Finished
    games may share a code with a new room — that's fine because the
    join lookup filters by status.
    """
    for _ in range(_ROOM_CODE_TRIES):
        code = _generate_room_code()
        taken = Game.objects.filter(
            room_code=code, status=GameStatus.WAITING
        ).exists()
        if not taken:
            return Game.objects.create(
                mode=GameMode.MULTIPLAYER,
                status=GameStatus.WAITING,
                player_x=user,
                room_code=code,
            )
    # Astronomically unlikely with <100 concurrent rooms.
    raise GameError("could not allocate a unique room code, try again")


@transaction.atomic
def join_room(user, room_code: str) -> Game:
    """Find a WAITING room by code and put `user` in the player_o slot."""
    code = (room_code or "").strip()
    if not code.isdigit() or len(code) != 4:
        raise GameError("room code must be 4 digits")

    # select_for_update locks the row so two simultaneous joiners can't
    # both win the slot.
    game = (
        Game.objects.select_for_update()
        .filter(room_code=code, status=GameStatus.WAITING)
        .first()
    )
    if game is None:
        raise GameError("room not found or already started")
    if game.player_x_id == user.id:
        raise GameError("you can't join your own room")

    game.player_o = user
    game.status = GameStatus.ACTIVE
    game.started_at = timezone.now()
    game.save(update_fields=["player_o", "status", "started_at"])
    return game
