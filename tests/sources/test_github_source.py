from pathlib import Path

from config import Config
from models import RepoInfo, Summary
from sources.base import RenderedNote
from sources.github.source import GitHubSource


def _cfg() -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=Path("/brain"), github_subdir="Recursos/Repositorios",
        git_push=True, gbrain_sync=True,
        script_dir=Path("/s"), log_path=Path("/s/sync.log"),
    )


def _repo(full_name, description="desc"):
    owner, name = full_name.split("/")
    return RepoInfo(full_name, owner, name, f"https://github.com/{full_name}", 1, description)


def test_name_and_subdir():
    src = GitHubSource(_cfg(), openai_client=None)
    assert src.name == "GitHub"
    assert src.subdir == "Recursos/Repositorios"


def test_fetch_delegates_to_get_starred():
    repos = [_repo("a/1"), _repo("a/2")]
    src = GitHubSource(_cfg(), openai_client=None, get_starred=lambda: repos)
    assert src.fetch() == repos


def test_stem_replaces_slash():
    src = GitHubSource(_cfg(), openai_client=None)
    assert src.stem(_repo("pallets/flask")) == "pallets-flask"


def test_render_uses_readme_and_matches_notes_render():
    from notes import render_note
    repo = _repo("pallets/flask")
    src = GitHubSource(
        _cfg(), openai_client=None,
        get_readme=lambda fn: "README de " + fn,
        summarize=lambda fn, text: (Summary("resumen", "descripcion"), 42),
    )
    note = src.render(repo)
    assert isinstance(note, RenderedNote)
    assert note.tokens == 42
    assert note.text == render_note(repo, Summary("resumen", "descripcion"))


def test_render_falls_back_to_description_when_no_readme():
    seen = {}

    def fake_summarize(fn, text):
        seen[fn] = text
        return Summary("s", "d"), 0

    src = GitHubSource(
        _cfg(), openai_client=None,
        get_readme=lambda fn: None,
        summarize=fake_summarize,
    )
    src.render(_repo("a/b", description="la descripcion"))
    assert seen["a/b"] == "la descripcion"
