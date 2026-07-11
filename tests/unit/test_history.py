"""Unit tests for the search history service."""

import os
import tempfile
import pytest

from bookcli.database import DatabaseManager
from bookcli.services.history import (
    add_search_history,
    get_search_history,
    clear_search_history
)


@pytest.fixture
async def db_manager():
    """Provides an initialized temporary DatabaseManager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_history.db")
        manager = DatabaseManager(db_file)
        await manager.initialize()
        yield manager


@pytest.mark.asyncio
async def test_search_history_flow(db_manager):
    """Test logging searches, retrieving history and clearing history."""
    # Ensure empty history first
    history = await get_search_history(db_manager)
    assert len(history) == 0

    # Add search records
    await add_search_history(db_manager, "Atomic Habits", results_count=5)
    await add_search_history(db_manager, "Clean Code", results_count=12)

    # Retrieve history
    history = await get_search_history(db_manager)
    assert len(history) == 2
    # Verify order is descending by timestamp (most recent first)
    assert history[0]["query"] == "Clean Code"
    assert history[0]["results_count"] == 12
    assert history[1]["query"] == "Atomic Habits"
    assert history[1]["results_count"] == 5

    # Clear history
    cleared = await clear_search_history(db_manager)
    assert cleared == 2

    # Verify history is now empty
    history_after = await get_search_history(db_manager)
    assert len(history_after) == 0
