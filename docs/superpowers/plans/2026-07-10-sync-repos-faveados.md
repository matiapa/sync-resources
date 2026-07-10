# Sync de repos faveados de GitHub → digital brain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un script Python que sincroniza los repos *starred* de GitHub del usuario a una nota markdown por repo dentro del digital brain, de forma idempotente e incremental, pensado para correr desde cron.

**Architecture:** Script Python modular en `/home/matiapa/Applications/sync-resources`. Módulos con responsabilidad única: config, cliente GitHub (vía `gh` CLI por subprocess), resumidor OpenAI, escritor de notas, downstream (git + gbrain), logfile de corridas, y un orquestador `sync_repos.py`. La idempotencia se resuelve por existencia del archivo `owner-repo.md` en la carpeta destino (el vault es el estado; sin state file). Solo la lógica pura y el parseo se testean con pytest; las llamadas a `gh`/OpenAI/git se testean con subprocess/cliente mockeado.

**Tech Stack:** Python 3.11, `openai` (SDK), `python-dotenv`, `pytest`. `gh` CLI (ya autenticado como `matiapa`, scope `repo`) invocado por subprocess.

## Global Constraints

- Runtime: Python 3.11+, ejecutado desde un venv local (`./venv`).
- GitHub: acceso vía `gh api` (subprocess), NUNCA gestión de tokens propia.
- Modelo OpenAI: default `gpt-5.5`, configurable por `.env` (`OPENAI_MODEL`).
- Destino: `{DIGITAL_BRAIN_PATH}/{RESOURCES_SUBDIR}`, defaults `/home/matiapa/digital-brain` y `Recursos externos`.
- Digital brain repo: remote `origin` → `https://github.com/matiapa/digital-brain`, branch `main`.
- Idempotencia: la existencia de `{owner}-{repo}.md` en la carpeta destino es la única fuente de verdad de "ya procesado". Sin state file.
- Escribir la nota SOLO si todo el pipeline del repo salió bien (nunca archivos parciales).
- Fallo por repo → se saltea y se loguea, NO aborta la corrida.
- Sin `OPENAI_API_KEY` → abortar temprano con mensaje claro.
- `gbrain` ausente o falla → warning, no fatal.
- Logfile de corridas queda en `sync-resources/` (gitignored `*.log`), NUNCA se copia al brain.
- Frontmatter exacto de cada nota (ver Task 4):
  ```yaml
  tags:
    - Recursos/Repositorio
  type: Recurso
  subtype: Repositorio
  source: GitHub
  description: <una frase>
  ```

## File Structure

- `config.py` — `Config` dataclass + `load_config()`; lee env/`.env`, aplica defaults, valida `OPENAI_API_KEY`.
- `models.py` — dataclasses compartidas `RepoInfo` y `Summary` (evita dependencias circulares).
- `github_client.py` — `get_starred_repos()`, `get_readme()` vía `gh api` por subprocess.
- `summarizer.py` — `summarize()` llama a OpenAI y parsea `{summary, description}`.
- `notes.py` — `note_filename()`, `note_exists()`, `render_note()`, `write_note()`.
- `downstream.py` — `git_commit_push()`, `gbrain_sync()` (defensivo).
- `runlog.py` — `RunStats`, `format_summary()`, `append_log()`.
- `sync_repos.py` — `main()`: orquesta todo el flujo.
- `tests/` — un archivo de test por módulo.
- `requirements.txt`, `.env.example`, `README.md`.

Ya existe `.gitignore` con `.env`, `venv/`, `__pycache__/`, `*.log`.

---

