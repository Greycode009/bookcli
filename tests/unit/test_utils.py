"""Unit tests for formatting and utility helpers."""

from bookcli.utils import format_size, format_speed, clean_filename


def test_format_size():
    """Test format_size formatting correctness."""
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024 * 1.5) == "1.50 MB"
    assert format_size(1024 * 1024 * 1024 * 2.25) == "2.25 GB"


def test_format_speed():
    """Test format_speed formatting correctness."""
    assert format_speed(100) == "100 B/s"
    assert format_speed(2048) == "2.00 KB/s"


def test_clean_filename():
    """Test clean_filename removes dangerous characters and format spaces."""
    assert clean_filename("Hello World!") == "Hello_World"
    assert clean_filename("Pride & Prejudice/1") == "Pride__Prejudice1"
    # Test length limitation
    long_title = "a" * 150
    assert len(clean_filename(long_title)) == 100
