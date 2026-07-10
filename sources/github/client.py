import base64
import json
import subprocess

from models import RepoInfo

GH_JQ = (
    ".[] | {"
    "full_name: .full_name, "
    "owner: .owner.login, "
    "name: .name, "
    "html_url: .html_url, "
    "stars: .stargazers_count, "
    "description: .description, "
    "pushed_at: .pushed_at"
    "}"
)


def get_starred_repos(run=subprocess.run) -> list[RepoInfo]:
    result = run(
        ["gh", "api", "user/starred", "--paginate", "--jq", GH_JQ],
        capture_output=True,
        text=True,
        check=True,
    )
    repos: list[RepoInfo] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        repos.append(
            RepoInfo(
                full_name=obj["full_name"],
                owner=obj["owner"],
                name=obj["name"],
                html_url=obj["html_url"],
                stars=obj["stars"],
                description=obj.get("description"),
                pushed_at=obj.get("pushed_at"),
            )
        )
    return repos


def get_readme(full_name: str, run=subprocess.run) -> str | None:
    try:
        result = run(
            ["gh", "api", f"repos/{full_name}/readme", "--jq", ".content"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    encoded = result.stdout.strip()
    if not encoded:
        return None
    return base64.b64decode(encoded).decode("utf-8", errors="replace")
