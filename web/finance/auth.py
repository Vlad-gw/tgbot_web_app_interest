import secrets
from rest_framework.exceptions import AuthenticationFailed
from .models import User


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def get_user_from_request(request) -> User:
    key = request.headers.get("X-API-KEY") or request.query_params.get("api_key")
    if not key:
        raise AuthenticationFailed("Missing X-API-KEY")
    user = User.objects.filter(api_key=key).first()
    if not user:
        raise AuthenticationFailed("Invalid API key")
    return user