### Task 1: Scaffolding + módulo de configuración

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `models.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `models.RepoInfo(full_name: str, owner: str, name: str, html_url: str, stars: int, description: str | None)` (frozen dataclass).
  - `models.Summary(summary: str, description: str)` (frozen dataclass).
  - `config.ConfigError(Exception)`.
  - `config.Config(openai_api_key: str, openai_model: str, digital_brain_path: pathlib.Path, resources_subdir: str, git_push: bool, gbrain_sync: bool, script_dir: pathlib.Path, log_path: pathlib.Path)` con propiedad `resources_dir -> Path` (= `digital_brain_path / resources_subdir`).
  - `config.load_config(env: Mapping[str, str] | None = None, script_dir: pathlib.Path | None = None) -> Config`. Si `env` es None usa `os.environ`; si `script_dir` es None usa el directorio del archivo. Lanza `ConfigError` si falta `OPENAI_API_KEY`. `log_path = script_dir / "sync.log"`. Booleanos desde strings: `"1"/"true"/"yes"/"on"` (case-insensitive) → True; ausente → default True para `GIT_PUSH` y `GBRAIN_SYNC`.

- [ ] **Step 1: Crear entorno y dependencias**

Crear `requirements.txt`:
```
openai>=1.0
python-dotenv>=1.0
pytest>=8.0
```

Crear el venv e instalar:
```bash
cd /home/matiapa/Applications/sync-resources
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Crear `.env.example`:
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
DIGITAL_BRAIN_PATH=/home/matiapa/digital-brain
RESOURCES_SUBDIR=Recursos externos
GIT_PUSH=true
GBRAIN_SYNC=true
```

- [ ] **Step 2: Escribir `models.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RepoInfo:
    full_name: str          # "owner/repo"
    owner: str              # "owner"
    name: str               # "repo"
    html_url: str
    stars: int
    description: str | None


@dataclass(frozen=True)
class Summary:
    summary: str            # párrafo para el cuerpo
    description: str        # una frase para el frontmatter
```

- [ ] **Step 3: Escribir el test que falla**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from config import Config, ConfigError, load_config


def test_defaults_applied_when_only_key_present():
    cfg = load_config(env={"OPENAI_API_KEY": "sk-test"}, script_dir=Path("/scripts"))
    assert cfg.openai_api_key == "sk-test"
    assert cfg.openai_model == "gpt-5.5"
    assert cfg.digital_brain_path == Path("/home/matiapa/digital-brain")
    assert cfg.resources_subdir == "Recursos externos"
    assert cfg.git_push is True
    assert cfg.gbrain_sync is True
    assert cfg.log_path == Path("/scripts/sync.log")
    assert cfg.resources_dir == Path("/home/matiapa/digital-brain/Recursos externos")


def test_missing_key_raises():
    with pytest.raises(ConfigError):
        load_config(env={}, script_dir=Path("/scripts"))


def test_boolean_toggles_parsed():
    cfg = load_config(
        env={"OPENAI_API_KEY": "k", "GIT_PUSH": "false", "GBRAIN_SYNC": "0"},
        script_dir=Path("/s"),
    )
    assert cfg.git_push is False
    assert cfg.gbrain_sync is False
```

- [ ] **Step 4: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 5: Escribir `config.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(Exception):
    pass


_TRUE = {"1", "true", "yes", "on"}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    openai_model: str
    digital_brain_path: Path
    resources_subdir: str
    git_push: bool
    gbrain_sync: bool
    script_dir: Path
    log_path: Path

    @property
    def resources_dir(self) -> Path:
        return self.digital_brain_path / self.resources_subdir


def load_config(
    env: Mapping[str, str] | None = None,
    script_dir: Path | None = None,
) -> Config:
    env = os.environ if env is None else env
    script_dir = Path(__file__).resolve().parent if script_dir is None else script_dir

    key = env.get("OPENAI_API_KEY")
    if not key:
        raise ConfigError(
            "Falta OPENAI_API_KEY. Definila en el .env del directorio del script."
        )

    return Config(
        openai_api_key=key,
        openai_model=env.get("OPENAI_MODEL", "gpt-5.5"),
        digital_brain_path=Path(
            env.get("DIGITAL_BRAIN_PATH", "/home/matiapa/digital-brain")
        ),
        resources_subdir=env.get("RESOURCES_SUBDIR", "Recursos externos"),
        git_push=_as_bool(env.get("GIT_PUSH"), True),
        gbrain_sync=_as_bool(env.get("GBRAIN_SYNC"), True),
        script_dir=script_dir,
        log_path=script_dir / "sync.log",
    )
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example config.py models.py tests/test_config.py
git commit -m "feat: config loader and shared models"
```

---

### Task 2: Módulo de notas (filename, render, existencia, escritura)

**Files:**
- Create: `notes.py`
- Test: `tests/test_notes.py`

