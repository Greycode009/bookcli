"""Service for managing search history in the SQLite database."""

import logging
from typing import List, Dict, Any
from bookcli.database import DatabaseManager

logger = logging.getLogger(__name__)


async def add_search_history(
    db_manager: DatabaseManager, query: str, results_count: int
) -> None:
    """Adds a search record to the search history table."""
    insert_sql = """
        INSERT INTO search_history (query, results_count)
        VALUES (?, ?)
    """
    async with db_manager.connection() as conn:
        try:
            await conn.execute(insert_sql, (query, results_count))
            await conn.commit()
            logger.debug("Logged search query '%s' with %d results to history", query, results_count)
        except Exception as e:
            logger.error("Failed to write to search history: %s", e)


async def get_search_history(
    db_manager: DatabaseManager, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieves list of search history entries, sorted by most recent first."""
    select_sql = """
        SELECT id, query, timestamp, results_count
        FROM search_history
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
    """
    async with db_manager.connection() as conn:
        try:
            async with conn.execute(select_sql, (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "query": row["query"],
                        "timestamp": row["timestamp"],
                        "results_count": row["results_count"]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error("Failed to fetch search history: %s", e)
            return []


async def clear_search_history(db_manager: DatabaseManager) -> int:
    """Clears all search history records. Returns the number of deleted records."""
    async with db_manager.connection() as conn:
        try:
            async with conn.execute("SELECT COUNT(*) FROM search_history") as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            await conn.execute("DELETE FROM search_history")
            await conn.commit()
            logger.info("Cleared search history database (%d items).", count)
            return count
        except Exception as e:
            logger.error("Failed to clear search history: %s", e)
            return 0
