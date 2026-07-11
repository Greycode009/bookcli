"""Unit tests for the concurrent search service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from bookcli.config import AppConfig, ProvidersConfig
from bookcli.database import DatabaseManager
from bookcli.models import BookMetadata
from bookcli.services.search import search_books


@pytest.fixture
def mock_config():
    """Provides a default AppConfig mock with all providers enabled."""
    return AppConfig(
        download_dir="/tmp/download",
        cache_ttl_seconds=3600,
        timeout_seconds=5,
        theme="dark",
        providers=ProvidersConfig(
            google_books=True,
            openlibrary=True,
            gutenberg=True,
            internet_archive=True
        )
    )


@pytest.fixture
def mock_db_manager():
    """Provides a mocked DatabaseManager."""
    manager = MagicMock(spec=DatabaseManager)
    # Mock database context connection
    mock_conn = AsyncMock()
    manager.connection.return_value.__aenter__.return_value = mock_conn
    return manager


@pytest.mark.asyncio
async def test_search_books_coordinates_providers(mock_config, mock_db_manager):
    """Test search_books executes searches concurrently and caches/history-logs results."""
    mock_book = BookMetadata(
        id="gutenberg:123",
        title="Concurrent Search Title",
        authors=["Author"],
        source="gutenberg",
        download_availability=True
    )

    # Patch providers search methods to return mock book
    with patch("bookcli.providers.google_books.GoogleBooksProvider.search", new_callable=AsyncMock, return_value=[mock_book]) as mock_gb_search, \
         patch("bookcli.providers.openlibrary.OpenLibraryProvider.search", new_callable=AsyncMock, return_value=[]) as mock_ol_search, \
         patch("bookcli.providers.gutenberg.GutenbergProvider.search", new_callable=AsyncMock, return_value=[mock_book]) as mock_gut_search, \
         patch("bookcli.providers.internet_archive.InternetArchiveProvider.search", new_callable=AsyncMock, return_value=[]) as mock_ia_search, \
         patch("bookcli.services.search.save_book_to_cache", new_callable=AsyncMock) as mock_save_cache, \
         patch("bookcli.services.search.add_search_history", new_callable=AsyncMock) as mock_add_hist:

        results = await search_books(
            query="Concurrent Search",
            config=mock_config,
            db_manager=mock_db_manager
        )

        # Assert each provider's search was called
        mock_gb_search.assert_called_once_with(query="Concurrent Search", author=None, isbn=None, publisher=None, subject=None)
        mock_ol_search.assert_called_once_with(query="Concurrent Search", author=None, isbn=None, publisher=None, subject=None)
        mock_gut_search.assert_called_once_with(query="Concurrent Search", author=None, isbn=None, publisher=None, subject=None)
        mock_ia_search.assert_called_once_with(query="Concurrent Search", author=None, isbn=None, publisher=None, subject=None)

        # Assert results are ranked/deduplicated (we returned 2 duplicates of same book, should merge to 1)
        assert len(results) == 1
        assert results[0].title == "Concurrent Search Title"

        # Assert caching was triggered
        assert mock_save_cache.call_count == 1

        # Assert search history logging was triggered
        mock_add_hist.assert_called_once()


@pytest.mark.asyncio
async def test_search_books_no_providers_enabled(mock_config, mock_db_manager):
    """Test search_books returns empty list when all providers are disabled."""
    mock_config.providers.google_books = False
    mock_config.providers.openlibrary = False
    mock_config.providers.gutenberg = False
    mock_config.providers.internet_archive = False

    results = await search_books(
        query="query",
        config=mock_config,
        db_manager=mock_db_manager
    )
    assert len(results) == 0
