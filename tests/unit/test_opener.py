"""Unit tests for the OS default application opener service."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from bookcli.opener import open_file_in_default_app
from bookcli.exceptions import BookCLIError


def test_open_file_not_exist():
    """Test exception raised when opening a non-existent file."""
    with pytest.raises(BookCLIError) as exc_info:
        open_file_in_default_app("non_existent_file.epub")
    assert "File not found" in str(exc_info.value)


def test_open_file_windows(tmp_path):
    """Test open_file_in_default_app on Windows platform."""
    test_file = tmp_path / "test.epub"
    test_file.write_text("content")

    with patch("sys.platform", "win32"):
        with patch("os.startfile") as mock_startfile:
            open_file_in_default_app(str(test_file))
            mock_startfile.assert_called_once_with(os.path.abspath(test_file))


def test_open_file_mac(tmp_path):
    """Test open_file_in_default_app on macOS platform."""
    test_file = tmp_path / "test.epub"
    test_file.write_text("content")

    with patch("sys.platform", "darwin"):
        with patch("subprocess.run") as mock_run:
            open_file_in_default_app(str(test_file))
            mock_run.assert_called_once_with(["open", os.path.abspath(test_file)], check=True)


def test_open_file_linux(tmp_path):
    """Test open_file_in_default_app on Linux platform."""
    test_file = tmp_path / "test.epub"
    test_file.write_text("content")

    with patch("sys.platform", "linux"):
        with patch("subprocess.run") as mock_run:
            open_file_in_default_app(str(test_file))
            mock_run.assert_called_once_with(["xdg-open", os.path.abspath(test_file)], check=True)
