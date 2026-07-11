# Borrado de notas de items des-faveados (GitHub unstar / X unbookmark) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `pipeline.process_source` so that, on every run, it deletes the notes of items that are no longer starred (GitHub) or bookmarked (X), while protecting against transient API failures wiping out real content.

**Architecture:** After the existing create-loop in `process_source`, diff the full `fetch()` result against the `.md` files already in the source's subdir. Ownership of a note is determined by its frontmatter (`source: <Source.name>`), so hand-added notes are never touched. A percentage guardrail (>50% of ≥5 owned notes going stale in one run) aborts deletion and reports it as an error instead of touching the filesystem. `RunStats`/`sync.log` gain a `deleted` counter, and `sync.py`'s git/GBrain trigger fires on deletions too, not just creations.

**Tech Stack:** Python 3.11, stdlib only for this feature (`pathlib`, `dataclasses`), pytest for tests.

## Global Constraints

- Ownership check: a note belongs to a source only if its frontmatter has a line `source: <Source.name>` (exact match, read from the raw text between the two `---` markers — no YAML library).
- `MIN_NOTES_FOR_THRESHOLD = 5`: the percentage guardrail only applies when the source has at least 5 owned notes on disk.
- `STALE_RATIO_THRESHOLD = 0.5`: if `len(stale) / len(owned) > 0.5` (and owned ≥ 5), abort deletion for that source and record an error; do not delete anything for that source in that run.
- Deletion diffing uses the **full** list returned by `source.fetch()`, never the `--limit`-truncated iteration — `--limit` only caps how many *new* notes get created.
- Commit message format when creations and/or deletions happened: `f"chore: sync {source.name} (+{stats.created}/-{stats.deleted})"`.
- Git commit+push and GBrain reindex trigger on `stats.created > 0 or stats.deleted > 0` (previously only `created > 0`).

---

### Task 1: `RunStats` gains `deleted`/`deleted_items`, `format_summary` reports them

**Files:**
- Modify: `runlog.py`
- Test: `tests/test_runlog.py`

