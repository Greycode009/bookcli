"""Default settings and constants for BookCLI."""

import os
from pathlib import Path

# Base Directory ~/.bookcli
BASE_DIR = Path(os.environ.get("BOOKCLI_HOME", Path.home() / ".bookcli"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# File Paths
DB_PATH = BASE_DIR / "bookcli.db"
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "downloads"
DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Default configuration settings
DEFAULT_CONFIG = {
    "download_dir": str(DEFAULT_DOWNLOAD_DIR),
    "cache_ttl_seconds": 86400,  # 1 day
    "timeout_seconds": 15,
    "theme": "dark",
    "providers": {
        "google_books": True,
        "openlibrary": True,
        "gutenberg": True,
        "internet_archive": True
    }
}
