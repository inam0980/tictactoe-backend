"""
Auth endpoints:
  POST /api/auth/register/  -> create account, return JWT pair + user
  POST /api/auth/login/     -> username+password -> JWT pair + user
  POST /api/auth/refresh/   -> refresh access token (built-in)
  GET  /api/auth/me/        -> current user's profile
  PATCH /api/auth/me/       -> update avatar_url, email
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


def _tokens_for(user) -> dict:
    """Issue a fresh refresh+access pair for `user`."""
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return Response(
            {"user": UserSerializer(user).data, "tokens": _tokens_for(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    Custom login (instead of SimpleJWT's TokenObtainPairView) so we can
    return the user profile alongside the tokens in one round-trip — the
    Flutter app needs both to populate its auth provider.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        if not username or not password:
            return Response(
                {"detail": "username and password required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.check_password(password):
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user.last_seen = timezone.now()
        user.save(update_fields=["last_seen"])
        return Response(
            {"user": UserSerializer(user).data, "tokens": _tokens_for(user)}
        )


class MeView(generics.RetrieveUpdateAPIView):
    """Current user's profile. Editable fields: avatar_url, email."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        for field in ("avatar_url", "email"):
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()
        return Response(UserSerializer(user).data)
