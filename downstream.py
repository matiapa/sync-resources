import shutil
import subprocess
import sys
from pathlib import Path


def git_commit_push(
    brain_path: Path,
    subdir: str,
    message: str,
    push: bool,
    run=subprocess.run,
) -> None:
    run(["git", "add", "--", subdir], cwd=brain_path, check=True)
    run(["git", "commit", "-m", message], cwd=brain_path, check=True)
    if push:
        run(["git", "push"], cwd=brain_path, check=True)


def gbrain_sync(
    brain_path: Path,
    enabled: bool,
    run=subprocess.run,
    which=shutil.which,
) -> bool:
    if not enabled:
        return True
    if which("gbrain") is None:
        print("WARN: gbrain no está instalado; se omite la reindexación.", file=sys.stderr)
        return False
    try:
        run(["gbrain", "import", str(brain_path)], check=True)
    except subprocess.CalledProcessError:
        print("WARN: gbrain import falló.", file=sys.stderr)
        return False
    return True
