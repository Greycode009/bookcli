"""Metadata cache using SQLite for BookCLI."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from bookcli.database import DatabaseManager
from bookcli.models import BookMetadata

logger = logging.getLogger(__name__)


async def get_book_from_cache(
    db_manager: DatabaseManager, book_id: str, ttl_seconds: int
) -> Optional[BookMetadata]:
    """Retrieves a book from the cache if it exists and has not expired."""
    query = "SELECT json_data, cached_at FROM cached_books WHERE id = ?"
    async with db_manager.connection() as conn:
        async with conn.execute(query, (book_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            json_data, cached_at_str = row[0], row[1]
            try:
                # SQLite datetime strings are stored in ISO format
                # Parse timestamp: 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS...'
                # We can replace ' ' with 'T' if needed, or use fromisoformat.
                # In standard SQLite datetime, it might not contain 'T', let's format it.
                if "T" not in cached_at_str:
                    # e.g., '2026-07-11 04:53:00'
                    cached_at = datetime.strptime(cached_at_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
                else:
                    # e.g., ISO format
                    cached_at = datetime.fromisoformat(cached_at_str)

                # Convert to naive or timezone-aware matching
                # Since datetime.now(timezone.utc) is timezone aware, let's make cached_at UTC aware.
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)

                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age > ttl_seconds:
                    logger.debug("Cache expired for book ID %s (age: %s seconds)", book_id, age)
                    # We could delete it, but simple overwrite on set is fine, or we can delete it now
                    await conn.execute("DELETE FROM cached_books WHERE id = ?", (book_id,))
                    await conn.commit()
                    return None

                data = json.loads(json_data)
                return BookMetadata(**data)
            except Exception as e:
                logger.error("Failed to parse cached book %s: %s", book_id, e)
                return None


async def save_book_to_cache(db_manager: DatabaseManager, book: BookMetadata) -> None:
    """Saves a book to the SQLite cache, overwriting if it already exists."""
    query = """
        INSERT OR REPLACE INTO cached_books (id, provider, json_data, cached_at)
        VALUES (?, ?, ?, ?)
    """
    async with db_manager.connection() as conn:
        try:
            # Save date in standard ISO format with timezone (UTC)
            now_str = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                query,
                (book.id, book.source, book.model_dump_json(), now_str)
            )
            await conn.commit()
            logger.debug("Saved book %s to cache", book.id)
        except Exception as e:
            logger.error("Failed to write book %s to cache: %s", book.id, e)


async def clear_cache_db(db_manager: DatabaseManager) -> int:
    """Clears all cached books. Returns the number of rows deleted."""
    async with db_manager.connection() as conn:
        async with conn.execute("SELECT COUNT(*) FROM cached_books") as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0

        await conn.execute("DELETE FROM cached_books")
        await conn.commit()
        logger.info("Cleared cached metadata database (%d items).", count)
        return count


async def get_cache_db_stats(db_manager: DatabaseManager) -> dict:
    """Gets metadata cache statistics."""
    async with db_manager.connection() as conn:
        async with conn.execute("SELECT COUNT(*), MIN(cached_at), MAX(cached_at) FROM cached_books") as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0
            oldest = row[1] if row and row[1] else "N/A"
            newest = row[2] if row and row[2] else "N/A"

        return {
            "total_items": count,
            "oldest_item": oldest,
            "newest_item": newest
        }
