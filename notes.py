import json
from pathlib import Path

from models import RepoInfo, Summary


def _yaml_scalar(value: str) -> str:
    """Emit a value as a YAML-safe double-quoted scalar.

    The description comes from an LLM and may contain ``: ``, quotes or
    newlines, any of which break an unquoted YAML scalar. A JSON string is a
    valid YAML double-quoted flow scalar, so json.dumps gives correct escaping.
    ``ensure_ascii=False`` keeps Spanish accents readable in the file.
    """
    return json.dumps(value, ensure_ascii=False)


def note_filename(full_name: str) -> str:
    return full_name.replace("/", "-") + ".md"


def note_exists(resources_dir: Path, full_name: str) -> bool:
    return (resources_dir / note_filename(full_name)).exists()


def _last_update(pushed_at: str | None) -> str:
    """Fecha (YYYY-MM-DD) del último push, o 'desconocida'.

    Se guarda la fecha absoluta (no un 'hace X meses') porque la nota se
    escribe una sola vez y nunca se actualiza: un valor relativo quedaría
    congelado y engañoso. El lector puede computar la antigüedad al momento
    de leer.
    """
    if not pushed_at:
        return "desconocida"
    return pushed_at[:10]


def render_note(repo: RepoInfo, summary: Summary) -> str:
    return (
        "---\n"
        "tags:\n"
        "  - Recursos/Repositorio\n"
        "type: Recurso\n"
        "subtype: Repositorio\n"
        "source: GitHub\n"
        f"description: {_yaml_scalar(summary.description)}\n"
        "---\n"
        "\n"
        f"# {repo.full_name}\n"
        "\n"
        f"{summary.summary}\n"
        "\n"
        "## Metadatos\n"
        f"- **Autor:** [{repo.owner}](https://github.com/{repo.owner})\n"
        f"- **Estrellas:** {repo.stars}\n"
        f"- **Última actualización:** {_last_update(repo.pushed_at)}\n"
        f"- **Repo:** {repo.html_url}\n"
    )


def write_note(resources_dir: Path, repo: RepoInfo, summary: Summary) -> Path:
    resources_dir.mkdir(parents=True, exist_ok=True)
    path = resources_dir / note_filename(repo.full_name)
    path.write_text(render_note(repo, summary), encoding="utf-8")
    return path
