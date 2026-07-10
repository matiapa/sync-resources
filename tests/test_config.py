from pathlib import Path

import pytest

from config import Config, ConfigError, load_config


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
