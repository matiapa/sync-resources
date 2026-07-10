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
    github_subdir: str
    git_push: bool
    gbrain_sync: bool
    script_dir: Path
    log_path: Path
    x_client_id: str | None = None
    x_client_secret: str | None = None
    x_subdir: str = "Recursos/Posts"
    x_token_path: Path | None = None


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
        github_subdir=env.get("GITHUB_SUBDIR", "Recursos/Repositorios"),
        git_push=_as_bool(env.get("GIT_PUSH"), True),
        gbrain_sync=_as_bool(env.get("GBRAIN_SYNC"), True),
        script_dir=script_dir,
        log_path=script_dir / "sync.log",
        x_client_id=env.get("X_CLIENT_ID"),
        x_client_secret=env.get("X_CLIENT_SECRET"),
        x_subdir=env.get("X_SUBDIR", "Recursos/Posts"),
        x_token_path=Path(env["X_TOKEN_PATH"]) if env.get("X_TOKEN_PATH") else script_dir / ".x_token.json",
    )
