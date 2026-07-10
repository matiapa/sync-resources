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


def test_x_defaults():
    cfg = load_config(env={"OPENAI_API_KEY": "k"}, script_dir=Path("/scripts"))
    assert cfg.x_client_id is None
    assert cfg.x_client_secret is None
    assert cfg.x_subdir == "Recursos/Posts"
    assert cfg.x_token_path == Path("/scripts/.x_token.json")


def test_x_from_env():
    cfg = load_config(
        env={"OPENAI_API_KEY": "k", "X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "sec",
             "X_SUBDIR": "Recursos/Tweets", "X_TOKEN_PATH": "/tmp/tok.json"},
        script_dir=Path("/s"),
    )
    assert cfg.x_client_id == "cid"
    assert cfg.x_client_secret == "sec"
    assert cfg.x_subdir == "Recursos/Tweets"
    assert cfg.x_token_path == Path("/tmp/tok.json")
