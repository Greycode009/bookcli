"""Database migrations for BookCLI."""

import logging
import aiosqlite

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 1: Create search_history table
    """
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        results_count INTEGER NOT NULL
    );
    """,
    # Migration 2: Create cached_books table
    """
    CREATE TABLE IF NOT EXISTS cached_books (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        json_data TEXT NOT NULL,
        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # Migration 3: Create downloads table
    """
    CREATE TABLE IF NOT EXISTS downloads (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        status TEXT NOT NULL,
        downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        checksum TEXT
    );
    """,
    # Migration 4: Create favorites table
    """
    CREATE TABLE IF NOT EXISTS favorites (
        book_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # Migration 5: Create search_results_session table for short indexing support
    """
    CREATE TABLE IF NOT EXISTS search_results_session (
        result_index INTEGER PRIMARY KEY,
        book_id TEXT NOT NULL
    );
    """
]


async def run_migrations(db_path: str) -> None:
    """Run all database migrations using aiosqlite."""
    logger.info("Running database migrations on %s...", db_path)
    async with aiosqlite.connect(db_path) as db:
        # Create a migration tracking table if it doesn't exist
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );
            """
        )
        await db.commit()

        # Get current version
        async with db.execute("SELECT version FROM schema_version LIMIT 1") as cursor:
            row = await cursor.fetchone()
            current_version = row[0] if row else 0

        logger.debug("Current DB schema version: %s", current_version)

        # Run any pending migrations
        for version, migration_sql in enumerate(MIGRATIONS, start=1):
            if version > current_version:
                logger.info("Applying migration version %s...", version)
                try:
                    await db.execute(migration_sql)
                    if current_version == 0 and version == 1:
                        await db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                    else:
                        await db.execute("UPDATE schema_version SET version = ?", (version,))
                    await db.commit()
                    current_version = version
                except Exception as e:
                    await db.rollback()
                    logger.error("Failed to apply migration %s: %s", version, e)
                    raise e

        logger.info("Database migrations completed successfully.")
