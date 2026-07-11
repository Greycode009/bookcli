"""Open Library API provider implementation."""

import logging
from typing import List, Optional
import httpx

from bookcli.exceptions import ProviderError, DownloadError
from bookcli.models import BookMetadata
from bookcli.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class OpenLibraryProvider(BaseProvider):
    """Open Library API provider."""

    def __init__(self, timeout_seconds: int = 15):
        super().__init__(name="openlibrary", timeout_seconds=timeout_seconds)
        self.search_url = "https://openlibrary.org/search.json"

    def _map_doc_to_metadata(self, doc: dict) -> BookMetadata:
        """Maps Open Library search document to BookMetadata."""
        work_key = doc.get("key", "")
        # Standardize ID: openlibrary:OL123W
        book_id = f"openlibrary:{work_key.split('/')[-1]}"

        title = doc.get("title", "Unknown Title")
        subtitle = doc.get("subtitle")
        authors = doc.get("author_name", [])
        
        # Publishers (Open Library returns a list)
        publishers = doc.get("publisher", [])
        publisher = publishers[0] if publishers else None

        published_year = doc.get("first_publish_year")
        pages = doc.get("number_of_pages_median")

        # Languages (Open Library returns ISO codes in list, e.g. ['eng'])
        languages = doc.get("language", [])
        language = languages[0] if languages else None

        # ISBN list
        isbns = doc.get("isbn", [])
        isbn = isbns[0] if isbns else None

        # Cover Image URL
        cover_i = doc.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else None

        # Internet Archive IDs (ia) for downloads
        ia_list = doc.get("ia", [])
        download_available = False
        download_url = None
        file_format = None

        if ia_list:
            # We filter out items that don't look like standard IA IDs (e.g. starting with markers like 'lending')
            valid_ia = [ia for ia in ia_list if not ia.startswith("lending:")]
            if valid_ia:
                ia_id = valid_ia[0]
                # Default to epub for IA download
                download_url = f"https://archive.org/download/{ia_id}/{ia_id}.epub"
                download_available = True
                file_format = "epub"

        return BookMetadata(
            id=book_id,
            title=title,
            subtitle=subtitle,
            authors=authors,
            description=None,  # Search endpoint doesn't return full description; get_book will fetch it
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
        """Searches Open Library."""
        params = {}
        if query.strip():
            params["q"] = query.strip()
        if author:
            params["author"] = author
        if isbn:
            params["isbn"] = isbn
        if publisher:
            params["publisher"] = publisher
        if subject:
            params["subject"] = subject

        if not params:
            return []

        params["limit"] = 20

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.search_url, params=params)
                if response.status_code != 200:
                    raise ProviderError(f"Open Library API returned status {response.status_code}")

                data = response.json()
                docs = data.get("docs", [])
                
                results = []
                for doc in docs:
                    try:
                        results.append(self._map_doc_to_metadata(doc))
                    except Exception as e:
                        logger.warning("Error parsing Open Library doc: %s", e)
                return results

        except httpx.RequestError as e:
            logger.error("HTTP error searching Open Library: %s", e)
            raise ProviderError(f"Network error querying Open Library API: {e}")
        except Exception as e:
            logger.error("Error searching Open Library: %s", e)
            raise ProviderError(f"Open Library search failed: {e}")

    async def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Fetches details for a single work from Open Library."""
        actual_id = book_id.split(":", 1)[-1]
        
        # Work URL (fetch the work JSON, e.g. /works/OL123W.json)
        work_url = f"https://openlibrary.org/works/{actual_id}.json"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Fetch detailed Work JSON
                work_response = await client.get(work_url)
                if work_response.status_code == 404:
                    return None
                if work_response.status_code != 200:
                    raise ProviderError(f"Open Library work endpoint returned {work_response.status_code}")
                
                work_data = work_response.json()

                # Get description
                description = None
                desc_field = work_data.get("description")
                if isinstance(desc_field, dict):
                    description = desc_field.get("value")
                elif isinstance(desc_field, str):
                    description = desc_field

                # Get authors (works only contain references to author keys, e.g. {"author": {"key": "/authors/OL123A"}})
                authors = []
                for auth_entry in work_data.get("authors", []):
                    auth_key = auth_entry.get("author", {}).get("key")
                    if auth_key:
                        # Fetch author detail to get name
                        auth_response = await client.get(f"https://openlibrary.org{auth_key}.json")
                        if auth_response.status_code == 200:
                            authors.append(auth_response.json().get("name", ""))

                # Fetch editions to find pages, publisher, ISBN, cover, and downloads
                # /works/OL123W/editions.json
                editions_url = f"https://openlibrary.org/works/{actual_id}/editions.json"
                editions_response = await client.get(editions_url)
                
                publisher = None
                published_year = None
                pages = None
                isbn = None
                cover_url = None
                download_available = False
                download_url = None
                file_format = None

                if editions_response.status_code == 200:
                    editions_data = editions_response.json()
                    entries = editions_data.get("entries", [])
                    
                    if entries:
                        # Check the first edition with details
                        first_ed = entries[0]
                        
                        publishers = first_ed.get("publishers", [])
                        publisher = publishers[0] if publishers else None

                        pub_date = first_ed.get("publish_date")
                        if pub_date:
                            # Try parsing year
                            try:
                                published_year = int(pub_date.split()[-1])
                            except ValueError:
                                pass

                        pages = first_ed.get("number_of_pages")
                        
                        isbns = first_ed.get("isbn_13", []) or first_ed.get("isbn_10", [])
                        isbn = isbns[0] if isbns else None

                        # Cover URL if present
                        covers = first_ed.get("covers", [])
                        if covers:
                            cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"

                        # Internet Archive IDs
                        ia_list = first_ed.get("ocaid") or first_ed.get("ia", [])
                        if isinstance(ia_list, str):
                            ia_list = [ia_list]
                        
                        if ia_list:
                            valid_ia = [ia for ia in ia_list if not ia.startswith("lending:")]
                            if valid_ia:
                                ia_id = valid_ia[0]
                                download_url = f"https://archive.org/download/{ia_id}/{ia_id}.epub"
                                download_available = True
                                file_format = "epub"

                return BookMetadata(
                    id=book_id,
                    title=work_data.get("title", "Unknown Title"),
                    subtitle=work_data.get("subtitle"),
                    authors=authors,
                    description=description,
                    language=None,
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

        except httpx.RequestError as e:
            raise ProviderError(f"Network error getting Open Library Work: {e}")
        except Exception as e:
            raise ProviderError(f"Open Library Work retrieval failed: {e}")

    async def download(self, book: BookMetadata, dest_path: str) -> None:
        """Downloads the Open Library Book. Delegates to central downloader."""
        if not book.download_availability or not book.download_url:
            raise DownloadError("No legal download URL available for this Open Library book.")
        
        # Import dynamically to avoid circular dependencies
        from bookcli.downloader import download_file
        await download_file(book.download_url, dest_path, self.timeout_seconds)
