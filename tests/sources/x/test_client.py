from types import SimpleNamespace

from sources.x import client
from sources.x.models import Tweet, QuotedTweet


def _resp(json_body, status=200):
    return SimpleNamespace(status_code=status, ok=(200 <= status < 300),
                           text=str(json_body), json=lambda: json_body)


PAGE = {
    "data": [
        {
            "id": "100", "text": "un tweet con imagen", "author_id": "u1",
            "created_at": "2026-06-28T14:00:00.000Z",
            "attachments": {"media_keys": ["m1"]},
        },
        {
            "id": "200", "text": "cito a alguien", "author_id": "u1",
            "created_at": "2026-06-29T10:00:00.000Z",
            "referenced_tweets": [{"type": "quoted", "id": "999"}],
        },
    ],
    "includes": {
        "users": [
            {"id": "u1", "username": "jane", "name": "Jane Dev"},
            {"id": "u2", "username": "other", "name": "Other"},
        ],
        "tweets": [{"id": "999", "author_id": "u2", "text": "texto citado"}],
        "media": [{"media_key": "m1", "type": "photo", "url": "https://pbs.twimg.com/a.jpg"}],
    },
    "meta": {},
}


def test_parse_bookmarks_builds_tweets_with_media_and_quote():
    tweets = client.parse_bookmarks(PAGE)
    assert tweets[0] == Tweet(
        id="100", text="un tweet con imagen", author_username="jane",
        author_name="Jane Dev", created_at="2026-06-28T14:00:00.000Z",
        media_urls=("https://pbs.twimg.com/a.jpg",),
    )
    assert tweets[1].quoted == QuotedTweet(author_username="other", text="texto citado")


def test_parse_bookmarks_video_uses_best_mp4_variant():
    page = {
        "data": [{"id": "1", "text": "vid", "author_id": "u1",
                  "created_at": "2026-06-28T14:00:00.000Z",
                  "attachments": {"media_keys": ["v1"]}}],
        "includes": {
            "users": [{"id": "u1", "username": "jane", "name": "Jane"}],
            "media": [{"media_key": "v1", "type": "video",
                       "variants": [
                           {"bit_rate": 256000, "content_type": "video/mp4", "url": "low.mp4"},
                           {"bit_rate": 832000, "content_type": "video/mp4", "url": "high.mp4"},
                           {"content_type": "application/x-mpegURL", "url": "stream.m3u8"},
                       ]}],
        },
        "meta": {},
    }
    tweets = client.parse_bookmarks(page)
    assert tweets[0].media_urls == ("high.mp4",)


def test_get_user_id():
    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.endswith("/users/me")
        return _resp({"data": {"id": "u1", "username": "jane", "name": "Jane"}})

    assert client.get_user_id("token", get=fake_get) == "u1"


def test_get_bookmarks_follows_pagination():
    pages = [
        {"data": [{"id": "1", "text": "a", "author_id": "u1",
                   "created_at": "2026-06-28T14:00:00.000Z"}],
         "includes": {"users": [{"id": "u1", "username": "j", "name": "J"}]},
         "meta": {"next_token": "TOK"}},
        {"data": [{"id": "2", "text": "b", "author_id": "u1",
                   "created_at": "2026-06-29T14:00:00.000Z"}],
         "includes": {"users": [{"id": "u1", "username": "j", "name": "J"}]},
         "meta": {}},
    ]
    seen_tokens = []

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_tokens.append(params.get("pagination_token"))
        return _resp(pages.pop(0))

    tweets = client.get_bookmarks("u1", "token", get=fake_get)
    assert [t.id for t in tweets] == ["1", "2"]
    assert seen_tokens == [None, "TOK"]   # 1ra sin token, 2da con next_token
