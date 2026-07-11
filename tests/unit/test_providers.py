"""Comprehensive unit tests for the book metadata search and download providers."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from bookcli.exceptions import ProviderError, DownloadError
from bookcli.models import BookMetadata
from bookcli.providers.google_books import GoogleBooksProvider
from bookcli.providers.openlibrary import OpenLibraryProvider
from bookcli.providers.gutenberg import GutenbergProvider
from bookcli.providers.internet_archive import InternetArchiveProvider


# --- Google Books Provider Tests ---

@pytest.mark.asyncio
async def test_google_books_search_success():
    """Test successful search and parsing of Google Books volumes."""
    provider = GoogleBooksProvider()
    mock_data = {
        "items": [
            {
                "id": "abcde",
                "volumeInfo": {
                    "title": "Google Books Test Title",
                    "authors": ["Google Author"],
                    "publishedDate": "2021-05",
                    "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9781111111111"}]
                },
                "accessInfo": {
                    "epub": {"isAvailable": True, "downloadLink": "http://example.com/gb.epub"}
                }
            }
        ]
    }
    
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await provider.search("query")
        assert len(results) == 1
        book = results[0]
        assert book.id == "google:abcde"
        assert book.title == "Google Books Test Title"
        assert book.authors == ["Google Author"]
        assert book.published_year == 2021
        assert book.isbn == "9781111111111"
        assert book.download_availability is True
        assert book.download_url == "http://example.com/gb.epub"


@pytest.mark.asyncio
async def test_google_books_get_book():
    """Test single volume retrieval in Google Books."""
    provider = GoogleBooksProvider()
    mock_data = {
        "id": "abcde",
        "volumeInfo": {"title": "Single Volume Test", "authors": ["Author"]},
        "accessInfo": {}
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        book = await provider.get_book("google:abcde")
        assert book is not None
        assert book.title == "Single Volume Test"


@pytest.mark.asyncio
async def test_google_books_download():
    """Test download method on GoogleBooksProvider."""
    provider = GoogleBooksProvider()
    book_ok = BookMetadata(
        id="google:1", title="Book", authors=[], source="google_books",
        download_availability=True, download_url="http://url.com/a.epub"
    )
    book_fail = BookMetadata(
        id="google:2", title="Book", authors=[], source="google_books",
        download_availability=False
    )

    with patch("bookcli.downloader.download_file", new_callable=AsyncMock) as mock_dl:
        await provider.download(book_ok, "dest.epub")
        mock_dl.assert_called_once_with("http://url.com/a.epub", "dest.epub", 15)

        with pytest.raises(DownloadError):
            await provider.download(book_fail, "dest.epub")


# --- Open Library Provider Tests ---

@pytest.mark.asyncio
async def test_openlibrary_search_success():
    """Test successful search and parsing of Open Library works."""
    provider = OpenLibraryProvider()
    mock_data = {
        "docs": [
            {
                "key": "/works/OL1234W",
                "title": "Open Library Test Book",
                "author_name": ["OL Author"],
                "isbn": ["9782222222222"],
                "ia": ["oltestiaid"]
            }
        ]
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await provider.search("query")
        assert len(results) == 1
        book = results[0]
        assert book.id == "openlibrary:OL1234W"
        assert book.title == "Open Library Test Book"
        assert book.authors == ["OL Author"]
        assert book.isbn == "9782222222222"
        assert book.download_availability is True
        assert book.download_url == "https://archive.org/download/oltestiaid/oltestiaid.epub"


@pytest.mark.asyncio
async def test_openlibrary_get_book():
    """Test detailed Work and Edition fetching in Open Library."""
    provider = OpenLibraryProvider()
    
    # We mock multiple client.get requests:
    # 1. Work endpoint -> description, authors list
    # 2. Author endpoint -> author name
    # 3. Editions endpoint -> publishers, publish_date, ia id
    
    mock_work = {"title": "Open Library Detail", "description": {"value": "Work Description"}, "authors": [{"author": {"key": "/authors/OL123A"}}]}
    mock_author = {"name": "OL Author Name"}
    mock_editions = {"entries": [{"publishers": ["OL Publisher"], "publish_date": "January 1, 2010", "ocaid": "iaeditionid"}]}

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock(status_code=200)
        if "works/" in url and "editions" not in url:
            resp.json.return_value = mock_work
        elif "authors/" in url:
            resp.json.return_value = mock_author
        elif "editions" in url:
            resp.json.return_value = mock_editions
        else:
            resp.status_code = 404
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        book = await provider.get_book("openlibrary:OL1234W")
        assert book is not None
        assert book.title == "Open Library Detail"
        assert book.description == "Work Description"
        assert book.authors == ["OL Author Name"]
        assert book.publisher == "OL Publisher"
        assert book.published_year == 2010
        assert book.download_availability is True
        assert book.download_url == "https://archive.org/download/iaeditionid/iaeditionid.epub"


@pytest.mark.asyncio
async def test_openlibrary_download():
    """Test OpenLibraryProvider download delegation."""
    provider = OpenLibraryProvider()
    book = BookMetadata(
        id="openlibrary:1", title="OL Book", authors=[], source="openlibrary",
        download_availability=True, download_url="http://url.com/ol.epub"
    )
    with patch("bookcli.downloader.download_file", new_callable=AsyncMock) as mock_dl:
        await provider.download(book, "dest.epub")
        mock_dl.assert_called_once_with("http://url.com/ol.epub", "dest.epub", 15)


# --- Project Gutenberg Provider Tests ---

@pytest.mark.asyncio
async def test_gutenberg_search_success():
    """Test successful search and parsing of Project Gutenberg books via Gutendex."""
    provider = GutenbergProvider()
    mock_data = {
        "results": [
            {
                "id": 1342,
                "title": "Pride and Prejudice",
                "authors": [{"name": "Austen, Jane"}],
                "languages": ["en"],
                "formats": {
                    "application/epub+zip": "https://www.gutenberg.org/ebooks/1342.epub.images",
                    "image/jpeg": "https://www.gutenberg.org/cache/epub/1342/pg1342.cover.medium.jpg"
                }
            }
        ]
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await provider.search("Pride")
        assert len(results) == 1
        book = results[0]
        assert book.id == "gutenberg:1342"
        assert book.authors == ["Jane Austen"]
        assert book.download_availability is True
        assert book.download_url == "https://www.gutenberg.org/ebooks/1342.epub.images"


@pytest.mark.asyncio
async def test_gutenberg_get_book():
    """Test get_book for Gutenberg book by ID."""
    provider = GutenbergProvider()
    mock_data = {
        "id": 1342,
        "title": "Pride and Prejudice",
        "authors": [{"name": "Austen, Jane"}]
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        book = await provider.get_book("gutenberg:1342")
        assert book is not None
        assert book.title == "Pride and Prejudice"


@pytest.mark.asyncio
async def test_gutenberg_download():
    """Test GutenbergProvider download delegation."""
    provider = GutenbergProvider()
    book = BookMetadata(
        id="gutenberg:1342", title="Pride", authors=[], source="gutenberg",
        download_availability=True, download_url="http://url.com/1342.epub"
    )
    with patch("bookcli.downloader.download_file", new_callable=AsyncMock) as mock_dl:
        await provider.download(book, "dest.epub")
        mock_dl.assert_called_once_with("http://url.com/1342.epub", "dest.epub", 15)


# --- Internet Archive Provider Tests ---

@pytest.mark.asyncio
async def test_internet_archive_search_success():
    """Test successful search and parsing of Internet Archive texts."""
    provider = InternetArchiveProvider()
    mock_data = {
        "response": {
            "docs": [
                {
                    "identifier": "iatestbook",
                    "title": "Internet Archive Book",
                    "creator": ["IA Creator"],
                    "date": "2005-06-12T00:00:00Z",
                    "format": ["EPUB", "Metadata"]
                }
            ]
        }
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await provider.search("query")
        assert len(results) == 1
        book = results[0]
        assert book.id == "internet_archive:iatestbook"
        assert book.title == "Internet Archive Book"
        assert book.authors == ["IA Creator"]
        assert book.published_year == 2005
        assert book.download_availability is True
        assert book.download_url == "https://archive.org/download/iatestbook/iatestbook.epub"


@pytest.mark.asyncio
async def test_internet_archive_get_book():
    """Test get_book for Internet Archive metadata API."""
    provider = InternetArchiveProvider()
    mock_data = {
        "metadata": {"title": "IA Detail Title", "creator": "IA Creator", "date": "1999"},
        "files": [{"format": "EPUB", "name": "iatestbook.epub"}]
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        book = await provider.get_book("internet_archive:iatestbook")
        assert book is not None
        assert book.title == "IA Detail Title"
        assert book.authors == ["IA Creator"]
        assert book.published_year == 1999
        assert book.download_availability is True
        assert book.download_url == "https://archive.org/download/iatestbook/iatestbook.epub"


@pytest.mark.asyncio
async def test_internet_archive_download():
    """Test InternetArchiveProvider download delegation."""
    provider = InternetArchiveProvider()
    book = BookMetadata(
        id="internet_archive:1", title="IA Book", authors=[], source="internet_archive",
        download_availability=True, download_url="http://url.com/ia.epub"
    )
    with patch("bookcli.downloader.download_file", new_callable=AsyncMock) as mock_dl:
        await provider.download(book, "dest.epub")
        mock_dl.assert_called_once_with("http://url.com/ia.epub", "dest.epub", 15)


# --- Provider Exception Tests ---

@pytest.mark.asyncio
async def test_provider_network_error():
    """Test standard provider exception wrapping for network errors."""
    provider = GutenbergProvider()
    with patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Network Down")):
        with pytest.raises(ProviderError) as exc_info:
            await provider.search("query")
        assert "Network error querying Gutendex API" in str(exc_info.value)
