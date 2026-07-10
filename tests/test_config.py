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