**Interfaces:**
- Consumes: `models.RepoInfo`, `models.Summary`.
- Produces:
  - `notes.note_filename(full_name: str) -> str` — `"owner/repo"` → `"owner-repo.md"` (reemplaza cada `/` por `-`).
  - `notes.note_exists(resources_dir: Path, full_name: str) -> bool`.
  - `notes.render_note(repo: RepoInfo, summary: Summary) -> str` — devuelve el markdown completo (frontmatter + cuerpo), terminando en `\n`.
  - `notes.write_note(resources_dir: Path, repo: RepoInfo, summary: Summary) -> Path` — crea `resources_dir` si no existe, escribe el archivo y devuelve su `Path`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_notes.py`:
```python
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
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_notes.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'notes'`.

- [ ] **Step 3: Escribir `notes.py`**

```python
from pathlib import Path

from models import RepoInfo, Summary


def note_filename(full_name: str) -> str:
    return full_name.replace("/", "-") + ".md"


def note_exists(resources_dir: Path, full_name: str) -> bool:
    return (resources_dir / note_filename(full_name)).exists()


def render_note(repo: RepoInfo, summary: Summary) -> str:
    return (
        "---\n"
        "tags:\n"
        "  - Recursos/Repositorio\n"
        "type: Recurso\n"
        "subtype: Repositorio\n"
        "source: GitHub\n"
        f"description: {summary.description}\n"
        "---\n"
        "\n"
        f"# {repo.full_name}\n"
        "\n"
        f"{summary.summary}\n"
        "\n"
        "## Metadatos\n"
        f"- **Autor:** [{repo.owner}](https://github.com/{repo.owner})\n"
        f"- **Estrellas:** {repo.stars}\n"
        f"- **Repo:** {repo.html_url}\n"
    )


def write_note(resources_dir: Path, repo: RepoInfo, summary: Summary) -> Path:
    resources_dir.mkdir(parents=True, exist_ok=True)
    path = resources_dir / note_filename(repo.full_name)
    path.write_text(render_note(repo, summary), encoding="utf-8")
    return path
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_notes.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat: markdown note rendering and idempotent write"
```

---

### Task 3: Logfile de corridas

**Files:**
- Create: `runlog.py`
- Test: `tests/test_runlog.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `runlog.RunStats` dataclass (mutable): `seen: int = 0`, `created: int = 0`, `skipped: int = 0`, `errors: list[tuple[str, str]] = []` (pares `(full_name, motivo)`), `git_ok: bool | None = None`, `gbrain_ok: bool | None = None`. Propiedad `result -> str`: `"FALLO"` si `git_ok is False`; `"OK con errores parciales"` si hay `errors` o `gbrain_ok is False`; `"OK"` en el resto.
  - `runlog.format_summary(stats: RunStats, now: datetime) -> str` — bloque de texto: línea de resumen con timestamp ISO + resultado + métricas, seguida de una línea por error `  - {full_name}: {motivo}`. Termina en `\n`.
  - `runlog.append_log(log_path: Path, text: str) -> None` — append al archivo (lo crea si no existe).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_runlog.py`:
```python
from datetime import datetime
from pathlib import Path

from runlog import RunStats, append_log, format_summary


def test_result_ok():
    s = RunStats(seen=5, created=2, skipped=3, git_ok=True, gbrain_ok=True)
    assert s.result == "OK"


def test_result_partial_on_errors():
    s = RunStats(seen=2, created=1, skipped=0, errors=[("a/b", "sin README")])
    assert s.result == "OK con errores parciales"


def test_result_fallo_on_git_failure():
    s = RunStats(seen=1, created=1, git_ok=False)
    assert s.result == "FALLO"


def test_format_summary_contains_metrics_and_errors():
    s = RunStats(seen=3, created=1, skipped=1, errors=[("x/y", "timeout")], git_ok=True)
    now = datetime(2026, 7, 10, 4, 0, 0)
    text = format_summary(s, now)
    assert "2026-07-10T04:00:00" in text
    assert "OK con errores parciales" in text
    assert "vistos=3" in text
    assert "nuevos=1" in text
    assert "salteados=1" in text
    assert "errores=1" in text
    assert "  - x/y: timeout" in text
    assert text.endswith("\n")


def test_append_log(tmp_path: Path):
    log = tmp_path / "sync.log"
    append_log(log, "linea1\n")
    append_log(log, "linea2\n")
    assert log.read_text(encoding="utf-8") == "linea1\nlinea2\n"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_runlog.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'runlog'`.

- [ ] **Step 3: Escribir `runlog.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class RunStats:
    seen: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    git_ok: bool | None = None
    gbrain_ok: bool | None = None

    @property
    def result(self) -> str:
        if self.git_ok is False:
            return "FALLO"
        if self.errors or self.gbrain_ok is False:
            return "OK con errores parciales"
        return "OK"