**Interfaces:**
- Consumes: nothing new (pure extension of existing `RunStats`/`format_summary`).
- Produces: `RunStats.deleted: int = 0`, `RunStats.deleted_items: list[str] = field(default_factory=list)` — Task 2 and Task 3 read/write these fields directly.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_runlog.py`:

```python
def test_format_summary_contains_deleted_count_and_detail():
    s = RunStats(seen=4, created=0, skipped=2, deleted=2,
                 deleted_items=["owner-repo-viejo", "owner-otro-repo"],
                 git_ok=True)
    now = datetime(2026, 7, 11, 4, 0, 0)
    text = format_summary(s, now)
    assert "borrados=2" in text
    assert "  - borrado: owner-repo-viejo" in text
    assert "  - borrado: owner-otro-repo" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_runlog.py::test_format_summary_contains_deleted_count_and_detail -v`
Expected: FAIL — `TypeError: RunStats.__init__() got an unexpected keyword argument 'deleted'`

- [ ] **Step 3: Extend `RunStats` and `format_summary`**

In `runlog.py`, replace the `RunStats` dataclass body:

```python
@dataclass
class RunStats:
    seen: int = 0
    created: int = 0
    skipped: int = 0
    deleted: int = 0
    deleted_items: list[str] = field(default_factory=list)
    tokens: int = 0
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
```

Replace `format_summary`:

```python
def format_summary(stats: RunStats, now: datetime) -> str:
    line = (
        f"[{now.isoformat()}] {stats.result} "
        f"vistos={stats.seen} nuevos={stats.created} "
        f"salteados={stats.skipped} borrados={stats.deleted} "
        f"errores={len(stats.errors)} "
        f"tokens={stats.tokens}"
    )
    lines = [line]
    for stem in stats.deleted_items:
        lines.append(f"  - borrado: {stem}")
    for full_name, reason in stats.errors:
        lines.append(f"  - {full_name}: {reason}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_runlog.py -v`
Expected: all PASS, including the pre-existing `test_format_summary_contains_metrics_and_errors` (it only asserts substrings, so the new `borrados=0` segment doesn't break it).

- [ ] **Step 5: Commit**

```bash
git add runlog.py tests/test_runlog.py
git commit -m "feat: add deleted count to RunStats and sync.log summary"
```

---

### Task 2: `pipeline.process_source` deletes stale notes with ownership + threshold guardrail

**Files:**
- Modify: `pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `RunStats.deleted` / `RunStats.deleted_items` from Task 1. `Source.name` (already in `sources/base.py`'s `Source` protocol). `Source.stem(item) -> str`, `Source.fetch() -> list` (already existing).
- Produces: `process_source(cfg, source, limit=None, progress=None) -> RunStats` — unchanged signature, now also populates `stats.deleted` / `stats.deleted_items` and may append `(f"<{source.name}>", "borrado abortado: ...")` to `stats.errors`. No new public functions are consumed by later tasks; Task 3 only observes `stats.deleted`.

- [ ] **Step 1: Update `FakeSource.render` to emit real frontmatter and fix the one test that checks exact note content**

`FakeSource.render` currently returns a bare body string (`"cuerpo de {item}"`), which can't carry a `source:` frontmatter field for ownership testing. Change it in `tests/test_pipeline.py`:

```python
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
        text = f"---\nsource: {self.name}\n---\n\ncuerpo de {item}\n"
        return RenderedNote(text=text, tokens=self.tokens)
```

Update `test_creates_notes_for_new_items` (the only test asserting exact file content) to match:

```python
def test_creates_notes_for_new_items(tmp_path):
    cfg = _cfg(tmp_path)
    src = FakeSource(items=["a", "b"])
    stats = process_source(cfg, src)
    assert stats.seen == 2
    assert stats.created == 2
    assert stats.skipped == 0
    assert stats.tokens == 6
    assert (tmp_path / "res" / "a.md").read_text(encoding="utf-8") == (
        "---\nsource: Fake\n---\n\ncuerpo de a\n"
    )
    assert (tmp_path / "res" / "b.md").exists()
```

Also add a small helper used by the new deletion tests, right below the `FakeSource` class:

```python
def _owned_note(name: str, body: str) -> str:
    return f"---\nsource: {name}\n---\n\n{body}\n"
```

- [ ] **Step 2: Run existing tests to confirm the FakeSource change alone doesn't break anything else**

Run: `./venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: all PASS (the other tests don't assert exact note content).

- [ ] **Step 3: Write the failing deletion tests**

Add to `tests/test_pipeline.py`:

```python
def test_deletes_notes_for_items_no_longer_fetched(tmp_path):
    cfg = _cfg(tmp_path)
    res = tmp_path / "res"
    res.mkdir()
    (res / "a.md").write_text(_owned_note("Fake", "cuerpo de a"), encoding="utf-8")
    (res / "b.md").write_text(_owned_note("Fake", "cuerpo de b"), encoding="utf-8")
    src = FakeSource(items=["a"])  # "b" ya no está faveado
    stats = process_source(cfg, src)
    assert stats.deleted == 1
    assert stats.deleted_items == ["b"]
    assert (res / "a.md").exists()
    assert not (res / "b.md").exists()


def test_does_not_delete_note_without_matching_source_frontmatter(tmp_path):
    cfg = _cfg(tmp_path)
    res = tmp_path / "res"
    res.mkdir()
    (res / "manual.md").write_text("# Nota agregada a mano\n", encoding="utf-8")
    src = FakeSource(items=[])
    stats = process_source(cfg, src)
    assert stats.deleted == 0
    assert (res / "manual.md").exists()


def test_aborts_deletion_when_stale_ratio_exceeds_threshold(tmp_path):
    cfg = _cfg(tmp_path)
    res = tmp_path / "res"
    res.mkdir()
    stems = [f"item{i}" for i in range(5)]
    for stem in stems:
        (res / f"{stem}.md").write_text(_owned_note("Fake", stem), encoding="utf-8")
    src = FakeSource(items=[])  # fetch vacío: borraría el 100%
    stats = process_source(cfg, src)
    assert stats.deleted == 0
    assert stats.deleted_items == []
    assert len(stats.errors) == 1
    assert "borrado abortado" in stats.errors[0][1]
    for stem in stems:
        assert (res / f"{stem}.md").exists()


def test_deletion_below_threshold_floor_is_not_blocked(tmp_path):
    cfg = _cfg(tmp_path)
    res = tmp_path / "res"
    res.mkdir()
    (res / "a.md").write_text(_owned_note("Fake", "a"), encoding="utf-8")
    (res / "b.md").write_text(_owned_note("Fake", "b"), encoding="utf-8")
    src = FakeSource(items=[])  # borra 2/2 (100%), pero por debajo del piso de 5
    stats = process_source(cfg, src)
    assert stats.deleted == 2
    assert not (res / "a.md").exists()
    assert not (res / "b.md").exists()


def test_deletion_uses_full_fetch_ignoring_limit(tmp_path):
    cfg = _cfg(tmp_path)
    res = tmp_path / "res"
    res.mkdir()
    (res / "c.md").write_text(_owned_note("Fake", "c"), encoding="utf-8")
    src = FakeSource(items=["a", "b"])  # "c" ya no está, aunque --limit corte la creación
    stats = process_source(cfg, src, limit=1)
    assert stats.created == 1
    assert stats.deleted == 1
    assert not (res / "c.md").exists()
```

- [ ] **Step 4: Run tests to verify the new ones fail**

Run: `./venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: the 5 new tests FAIL (no deletion behavior implemented yet — `stats.deleted` stays `0` and files aren't removed).

- [ ] **Step 5: Implement the deletion pass in `pipeline.py`**

Replace the full contents of `pipeline.py`:

```python
from pathlib import Path

from config import Config
from runlog import RunStats

MIN_NOTES_FOR_THRESHOLD = 5
STALE_RATIO_THRESHOLD = 0.5


def _frontmatter_source(path: Path) -> str | None:
    """Lee el valor del campo `source:` del frontmatter YAML, o None si no hay.

    No se usa un parser YAML: el formato de nota es fijo (un `---` inicial, un
    `---` de cierre, líneas `clave: valor`), así que un escaneo de texto simple
    alcanza y evita una dependencia nueva.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("source:"):
            return line[len("source:"):].strip()
    return None


def _delete_stale_notes(resources_dir: Path, source, fetched_stems: set, stats: RunStats) -> None:
    """Borra notas de `source` cuyo item ya no está en `fetched_stems`.

    Solo se consideran "owned" las notas cuyo frontmatter declara
    `source: <source.name>`, para no tocar notas agregadas a mano. Si el
    borrado alcanzaría más de la mitad de las notas owned (habiendo al menos
    MIN_NOTES_FOR_THRESHOLD), se aborta y se registra como error en vez de
    borrar: protege contra un fetch vacío o parcial por falla de la API (ese
    caso extremo cae en el mismo chequeo, porque ahí `stale == owned`, 100%).
    """
    if not resources_dir.exists():
        return
    owned = [p for p in resources_dir.glob("*.md") if _frontmatter_source(p) == source.name]
    stale = [p for p in owned if p.stem not in fetched_stems]
    if not stale:
        return
    if len(owned) >= MIN_NOTES_FOR_THRESHOLD and len(stale) / len(owned) > STALE_RATIO_THRESHOLD:
        stats.errors.append((
            f"<{source.name}>",
            f"borrado abortado: {len(stale)}/{len(owned)} notas superan el umbral del 50%",
        ))
        return
    for path in stale:
        try:
            path.unlink()
        except OSError as exc:
            stats.errors.append((path.stem, str(exc)))
            continue
        stats.deleted += 1
        stats.deleted_items.append(path.stem)


def process_source(cfg: Config, source, limit=None, progress=None) -> RunStats:
    """Sincroniza una fuente: escribe una nota por item nuevo y borra las de
    items des-faveados (unstar / unbookmark).

    La fuente de verdad de "ya procesado" es la existencia del archivo de nota;
    los items ya presentes se saltean sin llamar a ``render`` (así no se gasta
    en red ni en OpenAI). Los errores de ``render`` se registran y no cortan la
    corrida. Nunca se escriben archivos parciales. El borrado de notas
    des-faveadas usa el ``fetch()`` completo, sin acotar por ``limit``.
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

    fetched_stems = {source.stem(item) for item in items}
    _delete_stale_notes(resources_dir, source, fetched_stems, stats)
    return stats
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: all PASS (10 tests: 5 pre-existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "feat: delete notes for unstarred/unbookmarked items with threshold guardrail"
```

---

### Task 3: `sync.py` triggers commit+push+GBrain on deletions too

**Files:**
- Modify: `sync.py:126-138`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `RunStats.deleted` (Task 1), `process_source` now populating it via real deletions (Task 2), `downstream.git_commit_push(brain_path, subdir, message, push, run=subprocess.run) -> None` (existing, unchanged signature).
- Produces: nothing new consumed by other tasks — this is the final integration point.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sync.py`:

```python
def test_deletion_only_run_triggers_git_commit(tmp_path, monkeypatch):
    """Si la única novedad de la corrida es un borrado (sin notas nuevas),
    igual debe dispararse el commit+push al digital brain."""
    from dataclasses import dataclass, field

    from sources.base import RenderedNote

    @dataclass
    class FakeSource:
        name: str
        subdir: str
        items: list = field(default_factory=list)

        def fetch(self):
            return self.items

        def stem(self, item):
            return item

        def render(self, item):
            return RenderedNote(f"---\nsource: {self.name}\n---\n\n# {item}\n", 0)

    src = FakeSource(name="Ok", subdir="ok", items=[])
    res_dir = tmp_path / "ok"
    res_dir.mkdir()
    (res_dir / "stale.md").write_text("---\nsource: Ok\n---\n\nviejo\n", encoding="utf-8")

    commits = []
    monkeypatch.setattr("sync.build_sources", lambda cfg, client: [src])
    monkeypatch.setattr("sync.load_config", lambda: _cfg().__class__(
        **{**_cfg().__dict__, "digital_brain_path": tmp_path,
           "log_path": tmp_path / "sync.log", "git_push": False, "gbrain_sync": False}
    ))
    monkeypatch.setattr("sync.OpenAI", lambda api_key: None)
    monkeypatch.setattr("sync.load_dotenv", lambda: None)
    monkeypatch.setattr("downstream.git_commit_push", lambda *a, **k: commits.append(a))

    exit_code = main([])

    assert not (res_dir / "stale.md").exists()
    assert len(commits) == 1
    assert exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_sync.py::test_deletion_only_run_triggers_git_commit -v`
Expected: FAIL — `assert len(commits) == 1` fails with `commits == []`, because the current gate is `if stats.created > 0:` and `created` is 0 here.

- [ ] **Step 3: Update the trigger gate and commit message in `sync.py`**

In `sync.py`, replace:

```python
        if stats.created > 0:
            try:
                downstream.git_commit_push(
                    cfg.digital_brain_path,
                    source.subdir,
                    f"chore: sync {stats.created} {source.name} nuevos",
                    push=cfg.git_push,
                )
```

with:

```python
        if stats.created > 0 or stats.deleted > 0:
            try:
                downstream.git_commit_push(
                    cfg.digital_brain_path,
                    source.subdir,
                    f"chore: sync {source.name} (+{stats.created}/-{stats.deleted})",
                    push=cfg.git_push,
                )
```

(The rest of the block — `stats.git_ok = True`, the `except`, and the `gbrain_sync` call — stays exactly as is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_sync.py -v`
Expected: all PASS, including the pre-existing `test_source_fetch_failure_does_not_prevent_other_sources`.

- [ ] **Step 5: Run the full test suite**

Run: `./venv/bin/python -m pytest -v`
Expected: all PASS, no regressions across `tests/`.

- [ ] **Step 6: Commit**

```bash
git add sync.py tests/test_sync.py
git commit -m "feat: trigger digital brain commit+push on deletions, not just creations"
```

---

## Manual verification (post-implementation)

Not covered by unit tests — run once after all 3 tasks land, before relying on this in cron:

1. `./venv/bin/python sync.py --source github` on a repo that's actually still starred → confirm no notes are deleted (`borrados=0` in the log line).
2. Unstar a repo you previously synced, then run `./venv/bin/python sync.py --source github` again → confirm the log shows `borrados=1`, the note file is gone from `digital_brain_path/github_subdir`, and there's a new commit `chore: sync GitHub (+0/-1)`.
3. Same check for X: remove a bookmark, run `./venv/bin/python sync.py --source x`, confirm the corresponding note under `Recursos/Posts` is deleted and committed.
