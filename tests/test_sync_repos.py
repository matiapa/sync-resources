from pathlib import Path
from types import SimpleNamespace

from config import Config
from models import RepoInfo, Summary
from sync_repos import process_repos


def _cfg(tmp_path: Path) -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=tmp_path, resources_subdir="res",
        git_push=True, gbrain_sync=True,
        script_dir=tmp_path, log_path=tmp_path / "sync.log",
    )


def _repo(full_name):
    owner, name = full_name.split("/")
    return RepoInfo(full_name, owner, name, f"https://github.com/{full_name}", 1, "desc")


def test_process_respects_limit(tmp_path):
    cfg = _cfg(tmp_path)
    written = []
    deps = SimpleNamespace(
        get_readme=lambda fn: "r",
        summarize=lambda fn, text: (Summary("s", "d"), 10),
        note_exists=lambda rd, fn: False,
        write_note=lambda rd, repo, summary: written.append(repo.full_name),
    )
    repos = [_repo("a/1"), _repo("a/2"), _repo("a/3")]
    stats = process_repos(cfg, repos, deps, limit=2)
    assert stats.created == 2
    assert written == ["a/1", "a/2"]
    assert stats.seen == 2
    assert stats.tokens == 20


def test_process_skips_existing_and_creates_new(tmp_path):
    cfg = _cfg(tmp_path)
    written = []
    existing = {"a/old"}
    deps = SimpleNamespace(
        get_readme=lambda fn: "readme de " + fn,
        summarize=lambda fn, text: (Summary("sum " + fn, "desc " + fn), 7),
        note_exists=lambda rd, fn: fn in existing,
        write_note=lambda rd, repo, summary: written.append(repo.full_name),
    )
    stats = process_repos(cfg, [_repo("a/old"), _repo("a/new")], deps)
    assert stats.seen == 2
    assert stats.skipped == 1
    assert stats.created == 1
    assert written == ["a/new"]
    assert stats.errors == []
    assert stats.tokens == 7


def test_process_records_error_and_continues(tmp_path):
    cfg = _cfg(tmp_path)

    def boom(fn, text):
        raise RuntimeError("openai caído")

    deps = SimpleNamespace(
        get_readme=lambda fn: "x",
        summarize=boom,
        note_exists=lambda rd, fn: False,
        write_note=lambda rd, repo, summary: None,
    )
    stats = process_repos(cfg, [_repo("a/b")], deps)
    assert stats.created == 0
    assert stats.errors == [("a/b", "openai caído")]


def test_process_fallback_to_description_when_no_readme(tmp_path):
    cfg = _cfg(tmp_path)
    seen_text = {}

    def fake_summarize(fn, text):
        seen_text[fn] = text
        return Summary("s", "d"), 0

    deps = SimpleNamespace(
        get_readme=lambda fn: None,
        summarize=fake_summarize,
        note_exists=lambda rd, fn: False,
        write_note=lambda rd, repo, summary: None,
    )
    process_repos(cfg, [_repo("a/b")], deps)
    assert seen_text["a/b"] == "desc"  # description del repo
