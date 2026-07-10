from pathlib import Path

import pytest

from config import Config
from sources.base import RenderedNote
from sources.x.auth import AuthError, TokenStore
from sources.x.models import Tweet, QuotedTweet
from sources.x.source import XSource


def _cfg(tmp_path, cid="cid", sec="sec") -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=tmp_path, github_subdir="Recursos/Repositorios",
        git_push=True, gbrain_sync=True, script_dir=tmp_path,
        log_path=tmp_path / "sync.log",
        x_client_id=cid, x_client_secret=sec, x_subdir="Recursos/Posts",
        x_token_path=tmp_path / ".x_token.json",
    )


def _tweet(tid="1"):
    return Tweet(id=tid, text="hola", author_username="jane", author_name="Jane",
                 created_at="2026-06-28T14:00:00.000Z")


def test_name_and_subdir(tmp_path):
    src = XSource(_cfg(tmp_path), openai_client=None)
    assert src.name == "X"
    assert src.subdir == "Recursos/Posts"


def test_stem_is_tweet_id(tmp_path):
    src = XSource(_cfg(tmp_path), openai_client=None)
    assert src.stem(_tweet("42")) == "42"


def test_fetch_raises_when_credentials_missing(tmp_path):
    src = XSource(_cfg(tmp_path, cid=None), openai_client=None)
    with pytest.raises(AuthError):
        src.fetch()


def test_fetch_resolves_user_id_and_returns_bookmarks(tmp_path):
    store = TokenStore(tmp_path / ".x_token.json")
    store.save({"access_token": "at", "refresh_token": "rt",
                "expires_at": "2999-01-01T00:00:00", "user_id": None})
    calls = {}

    def fake_get_user_id(token, **k):
        calls["user_id_fetched"] = True
        return "u1"

    def fake_get_bookmarks(user_id, token, **k):
        calls["user_id_used"] = user_id
        return [_tweet("1"), _tweet("2")]

    src = XSource(
        _cfg(tmp_path), openai_client=None,
        get_valid_access_token=lambda *a, **k: "at",
        get_user_id=fake_get_user_id, get_bookmarks=fake_get_bookmarks,
        token_store=store,
    )
    tweets = src.fetch()
    assert [t.id for t in tweets] == ["1", "2"]
    assert calls["user_id_used"] == "u1"
    # user_id se persiste en el store
    assert store.load()["user_id"] == "u1"


def test_fetch_uses_cached_user_id(tmp_path):
    store = TokenStore(tmp_path / ".x_token.json")
    store.save({"access_token": "at", "refresh_token": "rt",
                "expires_at": "2999-01-01T00:00:00", "user_id": "cached"})

    def fake_get_user_id(token, **k):
        raise AssertionError("no debería pedir user_id")

    src = XSource(
        _cfg(tmp_path), openai_client=None,
        get_valid_access_token=lambda *a, **k: "at",
        get_user_id=fake_get_user_id,
        get_bookmarks=lambda user_id, token, **k: [_tweet("1")],
        token_store=store,
    )
    assert [t.id for t in src.fetch()] == ["1"]


def test_render_builds_note_with_description(tmp_path):
    from sources.x.notes import render_post_note
    seen = {}

    def fake_describe(text, model, client):
        seen["text"] = text
        return "una frase", 9

    src = XSource(_cfg(tmp_path), openai_client=None, describe=fake_describe)
    tw = Tweet(id="1", text="cuerpo", author_username="jane", author_name="Jane",
               created_at="2026-06-28T14:00:00.000Z",
               quoted=QuotedTweet("other", "citado"))
    note = src.render(tw)
    assert isinstance(note, RenderedNote)
    assert note.tokens == 9
    assert note.text == render_post_note(tw, "una frase")
    # el texto que va al LLM incluye cuerpo y citado
    assert "cuerpo" in seen["text"]
    assert "citado" in seen["text"]
