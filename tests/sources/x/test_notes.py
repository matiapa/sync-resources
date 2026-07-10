import yaml

from sources.x.models import Tweet, QuotedTweet
from sources.x.notes import render_post_note


def _tweet(**kw):
    base = dict(id="123", text="cuerpo crudo\ncon salto", author_username="janedev",
                author_name="Jane Dev", created_at="2026-06-28T14:00:00.000Z")
    base.update(kw)
    return Tweet(**base)


def test_render_has_frontmatter_and_body():
    md = render_post_note(_tweet(), "Frase de descripcion.")
    fm = md.split("---\n")[1]
    parsed = yaml.safe_load(fm)
    assert parsed["type"] == "Recurso"
    assert parsed["subtype"] == "Post"
    assert parsed["source"] == "X"
    assert parsed["tags"] == ["Recursos/Post"]
    assert parsed["description"] == "Frase de descripcion."
    assert "# Post de Jane Dev (@janedev)" in md
    assert "cuerpo crudo\ncon salto" in md
    assert "[@janedev](https://x.com/janedev) (Jane Dev)" in md
    assert "**Fecha:** 2026-06-28" in md
    assert "https://x.com/janedev/status/123" in md
    assert md.endswith("\n")


def test_render_includes_quote_when_present():
    md = render_post_note(_tweet(quoted=QuotedTweet("other", "lo citado")), "d")
    assert "> **Cita a @other:**" in md
    assert "> lo citado" in md


def test_render_omits_quote_and_media_when_absent():
    md = render_post_note(_tweet(), "d")
    assert "Cita a" not in md
    assert "## Media" not in md


def test_render_includes_media_section():
    md = render_post_note(_tweet(media_urls=("https://pbs.twimg.com/a.jpg", "https://v/b.mp4")), "d")
    assert "## Media" in md
    assert "- https://pbs.twimg.com/a.jpg" in md
    assert "- https://v/b.mp4" in md


def test_description_with_colon_stays_valid_yaml():
    md = render_post_note(_tweet(), 'Tema: por qué "esto" importa')
    fm = md.split("---\n")[1]
    assert yaml.safe_load(fm)["description"] == 'Tema: por qué "esto" importa'
