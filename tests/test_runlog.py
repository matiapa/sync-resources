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
    s = RunStats(seen=3, created=1, skipped=1, errors=[("x/y", "timeout")],
                 git_ok=True, tokens=456)
    now = datetime(2026, 7, 10, 4, 0, 0)
    text = format_summary(s, now)
    assert "2026-07-10T04:00:00" in text
    assert "OK con errores parciales" in text
    assert "vistos=3" in text
    assert "nuevos=1" in text
    assert "salteados=1" in text
    assert "errores=1" in text
    assert "tokens=456" in text
    assert "  - x/y: timeout" in text
    assert text.endswith("\n")


def test_append_log(tmp_path: Path):
    log = tmp_path / "sync.log"
    append_log(log, "linea1\n")
    append_log(log, "linea2\n")
    assert log.read_text(encoding="utf-8") == "linea1\nlinea2\n"
