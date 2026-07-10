import base64
import subprocess
from types import SimpleNamespace

from sources.github import client as gh
from models import RepoInfo


def _completed(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_get_starred_repos_parses_jsonl():
    jsonl = (
        '{"full_name":"pallets/flask","owner":"pallets","name":"flask",'
        '"html_url":"https://github.com/pallets/flask","stars":67000,'
        '"description":"micro","pushed_at":"2026-06-01T12:00:00Z"}\n'
        '{"full_name":"psf/requests","owner":"psf","name":"requests",'
        '"html_url":"https://github.com/psf/requests","stars":52000,'
        '"description":null,"pushed_at":null}\n'
        "\n"
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(jsonl)

    repos = gh.get_starred_repos(run=fake_run)
    assert repos == [
        RepoInfo("pallets/flask", "pallets", "flask",
                 "https://github.com/pallets/flask", 67000, "micro",
                 "2026-06-01T12:00:00Z"),
        RepoInfo("psf/requests", "psf", "requests",
                 "https://github.com/psf/requests", 52000, None, None),
    ]
    assert calls[0][:3] == ["gh", "api", "user/starred"]
    assert "--paginate" in calls[0]
    assert gh.GH_JQ in calls[0]


def test_get_readme_decodes_base64():
    content = base64.b64encode("Hola README".encode()).decode()

    def fake_run(cmd, **kwargs):
        return _completed(content)

    assert gh.get_readme("pallets/flask", run=fake_run) == "Hola README"


def test_get_readme_returns_none_when_missing():
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="Not Found")

    assert gh.get_readme("owner/norepo", run=fake_run) is None
