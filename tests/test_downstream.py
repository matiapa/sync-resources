import subprocess
from pathlib import Path

from downstream import git_commit_push, gbrain_sync


def test_git_commit_push_runs_add_commit_push():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        return None

    git_commit_push(Path("/brain"), "Recursos externos", "msg", push=True, run=fake_run)
    assert calls[0][0][:2] == ["git", "add"]
    assert "Recursos externos" in calls[0][0]
    assert calls[1][0][:2] == ["git", "commit"]
    assert calls[2][0] == ["git", "push"]
    assert all(cwd == Path("/brain") for _, cwd in calls)


def test_git_commit_push_skips_push_when_false():
    calls = []
    git_commit_push(Path("/b"), "d", "m", push=False, run=lambda cmd, **k: calls.append(cmd))
    assert ["git", "push"] not in calls


def test_gbrain_sync_disabled_is_noop():
    assert gbrain_sync(Path("/b"), enabled=False, run=None, which=lambda _: None) is True


def test_gbrain_sync_missing_binary_returns_false():
    assert gbrain_sync(Path("/b"), enabled=True, run=None, which=lambda _: None) is False


def test_gbrain_sync_runs_import_when_present():
    calls = []
    ok = gbrain_sync(
        Path("/brain"),
        enabled=True,
        run=lambda cmd, **k: calls.append(cmd),
        which=lambda _: "/usr/bin/gbrain",
    )
    assert ok is True
    assert calls[0][0] == "gbrain"
    assert calls[0][1] == "import"
    assert str(Path("/brain")) in [str(x) for x in calls[0]]


def test_gbrain_sync_returns_false_on_failure():
    def boom(cmd, **k):
        raise subprocess.CalledProcessError(1, cmd)

    ok = gbrain_sync(Path("/b"), enabled=True, run=boom, which=lambda _: "/usr/bin/gbrain")
    assert ok is False
