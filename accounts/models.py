"""
Custom User model.

We extend AbstractUser instead of using Django's default so we can add
profile fields (avatar, stats) later without painful migrations.
Stats are denormalised on the user row for O(1) leaderboard reads.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    avatar_url = models.URLField(blank=True, default="")

    # Denormalised stats. Updated whenever a game finishes.
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)

    # Last-seen timestamp drives the online-players list in the lobby.
    last_seen = models.DateTimeField(null=True, blank=True)

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        played = self.games_played
        return round(self.wins / played, 3) if played else 0.0

    def __str__(self) -> str:
        return self.username
