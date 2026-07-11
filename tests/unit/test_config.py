"""Unit tests for configuration loading and validation."""

from pathlib import Path
from unittest.mock import patch
from bookcli.config import load_config, AppConfig, ProvidersConfig


def test_default_config_loading(tmp_path):
    """Test loading configuration when no file exists defaults cleanly."""
    # Point to a temporary path that does not exist
    non_existent_file = tmp_path / "non_existent_config.json"
    
    with patch("bookcli.config.CONFIG_PATH", non_existent_file):
        config = load_config()
        assert isinstance(config, AppConfig)
        assert config.cache_ttl_seconds == 86400
        assert config.timeout_seconds == 15
        assert config.theme == "dark"
        assert isinstance(config.providers, ProvidersConfig)
        assert config.providers.google_books is True


def test_invalid_config_fallback(tmp_path):
    """Test fallback to defaults when configuration is invalid or corrupted."""
    # Write invalid config to temp path
    invalid_file = tmp_path / "invalid_config.json"
    invalid_file.write_text('{"cache_ttl_seconds": -10, "timeout_seconds": "invalid"}', encoding="utf-8")
    
    with patch("bookcli.config.CONFIG_PATH", invalid_file):
        config = load_config()
        # Should fallback to default settings because validation failed
        assert config.cache_ttl_seconds == 86400
        assert config.timeout_seconds == 15
