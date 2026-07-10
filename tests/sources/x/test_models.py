from sources.x.models import Tweet, QuotedTweet


def test_tweet_minimal_defaults():
    t = Tweet(id="1", text="hola", author_username="jane",
              author_name="Jane", created_at="2026-06-28T14:00:00.000Z")
    assert t.quoted is None
    assert t.media_urls == ()


def test_tweet_with_quote_and_media():
    q = QuotedTweet(author_username="other", text="citado")
    t = Tweet(id="2", text="mira esto", author_username="jane", author_name="Jane",
              created_at="2026-06-28T14:00:00.000Z", quoted=q,
              media_urls=("https://pbs.twimg.com/a.jpg",))
    assert t.quoted.author_username == "other"
    assert t.media_urls == ("https://pbs.twimg.com/a.jpg",)
