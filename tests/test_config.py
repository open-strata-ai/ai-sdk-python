"""Config loading tests (env / TOML file / merge priority)."""

import os

from openstrata_sdk.config import Config, load_config


def test_from_env_override(monkeypatch):
    monkeypatch.setenv("OPENSTRATA_GATEWAY_PROVIDER", "higress")
    monkeypatch.setenv("OPENSTRATA_GATEWAY_BASE_URL", "http://gw:8080")
    cfg = Config.from_env()
    assert cfg.gateway_provider == "higress"
    assert cfg.gateway_base_url == "http://gw:8080"


def test_from_file_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_BASE_URL", "http://env-gw:8080")
    p = tmp_path / "openstrata.toml"
    p.write_text(
        "[openstrata.gateway]\n"
        'provider = "logging"\n'
        'base_url = "${GATEWAY_BASE_URL}"\n'
        "[openstrata.model]\n"
        'qwen = { type = "dashscope", default = true }\n'
        "[openstrata.cache]\n"
        'provider = "redis"\n'
        "[openstrata.vector_store]\n"
        'preference = "qdrant"\n'
    )
    cfg = Config.from_file(str(p))
    assert cfg.gateway_provider == "logging"
    assert cfg.gateway_base_url == "http://env-gw:8080"  # ${VAR} expanded
    assert cfg.cache_provider == "redis"
    assert cfg.vector_store_provider == "qdrant"


def test_load_config_merge_priority():
    base = Config(gateway_provider="logging")
    override = Config(gateway_provider="higress", gateway_base_url="http://gw")
    merged = load_config(base, override)
    assert merged.gateway_provider == "higress"
    assert merged.gateway_base_url == "http://gw"
