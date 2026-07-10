import json

from sources.x.models import Tweet


def _yaml_scalar(value: str) -> str:
    """Escalar YAML seguro (mismo criterio que notes._yaml_scalar)."""
    return json.dumps(value, ensure_ascii=False)


def render_post_note(tweet: Tweet, description: str) -> str:
    parts = [
        "---\n",
        "tags:\n",
        "  - Recursos/Post\n",
        "type: Recurso\n",
        "subtype: Post\n",
        "source: X\n",
        f"description: {_yaml_scalar(description)}\n",
        "---\n",
        "\n",
        f"# Post de {tweet.author_name} (@{tweet.author_username})\n",
        "\n",
        f"{tweet.text}\n",
    ]
    if tweet.quoted is not None:
        parts.append("\n")
        parts.append(f"> **Cita a @{tweet.quoted.author_username}:**\n")
        for line in tweet.quoted.text.split("\n"):
            parts.append(f"> {line}\n")
    if tweet.media_urls:
        parts.append("\n## Media\n")
        for url in tweet.media_urls:
            parts.append(f"- {url}\n")
    parts.append("\n## Metadatos\n")
    parts.append(f"- **Autor:** [@{tweet.author_username}](https://x.com/{tweet.author_username}) ({tweet.author_name})\n")
    parts.append(f"- **Fecha:** {tweet.created_at[:10]}\n")
    parts.append(f"- **Post:** https://x.com/{tweet.author_username}/status/{tweet.id}\n")
    return "".join(parts)
