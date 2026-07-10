# Refactor a la abstracción `Source` (Plan 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-expresar el sync de repos de GitHub como una implementación de una abstracción `Source` + driver genérico, sin cambiar el comportamiento observable (las notas generadas son idénticas).

**Architecture:** Se introduce `sources/base.py` (`Source` Protocol + `RenderedNote`), un driver genérico `pipeline.py` (`process_source`) que itera items, saltea los ya presentes por existencia de archivo, y escribe notas; y un entrypoint único `sync.py` que registra y corre las fuentes. La fuente GitHub existente pasa a `sources/github/` reusando `notes.py`, `summarizer.py` y `models.py` sin cambios. El viejo `sync_repos.py` se elimina al final.

**Tech Stack:** Python 3.11+, pytest, OpenAI SDK, `gh` CLI, tqdm, python-dotenv.

## Global Constraints

- Python 3.11+ (usa `str | None`, `dataclass(frozen=True)`).
- **Patrón de inyección de dependencias:** funciones/clases que tocan red o servicios externos reciben el ejecutor/cliente como parámetro (ej. `run=subprocess.run`, cliente OpenAI, callables de GitHub) para poder testear sin red. Seguir el estilo existente.
- **TDD estricto:** test que falla → implementación mínima → test verde → commit.
- **Sin cambio de comportamiento en GitHub:** una corrida de `sync.py --source github` debe producir exactamente las mismas notas (mismo filename, mismo contenido) que producía `sync_repos.py`.
- **Tests existentes de `notes.py` deben seguir verdes sin modificarse** (`tests/test_notes.py`, `tests/test_runlog.py`).
- Barra de progreso tqdm con `disable=None` (se apaga sola en no-TTY como cron).
- Tests corren con `./venv/bin/python -m pytest`.
- Todo commit termina con:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

## File Structure (estado final del Plan 1)

```
sync.py                 # NUEVO entrypoint: registra y corre fuentes; --source, --limit
pipeline.py             # NUEVO driver genérico: process_source()
config.py               # MODIF: github_subdir por-fuente; se quita resources_dir
downstream.py           # sin cambios
runlog.py               # sin cambios (etiqueta por-fuente queda para Plan 2)
notes.py                # sin cambios (render de nota GitHub)
summarizer.py           # sin cambios
models.py               # sin cambios
sources/
  __init__.py           # NUEVO (marcador de paquete)
  base.py               # NUEVO: Source (Protocol), RenderedNote
  github/
    __init__.py         # NUEVO
    client.py           # MOVIDO desde github_client.py (contenido idéntico)
    source.py           # NUEVO: GitHubSource
sync_repos.py           # ELIMINADO en Task 6
github_client.py        # ELIMINADO (movido) en Task 6
tests/
  test_pipeline.py      # NUEVO
  sources/
    __init__.py         # NUEVO
    test_github_source.py  # NUEVO
  test_config.py        # MODIF (nueva forma de Config)
  test_github_client.py # MODIF (import path) en Task 6
  test_sync_repos.py    # ELIMINADO en Task 6
```

---

### Task 1: `sources/base.py` — interfaz `Source` y `RenderedNote`

**Files:**
- Create: `sources/__init__.py`
- Create: `sources/base.py`
- Create: `tests/sources/__init__.py`
- Test: `tests/sources/test_base.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `RenderedNote(text: str, tokens: int = 0)` — dataclass frozen.
  - `Source` — Protocol con atributos `name: str`, `subdir: str` y métodos `fetch() -> list`, `stem(item) -> str`, `render(item) -> RenderedNote`.

- [ ] **Step 1: Write the failing test**

`tests/sources/__init__.py` → archivo vacío.

`tests/sources/test_base.py`:
```python
from sources.base import RenderedNote


def test_rendered_note_defaults_tokens_to_zero():
    note = RenderedNote(text="hola")
    assert note.text == "hola"
    assert note.tokens == 0


def test_rendered_note_is_frozen():
    note = RenderedNote(text="x", tokens=5)
    try:
        note.text = "y"
    except Exception as exc:
        assert "frozen" in type(exc).__name__.lower() or "cannot assign" in str(exc).lower()
    else:
        raise AssertionError("RenderedNote debería ser inmutable")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/test_base.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sources'`.

