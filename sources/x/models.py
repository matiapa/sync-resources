from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuotedTweet:
    author_username: str
    text: str


@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    author_username: str
    author_name: str
    created_at: str                       # ISO8601 crudo de la API
    quoted: QuotedTweet | None = None
    media_urls: tuple[str, ...] = field(default_factory=tuple)
