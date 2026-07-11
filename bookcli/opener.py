"""OS default application opener service for BookCLI."""

import os
import sys
import subprocess
import logging
from bookcli.exceptions import BookCLIError

logger = logging.getLogger(__name__)


def open_file_in_default_app(file_path: str) -> None:
    """Opens a file using the operating system's default application."""
    if not os.path.exists(file_path):
        raise BookCLIError(f"File not found: {file_path}")

    abs_path = os.path.abspath(file_path)
    logger.info("Opening file: %s", abs_path)

    try:
        if sys.platform.startswith("win32"):
            # Windows
            os.startfile(abs_path)
        elif sys.platform.startswith("darwin"):
            # macOS
            subprocess.run(["open", abs_path], check=True)
        else:
            # Linux / Unix
            subprocess.run(["xdg-open", abs_path], check=True)
    except Exception as e:
        logger.error("Failed to open file %s: %s", abs_path, e)
        raise BookCLIError(f"Failed to open file in default application: {e}")
