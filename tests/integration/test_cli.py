"""Integration tests for the BookCLI commands using CliRunner."""

import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from typer.testing import CliRunner

from bookcli.cli import app
from bookcli.models import BookMetadata
from bookcli.database import DatabaseManager

runner = CliRunner()


@pytest.fixture(autouse=True)
def temp_db_and_config():
    """Redirect DB_PATH and CONFIG_PATH to temporary locations for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_db = Path(tmpdir) / "test_bookcli.db"
        temp_cfg = Path(tmpdir) / "test_config.json"
        temp_dl = Path(tmpdir) / "test_downloads"
        temp_dl.mkdir(parents=True, exist_ok=True)

        with patch("bookcli.cli.DB_PATH", temp_db), \
             patch("bookcli.settings.DB_PATH", temp_db), \
             patch("bookcli.settings.CONFIG_PATH", temp_cfg), \
             patch("bookcli.config.CONFIG_PATH", temp_cfg), \
             patch("bookcli.settings.DEFAULT_DOWNLOAD_DIR", temp_dl):
            yield


def test_config_command():
    """Test the config list command runs and shows correct outputs."""
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "BookCLI Current Configuration" in result.stdout
    assert "Download Directory" in result.stdout


def test_config_set_command():
    """Test changing config parameters via CLI config set."""
    result = runner.invoke(app, ["config", "set", "theme", "light"])
    assert result.exit_code == 0
    assert "Successfully updated configuration setting 'theme' to 'light'" in result.stdout

    # Verify change is reflected
    result_list = runner.invoke(app, ["config"])
    assert "light" in result_list.stdout


@patch("bookcli.cli.search_books", new_callable=AsyncMock)
def test_search_and_info_flow(mock_search_books):
    """Test the search -> session table mapping -> info command integration flow."""
    mock_book = BookMetadata(
        id="gutenberg:1234",
        title="Integration Testing Book",
        authors=["Testy McTest"],
        published_year=2026,
        source="gutenberg",
        download_availability=True,
        download_url="https://example.com/test.epub",
        file_format="epub",
        description="A book for integration tests."
    )
    mock_search_books.return_value = [mock_book]

    # 1. Run search command
    search_result = runner.invoke(app, ["search", "Integration Testing"])
    assert search_result.exit_code == 0
    assert "Integration Testing Book" in search_result.stdout
    assert "1" in search_result.stdout

    # 2. Run info command with the resolved numeric index 1
    with patch("bookcli.cli.get_book_from_cache", new_callable=AsyncMock, return_value=mock_book):
        info_result = runner.invoke(app, ["info", "1"])
        assert info_result.exit_code == 0
        assert "Book Details: gutenberg:1234" in info_result.stdout
        assert "Integration Testing Book" in info_result.stdout


def test_cache_commands():
    """Test clearing and retrieving stats from the cache command."""
    stats_result = runner.invoke(app, ["cache", "stats"])
    assert stats_result.exit_code == 0
    assert "Metadata Cache Statistics" in stats_result.stdout

    clear_result = runner.invoke(app, ["cache", "clear"])
    assert clear_result.exit_code == 0
    assert "Metadata cache cleared" in clear_result.stdout


def test_history_command():
    """Test history command retrieves recorded searches."""
    from bookcli.settings import DB_PATH
    db_manager = DatabaseManager(str(DB_PATH))
    
    async def setup_history():
        await db_manager.initialize()
        from bookcli.services.history import add_search_history
        await add_search_history(db_manager, "HistoryQuery", results_count=3)
        
    import asyncio
    asyncio.run(setup_history())

    # Run history command
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "HistoryQuery" in result.stdout


def test_favorite_commands():
    """Test adding, listing, and removing favorites."""
    mock_book = BookMetadata(
        id="gutenberg:777",
        title="Favorite Book Title",
        authors=["Fav Author"],
        source="gutenberg",
        download_availability=False
    )

    # 1. Prepare search session mapping in database
    from bookcli.settings import DB_PATH
    db_manager = DatabaseManager(str(DB_PATH))
    
    async def setup_session():
        await db_manager.initialize()
        from bookcli.cache import save_book_to_cache
        await save_book_to_cache(db_manager, mock_book)
        async with db_manager.connection() as conn:
            await conn.execute("INSERT INTO search_results_session (result_index, book_id) VALUES (1, 'gutenberg:777')")
            await conn.commit()
            
    import asyncio
    asyncio.run(setup_session())

    # 2. Add to favorites
    add_result = runner.invoke(app, ["favorite", "add", "1"])
    assert add_result.exit_code == 0
    assert "Added 'Favorite Book Title' to favorites" in add_result.stdout

    # 3. List favorites
    list_result = runner.invoke(app, ["favorite", "list"])
    assert list_result.exit_code == 0
    assert "Favorite Book Title" in list_result.stdout

    # 4. Remove from favorites
    remove_result = runner.invoke(app, ["favorite", "remove", "1"])
    assert remove_result.exit_code == 0
    assert "Removed 'Favorite Book Title' from favorites" in remove_result.stdout


def test_download_and_open_commands():
    """Test download and open commands integration."""
    mock_book = BookMetadata(
        id="gutenberg:888",
        title="Downloadable Book",
        authors=["Author"],
        source="gutenberg",
        download_availability=True,
        download_url="https://example.com/dl.epub",
        file_format="epub"
    )

    from bookcli.settings import DB_PATH
    db_manager = DatabaseManager(str(DB_PATH))

    async def setup_session():
        await db_manager.initialize()
        from bookcli.cache import save_book_to_cache
        await save_book_to_cache(db_manager, mock_book)
        async with db_manager.connection() as conn:
            await conn.execute("INSERT INTO search_results_session (result_index, book_id) VALUES (1, 'gutenberg:888')")
            await conn.commit()

    import asyncio
    asyncio.run(setup_session())

    # Define mock download side effect to write a dummy file so os.path.getsize succeeds
    async def mock_download_side_effect(url, dest_path, timeout):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write("dummy content")
        return "mock_checksum_hash"

    # Mock central file downloader
    with patch("bookcli.downloader.download_file", new_callable=AsyncMock, side_effect=mock_download_side_effect), \
         patch("bookcli.cli.open_file_in_default_app") as mock_open:
        
        # 1. Download
        dl_result = runner.invoke(app, ["download", "1"])
        assert dl_result.exit_code == 0
        assert "Successfully downloaded!" in dl_result.stdout
        assert "SHA256 Checksum: mock_checksum_hash" in dl_result.stdout

        # 2. Open
        open_result = runner.invoke(app, ["open", "1"])
        assert open_result.exit_code == 0
        assert "Opening file" in open_result.stdout
        mock_open.assert_called_once()


def test_download_custom_path():
    """Test downloading a book to a custom output path (both directory and specific filename)."""
    mock_book = BookMetadata(
        id="gutenberg:999",
        title="Custom Path Book",
        authors=["Author"],
        source="gutenberg",
        download_availability=True,
        download_url="https://example.com/custom.epub",
        file_format="epub"
    )

    from bookcli.settings import DB_PATH
    db_manager = DatabaseManager(str(DB_PATH))

    async def setup_session():
        await db_manager.initialize()
        from bookcli.cache import save_book_to_cache
        await save_book_to_cache(db_manager, mock_book)
        async with db_manager.connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO search_results_session (result_index, book_id) VALUES (1, 'gutenberg:999')")
            await conn.commit()

    import asyncio
    asyncio.run(setup_session())

    async def mock_download_side_effect(url, dest_path, timeout):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write("dummy content")
        return "mock_checksum_hash"

    with patch("bookcli.downloader.download_file", new_callable=AsyncMock, side_effect=mock_download_side_effect):
        with tempfile.TemporaryDirectory() as tmp_dl_dir:
            # 1. Test downloading to a custom directory (ends with slash)
            custom_dir = os.path.join(tmp_dl_dir, "new_folder") + "/"
            dl_result = runner.invoke(app, ["download", "1", "-o", custom_dir])
            assert dl_result.exit_code == 0
            assert "Successfully downloaded!" in dl_result.stdout
            
            # The destination filename should be based on the clean book title and ID
            expected_filename = "Custom_Path_Book_gutenberg_999.epub"
            expected_filepath = os.path.join(tmp_dl_dir, "new_folder", expected_filename)
            assert os.path.exists(expected_filepath)

            # 2. Test downloading to a custom directory (no suffix)
            custom_dir2 = os.path.join(tmp_dl_dir, "new_folder2")
            dl_result2 = runner.invoke(app, ["download", "1", "-o", custom_dir2])
            assert dl_result2.exit_code == 0
            assert "Successfully downloaded!" in dl_result2.stdout
            expected_filepath_dir2 = os.path.join(tmp_dl_dir, "new_folder2", expected_filename)
            assert os.path.exists(expected_filepath_dir2)

            # 3. Test downloading to an exact file path (ends with suffix)
            custom_filepath = os.path.join(tmp_dl_dir, "another_folder", "specified_name.epub")
            dl_result3 = runner.invoke(app, ["download", "1", "-o", custom_filepath])
            assert dl_result3.exit_code == 0
            assert "Successfully downloaded!" in dl_result3.stdout
            assert os.path.exists(custom_filepath)


def test_config_validation_errors():
    """Test configuration validation error messages."""
    res = runner.invoke(app, ["config", "set", "cache-ttl", "not-an-integer"])
    assert res.exit_code != 0
    assert "Cache TTL must be an integer" in res.stdout

    res = runner.invoke(app, ["config", "set", "timeout", "not-an-integer"])
    assert res.exit_code != 0
    assert "Timeout must be an integer" in res.stdout

    res = runner.invoke(app, ["config", "set", "provider", "true"])
    assert res.exit_code != 0
    assert "must specify a provider name" in res.stdout

    res = runner.invoke(app, ["config", "set", "provider", "true", "invalid-provider"])
    assert res.exit_code != 0
    assert "Unknown provider" in res.stdout

    res = runner.invoke(app, ["config", "set", "invalid-key", "value"])
    assert res.exit_code != 0
    assert "Unknown config key" in res.stdout


def test_command_edge_cases():
    """Test command errors and edge cases."""
    res = runner.invoke(app, ["search"])
    assert res.exit_code != 0
    assert "You must provide a search query" in res.stdout

    res = runner.invoke(app, ["open", "99"])
    assert res.exit_code != 0
    assert "not found in the last search results" in res.stdout

    res = runner.invoke(app, ["favorite", "add", "99"])
    assert res.exit_code != 0
    assert "not found in the last search results" in res.stdout

    res = runner.invoke(app, ["favorite", "remove", "internet_archive:not_existing"])
    assert res.exit_code != 0
    assert "is not in favorites" in res.stdout


@patch("bookcli.cli.search_books", new_callable=AsyncMock)
def test_search_export(mock_search_books):
    """Test search with JSON and CSV exports."""
    mock_book = BookMetadata(
        id="gutenberg:1",
        title="Export Book",
        authors=["Export Author"],
        published_year=2020,
        source="gutenberg",
        download_availability=True
    )
    mock_search_books.return_value = [mock_book]

    try:
        res_json = runner.invoke(app, ["search", "Export", "--export", "json"])
        assert res_json.exit_code == 0
        assert "Exported results to search_results.json" in res_json.stdout
        assert os.path.exists("search_results.json")
        
        res_csv = runner.invoke(app, ["search", "Export", "--export", "csv"])
        assert res_csv.exit_code == 0
        assert "Exported results to search_results.csv" in res_csv.stdout
        assert os.path.exists("search_results.csv")
        
        res_inv = runner.invoke(app, ["search", "Export", "--export", "invalid"])
        assert "Invalid export format" in res_inv.stdout
    finally:
        if os.path.exists("search_results.json"):
            os.remove("search_results.json")
        if os.path.exists("search_results.csv"):
            os.remove("search_results.csv")


@patch("bookcli.cli.search_books", new_callable=AsyncMock)
def test_search_interactive(mock_search_books):
    """Test interactive explorer loop at the end of search command."""
    mock_book = BookMetadata(
        id="gutenberg:1",
        title="Interactive Book",
        authors=["Author"],
        source="gutenberg",
        download_availability=True
    )
    mock_search_books.return_value = [mock_book]

    with patch.dict(os.environ, {"BOOKCLI_INTERACTIVE": "true"}), \
         patch("rich.console.Console.input", side_effect=["i 1", "q"]):
        
        from bookcli.settings import DB_PATH
        db_manager = DatabaseManager(str(DB_PATH))
        async def setup_cache():
            await db_manager.initialize()
            from bookcli.cache import save_book_to_cache
            await save_book_to_cache(db_manager, mock_book)
        import asyncio
        asyncio.run(setup_cache())

        res = runner.invoke(app, ["search", "InteractiveQuery"])
        assert res.exit_code == 0
        assert "Interactive Explorer Mode" in res.stdout
        assert "Book Details: gutenberg:1" in res.stdout


@patch("bookcli.cli.search_books", new_callable=AsyncMock)
def test_search_interactive_download_custom_path(mock_search_books):
    """Test downloading a book via interactive explorer mode to a custom path."""
    mock_book = BookMetadata(
        id="gutenberg:777",
        title="Interactive Custom Book",
        authors=["Author"],
        source="gutenberg",
        download_availability=True,
        download_url="https://example.com/dl.epub",
        file_format="epub"
    )
    mock_search_books.return_value = [mock_book]

    async def mock_download_side_effect(url, dest_path, timeout):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write("interactive content")
        return "checksum_777"

    with tempfile.TemporaryDirectory() as tmp_dl_dir:
        custom_filepath = os.path.join(tmp_dl_dir, "interactive_folder", "inter_specified.epub")
        # Input sequence: download to custom path, then quit
        input_sequence = [f"1 -o {custom_filepath}", "q"]

        with patch.dict(os.environ, {"BOOKCLI_INTERACTIVE": "true"}), \
             patch("rich.console.Console.input", side_effect=input_sequence), \
             patch("bookcli.downloader.download_file", new_callable=AsyncMock, side_effect=mock_download_side_effect):
            
            from bookcli.settings import DB_PATH
            db_manager = DatabaseManager(str(DB_PATH))
            async def setup_cache():
                await db_manager.initialize()
                from bookcli.cache import save_book_to_cache
                await save_book_to_cache(db_manager, mock_book)
            import asyncio
            asyncio.run(setup_cache())

            res = runner.invoke(app, ["search", "InteractiveQuery"])
            assert res.exit_code == 0
            assert "Interactive Explorer Mode" in res.stdout
            assert "Successfully downloaded!" in res.stdout
            assert os.path.exists(custom_filepath)


def test_dashboard_non_interactive():
    """Test that running the CLI with no arguments in a non-interactive environment displays help/banner/guide and exits."""
    res = runner.invoke(app, [])
    assert res.exit_code == 0
    # Verify banner / guide content is printed
    assert "Search, inspect, and legally download books" in res.stdout
    assert "Direct CLI Commands Guide" in res.stdout
    assert "Note: Run in an interactive terminal" in res.stdout




