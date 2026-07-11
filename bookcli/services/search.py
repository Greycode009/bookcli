"""Service coordinating concurrent search across multiple providers."""

import asyncio
import logging
from typing import List, Optional

from bookcli.config import AppConfig
from bookcli.database import DatabaseManager
from bookcli.models import BookMetadata
from bookcli.cache import save_book_to_cache
from bookcli.services.ranking import rank_and_deduplicate
from bookcli.services.history import add_search_history
from bookcli.providers.google_books import GoogleBooksProvider
from bookcli.providers.openlibrary import OpenLibraryProvider
from bookcli.providers.gutenberg import GutenbergProvider
from bookcli.providers.internet_archive import InternetArchiveProvider

logger = logging.getLogger(__name__)


async def search_books(
    query: str,
    config: AppConfig,
    db_manager: DatabaseManager,
    author: Optional[str] = None,
    isbn: Optional[str] = None,
    publisher: Optional[str] = None,
    subject: Optional[str] = None
) -> List[BookMetadata]:
    """Searches concurrently across all enabled book search providers, merges and ranks results.

    Saves results to cache and logs the search query to history.
    """
    providers = []

    # Instantiate only enabled providers
    if config.providers.google_books:
        providers.append(GoogleBooksProvider(timeout_seconds=config.timeout_seconds))
    if config.providers.openlibrary:
        providers.append(OpenLibraryProvider(timeout_seconds=config.timeout_seconds))
    if config.providers.gutenberg:
        providers.append(GutenbergProvider(timeout_seconds=config.timeout_seconds))
    if config.providers.internet_archive:
        providers.append(InternetArchiveProvider(timeout_seconds=config.timeout_seconds))

    if not providers:
        logger.warning("No search providers are enabled.")
        return []

    # Run searches concurrently
    tasks = [
        provider.search(
            query=query,
            author=author,
            isbn=isbn,
            publisher=publisher,
            subject=subject
        )
        for provider in providers
    ]

    # Gather with return_exceptions=True to avoid one provider crash blocking others
    search_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_books: List[BookMetadata] = []
    for provider, result in zip(providers, search_results):
        if isinstance(result, Exception):
            logger.error("Provider %s search failed: %s", provider.name, result)
        elif result:
            all_books.extend(result)

    # Rank and deduplicate
    ranked_books = rank_and_deduplicate(
        books=all_books,
        query=query,
        author=author,
        isbn=isbn
    )

    # Cache metadata for each book (so it can be retrieved via book info <id> or book download <id> instantly)
    # This also allows offline metadata lookup.
    cache_tasks = [save_book_to_cache(db_manager, book) for book in ranked_books]
    if cache_tasks:
        await asyncio.gather(*cache_tasks, return_exceptions=True)

    # Log to history
    try:
        await add_search_history(
            db_manager=db_manager,
            query=query or f"[author:{author or ''} isbn:{isbn or ''} pub:{publisher or ''} subj:{subject or ''}]",
            results_count=len(ranked_books)
        )
    except Exception as history_err:
        logger.error("Failed to write search history: %s", history_err)

    return ranked_books
