from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


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


def append_log(log_path: Path, text: str) -> None:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text)
