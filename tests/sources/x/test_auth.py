import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from sources.x import auth


def test_generate_pkce_challenge_matches_verifier():
    verifier, challenge = auth.generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert challenge == expected


def test_build_authorize_url_has_required_params():
    url = auth.build_authorize_url("cid", "http://127.0.0.1:8723/callback", "chal", "st")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8723/callback"]
    assert q["code_challenge"] == ["chal"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["st"]
    assert q["scope"] == [auth.SCOPES]


def _resp(json_body, status=200):
    return SimpleNamespace(
        status_code=status, json=lambda: json_body,
        text=str(json_body), ok=(200 <= status < 300),
    )


def test_exchange_code_posts_with_basic_auth():
    calls = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        calls["url"] = url
        calls["data"] = data
        calls["auth"] = auth
        return _resp({"access_token": "at", "refresh_token": "rt", "expires_in": 7200})

    body = auth.exchange_code("cid", "sec", "the-code", "verifier",
                              "http://127.0.0.1:8723/callback", post=fake_post)
    assert body["access_token"] == "at"
    assert calls["url"] == auth.TOKEN_URL
    assert calls["auth"] == ("cid", "sec")
    assert calls["data"]["grant_type"] == "authorization_code"
    assert calls["data"]["code"] == "the-code"
    assert calls["data"]["code_verifier"] == "verifier"
    assert calls["data"]["redirect_uri"] == "http://127.0.0.1:8723/callback"


def test_refresh_access_token_uses_refresh_grant():
    seen = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        seen["data"] = data
        return _resp({"access_token": "new", "refresh_token": "rot", "expires_in": 7200})

    body = auth.refresh_access_token("cid", "sec", "old-rt", post=fake_post)
    assert body["access_token"] == "new"
    assert seen["data"]["grant_type"] == "refresh_token"
    assert seen["data"]["refresh_token"] == "old-rt"


def test_exchange_code_raises_on_error():
    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        return _resp({"error": "invalid_grant"}, status=400)

    with pytest.raises(auth.AuthError):
        auth.exchange_code("cid", "sec", "bad", "v", "http://127.0.0.1:8723/callback", post=fake_post)


import json
from datetime import datetime, timedelta
from pathlib import Path

from sources.x.auth import TokenStore, save_token_response, get_valid_access_token, AuthError


def _store(tmp_path) -> TokenStore:
    return TokenStore(tmp_path / ".x_token.json")


def test_store_load_missing_returns_empty(tmp_path):
    assert _store(tmp_path).load() == {}


def test_save_token_response_normalizes_and_persists(tmp_path):
    store = _store(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, 0)
    data = save_token_response(store,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 7200},
        user_id="u1", now=lambda: now)
    assert data["access_token"] == "at"
    assert data["refresh_token"] == "rt"
    assert data["user_id"] == "u1"
    assert data["expires_at"] == (now + timedelta(seconds=7200)).isoformat()
    # persistido en disco
    assert json.loads(Path(store.path).read_text())["access_token"] == "at"


def test_get_valid_access_token_returns_current_when_fresh(tmp_path):
    store = _store(tmp_path)
    future = (datetime(2026, 7, 10, 12, 0, 0) + timedelta(hours=1)).isoformat()
    store.save({"access_token": "fresh", "refresh_token": "rt", "expires_at": future, "user_id": "u1"})

    def fail_post(*a, **k):
        raise AssertionError("no debería refrescar")

    tok = get_valid_access_token(store, "cid", "sec",
        now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=fail_post)
    assert tok == "fresh"


def test_get_valid_access_token_refreshes_and_rotates(tmp_path):
    store = _store(tmp_path)
    past = (datetime(2026, 7, 10, 12, 0, 0) - timedelta(minutes=1)).isoformat()
    store.save({"access_token": "old", "refresh_token": "old-rt", "expires_at": past, "user_id": "u1"})

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        from types import SimpleNamespace
        return SimpleNamespace(status_code=200, ok=True, text="",
            json=lambda: {"access_token": "new", "refresh_token": "new-rt", "expires_in": 7200})

    tok = get_valid_access_token(store, "cid", "sec",
        now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=fake_post)
    assert tok == "new"
    saved = store.load()
    assert saved["refresh_token"] == "new-rt"   # rotación persistida
    assert saved["user_id"] == "u1"             # user_id conservado


def test_get_valid_access_token_without_refresh_token_raises(tmp_path):
    store = _store(tmp_path)  # vacío
    with pytest.raises(AuthError):
        get_valid_access_token(store, "cid", "sec",
            now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=lambda *a, **k: None)
