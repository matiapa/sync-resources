import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = "bookmark.read tweet.read users.read offline.access"

_TIMEOUT = 30


class AuthError(Exception):
    pass


def generate_pkce() -> tuple[str, str]:
    """Genera (code_verifier, code_challenge) para OAuth 2.0 PKCE (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, code_challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(data: dict, client_id: str, client_secret: str, post) -> dict:
    resp = post(
        TOKEN_URL,
        data=data,
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    if not getattr(resp, "ok", 200 <= resp.status_code < 300):
        raise AuthError(f"Token endpoint devolvió {resp.status_code}: {resp.text}")
    return resp.json()


def exchange_code(client_id, client_secret, code, code_verifier, redirect_uri, *, post=requests.post) -> dict:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        client_id, client_secret, post,
    )


def refresh_access_token(client_id, client_secret, refresh_token, *, post=requests.post) -> dict:
    return _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        client_id, client_secret, post,
    )
