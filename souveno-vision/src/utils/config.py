"""Configuration loader: config/default.yaml  <  config/local.yaml  <  environment.

Environment overrides use SOUVENO_<SECTION>__<KEY> (double underscore), e.g.
SOUVENO_MODEL__CONFIDENCE=0.5 or SOUVENO_SOURCE__RTSP__STREAM_PROFILE=sub.
A .env file next to the project root is loaded automatically (python-dotenv)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
ENV_PREFIX = "SOUVENO_"


class Config:
    """Attribute + mapping access over a nested dict: cfg.model.confidence, cfg["model"]["confidence"]."""

    def __init__(self, data: dict[str, Any]):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, item: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if item in data:
            value = data[item]
            return Config(value) if isinstance(value, dict) else value
        raise AttributeError(f"No configuration key '{item}'")

    def __getitem__(self, item: str) -> Any:
        value = self._data[item]
        return Config(value) if isinstance(value, dict) else value

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def get(self, item: str, default: Any = None) -> Any:
        value = self._data.get(item, default)
        return Config(value) if isinstance(value, dict) else value

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        return f"Config({self._data!r})"


def _coerce(raw: str, reference: Any) -> Any:
    if isinstance(reference, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    if isinstance(reference, float):
        return float(raw)
    if isinstance(reference, (list, dict)):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return [v.strip() for v in raw.split(",") if v.strip()]
    return raw


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def apply_env_overrides(data: dict, environ: dict | None = None) -> dict:
    environ = os.environ if environ is None else environ
    out = copy.deepcopy(data)
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX) or "__" not in key:
            continue
        path = key[len(ENV_PREFIX):].lower().split("__")
        node = out
        ok = True
        for part in path[:-1]:
            if not isinstance(node.get(part), dict):
                ok = False
                break
            node = node[part]
        if not ok:
            continue
        leaf = path[-1]
        node[leaf] = _coerce(raw, node.get(leaf))
    return out


def load_config(default_path: Path | None = None, local_path: Path | None = None,
                env: dict | None = None, load_dotenv: bool = True) -> Config:
    default_path = default_path or CONFIG_DIR / "default.yaml"
    local_path = local_path or CONFIG_DIR / "local.yaml"
    if load_dotenv:
        try:
            from dotenv import load_dotenv as _load
            _load(BASE_DIR / ".env", override=False)
        except Exception:
            pass
    with open(default_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if local_path and Path(local_path).exists():
        with open(local_path, "r", encoding="utf-8") as fh:
            data = deep_merge(data, yaml.safe_load(fh) or {})
    data = apply_env_overrides(data, env)
    return Config(data)


def resolve_path(value: str | Path, base: Path = BASE_DIR) -> Path:
    p = Path(value)
    return p if p.is_absolute() else base / p


def save_local_overrides(overrides: dict, local_path: Path | None = None) -> Path:
    """Persist dashboard settings into config/local.yaml (never credentials)."""
    local_path = local_path or CONFIG_DIR / "local.yaml"
    existing = {}
    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
    merged = deep_merge(existing, overrides)
    with open(local_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(merged, fh, sort_keys=False)
    return local_path
