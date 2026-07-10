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
