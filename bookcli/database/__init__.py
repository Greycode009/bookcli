"""Database connection and query management using aiosqlite."""

import os
import aiosqlite
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from bookcli.database.migrations import run_migrations

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections and tables initialization."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # Ensure parent directory exists
        parent_dir = os.path.dirname(db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Context manager for obtaining a database connection."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def initialize(self) -> None:
        """Runs migrations to initialize database schema."""
        await run_migrations(self.db_path)