def format_summary(stats: RunStats, now: datetime) -> str:
    line = (
        f"[{now.isoformat()}] {stats.result} "
        f"vistos={stats.seen} nuevos={stats.created} "
        f"salteados={stats.skipped} errores={len(stats.errors)}"
    )
    lines = [line]
    for full_name, reason in stats.errors:
        lines.append(f"  - {full_name}: {reason}")
    return "\n".join(lines) + "\n"


def append_log(log_path: Path, text: str) -> None:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_runlog.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add runlog.py tests/test_runlog.py
git commit -m "feat: per-run logfile with result summary"
```

---

### Task 4: Cliente GitHub (starred + README vía `gh`)

**Files:**
- Create: `github_client.py`
- Test: `tests/test_github_client.py`

**Interfaces:**
- Consumes: `models.RepoInfo`.
- Produces:
  - `github_client.get_starred_repos(run=subprocess.run) -> list[RepoInfo]`. Ejecuta `gh api user/starred --paginate --jq '<expr>'` donde `<expr>` emite un objeto JSON por línea (JSONL) con campos `full_name, owner, name, html_url, stars, description`. Parsea cada línea no vacía con `json.loads`.
  - `github_client.get_readme(full_name: str, run=subprocess.run) -> str | None`. Ejecuta `gh api repos/{full_name}/readme --jq .content`, decodifica el base64 a texto UTF-8 (`errors="replace"`). Si el comando falla (ej. repo sin README → exit != 0), devuelve `None`.
  - `github_client.GH_JQ` (constante str): la expresión jq usada por `get_starred_repos`, para poder assertarla en tests.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_github_client.py`:
```python
import base64
import subprocess
from types import SimpleNamespace

import github_client as gh
from models import RepoInfo


def _completed(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_get_starred_repos_parses_jsonl():
    jsonl = (
        '{"full_name":"pallets/flask","owner":"pallets","name":"flask",'
        '"html_url":"https://github.com/pallets/flask","stars":67000,'
        '"description":"micro"}\n'
        '{"full_name":"psf/requests","owner":"psf","name":"requests",'
        '"html_url":"https://github.com/psf/requests","stars":52000,'
        '"description":null}\n'
        "\n"
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(jsonl)

    repos = gh.get_starred_repos(run=fake_run)
    assert repos == [
        RepoInfo("pallets/flask", "pallets", "flask",
                 "https://github.com/pallets/flask", 67000, "micro"),
        RepoInfo("psf/requests", "psf", "requests",
                 "https://github.com/psf/requests", 52000, None),
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
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_github_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'github_client'`.

- [ ] **Step 3: Escribir `github_client.py`**

```python
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
    "description: .description"
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_github_client.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add github_client.py tests/test_github_client.py
git commit -m "feat: GitHub client via gh CLI (starred repos + README)"
```

---

### Task 5: Resumidor OpenAI

