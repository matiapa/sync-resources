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
