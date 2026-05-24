from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import ChatMessage, Game, Move


class MoveSerializer(serializers.ModelSerializer):
    player = UserSerializer(read_only=True)

    class Meta:
        model = Move
        fields = ("id", "player", "mark", "position", "move_number", "played_at")


class GameSerializer(serializers.ModelSerializer):
    player_x = UserSerializer(read_only=True)
    player_o = UserSerializer(read_only=True)
    winner = UserSerializer(read_only=True)
    moves = MoveSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = (
            "id", "mode", "status", "result",
            "player_x", "player_o", "winner",
            "board_state", "turn",
            "created_at", "started_at", "ended_at",
            "moves",
        )


class GameHistoryItemSerializer(serializers.ModelSerializer):
    """Lightweight shape for the history list (no moves expanded)."""
    opponent = serializers.SerializerMethodField()
    my_result = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = (
            "id", "mode", "status", "result",
            "opponent", "my_result",
            "created_at", "ended_at",
        )

    def get_opponent(self, obj):
        me = self.context["request"].user
        if obj.is_solo:
            return {"username": f"AI ({obj.get_mode_display()})", "is_ai": True}
        other = obj.player_o if obj.player_x_id == me.id else obj.player_x
        if other is None:
            return None
        return {"id": other.id, "username": other.username, "avatar_url": other.avatar_url}

    def get_my_result(self, obj):
        if obj.status != "finished":
            return None
        me = self.context["request"].user
        if obj.result == "draw":
            return "draw"
        return "win" if obj.winner_id == me.id else "loss"


class ChatMessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ("id", "sender", "text", "sent_at")
