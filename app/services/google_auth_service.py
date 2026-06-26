from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings


@dataclass
class GoogleUserInfo:
    google_id: str
    email: str
    name: str
    avatar_url: str | None


def verify_google_token(token: str) -> GoogleUserInfo:
    request = google_requests.Request()
    idinfo = id_token.verify_oauth2_token(token, request, settings.GOOGLE_CLIENT_ID)

    return GoogleUserInfo(
        google_id=idinfo["sub"],
        email=idinfo["email"],
        name=idinfo.get("name", ""),
        avatar_url=idinfo.get("picture"),
    )
