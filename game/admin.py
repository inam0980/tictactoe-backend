from django.contrib import admin

from .models import ChatMessage, Game, Move


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "status", "result", "player_x", "player_o", "winner", "created_at")
    list_filter = ("status", "mode", "result")
    readonly_fields = ("id", "created_at", "started_at", "ended_at")


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("game", "move_number", "player", "mark", "position", "played_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("game", "sender", "text", "sent_at")
