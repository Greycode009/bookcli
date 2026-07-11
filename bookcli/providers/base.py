"""Base class and interface for book search and metadata providers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from bookcli.models import BookMetadata


class BaseProvider(ABC):
    """Abstract base class representing a book metadata and search provider."""

    def __init__(self, name: str, timeout_seconds: int = 15):
        self.name = name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def search(
        self,
        query: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        publisher: Optional[str] = None,
        subject: Optional[str] = None
    ) -> List[BookMetadata]:
        """Searches the provider for books matching the search criteria.

        Args:
            query: Free-text search query.
            author: Optional author name to filter/search.
            isbn: Optional ISBN to search.
            publisher: Optional publisher to search.
            subject: Optional subject to search.

        Returns:
            A list of validated BookMetadata items.
        """
        pass

    @abstractmethod
    async def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Fetches detailed metadata for a specific book by ID.

        Args:
            book_id: Unique identifier for the book.

        Returns:
            BookMetadata if found, else None.
        """
        pass

    @abstractmethod
    async def download(self, book: BookMetadata, dest_path: str) -> None:
        """Downloads the book content to the destination path.

        Args:
            book: The BookMetadata object containing download information.
            dest_path: Location where the file will be saved.

        Raises:
            DownloadError: If download fails or is not available.
        """
        pass
