"""Unit tests for config_loader.py — YAML loading and ${ENV_VAR} expansion."""
import os
from unittest.mock import patch, mock_open

import pytest

from config_loader import _expand_env, _walk, load_config


# ── _expand_env tests ──────────────────────────────────────────

class TestExpandEnv:
    """Tests for the _expand_env function."""

    def test_expand_single_env_var(self):
        """Environment variable placeholder is replaced with its value."""
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert _expand_env("${MY_VAR}") == "hello"

    def test_expand_multiple_env_vars(self):
        """Multiple placeholders in one string are all expanded."""
        with patch.dict(os.environ, {"HOST": "localhost", "PORT": "8080"}):
            result = _expand_env("${HOST}:${PORT}")
            assert result == "localhost:8080"

    def test_expand_missing_env_var_returns_empty(self):
        """Missing env var is replaced with empty string."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the var is truly absent
            os.environ.pop("NONEXISTENT_VAR_123", None)
            result = _expand_env("${NONEXISTENT_VAR_123}")
            assert result == ""

    def test_expand_no_placeholder_returns_unchanged(self):
        """String without placeholders is returned as-is."""
        assert _expand_env("plain text") == "plain text"

    def test_expand_empty_string(self):
        """Empty string is returned as-is."""
        assert _expand_env("") == ""

    def test_expand_partial_string_with_var(self):
        """Placeholder embedded in a longer string is expanded correctly."""
        with patch.dict(os.environ, {"TOKEN": "abc123"}):
            result = _expand_env("Bearer ${TOKEN}")
            assert result == "Bearer abc123"

    def test_expand_missing_var_logs_warning(self):
        """Missing env var triggers a warning log."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MISSING_VAR_XYZ", None)
            with patch("config_loader.logger") as mock_logger:
                _expand_env("${MISSING_VAR_XYZ}")
                mock_logger.warning.assert_called_once()
                assert "MISSING_VAR_XYZ" in mock_logger.warning.call_args[0][0]


# ── _walk tests ────────────────────────────────────────────────

class TestWalk:
    """Tests for the _walk function that recursively expands env vars."""

    def test_walk_dict_with_string_values(self):
        """Dict with string values gets env vars expanded."""
        with patch.dict(os.environ, {"VAL": "expanded"}):
            result = _walk({"key": "${VAL}"})
            assert result == {"key": "expanded"}

    def test_walk_nested_dict(self):
        """Nested dicts are walked recursively."""
        with patch.dict(os.environ, {"INNER": "deep"}):
            result = _walk({"outer": {"inner": "${INNER}"}})
            assert result == {"outer": {"inner": "deep"}}

    def test_walk_list(self):
        """Lists are walked and each element is expanded."""
        with patch.dict(os.environ, {"ITEM": "val"}):
            result = _walk(["${ITEM}", "plain"])
            assert result == ["val", "plain"]

    def test_walk_integer_passthrough(self):
        """Non-string primitives (int) are returned unchanged."""
        assert _walk(42) == 42

    def test_walk_none_passthrough(self):
        """None is returned unchanged."""
        assert _walk(None) is None

    def test_walk_bool_passthrough(self):
        """Boolean values are returned unchanged."""
        assert _walk(True) is True
        assert _walk(False) is False

    def test_walk_mixed_structure(self):
        """Complex nested structure with mixed types is walked correctly."""
        with patch.dict(os.environ, {"NAME": "meter"}):
            data = {
                "devices": [
                    {"type": "${NAME}", "port": 8080, "enabled": True}
                ],
                "count": 3,
            }
            result = _walk(data)
            assert result["devices"][0]["type"] == "meter"
            assert result["devices"][0]["port"] == 8080
            assert result["devices"][0]["enabled"] is True
            assert result["count"] == 3


# ── load_config tests ──────────────────────────────────────────

class TestLoadConfig:
    """Tests for the load_config function."""

    def test_load_config_reads_yaml_and_expands_vars(self, sample_yaml_content):
        """Config file is loaded and env vars are expanded."""
        with patch.dict(os.environ, {
            "SWITCHBOT_TOKEN": "my_token",
            "SWITCHBOT_SECRET": "my_secret",
        }):
            m = mock_open(read_data=sample_yaml_content)
            with patch("builtins.open", m):
                config = load_config("/fake/path.yaml")

            assert config["api"]["token"] == "my_token"
            assert config["api"]["secret"] == "my_secret"
            assert config["polling"]["sensor_interval_sec"] == 120
            assert len(config["devices"]) == 1
            assert config["devices"][0]["type"] == "meter"

    def test_load_config_uses_default_path(self, sample_yaml_content):
        """Default path is /app/config/switchbot.yaml."""
        with patch.dict(os.environ, {
            "SWITCHBOT_TOKEN": "t",
            "SWITCHBOT_SECRET": "s",
        }):
            m = mock_open(read_data=sample_yaml_content)
            with patch("builtins.open", m):
                load_config()
            m.assert_called_once_with("/app/config/switchbot.yaml")

    def test_load_config_file_not_found(self):
        """FileNotFoundError is raised when config file does not exist."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/switchbot.yaml")

    def test_load_config_logs_device_count(self, sample_yaml_content):
        """Loaded config logs the number of devices found."""
        with patch.dict(os.environ, {
            "SWITCHBOT_TOKEN": "t",
            "SWITCHBOT_SECRET": "s",
        }):
            m = mock_open(read_data=sample_yaml_content)
            with patch("builtins.open", m):
                with patch("config_loader.logger") as mock_logger:
                    load_config("/fake/path.yaml")
                    mock_logger.info.assert_called_once()
                    assert "1 devices" in mock_logger.info.call_args[0][0]
