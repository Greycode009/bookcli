"""Unit tests for the metadata caching system."""

import os
import tempfile
import pytest
from datetime import datetime, timedelta, timezone

from bookcli.database import DatabaseManager
from bookcli.models import BookMetadata
from bookcli.cache import (
    get_book_from_cache,
    save_book_to_cache,
    clear_cache_db,
    get_cache_db_stats
)


@pytest.fixture
async def db_manager():
    """Provides an initialized temporary DatabaseManager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_cache.db")
        manager = DatabaseManager(db_file)
        await manager.initialize()
        yield manager


@pytest.mark.asyncio
async def test_cache_save_and_retrieve(db_manager):
    """Test saving a book to cache and retrieving it within TTL."""
    book = BookMetadata(
        id="gutenberg:9999",
        title="Cache Test Book",
        authors=["Author One", "Author Two"],
        published_year=2020,
        source="gutenberg",
        download_availability=True,
        download_url="http://example.com/cache.epub",
        file_format="epub"
    )

    # Save to cache
    await save_book_to_cache(db_manager, book)

    # Retrieve from cache
    cached = await get_book_from_cache(db_manager, "gutenberg:9999", ttl_seconds=100)
    assert cached is not None
    assert cached.title == "Cache Test Book"
    assert cached.authors == ["Author One", "Author Two"]
    assert cached.download_url == "http://example.com/cache.epub"


@pytest.mark.asyncio
async def test_cache_expiry(db_manager):
    """Test cached books expire after TTL."""
    book = BookMetadata(
        id="gutenberg:1010",
        title="Expired Book",
        authors=["Author"],
        source="gutenberg"
    )

    await save_book_to_cache(db_manager, book)

    # Retrieve with TTL = -1 (guaranteed to expire)
    cached = await get_book_from_cache(db_manager, "gutenberg:1010", ttl_seconds=-1)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_clear_and_stats(db_manager):
    """Test clearing cache and cache stats functions."""
    book1 = BookMetadata(id="gutenberg:1", title="Book 1", source="gutenberg")
    book2 = BookMetadata(id="gutenberg:2", title="Book 2", source="gutenberg")

    await save_book_to_cache(db_manager, book1)
    await save_book_to_cache(db_manager, book2)

    # Check stats
    stats = await get_cache_db_stats(db_manager)
    assert stats["total_items"] == 2

    # Clear cache
    cleared = await clear_cache_db(db_manager)
    assert cleared == 2

    # Check stats after clear
    stats_after = await get_cache_db_stats(db_manager)
    assert stats_after["total_items"] == 0
