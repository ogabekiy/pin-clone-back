from typing import Any, Dict
from google.oauth2 import id_token
from google.auth.transport import requests
from app.core.config import settings


def verify_google_token(token: str) -> Dict[str, Any]:
    """
    Verifies the Google ID token and returns payload containing 'sub', 'email', 'name', 'picture'.
    Rule 8 & 9: Always verify token on backend, identify user by 'sub' (google_id).
    """
    try:
        id_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID if settings.GOOGLE_CLIENT_ID else None,
        )
        return {
            "google_id": id_info["sub"],
            "email": id_info.get("email"),
            "name": id_info.get("name"),
            "avatar_url": id_info.get("picture"),
        }
    except Exception as e:
        raise ValueError(f"Google ID tokeni yaroqsiz: {str(e)}")

