import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
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


class TokenStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def save_token_response(store: TokenStore, body: dict, user_id: str | None = None,
                        now=datetime.now) -> dict:
    prev = store.load()
    expires_at = (now() + timedelta(seconds=int(body.get("expires_in", 7200)))).isoformat()
    data = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", prev.get("refresh_token")),
        "expires_at": expires_at,
        "user_id": user_id if user_id is not None else prev.get("user_id"),
    }
    store.save(data)
    return data


def get_valid_access_token(store: TokenStore, client_id: str, client_secret: str, *,
                           now=datetime.now, post=requests.post, skew_seconds: int = 300) -> str:
    data = store.load()
    expires_at = data.get("expires_at")
    if data.get("access_token") and expires_at:
        remaining = datetime.fromisoformat(expires_at) - now()
        if remaining.total_seconds() > skew_seconds:
            return data["access_token"]
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise AuthError("No hay refresh token guardado. Re-autorizá con `sync.py auth x`.")
    body = refresh_access_token(client_id, client_secret, refresh_token, post=post)
    data = save_token_response(store, body, user_id=data.get("user_id"), now=now)
    return data["access_token"]