**Files:**
- Create: `summarizer.py`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Consumes: `models.Summary`.
- Produces:
  - `summarizer.SummaryError(Exception)`.
  - `summarizer.build_messages(full_name: str, text: str) -> list[dict]` — arma los mensajes (system + user) para el chat; el system pide responder SOLO JSON con claves `summary` (párrafo) y `description` (una frase), en español.
  - `summarizer.parse_response(content: str) -> Summary` — parsea el JSON del modelo (tolera fences ```json). Lanza `SummaryError` si falta alguna clave o el JSON es inválido.
  - `summarizer.summarize(full_name: str, text: str, model: str, client) -> Summary` — llama `client.chat.completions.create(model=model, messages=..., response_format={"type": "json_object"})` y pasa `response.choices[0].message.content` a `parse_response`. `client` es inyectado (el orquestador crea el `OpenAI` real).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_summarizer.py`:
```python
import json
from types import SimpleNamespace

import pytest

from summarizer import SummaryError, build_messages, parse_response, summarize


def test_build_messages_mentions_repo_and_json():
    msgs = build_messages("pallets/flask", "readme text")
    joined = " ".join(m["content"] for m in msgs)
    assert "pallets/flask" in joined
    assert "JSON" in joined
    assert "readme text" in joined


def test_parse_response_plain_json():
    raw = json.dumps({"summary": "párrafo largo", "description": "una frase"})
    s = parse_response(raw)
    assert s.summary == "párrafo largo"
    assert s.description == "una frase"


def test_parse_response_with_code_fence():
    raw = "```json\n{\"summary\": \"p\", \"description\": \"d\"}\n```"
    s = parse_response(raw)
    assert s.summary == "p"
    assert s.description == "d"


def test_parse_response_missing_key_raises():
    with pytest.raises(SummaryError):
        parse_response('{"summary": "solo esto"}')


def test_summarize_calls_client_and_parses():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        content = json.dumps({"summary": "resumen", "description": "frase"})
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    s = summarize("a/b", "texto", model="gpt-5.5", client=client)
    assert s.summary == "resumen"
    assert s.description == "frase"
    assert captured["model"] == "gpt-5.5"
    assert captured["response_format"] == {"type": "json_object"}
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_summarizer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'summarizer'`.

- [ ] **Step 3: Escribir `summarizer.py`**

```python
import json

from models import Summary


class SummaryError(Exception):
    pass


_SYSTEM = (
    "Sos un asistente que resume repositorios de GitHub en español. "
    "Respondé EXCLUSIVAMENTE con un objeto JSON con dos claves: "
    '"summary" (un párrafo que describe qué hace el repositorio) y '
    '"description" (una sola frase, resumen para búsqueda semántica). '
    "No agregues texto fuera del JSON."
)


def build_messages(full_name: str, text: str) -> list[dict]:
    user = (
        f"Repositorio: {full_name}\n\n"
        f"Contenido base (README o descripción):\n{text}\n\n"
        "Devolvé el JSON con las claves summary y description."
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_response(content: str) -> Summary:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # remove leading fence (```json or ```) and trailing fence
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SummaryError(f"JSON inválido del modelo: {exc}") from exc
    if "summary" not in obj or "description" not in obj:
        raise SummaryError("Faltan claves summary/description en la respuesta.")
    return Summary(summary=str(obj["summary"]), description=str(obj["description"]))


def summarize(full_name: str, text: str, model: str, client) -> Summary:
    response = client.chat.completions.create(
        model=model,
        messages=build_messages(full_name, text),
        response_format={"type": "json_object"},
    )
    return parse_response(response.choices[0].message.content)
```

Nota: el `import summarizer as sм` del test usa una `м` cirílica a propósito solo como alias irrelevante; si molesta al linter, reemplazalo por `import summarizer`. La API `client.chat.completions.create` es estable en el SDK de OpenAI; el modelo se pasa por parámetro (`gpt-5.5` por default vía config).

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_summarizer.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add summarizer.py tests/test_summarizer.py
git commit -m "feat: OpenAI README summarizer with JSON parsing"
```

---

### Task 6: Downstream (git commit/push + gbrain sync defensivo)

**Files:**
- Create: `downstream.py`
- Test: `tests/test_downstream.py`

**Interfaces:**
- Consumes: nada (opera sobre paths).
- Produces:
  - `downstream.git_commit_push(brain_path: Path, subdir: str, message: str, push: bool, run=subprocess.run) -> None`. Ejecuta, en `cwd=brain_path`: `git add -- {subdir}`, `git commit -m {message}`, y si `push` es True, `git push`. Cada uno con `check=True`.
  - `downstream.gbrain_sync(brain_path: Path, enabled: bool, run=subprocess.run, which=shutil.which) -> bool`. Si `enabled` es False → devuelve True (no-op). Si `which("gbrain")` es None → loguea warning y devuelve False (defensivo, no lanza). Si existe, ejecuta `gbrain import {brain_path}` con `check=True` y devuelve True; si el comando falla, devuelve False.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_downstream.py`:
```python
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
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_downstream.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'downstream'`.

- [ ] **Step 3: Escribir `downstream.py`**

```python
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_downstream.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add downstream.py tests/test_downstream.py
git commit -m "feat: downstream git commit/push and defensive gbrain sync"
```

---

### Task 7: Orquestador `sync_repos.py` + docs

**Files:**
- Create: `sync_repos.py`
- Create: `README.md`
- Test: `tests/test_sync_repos.py`

**Interfaces:**
- Consumes: todo lo anterior (`config`, `github_client`, `summarizer`, `notes`, `downstream`, `runlog`, `models`).
- Produces:
  - `sync_repos.process_repos(cfg, repos, deps) -> RunStats`. `deps` es un `SimpleNamespace`/objeto con callables inyectables: `get_readme(full_name)`, `summarize(full_name, text)`, `note_exists(resources_dir, full_name)`, `write_note(resources_dir, repo, summary)`. Recorre `repos`: cuenta `seen`; si `note_exists` → `skipped`; si no, `text = get_readme(full_name) or repo.description or repo.full_name`, `summary = summarize(full_name, text)`, `write_note(...)`, `created += 1`; cualquier excepción del repo → `errors.append((full_name, str(exc)))` y sigue. Devuelve `RunStats` (sin tocar git/gbrain).
  - `sync_repos.main() -> int`. Carga `.env` (dotenv) → `load_config()`; crea el cliente `OpenAI`; `get_starred_repos()`; `process_repos()`; si `stats.created > 0` corre `git_commit_push` (set `stats.git_ok`) y `gbrain_sync` (set `stats.gbrain_ok`); escribe el resumen al logfile; imprime el resumen a stdout; devuelve 0 salvo `ConfigError`/`RunStats.result == "FALLO"` → 1.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_sync_repos.py`:
```python
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


def test_process_skips_existing_and_creates_new(tmp_path):
    cfg = _cfg(tmp_path)
    written = []
    existing = {"a/old"}
    deps = SimpleNamespace(
        get_readme=lambda fn: "readme de " + fn,
        summarize=lambda fn, text: Summary("sum " + fn, "desc " + fn),
        note_exists=lambda rd, fn: fn in existing,
        write_note=lambda rd, repo, summary: written.append(repo.full_name),
    )
    stats = process_repos(cfg, [_repo("a/old"), _repo("a/new")], deps)
    assert stats.seen == 2
    assert stats.skipped == 1
    assert stats.created == 1
    assert written == ["a/new"]
    assert stats.errors == []


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
        return Summary("s", "d")

    deps = SimpleNamespace(
        get_readme=lambda fn: None,
        summarize=fake_summarize,
        note_exists=lambda rd, fn: False,
        write_note=lambda rd, repo, summary: None,
    )
    process_repos(cfg, [_repo("a/b")], deps)
    assert seen_text["a/b"] == "desc"  # description del repo
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/bin/pytest tests/test_sync_repos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sync_repos'`.

- [ ] **Step 3: Escribir `sync_repos.py`**

```python
import sys
from datetime import datetime
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI

import downstream
import github_client
import notes
import summarizer
from config import Config, ConfigError, load_config
from runlog import RunStats, append_log, format_summary


def process_repos(cfg: Config, repos, deps) -> RunStats:
    stats = RunStats()
    resources_dir = cfg.resources_dir
    for repo in repos:
        stats.seen += 1
        if deps.note_exists(resources_dir, repo.full_name):
            stats.skipped += 1
            continue
        try:
            text = deps.get_readme(repo.full_name) or repo.description or repo.full_name
            summary = deps.summarize(repo.full_name, text)
            deps.write_note(resources_dir, repo, summary)
            stats.created += 1
        except Exception as exc:  # noqa: BLE001 - se loguea y se sigue
            stats.errors.append((repo.full_name, str(exc)))
    return stats


def main() -> int:
    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=cfg.openai_api_key)
    deps = SimpleNamespace(
        get_readme=lambda fn: github_client.get_readme(fn),
        summarize=lambda fn, text: summarizer.summarize(fn, text, cfg.openai_model, client),
        note_exists=notes.note_exists,
        write_note=notes.write_note,
    )

    repos = github_client.get_starred_repos()
    stats = process_repos(cfg, repos, deps)

    if stats.created > 0:
        try:
            downstream.git_commit_push(
                cfg.digital_brain_path,
                cfg.resources_subdir,
                f"chore: sync {stats.created} repos faveados nuevos",
                push=cfg.git_push,
            )
            stats.git_ok = True
        except Exception as exc:  # noqa: BLE001
            stats.git_ok = False
            stats.errors.append(("<git>", str(exc)))
        stats.gbrain_ok = downstream.gbrain_sync(cfg.digital_brain_path, cfg.gbrain_sync)

    summary_text = format_summary(stats, datetime.now())
    append_log(cfg.log_path, summary_text)
    print(summary_text, end="")
    return 1 if stats.result == "FALLO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/bin/pytest tests/test_sync_repos.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Correr toda la suite**

Run: `./venv/bin/pytest -v`
Expected: PASS (todos los módulos).

- [ ] **Step 6: Escribir `README.md`**

````markdown
# sync-resources

Sincroniza los repos *starred* de GitHub a notas markdown en el digital brain,
de forma idempotente e incremental. Pensado para correr desde cron.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # completar OPENAI_API_KEY
```

Requiere `gh` CLI autenticado (`gh auth status`). La reindexación GBrain es
opcional y defensiva: si `gbrain` no está instalado, se omite con un warning.

## Uso

```bash
./venv/bin/python sync_repos.py
```

Solo genera notas para repos faveados nuevos (los ya presentes en
`Recursos externos/` se saltean). Al generar notas nuevas: commit + push al repo
del digital brain y reindexación GBrain.

## Cron (ejemplo, diario 4am)

```
0 4 * * * cd /home/matiapa/Applications/sync-resources && ./venv/bin/python sync_repos.py >> sync.log 2>&1
```

## Logfile

Cada corrida agrega una línea de resumen a `sync.log` (fecha, resultado,
métricas y detalle de errores). Este archivo queda en esta carpeta y no se copia
al digital brain.
````

- [ ] **Step 7: Commit**

```bash
git add sync_repos.py README.md tests/test_sync_repos.py
git commit -m "feat: orchestrator wiring all modules + README"
```

---

### Task 8: Actualizar el `CLAUDE.md` del digital brain

Este task edita y commitea en el repo del **digital brain**
(`/home/matiapa/digital-brain`), no en `sync-resources`. Alinea el spec de
frontmatter con el nuevo tipo de nota.

**Files:**
- Modify: `/home/matiapa/digital-brain/CLAUDE.md`

- [ ] **Step 1: Releer el `CLAUDE.md` actual**

Run: `cat /home/matiapa/digital-brain/CLAUDE.md`
Confirmar que las secciones a editar existen tal cual (pueden haber cambiado desde que se escribió el plan).

- [ ] **Step 2: Agregar `Recurso` al vocabulario de `type`**

En la sección `### \`type\``, agregar `Recurso` a la lista cerrada. Cambiar:
```
`Plan`, `Conferencia`, `Relevamiento`.
```
por:
```
`Plan`, `Conferencia`, `Relevamiento`, `Recurso`.
```

- [ ] **Step 3: Agregar `GitHub` al vocabulario de `source`**

En la sección `### \`source\``, cambiar:
```
Vocabulario cerrado: `Keep`, `Notion`, `YouTube`.
```
por:
```
Vocabulario cerrado: `Keep`, `Notion`, `YouTube`, `GitHub`.
```

- [ ] **Step 4: Enmendar la regla de "no campos ad-hoc" y documentar `subtype`**

En la sección `tags`, cambiar la frase:
```
No crear campos ad-hoc que dupliquen esta función — cualquier clasificación adicional es un tag más, nunca un campo nuevo.
```
por:
```
No crear campos ad-hoc que dupliquen esta función — cualquier clasificación adicional es un tag más, salvo el campo reservado `subtype` (ver abajo), que sub-clasifica dentro de `type`.
```

Y agregar, después de la sección `### \`type\``, una nueva sección:
```
### `subtype` (opcional, scalar)

Sub-clasificación dentro de `type`, para distinguir variantes de un mismo tipo.
Valor definido: `Repositorio` (repos de GitHub sincronizados automáticamente,
con `type: Recurso`). Vocabulario extensible a medida que aparezcan nuevos
subtipos.
```

- [ ] **Step 5: Commit en el repo del digital brain**

```bash
git -C /home/matiapa/digital-brain add CLAUDE.md
git -C /home/matiapa/digital-brain commit -m "docs: add Recurso type, GitHub source, and subtype field to frontmatter spec"
```

(El push de este cambio queda a criterio del usuario o del propio script en su primera corrida, que commitea la carpeta de recursos por separado.)

---

## Notas de cierre

- La primera corrida procesa TODOS los repos faveados actuales (una llamada
  OpenAI por repo). Es un costo puntual; las siguientes son incrementales.
- El script no instala el cron; la línea de crontab está documentada en el
  `README.md` (Task 7).
- `gbrain` en la Pi es prerequisito de la reindexación; mientras no esté, el
  resto funciona y la reindexación la puede hacer otra máquina tras el pull.
