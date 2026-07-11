"""Unit tests for the DatabaseManager and migration system."""

import os
import tempfile
import pytest
from bookcli.database import DatabaseManager


@pytest.mark.asyncio
async def test_database_manager_initialization():
    """Test database manager creates database and runs migrations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test.db")
        db_manager = DatabaseManager(db_file)
        
        # Verify db file does not exist yet
        assert not os.path.exists(db_file)
        
        # Run initialization
        await db_manager.initialize()
        
        # Verify db file is created
        assert os.path.exists(db_file)
        
        # Test connection works and tables are created
        async with db_manager.connection() as conn:
            # Check schema version table is present
            async with conn.execute("SELECT version FROM schema_version LIMIT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 5  # Migration 5 is the latest
