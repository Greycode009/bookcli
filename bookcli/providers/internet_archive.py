"""Internet Archive API provider implementation."""

import logging
from typing import List, Optional
import httpx

from bookcli.exceptions import ProviderError, DownloadError
from bookcli.models import BookMetadata
from bookcli.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class InternetArchiveProvider(BaseProvider):
    """Internet Archive provider using the Advanced Search and Metadata APIs."""

    def __init__(self, timeout_seconds: int = 15):
        super().__init__(name="internet_archive", timeout_seconds=timeout_seconds)
        self.search_url = "https://archive.org/advancedsearch.php"
        self.metadata_url = "https://archive.org/metadata"

    def _build_query(
        self,
        query: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        publisher: Optional[str] = None,
        subject: Optional[str] = None
    ) -> str:
        """Builds an Lucene-style search query for the Internet Archive API."""
        parts = ["mediatype:texts"]
        
        if query.strip():
            # Escape queries or keep them simple. Quoting title search terms is safer.
            parts.append(f'(title:("{query}") OR "{query}")')
        if author:
            parts.append(f'creator:("{author}")')
        if isbn:
            # IA occasionally indexes isbn under isbn field
            parts.append(f'isbn:("{isbn}")')
        if publisher:
            parts.append(f'publisher:("{publisher}")')
        if subject:
            parts.append(f'subject:("{subject}")')
            
        return " AND ".join(parts)

    def _parse_creator(self, creator_field: Optional[object]) -> List[str]:
        """Creator field in IA can be a string, a list of strings, or None."""
        if not creator_field:
            return []
        if isinstance(creator_field, list):
            return [str(c) for c in creator_field if c]
        if isinstance(creator_field, str):
            return [creator_field]
        return [str(creator_field)]

    def _parse_year(self, date_field: Optional[str]) -> Optional[int]:
        """Extracts the year from '2005-10-12T00:00:00Z' or '2005'."""
        if not date_field:
            return None
        try:
            # Take the first 4 characters
            year = date_field[:4]
            return int(year)
        except (ValueError, IndexError):
            return None

    def _map_doc_to_metadata(self, doc: dict) -> BookMetadata:
        """Maps an IA search document to BookMetadata."""
        identifier = doc.get("identifier", "")
        book_id = f"internet_archive:{identifier}"

        title = doc.get("title", "Unknown Title")
        authors = self._parse_creator(doc.get("creator"))
        publisher = doc.get("publisher")
        if isinstance(publisher, list) and publisher:
            publisher = publisher[0]

        published_year = self._parse_year(doc.get("date"))
        description = doc.get("description")
        if isinstance(description, list) and description:
            description = description[0]

        language = doc.get("language")
        if isinstance(language, list) and language:
            language = language[0]

        # Isbns (IA sometimes has list or string)
        isbn_val = doc.get("isbn")
        isbn = None
        if isbn_val:
            if isinstance(isbn_val, list):
                isbn = isbn_val[0]
            else:
                isbn = str(isbn_val)

        # Cover Image URL is standard for IA
        cover_url = f"https://archive.org/services/img/{identifier}" if identifier else None

        # Determine download availability
        # We check the 'format' field if returned
        formats = doc.get("format", [])
        if isinstance(formats, str):
            formats = [formats]

        download_available = False
        download_url = None
        file_format = None

        # Check if epub or pdf formats are present
        has_epub = any("EPUB" in fmt.upper() for fmt in formats)
        has_pdf = any("PDF" in fmt.upper() for fmt in formats)

        if has_epub:
            download_url = f"https://archive.org/download/{identifier}/{identifier}.epub"
            download_available = True
            file_format = "epub"
        elif has_pdf:
            download_url = f"https://archive.org/download/{identifier}/{identifier}.pdf"
            download_available = True
            file_format = "pdf"

        return BookMetadata(
            id=book_id,
            title=title,
            subtitle=None,
            authors=authors,
            description=description,
            language=language,
            publisher=publisher,
            published_year=published_year,
            pages=None,
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
        """Searches Internet Archive advanced search."""
        q_param = self._build_query(query, author, isbn, publisher, subject)
        if not q_param:
            return []

        params = {
            "q": q_param,
            "fl[]": [
                "identifier", "title", "creator", "publisher",
                "date", "language", "description", "isbn", "format"
            ],
            "rows": 20,
            "output": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.search_url, params=params)
                if response.status_code != 200:
                    raise ProviderError(f"Internet Archive API returned status {response.status_code}")
                
                data = response.json()
                response_data = data.get("response", {})
                docs = response_data.get("docs", [])

                results = []
                for doc in docs:
                    try:
                        results.append(self._map_doc_to_metadata(doc))
                    except Exception as e:
                        logger.warning("Error parsing Internet Archive doc: %s", e)
                return results

        except httpx.RequestError as e:
            logger.error("HTTP error searching Internet Archive: %s", e)
            raise ProviderError(f"Network error querying Internet Archive: {e}")
        except Exception as e:
            logger.error("Error searching Internet Archive: %s", e)
            raise ProviderError(f"Internet Archive search failed: {e}")

    async def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Gets detailed metadata from the IA Metadata API."""
        actual_id = book_id.split(":", 1)[-1]
        url = f"{self.metadata_url}/{actual_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise ProviderError(f"Internet Archive Metadata API returned status {response.status_code}")
                
                data = response.json()
                metadata = data.get("metadata", {})
                
                # Formats are in 'files' list in metadata API
                files = data.get("files", [])
                formats = [f.get("format", "") for f in files if f.get("format")]

                # Construct standard doc for mapping
                doc = {
                    "identifier": actual_id,
                    "title": metadata.get("title", ["Unknown Title"])[0] if isinstance(metadata.get("title"), list) else metadata.get("title"),
                    "creator": metadata.get("creator"),
                    "publisher": metadata.get("publisher"),
                    "date": metadata.get("date", [""])[0] if isinstance(metadata.get("date"), list) else metadata.get("date"),
                    "language": metadata.get("language"),
                    "description": metadata.get("description"),
                    "isbn": metadata.get("isbn"),
                    "format": formats
                }

                book = self._map_doc_to_metadata(doc)

                # Override guessed download URL with exact filename from metadata
                epub_name = None
                pdf_name = None
                for f in files:
                    name = f.get("name", "")
                    fmt = f.get("format", "").upper()
                    if "EPUB" in fmt and name.lower().endswith(".epub"):
                        epub_name = name
                    elif "PDF" in fmt and name.lower().endswith(".pdf"):
                        pdf_name = name

                import urllib.parse
                if epub_name:
                    safe_name = urllib.parse.quote(epub_name)
                    book.download_url = f"https://archive.org/download/{actual_id}/{safe_name}"
                    book.download_availability = True
                    book.file_format = "epub"
                elif pdf_name:
                    safe_name = urllib.parse.quote(pdf_name)
                    book.download_url = f"https://archive.org/download/{actual_id}/{safe_name}"
                    book.download_availability = True
                    book.file_format = "pdf"
                else:
                    book.download_url = None
                    book.download_availability = False
                    book.file_format = None

                return book

        except httpx.RequestError as e:
            raise ProviderError(f"Network error getting IA metadata: {e}")
        except Exception as e:
            raise ProviderError(f"Internet Archive metadata retrieval failed: {e}")

    async def download(self, book: BookMetadata, dest_path: str) -> None:
        """Downloads the Internet Archive book. Delegates to central downloader."""
        if not book.download_availability or not book.download_url:
            raise DownloadError("No download URL available for this Internet Archive book.")
        
        # Import dynamically to avoid circular dependencies
        from bookcli.downloader import download_file
        await download_file(book.download_url, dest_path, self.timeout_seconds)
