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
