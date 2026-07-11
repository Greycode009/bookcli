"""Google Books API provider implementation."""

import logging
from typing import List, Optional
import httpx

from bookcli.exceptions import ProviderError, DownloadError
from bookcli.models import BookMetadata
from bookcli.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class GoogleBooksProvider(BaseProvider):
    """Google Books API provider."""

    def __init__(self, timeout_seconds: int = 15):
        super().__init__(name="google_books", timeout_seconds=timeout_seconds)
        self.base_url = "https://www.googleapis.com/books/v1/volumes"

    def _build_query(
        self,
        query: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        publisher: Optional[str] = None,
        subject: Optional[str] = None
    ) -> str:
        """Constructs the Google Books 'q' parameter query string."""
        parts = []
        if query.strip():
            parts.append(query.strip())
        if author:
            parts.append(f"inauthor:{author}")
        if isbn:
            parts.append(f"isbn:{isbn}")
        if publisher:
            parts.append(f"inpublisher:{publisher}")
        if subject:
            parts.append(f"subject:{subject}")
        return " ".join(parts)

    def _parse_published_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extracts the year from a Google Books publishedDate (e.g. '2016-11' or '2016')."""
        if not date_str:
            return None
        try:
            year_part = date_str.split("-")[0]
            return int(year_part)
        except (ValueError, IndexError):
            return None

    def _parse_isbn(self, identifiers: Optional[List[dict]]) -> Optional[str]:
        """Finds the ISBN_13 or ISBN_10 from the industry identifiers list."""
        if not identifiers:
            return None
        # Prefer ISBN_13
        for ident in identifiers:
            if ident.get("type") == "ISBN_13":
                return ident.get("identifier")
        # Fallback to ISBN_10
        for ident in identifiers:
            if ident.get("type") == "ISBN_10":
                return ident.get("identifier")
        # Fallback to any identifier
        if identifiers:
            return identifiers[0].get("identifier")
        return None

    def _map_volume_to_metadata(self, item: dict) -> BookMetadata:
        """Maps Google Books API volume resource to BookMetadata model."""
        volume_info = item.get("volumeInfo", {})
        access_info = item.get("accessInfo", {})

        book_id = f"google:{item.get('id')}"
        title = volume_info.get("title", "Unknown Title")
        subtitle = volume_info.get("subtitle")
        authors = volume_info.get("authors", [])
        description = volume_info.get("description")
        language = volume_info.get("language")
        publisher = volume_info.get("publisher")
        published_year = self._parse_published_year(volume_info.get("publishedDate"))
        pages = volume_info.get("pageCount")
        isbn = self._parse_isbn(volume_info.get("industryIdentifiers"))

        image_links = volume_info.get("imageLinks", {})
        # Prefer thumbnail, then smallThumbnail
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")

        # Determine download availability and format
        # Check if direct download is allowed legally (public domain or explicitly free)
        download_available = False
        download_url = None
        file_format = None

        epub_info = access_info.get("epub", {})
        pdf_info = access_info.get("pdf", {})

        # If epub download link is available
        if epub_info.get("isAvailable") and epub_info.get("downloadLink"):
            download_available = True
            download_url = epub_info.get("downloadLink")
            file_format = "epub"
        # Otherwise, check pdf
        elif pdf_info.get("isAvailable") and pdf_info.get("downloadLink"):
            download_available = True
            download_url = pdf_info.get("downloadLink")
            file_format = "pdf"

        # Double check viewability / public domain
        # If publicDomain is True, but there's no downloadLink, sometimes viewability allows reading
        # But we only want to support downloading actual files.
        # So we stick to epub/pdf downloadLink availability.

        return BookMetadata(
            id=book_id,
            title=title,
            subtitle=subtitle,
            authors=authors,
            description=description,
            language=language,
            publisher=publisher,
            published_year=published_year,
            pages=pages,
            isbn=isbn,
            cover_url=cover_url,
            download_url=download_url,
            source=self.name,
            download_availability=download_available,
            file_format=file_format
        )

    async def search(
        self,
        query: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        publisher: Optional[str] = None,
        subject: Optional[str] = None
    ) -> List[BookMetadata]:
        """Searches Google Books API."""
        q_param = self._build_query(query, author, isbn, publisher, subject)
        if not q_param:
            return []

        params = {
            "q": q_param,
            "maxResults": 20,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code != 200:
                    raise ProviderError(f"Google Books API returned status {response.status_code}")
                
                data = response.json()
                items = data.get("items", [])
                
                results = []
                for item in items:
                    try:
                        results.append(self._map_volume_to_metadata(item))
                    except Exception as parse_err:
                        logger.warning("Error parsing Google Book volume: %s", parse_err)
                return results

        except httpx.RequestError as e:
            logger.error("HTTP error searching Google Books: %s", e)
            raise ProviderError(f"Network error querying Google Books API: {e}")
        except Exception as e:
            logger.error("Error searching Google Books: %s", e)
            raise ProviderError(f"Google Books search failed: {e}")

    async def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Fetches detailed volume metadata by volume ID."""
        # Strips prefix e.g., google:abcde -> abcde
        actual_id = book_id.split(":", 1)[-1]
        url = f"{self.base_url}/{actual_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise ProviderError(f"Google Books API returned status {response.status_code}")
                
                return self._map_volume_to_metadata(response.json())
        except httpx.RequestError as e:
            raise ProviderError(f"Network error getting Google Book: {e}")
        except Exception as e:
            raise ProviderError(f"Google Books retrieval failed: {e}")

    async def download(self, book: BookMetadata, dest_path: str) -> None:
        """Downloads the Google Book. Delegates to central downloader."""
        if not book.download_availability or not book.download_url:
            raise DownloadError("No legal download URL available for this Google Book.")
        
        # Import dynamically to avoid circular dependencies
        from bookcli.downloader import download_file
        await download_file(book.download_url, dest_path, self.timeout_seconds)
