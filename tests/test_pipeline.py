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
        text = f"---\nsource: {self.name}\n---\n\ncuerpo de {item}\n"
        return RenderedNote(text=text, tokens=self.tokens)


def _owned_note(name: str, body: str) -> str:
    return f"---\nsource: {name}\n---\n\n{body}\n"


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
