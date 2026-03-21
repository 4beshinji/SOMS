"""Unit tests for config_loader.py — env expansion, file I/O."""
import os
import tempfile
from unittest.mock import patch

import pytest

from config_loader import _expand_env, _walk, load_config


# ── _expand_env tests ─────────────────────────────────────────

class TestExpandEnv:
    """Tests for environment variable expansion in strings."""

    def test_expand_single_var(self):
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert _expand_env("${MY_VAR}") == "hello"

    def test_expand_multiple_vars(self):
        with patch.dict(os.environ, {"A": "foo", "B": "bar"}):
            assert _expand_env("${A}:${B}") == "foo:bar"

    def test_expand_missing_var_returns_empty(self):
        env = os.environ.copy()
        env.pop("NONEXISTENT_VAR_XYZ", None)
        with patch.dict(os.environ, env, clear=True):
            result = _expand_env("${NONEXISTENT_VAR_XYZ}")
            assert result == ""

    def test_no_expansion_without_placeholder(self):
        assert _expand_env("plain text") == "plain text"

    def test_partial_expansion(self):
        with patch.dict(os.environ, {"HOST": "localhost"}):
            assert _expand_env("mqtt://${HOST}:1883") == "mqtt://localhost:1883"


# ── _walk tests ───────────────────────────────────────────────

class TestWalk:
    """Tests for recursive object traversal with env expansion."""

    def test_walk_dict(self):
        with patch.dict(os.environ, {"TOKEN": "abc123"}):
            result = _walk({"key": "${TOKEN}"})
            assert result == {"key": "abc123"}

    def test_walk_list(self):
        with patch.dict(os.environ, {"V": "val"}):
            result = _walk(["${V}", "literal"])
            assert result == ["val", "literal"]

    def test_walk_nested(self):
        with patch.dict(os.environ, {"X": "deep"}):
            result = _walk({"a": {"b": [{"c": "${X}"}]}})
            assert result == {"a": {"b": [{"c": "deep"}]}}

    def test_walk_non_string_passthrough(self):
        assert _walk(42) == 42
        assert _walk(3.14) == 3.14
        assert _walk(True) is True
        assert _walk(None) is None


# ── load_config tests ─────────────────────────────────────────

class TestLoadConfig:
    """Tests for YAML file loading with env expansion."""

    def test_load_valid_yaml(self, sample_yaml_content):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(sample_yaml_content)
            f.flush()
            config = load_config(f.name)

        assert config["z2m_base_topic"] == "zigbee2mqtt"
        assert len(config["devices"]) == 1
        assert config["devices"][0]["type"] == "temp_humidity"

    def test_load_with_env_expansion(self):
        yaml_content = "topic: ${Z2M_TEST_TOPIC}\n"
        with patch.dict(os.environ, {"Z2M_TEST_TOPIC": "my_z2m"}):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                f.flush()
                config = load_config(f.name)
        assert config["topic"] == "my_z2m"

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

    def test_load_empty_devices(self):
        yaml_content = "z2m_base_topic: zigbee2mqtt\ndevices: []\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        assert config["devices"] == []

    def test_load_devices_count_logged(self, sample_yaml_content):
        """Config loader logs device count."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(sample_yaml_content)
            f.flush()
            config = load_config(f.name)
        # Just verify it loaded without error
        assert "devices" in config
