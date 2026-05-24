"""
Game domain models.

A Game row is the single source of truth for a match. `board_state` is
stored as a 9-char string ("XOX.O.X..") rather than 9 separate columns,
because we always read/write the whole board together and the UI just
unpacks it.

Move rows are kept for replay/history. We do NOT reconstruct the board
from Move rows during play — board_state on Game is authoritative.
"""

import uuid

from django.conf import settings
from django.db import models


class GameMode(models.TextChoices):
    AI_EASY = "ai_easy", "AI — Easy"
    AI_MEDIUM = "ai_medium", "AI — Medium"
    AI_HARD = "ai_hard", "AI — Hard"
    MULTIPLAYER = "multiplayer", "Multiplayer"


class GameStatus(models.TextChoices):
    WAITING = "waiting", "Waiting for opponent"
    ACTIVE = "active", "In progress"
    FINISHED = "finished", "Finished"
    ABANDONED = "abandoned", "Abandoned"


class GameResult(models.TextChoices):
    X_WON = "x_won", "X won"
    O_WON = "o_won", "O won"
    DRAW = "draw", "Draw"


EMPTY_BOARD = "........."  # 9 dots = 9 empty cells


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    mode = models.CharField(max_length=20, choices=GameMode.choices)
    status = models.CharField(
        max_length=20, choices=GameStatus.choices, default=GameStatus.WAITING
    )
    result = models.CharField(
        max_length=10, choices=GameResult.choices, blank=True, default=""
    )

    # player_x always exists. player_o is null for solo (AI) games until
    # an AI bot move is recorded — for AI games we leave it null forever
    # and the "opponent" is implied by the mode.
    player_x = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="games_as_x",
    )
    player_o = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="games_as_o",
        null=True, blank=True,
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="games_won",
        null=True, blank=True,
    )

    # 9-char board. "." = empty, "X" or "O" = mark.
    board_state = models.CharField(max_length=9, default=EMPTY_BOARD)
    # Whose turn ("X" or "O"). X always starts.
    turn = models.CharField(max_length=1, default="X")

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        o = self.player_o.username if self.player_o else f"AI ({self.mode})"
        return f"{self.player_x.username} vs {o} [{self.status}]"

    @property
    def is_solo(self) -> bool:
        return self.mode in {
            GameMode.AI_EASY, GameMode.AI_MEDIUM, GameMode.AI_HARD,
        }


class Move(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="moves")
    # Null player = AI move in a solo game.
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    mark = models.CharField(max_length=1)        # "X" or "O"
    position = models.PositiveSmallIntegerField()  # 0..8
    move_number = models.PositiveSmallIntegerField()  # 1..9
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["move_number"]
        unique_together = [("game", "move_number"), ("game", "position")]


class ChatMessage(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.CharField(max_length=200)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_at"]
