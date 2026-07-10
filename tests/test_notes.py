from pathlib import Path

from models import RepoInfo, Summary
from notes import note_exists, note_filename, render_note, write_note


REPO = RepoInfo(
    full_name="pallets/flask",
    owner="pallets",
    name="flask",
    html_url="https://github.com/pallets/flask",
    stars=67000,
    description="The Python micro framework.",
)
SUMMARY = Summary(
    summary="Flask es un micro-framework web para Python.",
    description="Micro-framework web minimalista para Python.",
)


def test_note_filename():
    assert note_filename("pallets/flask") == "pallets-flask.md"


def test_render_note_has_frontmatter_and_body():
    md = render_note(REPO, SUMMARY)
    assert md.startswith("---\n")
    assert "tags:\n  - Recursos/Repositorio\n" in md
    assert "type: Recurso\n" in md
    assert "subtype: Repositorio\n" in md
    assert "source: GitHub\n" in md
    assert "description: Micro-framework web minimalista para Python.\n" in md
    assert "# pallets/flask" in md
    assert "Flask es un micro-framework web para Python." in md
    assert "[pallets](https://github.com/pallets)" in md
    assert "**Estrellas:** 67000" in md
    assert "https://github.com/pallets/flask" in md
    assert md.endswith("\n")


def test_write_and_exists(tmp_path: Path):
    assert note_exists(tmp_path, "pallets/flask") is False
    path = write_note(tmp_path, REPO, SUMMARY)
    assert path == tmp_path / "pallets-flask.md"
    assert path.read_text(encoding="utf-8") == render_note(REPO, SUMMARY)
    assert note_exists(tmp_path, "pallets/flask") is True
