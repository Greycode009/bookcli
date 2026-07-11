"""General utility helper functions for formatting and CLI presentation."""

from typing import Union


def format_size(size_in_bytes: Union[int, float]) -> str:
    """Formats raw byte sizes into human-readable strings (KB, MB, GB)."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bytes_per_second: Union[int, float]) -> str:
    """Formats transfer speed into human-readable strings (KB/s, MB/s)."""
    return f"{format_size(bytes_per_second)}/s"


def clean_filename(title: str) -> str:
    """Cleans a string to make it safe for a filename."""
    # Strip non-alphanumeric, spaces, underscores, dashes
    cleaned = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip()
    # Replace spaces with underscores
    cleaned = cleaned.replace(" ", "_")
    # Limit length
    return cleaned[:100]
