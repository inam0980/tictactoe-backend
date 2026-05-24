"""
DRF serializers translate model instances <-> JSON.

- RegisterSerializer: validates signup input, creates user with hashed pw.
- UserSerializer: read-only public profile shape used everywhere else.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")
        extra_kwargs = {"email": {"required": False, "allow_blank": True}}

    def create(self, validated_data):
        # create_user hashes the password (set_password). Never store raw.
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )


class UserSerializer(serializers.ModelSerializer):
    games_played = serializers.IntegerField(read_only=True)
    win_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "avatar_url",
            "wins", "losses", "draws", "games_played", "win_rate",
            "date_joined", "last_seen",
        )
        read_only_fields = fields