- [ ] **Step 3: Write minimal implementation**

`sources/__init__.py` → archivo vacío.

`sources/base.py`:
```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RenderedNote:
    """Nota lista para escribir en disco.

    ``tokens`` es el consumo OpenAI usado para renderizarla (0 si la fuente
    no usa LLM).
    """
    text: str
    tokens: int = 0


@runtime_checkable
class Source(Protocol):
    """Una fuente de recursos a sincronizar (GitHub, X, ...).

    El driver genérico (``pipeline.process_source``) solo depende de esta
    interfaz: obtiene los items, deriva un ID estable por item para el nombre
    de archivo, y renderiza la nota.
    """
    name: str        # etiqueta legible: "GitHub", "X"
    subdir: str      # subcarpeta destino dentro del digital brain

    def fetch(self) -> list:
        """Trae los items de la fuente (repos, tweets, ...)."""
        ...

    def stem(self, item) -> str:
        """ID estable del item, sin extensión: es el nombre de archivo."""
        ...

    def render(self, item) -> "RenderedNote":
        """Arma la nota del item (incluye llamadas a LLM si la fuente las usa)."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/test_base.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/__init__.py sources/base.py tests/sources/__init__.py tests/sources/test_base.py
git commit -m "feat: add Source protocol and RenderedNote

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `pipeline.py` — driver genérico `process_source`

**Files:**
- Create: `pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `config.Config` (usa `digital_brain_path`), `runlog.RunStats`, `sources.base.RenderedNote`.
- Produces:
  - `process_source(cfg: Config, source, limit: int | None = None, progress=None) -> RunStats`
    - Itera `source.fetch()`; por item incrementa `seen`; si existe `{brain}/{source.subdir}/{source.stem(item)}.md` incrementa `skipped` y saltea; si no, llama `source.render(item)`, escribe el archivo, suma `note.tokens`, incrementa `created`. Excepciones de `render` → `errors.append((source.stem(item), str(exc)))` y sigue. `limit` corta cuando `created >= limit`. `progress` (si se pasa) envuelve el iterable.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from config import Config
from pipeline import process_source
from sources.base import RenderedNote


def _cfg(tmp_path: Path) -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=tmp_path, github_subdir="res",
        git_push=True, gbrain_sync=True,
        script_dir=tmp_path, log_path=tmp_path / "sync.log",
    )


@dataclass
class FakeSource:
    """Source de prueba: items son strings usados como stem y cuerpo."""
    items: list
    subdir: str = "res"
    name: str = "Fake"
    render_error: str | None = None
    tokens: int = 3

    def fetch(self):
        return self.items

    def stem(self, item):
        return item

    def render(self, item):
        if self.render_error is not None:
            raise RuntimeError(self.render_error)
        return RenderedNote(text=f"cuerpo de {item}", tokens=self.tokens)


def test_creates_notes_for_new_items(tmp_path):
    cfg = _cfg(tmp_path)
    src = FakeSource(items=["a", "b"])
    stats = process_source(cfg, src)
    assert stats.seen == 2
    assert stats.created == 2
    assert stats.skipped == 0
    assert stats.tokens == 6
    assert (tmp_path / "res" / "a.md").read_text(encoding="utf-8") == "cuerpo de a"
    assert (tmp_path / "res" / "b.md").exists()


def test_skips_existing_notes(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "res").mkdir()
    (tmp_path / "res" / "a.md").write_text("viejo", encoding="utf-8")
    src = FakeSource(items=["a", "b"])
    stats = process_source(cfg, src)
    assert stats.seen == 2
    assert stats.skipped == 1
    assert stats.created == 1
    # No se pisa la nota existente.
    assert (tmp_path / "res" / "a.md").read_text(encoding="utf-8") == "viejo"


def test_respects_limit(tmp_path):
    cfg = _cfg(tmp_path)
    src = FakeSource(items=["a", "b", "c"])
    stats = process_source(cfg, src, limit=2)
    assert stats.created == 2
    assert stats.seen == 2
    assert not (tmp_path / "res" / "c.md").exists()


