"""Configuration loading (DESIGN §7).

Priority (§7.1): constructor parameters > environment variables >
``pyproject.toml`` ``[tool.openstrata]`` / ``infrastructure/config`` fragment >
defaults. TOML is read with the stdlib :mod:`tomllib` (Python 3.11+), so no
third-party parser is required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore


@dataclass
class Config:
    gateway_provider: str = "logging"
    gateway_base_url: Optional[str] = None
    model_provider: str = "echo"
    cache_provider: str = "memory"
    vector_store_provider: str = "memory"
    observability_otel: bool = True
    audit_log: bool = True
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Config":
        def env(name: str, default=None):
            return os.environ.get(f"OPENSTRATA_{name}", default)

        return cls(
            gateway_provider=env("GATEWAY_PROVIDER", "logging"),
            gateway_base_url=env("GATEWAY_BASE_URL"),
            model_provider=env("MODEL_PROVIDER", "echo"),
            cache_provider=env("CACHE_PROVIDER", "memory"),
            vector_store_provider=env("VECTOR_STORE_PROVIDER", "memory"),
            observability_otel=env("OTEL_TRACES", "true").lower() != "false",
            audit_log=env("AUDIT_LOG", "true").lower() != "false",
        )

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> "Config":
        if path is None:
            return cls()
        if tomllib is None:  # pragma: no cover
            return cls()
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            return cls()
        node = data.get("openstrata") or data.get("tool", {}).get("openstrata") or {}
        gw = node.get("gateway", {})
        return cls(
            gateway_provider=gw.get("provider", "logging"),
            gateway_base_url=_subst(gw.get("base_url")),
            model_provider=node.get("model", {}).get("qwen", {}).get("type", "echo"),
            cache_provider=node.get("cache", {}).get("provider", "memory"),
            vector_store_provider=node.get("vector_store", {}).get("preference", "memory"),
        )


def _subst(value):
    """Expand ``${VAR}`` / ``${VAR:-default}`` in a string config value."""
    if not isinstance(value, str):
        return value
    if not value.startswith("${"):
        return value
    inner = value[2:-1]
    if ":" in inner:
        name, default = inner.split(":", 1)
        default = default.lstrip("-")
    else:
        name, default = inner, None
    return os.environ.get(name, default)


def load_config(*sources: Config) -> Config:
    """Merge configs; later sources override earlier ones (defaults first)."""
    merged = Config()
    for src in sources:
        if src is None:
            continue
        for f in (
            "gateway_provider", "gateway_base_url", "model_provider",
            "cache_provider", "vector_store_provider", "observability_otel",
            "audit_log",
        ):
            v = getattr(src, f)
            if v is not None:
                setattr(merged, f, v)
        merged.extra.update(src.extra)
    return merged


__all__ = ["Config", "load_config"]
