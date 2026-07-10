import requests

from sources.x.models import QuotedTweet, Tweet

API_BASE = "https://api.x.com/2"
_TIMEOUT = 30

BOOKMARK_FIELDS = {
    "tweet.fields": "created_at,text,author_id,referenced_tweets,attachments",
    "expansions": "author_id,referenced_tweets.id,referenced_tweets.id.author_id,attachments.media_keys",
    "user.fields": "name,username",
    "media.fields": "url,preview_image_url,type,variants",
    "max_results": "100",
}


class XApiError(Exception):
    pass


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _check(resp):
    if not getattr(resp, "ok", 200 <= resp.status_code < 300):
        raise XApiError(f"X API devolvió {resp.status_code}: {resp.text}")
    return resp.json()


def get_user_id(access_token: str, *, get=requests.get) -> str:
    resp = get(f"{API_BASE}/users/me", headers=_auth_headers(access_token), params=None, timeout=_TIMEOUT)
    return _check(resp)["data"]["id"]


def _best_media_url(media: dict) -> str | None:
    if media.get("type") == "photo":
        return media.get("url")
    variants = [v for v in media.get("variants", []) if v.get("content_type") == "video/mp4"]
    if variants:
        best = max(variants, key=lambda v: v.get("bit_rate", 0))
        return best.get("url")
    return media.get("preview_image_url")


def parse_bookmarks(payload: dict) -> list[Tweet]:
    includes = payload.get("includes", {})
    users = {u["id"]: u for u in includes.get("users", [])}
    tweets_by_id = {t["id"]: t for t in includes.get("tweets", [])}
    media_by_key = {m["media_key"]: m for m in includes.get("media", [])}

    result: list[Tweet] = []
    for item in payload.get("data", []):
        author = users.get(item.get("author_id"), {})
        quoted = None
        for ref in item.get("referenced_tweets", []):
            if ref.get("type") == "quoted":
                qt = tweets_by_id.get(ref.get("id"))
                if qt:
                    qa = users.get(qt.get("author_id"), {})
                    quoted = QuotedTweet(author_username=qa.get("username", ""), text=qt.get("text", ""))
                break
        media_urls = []
        for key in item.get("attachments", {}).get("media_keys", []):
            media = media_by_key.get(key)
            if media:
                url = _best_media_url(media)
                if url:
                    media_urls.append(url)
        result.append(Tweet(
            id=item["id"], text=item.get("text", ""),
            author_username=author.get("username", ""), author_name=author.get("name", ""),
            created_at=item.get("created_at", ""), quoted=quoted,
            media_urls=tuple(media_urls),
        ))
    return result


def get_bookmarks(user_id: str, access_token: str, *, get=requests.get) -> list[Tweet]:
    tweets: list[Tweet] = []
    next_token = None
    while True:
        params = dict(BOOKMARK_FIELDS)
        if next_token:
            params["pagination_token"] = next_token
        else:
            params["pagination_token"] = None
        resp = get(f"{API_BASE}/users/{user_id}/bookmarks",
                   headers=_auth_headers(access_token), params=params, timeout=_TIMEOUT)
        payload = _check(resp)
        tweets.extend(parse_bookmarks(payload))
        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
    return tweets
