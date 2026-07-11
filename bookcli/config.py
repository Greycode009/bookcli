"""Configuration management for BookCLI."""

import json
import logging
from pathlib import Path
from typing import Any, Dict
from pydantic import BaseModel, Field

from bookcli.settings import CONFIG_PATH, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class ProvidersConfig(BaseModel):
    """Configuration for individual book search providers."""
    google_books: bool = True
    openlibrary: bool = True
    gutenberg: bool = True
    internet_archive: bool = True


class AppConfig(BaseModel):
    """Application-wide configuration settings."""
    download_dir: str
    cache_ttl_seconds: int = Field(default=86400, ge=0)
    timeout_seconds: int = Field(default=15, ge=1)
    theme: str = "dark"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)


def load_config() -> AppConfig:
    """Loads configuration from config.json, merging with default config."""
    config_dict = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                # Merge user config with defaults (shallow dict update for top-level keys,
                # custom merge for nested providers)
                for key, value in user_config.items():
                    if key == "providers" and isinstance(value, dict):
                        # Merge providers dict
                        for p_key, p_val in value.items():
                            if p_key in config_dict["providers"]:
                                config_dict["providers"][p_key] = bool(p_val)
                    else:
                        config_dict[key] = value
        except Exception as e:
            logger.warning("Failed to load config file: %s. Using default settings.", e)

    # Instantiate and validate through Pydantic
    try:
        return AppConfig(**config_dict)
    except Exception as e:
        logger.warning("Validation of configuration failed: %s. Using default settings.", e)
        # Force default settings if validation fails
        return AppConfig(**DEFAULT_CONFIG)


def save_config(config: AppConfig) -> None:
    """Saves configuration to the config.json file."""
    try:
        # Create directory if it doesn't exist
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            # We use dump_model to turn it into dict, then standard json dump
            json.dump(config.model_dump(), f, indent=4)
        logger.info("Configuration saved successfully to %s", CONFIG_PATH)
    except Exception as e:
        logger.error("Failed to save configuration: %s", e)
        raise e
