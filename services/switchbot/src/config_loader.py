"""YAML config loader with ${ENV_VAR} expansion."""

import os
import re
import logging

import yaml

logger = logging.getLogger(__name__)

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""
    def _replace(m):
        var = m.group(1)
        result = os.environ.get(var, "")
        if not result:
            logger.warning(f"Environment variable {var} is not set")
        return result
    return _ENV_RE.sub(_replace, value)


def _walk(obj):
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v) for v in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def load_config(path: str = "/app/config/switchbot.yaml") -> dict:
    """Load and return config with env var expansion."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    config = _walk(raw)
    logger.info(f"Loaded config from {path}: {len(config.get('devices', []))} devices")
    return config