def test_uses_progress_wrapper(tmp_path):
    cfg = _cfg(tmp_path)
    wrapped = []

    def progress(iterable):
        for item in iterable:
            wrapped.append(item)
            yield item

    stats = process_source(cfg, FakeSource(items=["a", "b"]), progress=progress)
    assert wrapped == ["a", "b"]
    assert stats.created == 2


def test_records_error_and_continues(tmp_path):
    cfg = _cfg(tmp_path)
    src = FakeSource(items=["a"], render_error="openai caído")
    stats = process_source(cfg, src)
    assert stats.created == 0
    assert stats.errors == [("a", "openai caído")]
    assert not (tmp_path / "res" / "a.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'pipeline'`.

- [ ] **Step 3: Write minimal implementation**

`pipeline.py`:
```python
from config import Config
from runlog import RunStats


def process_source(cfg: Config, source, limit=None, progress=None) -> RunStats:
    """Sincroniza una fuente: escribe una nota por item nuevo.

    La fuente de verdad de "ya procesado" es la existencia del archivo de nota;
    los items ya presentes se saltean sin llamar a ``render`` (así no se gasta
    en red ni en OpenAI). Los errores de ``render`` se registran y no cortan la
    corrida. Nunca se escriben archivos parciales.
    """
    stats = RunStats()
    resources_dir = cfg.digital_brain_path / source.subdir
    items = source.fetch()
    iterable = items if progress is None else progress(items)
    for item in iterable:
        if limit is not None and stats.created >= limit:
            break
        stats.seen += 1
        path = resources_dir / (source.stem(item) + ".md")
        if path.exists():
            stats.skipped += 1
            continue
        try:
            note = source.render(item)
            resources_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(note.text, encoding="utf-8")
            stats.tokens += note.tokens
            stats.created += 1
        except Exception as exc:  # noqa: BLE001 - se loguea y se sigue
            stats.errors.append((source.stem(item), str(exc)))
    return stats
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS (5 passed).

Nota: este test construye `Config` con `github_subdir=...`, que aún no existe (se agrega en Task 3). **Ejecutar Task 3 antes de correr la suite completa.** Si querés verificar Task 2 de inmediato, corré solo `tests/test_pipeline.py` después de Task 3. Para mantener el orden TDD limpio, se recomienda hacer Task 3 inmediatamente después de escribir este archivo. (El test de arriba ya usa `github_subdir`; si corrés antes de Task 3 fallará al construir `Config`.)

- [ ] **Step 5: Commit**

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "feat: add generic process_source pipeline driver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Config por-fuente (`github_subdir`)

**Files:**
- Modify: `config.py`
- Modify: `tests/test_config.py`
- Modify: `sync_repos.py` (para seguir verde con la nueva Config)
- Modify: `tests/test_sync_repos.py` (helper `_cfg`)

**Interfaces:**
- Consumes: nada nuevo.
- Produces:
  - `Config` con campos: `openai_api_key, openai_model, digital_brain_path, github_subdir, git_push, gbrain_sync, script_dir, log_path`. **Se elimina** `resources_subdir` y la property `resources_dir`.
  - `load_config` lee `GITHUB_SUBDIR` (default `"Recursos/Repositorios"`).

- [ ] **Step 1: Update the failing tests**

En `tests/test_config.py`, reemplazar el cuerpo de `test_defaults_applied_when_only_key_present` y `test_boolean_toggles_parsed` por:
```python
def test_defaults_applied_when_only_key_present():
    cfg = load_config(env={"OPENAI_API_KEY": "sk-test"}, script_dir=Path("/scripts"))
    assert cfg.openai_api_key == "sk-test"
    assert cfg.openai_model == "gpt-5.5"
    assert cfg.digital_brain_path == Path("/home/matiapa/digital-brain")
    assert cfg.github_subdir == "Recursos/Repositorios"
    assert cfg.git_push is True
    assert cfg.gbrain_sync is True
    assert cfg.log_path == Path("/scripts/sync.log")


def test_github_subdir_overridden_from_env():
    cfg = load_config(
        env={"OPENAI_API_KEY": "k", "GITHUB_SUBDIR": "Recursos/Repos"},
        script_dir=Path("/s"),
    )
    assert cfg.github_subdir == "Recursos/Repos"
```
(Dejar `test_missing_key_raises` y `test_boolean_toggles_parsed` como están — no referencian `resources_subdir`.)

En `tests/test_sync_repos.py`, en el helper `_cfg`, cambiar `resources_subdir="res"` por `github_subdir="res"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError`/`TypeError`: `Config` no tiene `github_subdir`).

- [ ] **Step 3: Implement**

En `config.py`, reemplazar el campo `resources_subdir` y la property `resources_dir`:

```python
@dataclass(frozen=True)
class Config:
    openai_api_key: str
    openai_model: str
    digital_brain_path: Path
    github_subdir: str
    git_push: bool
    gbrain_sync: bool
    script_dir: Path
    log_path: Path
```
(Quitar por completo el bloque `@property def resources_dir`.)

En `load_config`, reemplazar la línea de `resources_subdir` por:
```python
        github_subdir=env.get("GITHUB_SUBDIR", "Recursos/Repositorios"),
```

En `sync_repos.py`, dentro de `process_repos`, cambiar:
```python
    resources_dir = cfg.resources_dir
```
por:
```python
    resources_dir = cfg.digital_brain_path / cfg.github_subdir
```
y en `main`, en la llamada a `downstream.git_commit_push`, cambiar `cfg.resources_subdir` por `cfg.github_subdir`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_config.py tests/test_sync_repos.py tests/test_pipeline.py -v`
Expected: PASS (todos verdes; `test_pipeline` ahora construye `Config` correctamente).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py sync_repos.py tests/test_sync_repos.py
git commit -m "refactor: make resources subdir per-source (github_subdir)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `GitHubSource` — fuente GitHub sobre la abstracción

**Files:**
- Create: `sources/github/__init__.py`
- Create: `sources/github/source.py`
- Test: `tests/sources/test_github_source.py`

**Interfaces:**
- Consumes: `sources.base.RenderedNote`; `github_client` (root, aún sin mover); `notes.render_note`; `summarizer.summarize`; `config.Config`; `models.RepoInfo`.
- Produces:
  - `GitHubSource(cfg, openai_client, *, get_starred=None, get_readme=None, summarize=None)` con:
    - `name = "GitHub"`, `subdir = cfg.github_subdir`.
    - `fetch() -> list[RepoInfo]`.
    - `stem(repo) -> str` = `repo.full_name.replace("/", "-")`.
    - `render(repo) -> RenderedNote` = README (o `description`/`full_name` como fallback) → `summarize` → `notes.render_note` → `RenderedNote(md, tokens)`.
    - Los kwargs `get_starred/get_readme/summarize` permiten inyectar en tests; si son `None`, usan las implementaciones reales.

- [ ] **Step 1: Write the failing test**

`tests/sources/test_github_source.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/test_github_source.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sources.github'`.

- [ ] **Step 3: Write minimal implementation**

`sources/github/__init__.py` → archivo vacío.

`sources/github/source.py`:
```python
import github_client
import notes
import summarizer
from sources.base import RenderedNote


class GitHubSource:
    """Fuente de repos *starred* de GitHub → notas markdown.

    El cuerpo de la nota es un resumen del README generado por LLM (comportamiento
    heredado de ``sync_repos``). Ver ``notes.render_note`` para el formato.
    """
    name = "GitHub"

    def __init__(self, cfg, openai_client, *, get_starred=None, get_readme=None, summarize=None):
        self.subdir = cfg.github_subdir
        self._get_starred = get_starred or github_client.get_starred_repos
        self._get_readme = get_readme or github_client.get_readme
        self._summarize = summarize or (
            lambda fn, text: summarizer.summarize(fn, text, cfg.openai_model, openai_client)
        )

    def fetch(self):
        return self._get_starred()

    def stem(self, repo):
        return repo.full_name.replace("/", "-")

    def render(self, repo):
        text = self._get_readme(repo.full_name) or repo.description or repo.full_name
        summary, tokens = self._summarize(repo.full_name, text)
        return RenderedNote(notes.render_note(repo, summary), tokens)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/test_github_source.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/github/__init__.py sources/github/source.py tests/sources/test_github_source.py
git commit -m "feat: add GitHubSource implementing the Source protocol

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `sync.py` — entrypoint único

**Files:**
- Create: `sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `config.load_config`, `pipeline.process_source`, `downstream`, `runlog.format_summary/append_log`, `sources.github.source.GitHubSource`.
- Produces:
  - `build_sources(cfg, openai_client) -> list` — registro de fuentes (por ahora `[GitHubSource(...)]`).
  - `main(argv=None) -> int` — parsea `--source {github}` y `--limit N`; por cada fuente corre `process_source`, y si hubo notas nuevas commitea/pushea (subdir de la fuente) + gbrain sync; escribe una línea de resumen por fuente al logfile. Devuelve 1 si alguna fuente resultó FALLO.

- [ ] **Step 1: Write the failing test**

`tests/test_sync.py`:
```python
from sync import build_sources
from config import Config
from pathlib import Path


def _cfg() -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=Path("/brain"), github_subdir="Recursos/Repositorios",
        git_push=True, gbrain_sync=True,
        script_dir=Path("/s"), log_path=Path("/s/sync.log"),
    )


def test_build_sources_includes_github():
    sources = build_sources(_cfg(), openai_client=None)
    names = [s.name for s in sources]
    assert "GitHub" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_sync.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sync'`.

- [ ] **Step 3: Write minimal implementation**

`sync.py`:
```python
import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

import downstream
from config import ConfigError, load_config
from pipeline import process_source
from runlog import append_log, format_summary
from sources.github.source import GitHubSource


def build_sources(cfg, openai_client) -> list:
    return [GitHubSource(cfg, openai_client)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza recursos externos (repos faveados, ...) al digital brain."
    )
    parser.add_argument(
        "--source",
        choices=["github"],
        default=None,
        help="Correr solo una fuente (default: todas).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como máximo N items nuevos por fuente (corrida de prueba).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=cfg.openai_api_key)
    sources = build_sources(cfg, client)
    if args.source:
        sources = [s for s in sources if s.name.lower() == args.source]

    exit_code = 0
    for source in sources:
        # disable=None apaga la barra en no-TTY (cron), evitando ensuciar sync.log.
        progress = lambda it, s=source: tqdm(
            it, desc=f"Sincronizando {s.name}", unit="item", disable=None
        )
        stats = process_source(cfg, source, limit=args.limit, progress=progress)

        if stats.created > 0:
            try:
                downstream.git_commit_push(
                    cfg.digital_brain_path,
                    source.subdir,
                    f"chore: sync {stats.created} {source.name} nuevos",
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
        if stats.result == "FALLO":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_sync.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Verify CLI wiring smoke (no red real)**

Run: `./venv/bin/python sync.py --help`
Expected: muestra el help con `--source {github}` y `--limit`.

- [ ] **Step 6: Commit**

```bash
git add sync.py tests/test_sync.py
git commit -m "feat: add unified sync.py entrypoint over Source pipeline

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Cutover — mover `github_client`, eliminar `sync_repos`, actualizar docs

**Files:**
- Create: `sources/github/client.py` (contenido idéntico a `github_client.py`)
- Delete: `github_client.py`
- Delete: `sync_repos.py`
- Delete: `tests/test_sync_repos.py`
- Modify: `sources/github/source.py` (import de `client`)
- Modify: `tests/test_github_client.py` (import path)
- Modify: `.env.example` (`GITHUB_SUBDIR`)
- Modify: `README.md` (uso de `sync.py`)

**Interfaces:**
- Consumes: lo ya definido.
- Produces: estructura final del Plan 1; `sources.github.client` expone `get_starred_repos`, `get_readme`, `GH_JQ` (idénticos a los de `github_client`).

- [ ] **Step 1: Mover el cliente de GitHub al paquete**

```bash
git mv github_client.py sources/github/client.py
```

- [ ] **Step 2: Actualizar el import en `GitHubSource`**

En `sources/github/source.py`, reemplazar:
```python
import github_client
```
por:
```python
from sources.github import client as github_client
```
(El resto del archivo no cambia: sigue usando `github_client.get_starred_repos` / `github_client.get_readme`.)

- [ ] **Step 3: Actualizar el import del test del cliente**

En `tests/test_github_client.py`, reemplazar:
```python
import github_client as gh
```
por:
```python
from sources.github import client as gh
```
(El resto del test no cambia: usa `gh.get_starred_repos`, `gh.get_readme`, `gh.GH_JQ`.)

- [ ] **Step 4: Eliminar el viejo entrypoint y su test**

```bash
git rm sync_repos.py tests/test_sync_repos.py
```

- [ ] **Step 5: Actualizar `.env.example`**

Reemplazar la línea `RESOURCES_SUBDIR=Recursos/Repositorios` por:
```
GITHUB_SUBDIR=Recursos/Repositorios
```
(Si `.env.example` tiene otro valor de `RESOURCES_SUBDIR`, mantener el valor y solo renombrar la clave a `GITHUB_SUBDIR`.)

Además, actualizar el `.env` local (gitignored) con el mismo renombre para que las corridas reales funcionen.

- [ ] **Step 6: Actualizar `README.md`**

Reemplazar todas las apariciones de `sync_repos.py` por `sync.py` en la sección de uso y en la línea de cron. Ajustar el texto para reflejar que el entrypoint ahora corre las fuentes registradas (`--source github` acota a GitHub). La sección "Corrida de prueba acotada" con `--limit N` sigue válida (ahora es por-fuente).

- [ ] **Step 7: Correr TODA la suite**

Run: `./venv/bin/python -m pytest -v`
Expected: PASS — todos los tests verdes, incluyendo `tests/test_notes.py` y `tests/test_runlog.py` sin cambios. Ningún test referencia `sync_repos` ni `github_client` (root).

- [ ] **Step 8: Smoke test end-to-end acotado (paridad de comportamiento)**

Verifica que `sync.py --source github --limit 1` genera una nota idéntica en forma a la del viejo flujo. Requiere `gh` autenticado y `OPENAI_API_KEY` en `.env`. Para no tocar el brain real, usar un destino temporal:

```bash
GITHUB_SUBDIR="Recursos/Repositorios" \
DIGITAL_BRAIN_PATH="/tmp/brain_smoke" GIT_PUSH=false GBRAIN_SYNC=false \
./venv/bin/python sync.py --source github --limit 1
```
Expected: crea `/tmp/brain_smoke/Recursos/Repositorios/<owner>-<repo>.md` con frontmatter válido (`source: GitHub`, `subtype: Repositorio`), cuerpo con resumen, y sección Metadatos con autor/estrellas/última actualización/repo. Imprime una línea de resumen `... OK vistos=... nuevos=1 ...`. Inspeccioná el archivo generado y confirmá que el formato coincide con el ejemplo del spec de repos.

Limpieza: `rm -rf /tmp/brain_smoke`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: cut over to sync.py; move github client into sources package

Elimina sync_repos.py y github_client.py (root), movidos a la abstracción
Source. Actualiza .env.example y README al nuevo entrypoint.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (sección Plan 1 del spec):**
- `sources/base.py` (`Source`, `RenderedNote`) → Task 1. ✓
- Driver genérico `pipeline.py` → Task 2. ✓
- Entrypoint `sync.py` (`--source`, `--limit`) → Task 5. ✓
- GitHub re-expresado como `sources/github/source.py` sin cambio de comportamiento → Task 4 (+ cliente movido en Task 6). ✓
- Config por-fuente (`GITHUB_SUBDIR`) → Task 3. ✓
- Tests de GitHub verdes; `sync.py --source github` produce las mismas notas → Task 6 Steps 7-8. ✓

**Placeholder scan:** sin TBD/TODO; todos los steps de código traen el código completo. ✓

**Type consistency:** `RenderedNote(text, tokens)` usado igual en Tasks 1, 2, 4. `process_source(cfg, source, limit, progress)` igual en Tasks 2 y 5. `GitHubSource(cfg, openai_client, *, get_starred, get_readme, summarize)` consistente entre Task 4 (def) y Task 5 (uso, sin kwargs → reales). `stem` sin `.md`; el pipeline agrega `.md`. `subdir` leído de `cfg.github_subdir` en Tasks 3/4. ✓

**Nota de orden:** el test de Task 2 usa `github_subdir` en `Config`, que se introduce en Task 3. Ejecutar Task 3 inmediatamente después de escribir Task 2 (o correr la suite recién tras Task 3). Señalado en Task 2 Step 4.
