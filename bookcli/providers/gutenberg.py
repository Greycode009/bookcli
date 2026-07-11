"""Project Gutenberg (via Gutendex API) provider implementation."""

import logging
from typing import List, Optional
import httpx

from bookcli.exceptions import ProviderError, DownloadError
from bookcli.models import BookMetadata
from bookcli.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class GutenbergProvider(BaseProvider):
    """Project Gutenberg provider using Gutendex API."""

    def __init__(self, timeout_seconds: int = 15):
        super().__init__(name="gutenberg", timeout_seconds=timeout_seconds)
        self.base_url = "https://gutendex.com/books/"

    def _format_author_name(self, name: str) -> str:
        """Converts 'Austen, Jane' to 'Jane Austen'."""
        if "," in name:
            parts = name.split(",", 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return name

    def _map_item_to_metadata(self, item: dict) -> BookMetadata:
        """Maps Gutendex book to BookMetadata."""
        book_id = f"gutenberg:{item.get('id')}"
        title = item.get("title", "Unknown Gutenberg Book")
        
        # Authors
        raw_authors = item.get("authors", [])
        authors = [self._format_author_name(a.get("name", "")) for a in raw_authors if a.get("name")]

        # Description
        subjects = item.get("subjects", [])
        bookshelves = item.get("bookshelves", [])
        description = f"Subjects: {', '.join(subjects)}"
        if bookshelves:
            description += f" | Bookshelves: {', '.join(bookshelves)}"

        # Languages
        languages = item.get("languages", [])
        language = languages[0] if languages else "en"

        # Formats and Cover
        formats = item.get("formats", {})
        
        # Look for cover URL
        # Gutendex formats dict can contain images:
        cover_url = None
        for fmt, url in formats.items():
            if "image/jpeg" in fmt and "cover.medium" in url:
                cover_url = url
                break
        if not cover_url:
            for fmt, url in formats.items():
                if "image/jpeg" in fmt and "cover.small" in url:
                    cover_url = url
                    break
        if not cover_url:
            # Fallback to any jpeg image in formats
            for fmt, url in formats.items():
                if "image" in fmt:
                    cover_url = url
                    break

        # Download Availability and URL
        download_available = False
        download_url = None
        file_format = None

        # Prefer epub
        epub_key = "application/epub+zip"
        txt_utf8_key = "text/plain; charset=utf-8"
        txt_us_ascii_key = "text/plain; charset=us-ascii"
        txt_key = "text/plain"

        if epub_key in formats:
            download_url = formats[epub_key]
            download_available = True
            file_format = "epub"
        elif txt_utf8_key in formats:
            download_url = formats[txt_utf8_key]
            download_available = True
            file_format = "txt"
        elif txt_us_ascii_key in formats:
            download_url = formats[txt_us_ascii_key]
            download_available = True
            file_format = "txt"
        elif txt_key in formats:
            download_url = formats[txt_key]
            download_available = True
            file_format = "txt"
        else:
            # Try to grab the first text/html or other formats
            for fmt, url in formats.items():
                if "epub" in fmt:
                    download_url = url
                    download_available = True
                    file_format = "epub"
                    break
                elif "text" in fmt:
                    download_url = url
                    download_available = True
                    file_format = "txt"
                    break

        return BookMetadata(
            id=book_id,
            title=title,
            subtitle=None,
            authors=authors,
            description=description,
            language=language,
            publisher="Project Gutenberg",
            published_year=None,  # Gutenberg works are public domain reprints
            pages=None,
            isbn=None,
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
        """Searches Project Gutenberg books using Gutendex."""
        # Gutendex supports a general search param
        params = {}
        
        # If query is provided, use search.
        # If query is empty but we have author or subject, we search that.
        search_terms = []
        if query.strip():
            search_terms.append(query.strip())
        if author:
            search_terms.append(author)
        
        if search_terms:
            params["search"] = " ".join(search_terms)

        if subject:
            params["topic"] = subject

        # ISBN is not applicable to Gutenberg books generally, but if requested, we skip or search normally.
        if isbn:
            params["search"] = isbn

        # Gutenberg publisher is always Gutenberg, so if publisher is requested and isn't gutenberg, we'd get 0 results.
        if publisher and "gutenberg" not in publisher.lower():
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code != 200:
                    raise ProviderError(f"Gutendex API returned status {response.status_code}")
                
                data = response.json()
                results = []
                for item in data.get("results", []):
                    try:
                        results.append(self._map_item_to_metadata(item))
                    except Exception as e:
                        logger.warning("Error parsing Gutendex book: %s", e)
                return results

        except httpx.RequestError as e:
            logger.error("HTTP error querying Gutendex: %s", e)
            raise ProviderError(f"Network error querying Gutendex API: {e}")
        except Exception as e:
            logger.error("Error searching Gutendex: %s", e)
            raise ProviderError(f"Gutenberg search failed: {e}")

    async def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Gets detailed metadata for a single Gutenberg book by its ID."""
        actual_id = book_id.split(":", 1)[-1]
        url = f"{self.base_url}/{actual_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise ProviderError(f"Gutendex book endpoint returned status {response.status_code}")
                
                return self._map_item_to_metadata(response.json())
        except httpx.RequestError as e:
            raise ProviderError(f"Network error getting Gutenberg book: {e}")
        except Exception as e:
            raise ProviderError(f"Gutenberg book retrieval failed: {e}")

    async def download(self, book: BookMetadata, dest_path: str) -> None:
        """Downloads the Gutenberg book. Delegates to central downloader."""
        if not book.download_availability or not book.download_url:
            raise DownloadError("No download URL available for this Gutenberg book.")
        
        # Import dynamically to avoid circular dependencies
        from bookcli.downloader import download_file
        await download_file(book.download_url, dest_path, self.timeout_seconds)
