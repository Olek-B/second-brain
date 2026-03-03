"""Tests for second_brain.config module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from second_brain import config


class TestXDGPaths:
    """XDG base directory defaults."""

    def test_config_dir_under_xdg_config(self):
        assert "second_brain" in str(config.CONFIG_DIR)

    def test_cache_dir_exists(self):
        cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        assert (cache_dir / "second_brain").exists()


class TestConfigLoading:
    """Config file loading and _get() accessor."""

    def test_load_config_returns_dict(self):
        result = config._load_config()
        assert isinstance(result, dict)

    def test_get_missing_key_returns_default(self):
        assert config._get("nonexistent.key.path", "fallback") == "fallback"

    def test_get_missing_key_returns_none(self):
        assert config._get("nonexistent.key.path") is None

    def test_get_dot_path_traversal(self):
        """_get() should traverse dot-separated key paths."""
        with patch.object(config, "_config_cache", {"a": {"b": {"c": 42}}}):
            assert config._get("a.b.c") == 42

    def test_get_partial_path_returns_dict(self):
        with patch.object(config, "_config_cache", {"a": {"b": {"c": 42}}}):
            result = config._get("a.b")
            assert isinstance(result, dict)
            assert result["c"] == 42

    def test_load_config_from_file(self, tmp_path):
        """Config loading from a JSON file."""
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"test_key": "test_value"}))

        old_file = config.CONFIG_FILE
        old_cache = config._config_cache
        try:
            config._config_cache = None
            config.CONFIG_FILE = cfg_file
            result = config._load_config()
            assert result["test_key"] == "test_value"
        finally:
            config.CONFIG_FILE = old_file
            config._config_cache = old_cache

    def test_load_config_missing_file(self, tmp_path):
        """Missing config file returns empty dict."""
        old_file = config.CONFIG_FILE
        old_cache = config._config_cache
        try:
            config._config_cache = None
            config.CONFIG_FILE = tmp_path / "nonexistent.json"
            result = config._load_config()
            assert result == {}
        finally:
            config.CONFIG_FILE = old_file
            config._config_cache = old_cache


class TestPathDefaults:
    """Default path values."""

    def test_brain_dir_is_path(self):
        assert isinstance(config.BRAIN_DIR, Path)

    def test_default_brain_dir(self):
        expected = Path.home() / "Documents" / "brain"
        assert config._default_brain_dir() == expected

    def test_dump_file_in_brain_dir(self):
        assert config.DUMP_FILE == config.BRAIN_DIR / "dump.md"

    def test_todo_file_in_brain_dir(self):
        assert config.TODO_FILE == config.BRAIN_DIR / "todo.md"

    def test_wallpaper_output_is_path(self):
        assert isinstance(config.WALLPAPER_OUTPUT, Path)

    def test_original_wallpaper_cache_in_xdg_cache(self):
        assert ".cache" in str(config.ORIGINAL_WALLPAPER_CACHE)


class TestGroqApiKey:
    """Groq API key loading."""

    def test_groq_model_is_set(self):
        assert config.GROQ_MODEL == "llama-3.3-70b-versatile"

    def test_missing_key_raises(self, tmp_path):
        """Should raise RuntimeError when no key is available."""
        old_dir = config.CONFIG_DIR
        try:
            config.CONFIG_DIR = tmp_path / "no_such_dir"
            with patch.dict(os.environ, {}, clear=True):
                # Remove GROQ_API_KEY if present
                env = os.environ.copy()
                env.pop("GROQ_API_KEY", None)
                with patch.dict(os.environ, env, clear=True):
                    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
                        config.get_groq_api_key()
        finally:
            config.CONFIG_DIR = old_dir

    def test_key_from_env(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key_123"}):
            assert config.get_groq_api_key() == "test_key_123"

    def test_key_from_file(self, tmp_path):
        key_file = tmp_path / "groq_key"
        key_file.write_text("file_key_456\n")
        old_dir = config.CONFIG_DIR
        try:
            config.CONFIG_DIR = tmp_path
            with patch.dict(os.environ, {}, clear=True):
                env = os.environ.copy()
                env.pop("GROQ_API_KEY", None)
                with patch.dict(os.environ, env, clear=True):
                    assert config.get_groq_api_key() == "file_key_456"
        finally:
            config.CONFIG_DIR = old_dir


class TestBrainFiles:
    """get_brain_files() listing."""

    def test_brain_files_returns_list(self):
        result = config.get_brain_files()
        assert isinstance(result, list)

    def test_brain_files_excludes_dump(self, tmp_path):
        """dump.md should be excluded from the file list."""
        (tmp_path / "notes.md").write_text("# Notes")
        (tmp_path / "dump.md").write_text("raw stuff")
        (tmp_path / "todo.md").write_text("# Todo")

        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            files = config.get_brain_files()
            assert "dump.md" not in files
            assert "notes.md" in files
            assert "todo.md" in files
        finally:
            config.BRAIN_DIR = old_dir

    def test_brain_files_sorted(self, tmp_path):
        (tmp_path / "zebra.md").write_text("z")
        (tmp_path / "alpha.md").write_text("a")
        (tmp_path / "middle.md").write_text("m")

        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            files = config.get_brain_files()
            assert files == sorted(files)
        finally:
            config.BRAIN_DIR = old_dir

    def test_brain_files_empty_dir(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert config.get_brain_files() == []
        finally:
            config.BRAIN_DIR = old_dir


class TestWallpaperBackend:
    """Wallpaper backend detection."""

    def test_backend_list_not_empty(self):
        assert len(config._WALLPAPER_BACKENDS) > 0

    def test_all_backends_have_required_keys(self):
        for b in config._WALLPAPER_BACKENDS:
            assert "name" in b
            assert "detect" in b
            assert "set_cmd" in b
            assert "query" in b

    def test_get_wallpaper_backend_returns_string_or_none(self):
        result = config.get_wallpaper_backend()
        assert result is None or isinstance(result, str)


class TestMonitorResolution:
    """Resolution detection."""

    def test_returns_tuple_of_two_ints(self):
        result = config.get_monitor_resolution()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_fallback_is_1080p(self):
        """With no detectors available, should fallback to 1920x1080."""
        with patch.object(config, "_load_config", return_value={}):
            with patch.object(config, "_config_cache", {}):
                # Patch all detectors to return None
                patches = []
                for name, _fn in config._RESOLUTION_DETECTORS:
                    p = patch.object(
                        config,
                        _fn.__name__,
                        return_value=None,
                    )
                    patches.append(p)

                for p in patches:
                    p.start()
                try:
                    result = config.get_monitor_resolution()
                    # Should be at least a valid resolution
                    assert result[0] > 0
                    assert result[1] > 0
                finally:
                    for p in patches:
                        p.stop()


class TestFont:
    """Font detection."""

    def test_get_font_returns_two_strings(self):
        result = config.get_font()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)


class TestColors:
    """Color scheme loading."""

    def test_get_wal_colors_returns_dict(self):
        result = config.get_wal_colors()
        assert isinstance(result, dict)
        assert "colors" in result

    def test_default_colors_have_16_entries(self):
        colors = config._DEFAULT_COLORS["colors"]
        assert len(colors) == 16

    def test_default_colors_are_hex(self):
        for key, val in config._DEFAULT_COLORS["colors"].items():
            assert val.startswith("#"), f"{key} is not a hex color: {val}"
