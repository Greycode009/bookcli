"""Command-line interface (CLI) for BookCLI using Typer and Rich."""

import builtins
import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.theme import Theme

from bookcli.settings import DB_PATH
from bookcli.config import load_config, save_config, AppConfig
from bookcli.database import DatabaseManager
from bookcli.exceptions import BookCLIError, BookNotFoundError
from bookcli.models import BookMetadata
from bookcli.cache import get_book_from_cache, clear_cache_db, get_cache_db_stats
from bookcli.opener import open_file_in_default_app
from bookcli.utils import format_size, clean_filename
from bookcli.services.search import search_books
from bookcli.services.history import get_search_history, clear_search_history

# Reconfigure standard output streams to UTF-8 to prevent charmap encoding errors on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Global rich console
console = Console()

# Initialize Typer App
app = typer.Typer(
    name="book",
    help="BookCLI: Search, inspect, and legally download books from public sources.",
    no_args_is_help=True
)

logger = logging.getLogger("bookcli")


async def resolve_book_id(db_manager: DatabaseManager, user_input: str) -> str:
    """Resolves short numeric session index or checks if it is a full string ID."""
    if user_input.isdigit():
        idx = int(user_input)
        async with db_manager.connection() as conn:
            async with conn.execute(
                "SELECT book_id FROM search_results_session WHERE result_index = ?", (idx,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
        raise BookNotFoundError(
            f"Numeric index '{idx}' not found in the last search results session. "
            "Please run a search first or provide a full provider ID (e.g. gutenberg:1342)."
        )
    return user_input


# --- Business Logic Subroutines for Commands and Interactive Mode ---

async def show_info_internal(db_manager: DatabaseManager, book_id_input: str, config: AppConfig) -> None:
    """Subroutine to display book metadata."""
    book_id = await resolve_book_id(db_manager, book_id_input)

    book = await get_book_from_cache(db_manager, book_id, config.cache_ttl_seconds)

    if not book:
        prefix = book_id.split(":", 1)[0]
        with console.status(f"[bold green]Fetching details from {prefix}..."):
            try:
                from bookcli.providers.google_books import GoogleBooksProvider
                from bookcli.providers.openlibrary import OpenLibraryProvider
                from bookcli.providers.gutenberg import GutenbergProvider
                from bookcli.providers.internet_archive import InternetArchiveProvider

                provider_map = {
                    "google": GoogleBooksProvider(config.timeout_seconds),
                    "openlibrary": OpenLibraryProvider(config.timeout_seconds),
                    "gutenberg": GutenbergProvider(config.timeout_seconds),
                    "internet_archive": InternetArchiveProvider(config.timeout_seconds)
                }

                provider = provider_map.get(prefix)
                if not provider:
                    raise BookCLIError(f"Unsupported provider prefix '{prefix}'.")

                book = await provider.get_book(book_id)
            except Exception as e:
                raise BookCLIError(f"Error fetching book from provider: {e}")

    if not book:
        raise BookNotFoundError(f"Book with ID '{book_id}' could not be resolved.")

    info_table = Table.grid(padding=1)
    info_table.add_column(style="bold yellow", justify="right", width=18)
    info_table.add_column()

    info_table.add_row("Title:", book.title)
    if book.subtitle:
        info_table.add_row("Subtitle:", book.subtitle)
    info_table.add_row("Author(s):", ", ".join(book.authors) if book.authors else "Unknown")
    if book.publisher:
        info_table.add_row("Publisher:", book.publisher)
    if book.published_year:
        info_table.add_row("Published Year:", str(book.published_year))
    if book.pages:
        info_table.add_row("Pages:", str(book.pages))
    if book.isbn:
        info_table.add_row("ISBN:", book.isbn)
    if book.language:
        info_table.add_row("Language:", book.language)
    if book.cover_url:
        info_table.add_row("Cover URL:", book.cover_url)
    
    avail_str = "[green]Available[/green]" if book.download_availability else "[red]Not Available[/red]"
    info_table.add_row("Download Status:", avail_str)
    if book.download_url:
        info_table.add_row("Download Link:", book.download_url)
        info_table.add_row("File Format:", book.file_format or "Unknown")

    info_table.add_row("Provider Source:", book.source)

    if book.description:
        desc_panel = Panel(book.description, title="Description", border_style="dim")
    else:
        desc_panel = ""

    main_panel = Panel(
        info_table,
        title=f"Book Details: {book.id}",
        border_style="green",
        expand=False
    )

    console.print(main_panel)
    if desc_panel:
        console.print(desc_panel)


async def download_book_internal(
    db_manager: DatabaseManager,
    book_id_input: str,
    config: AppConfig,
    custom_path: Optional[Path] = None
) -> str:
    """Subroutine to download a book. Returns the checksum on success, raises DownloadError on failure."""
    book_id = await resolve_book_id(db_manager, book_id_input)

    # For internet_archive, we always query get_book to resolve the exact filename
    # rather than using the guessed URL from search results cached during search.
    prefix = book_id.split(":", 1)[0]
    book = None
    if prefix == "internet_archive":
        try:
            from bookcli.providers.internet_archive import InternetArchiveProvider
            provider = InternetArchiveProvider(config.timeout_seconds)
            book = await provider.get_book(book_id)
            if book:
                from bookcli.cache import save_book_to_cache
                await save_book_to_cache(db_manager, book)
        except Exception as e:
            console.print(f"[yellow]IA Metadata resolution warning: {e}[/yellow]")

    if not book:
        book = await get_book_from_cache(db_manager, book_id, config.cache_ttl_seconds)

    if not book:
        try:
            from bookcli.providers.google_books import GoogleBooksProvider
            from bookcli.providers.openlibrary import OpenLibraryProvider
            from bookcli.providers.gutenberg import GutenbergProvider
            from bookcli.providers.internet_archive import InternetArchiveProvider

            provider_map = {
                "google": GoogleBooksProvider(config.timeout_seconds),
                "openlibrary": OpenLibraryProvider(config.timeout_seconds),
                "gutenberg": GutenbergProvider(config.timeout_seconds),
                "internet_archive": InternetArchiveProvider(config.timeout_seconds)
            }
            provider = provider_map.get(prefix)
            if provider:
                book = await provider.get_book(book_id)
        except Exception:
            pass

    if not book:
        raise BookNotFoundError(f"Could not resolve book metadata for ID '{book_id}'.")

    if not book.download_availability or not book.download_url:
        raise BookCLIError("No legal download URL is available for this book.")

    safe_title = clean_filename(book.title)
    ext = f".{book.file_format}" if book.file_format else ".epub"
    dest_filename = f"{safe_title}_{book.id.replace(':', '_')}{ext}"
    if custom_path:
        custom_path_obj = Path(custom_path)
        custom_path_str = str(custom_path_obj)
        if os.path.isdir(custom_path_str) or custom_path_str.endswith("/") or custom_path_str.endswith("\\") or not custom_path_obj.suffix:
            dest_path = os.path.join(custom_path_str, dest_filename)
        else:
            dest_path = custom_path_str
    else:
        dest_path = os.path.join(config.download_dir, dest_filename)

    # Ensure parent directory exists
    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    console.print(f"Starting download to: [cyan]{dest_path}[/cyan] ...")

    try:
        from bookcli.downloader import download_file
        checksum = await download_file(book.download_url, dest_path, config.timeout_seconds)

        async with db_manager.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO downloads (id, title, file_path, status, checksum)
                VALUES (?, ?, ?, ?, ?)
                """,
                (book.id, book.title, dest_path, "completed", checksum)
            )
            await conn.commit()

        console.print(f"[bold green]Successfully downloaded![/bold green]")
        console.print(f"File size: [yellow]{format_size(os.path.getsize(dest_path))}[/yellow]")
        console.print(f"SHA256 Checksum: [yellow]{checksum}[/yellow]")
        return checksum
    except Exception as e:
        async with db_manager.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO downloads (id, title, file_path, status, checksum)
                VALUES (?, ?, ?, ?, ?)
                """,
                (book.id, book.title, dest_path, "failed", None)
            )
            await conn.commit()
        raise BookCLIError(f"Download failed: {e}")


async def open_book_internal(db_manager: DatabaseManager, book_id_input: str) -> None:
    """Subroutine to open a downloaded book."""
    book_id = await resolve_book_id(db_manager, book_id_input)

    async with db_manager.connection() as conn:
        async with conn.execute(
            "SELECT file_path, status FROM downloads WHERE id = ? AND status = 'completed'", (book_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise BookCLIError(f"Book '{book_id}' has not been downloaded yet. Run 'book download' first.")
            file_path = row[0]

    open_file_in_default_app(file_path)
    console.print(f"[green]Opening file {file_path}...[/green]")


async def add_favorite_internal(db_manager: DatabaseManager, book_id_input: str, config: AppConfig) -> None:
    """Subroutine to add a book to favorites."""
    book_id = await resolve_book_id(db_manager, book_id_input)

    book = await get_book_from_cache(db_manager, book_id, config.cache_ttl_seconds)
    if not book:
        raise BookCLIError(f"Metadata for '{book_id}' not found in cache. Search or retrieve info first.")

    async with db_manager.connection() as conn:
        try:
            await conn.execute(
                "INSERT OR REPLACE INTO favorites (book_id, title) VALUES (?, ?)",
                (book.id, book.title)
            )
            await conn.commit()
            console.print(f"[green]Added '{book.title}' to favorites.[/green]")
        except Exception as e:
            raise BookCLIError(f"Error saving favorite: {e}")


# --- CLI Commands ---

@app.callback()
def global_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging (INFO)"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging (DEBUG)")
):
    """Global configuration callback for logging."""
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger.setLevel(level)


@app.command()
def search(
    query: str = typer.Argument("", help="Free text search query"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Filter by author name"),
    isbn: Optional[str] = typer.Option(None, "--isbn", help="Filter by exact ISBN"),
    publisher: Optional[str] = typer.Option(None, "--publisher", help="Filter by publisher name"),
    subject: Optional[str] = typer.Option(None, "--subject", help="Filter by subject/topic"),
    export: Optional[str] = typer.Option(None, "--export", help="Export to 'json' or 'csv' file"),
):
    """Search for books across all enabled providers."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        config = load_config()
        
        if not query.strip() and not (author or isbn or publisher or subject):
            console.print("[red]Error: You must provide a search query or at least one filter.[/red]")
            raise typer.Exit(code=1)

        with console.status("[bold green]Searching enabled providers..."):
            try:
                results = await search_books(
                    query=query,
                    config=config,
                    db_manager=db_manager,
                    author=author,
                    isbn=isbn,
                    publisher=publisher,
                    subject=subject
                )
            except Exception as e:
                console.print(Panel(f"[bold red]Search Error:[/bold red] {e}", title="Error", border_style="red"))
                raise typer.Exit(code=1)

        if not results:
            console.print("[yellow]No books found matching the search criteria.[/yellow]")
            return

        # Store search results session in DB
        async with db_manager.connection() as conn:
            await conn.execute("DELETE FROM search_results_session")
            for idx, book in enumerate(results, start=1):
                await conn.execute(
                    "INSERT INTO search_results_session (result_index, book_id) VALUES (?, ?)",
                    (idx, book.id)
                )
            await conn.commit()

        # Format output as Rich table
        table = Table(title=f"Search Results for '{query or 'Filters'}'")
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Title", style="magenta")
        table.add_column("Author(s)", style="green")
        table.add_column("Year", justify="center", style="yellow")
        table.add_column("Source", style="blue")
        table.add_column("Download", justify="center")

        for idx, book in enumerate(results, start=1):
            if book.download_availability:
                avail_str = f"[green]{book.file_format.upper()}[/green]" if book.file_format else "[green]Yes[/green]"
            else:
                avail_str = "[red]No[/red]"
            author_str = ", ".join(book.authors) if book.authors else "Unknown"
            year_str = str(book.published_year) if book.published_year else "N/A"
            table.add_row(
                str(idx),
                book.title,
                author_str,
                year_str,
                book.source,
                avail_str
            )

        console.print(table)
        console.print(f"[dim]Total: {len(results)} books.[/dim]")

        # Export if requested
        if export:
            export_fmt = export.lower()
            if export_fmt == "json":
                dest_file = "search_results.json"
                with builtins.open(dest_file, "w", encoding="utf-8") as f:
                    json.dump([b.model_dump() for b in results], f, indent=4)
                console.print(f"[green]Exported results to {dest_file}[/green]")
            elif export_fmt == "csv":
                dest_file = "search_results.csv"
                with builtins.open(dest_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["ID", "Title", "Authors", "Year", "Source", "Format", "Downloadable", "Download URL"])
                    for idx, b in enumerate(results, start=1):
                        writer.writerow([
                            idx, b.title, ", ".join(b.authors),
                            b.published_year or "N/A", b.source,
                            b.file_format or "N/A",
                            b.download_availability, b.download_url or ""
                        ])
                console.print(f"[green]Exported results to {dest_file}[/green]")
            else:
                console.print("[red]Invalid export format. Supported formats: json, csv.[/red]")

        # --- Interactive Explorer Loop (triggered if TTY is true) ---
        if sys.stdin.isatty() or os.environ.get("BOOKCLI_INTERACTIVE") == "true":
            console.print("\n[bold cyan]Interactive Explorer Mode[/bold cyan]")
            console.print("[dim]Enter <ID> to download, 'i <ID>' for info, 'f <ID>' to favorite, 'o <ID>' to open, or 'q' to quit.[/dim]")
            while True:
                try:
                    action = console.input("\n[bold yellow]Action > [/bold yellow]").strip()
                    if not action or action.lower() in ("q", "quit", "exit"):
                        break
                    
                    tokens = action.split()
                    if not tokens:
                        continue

                    if tokens[0].isdigit():
                        val = tokens[0]
                        custom_path = None
                        if len(tokens) >= 3 and tokens[1] in ("-o", "--output"):
                            custom_path = " ".join(tokens[2:])
                        elif len(tokens) > 1:
                            console.print("[red]Invalid output path syntax. Use: <ID> -o <path>[/red]")
                            continue
                        
                        try:
                            await download_book_internal(db_manager, val, config, custom_path=Path(custom_path) if custom_path else None)
                        except BookCLIError as e:
                            console.print(f"[red]Error: {e}[/red]")
                    elif len(tokens) >= 2:
                        cmd, val = tokens[0].lower(), " ".join(tokens[1:])
                        try:
                            if cmd == "i":
                                await show_info_internal(db_manager, val, config)
                            elif cmd == "f":
                                await add_favorite_internal(db_manager, val, config)
                            elif cmd == "o":
                                await open_book_internal(db_manager, val)
                            else:
                                console.print("[red]Unknown command prefix. Use 'i', 'f', 'o', or just the ID.[/red]")
                        except BookCLIError as e:
                            console.print(f"[red]Error: {e}[/red]")
                    else:
                        console.print("[red]Invalid input. Enter an ID index number or 'q' to exit.[/red]")
                except (KeyboardInterrupt, EOFError):
                    break

    asyncio.run(_run())


@app.command()
def info(
    book_id_input: str = typer.Argument(..., help="Numeric index from last search, or exact book ID"),
):
    """Show detailed metadata for a book."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()
        config = load_config()
        try:
            await show_info_internal(db_manager, book_id_input, config)
        except BookCLIError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command()
def download(
    book_id_input: str = typer.Argument(..., help="Numeric index from last search, or exact book ID"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Custom path (file path or directory) to save the downloaded book."
    ),
):
    """Download a book locally (if legally available)."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()
        config = load_config()
        try:
            await download_book_internal(db_manager, book_id_input, config, custom_path=output)
        except BookCLIError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command()
def open(
    book_id_input: str = typer.Argument(..., help="Numeric index from last search, or exact book ID"),
):
    """Open a downloaded book using the OS default application."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()
        try:
            await open_book_internal(db_manager, book_id_input)
        except BookCLIError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command()
def history():
    """Display past search history."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        hist = await get_search_history(db_manager, limit=20)
        if not hist:
            console.print("[yellow]Search history is empty.[/yellow]")
            return

        table = Table(title="Search History")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Query/Filters", style="magenta")
        table.add_column("Results Count", style="green", justify="right")

        for entry in hist:
            table.add_row(
                entry["timestamp"],
                entry["query"],
                str(entry["results_count"])
            )

        console.print(table)

    asyncio.run(_run())


# Favorites subcommand group
favorites_app = typer.Typer(help="Manage favorites list.")
app.add_typer(favorites_app, name="favorite")


@favorites_app.command("add")
def favorite_add(
    book_id_input: str = typer.Argument(..., help="Numeric index from last search, or exact book ID"),
):
    """Add a book to your favorites list."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()
        config = load_config()
        try:
            await add_favorite_internal(db_manager, book_id_input, config)
        except BookCLIError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@favorites_app.command("list")
def favorite_list():
    """List all favorite books."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        async with db_manager.connection() as conn:
            async with conn.execute("SELECT book_id, title, added_at FROM favorites ORDER BY added_at DESC") as cursor:
                rows = await cursor.fetchall()

        if not rows:
            console.print("[yellow]Favorites list is empty.[/yellow]")
            return

        table = Table(title="Favorite Books")
        table.add_column("Book ID", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Added At", style="green")

        for row in rows:
            table.add_row(
                row["book_id"],
                row["title"],
                row["added_at"]
            )

        console.print(table)

    asyncio.run(_run())


@favorites_app.command("remove")
def favorite_remove(
    book_id_input: str = typer.Argument(..., help="Book ID to remove"),
):
    """Remove a book from favorites list."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        try:
            book_id = await resolve_book_id(db_manager, book_id_input)
        except BookNotFoundError:
            book_id = book_id_input

        async with db_manager.connection() as conn:
            async with conn.execute("SELECT title FROM favorites WHERE book_id = ?", (book_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    console.print(f"[red]Book '{book_id}' is not in favorites.[/red]")
                    raise typer.Exit(code=1)
                title = row[0]

            await conn.execute("DELETE FROM favorites WHERE book_id = ?", (book_id,))
            await conn.commit()
            console.print(f"[green]Removed '{title}' from favorites.[/green]")

    asyncio.run(_run())


# Cache subcommand group
cache_app = typer.Typer(help="Manage local metadata cache.")
app.add_typer(cache_app, name="cache")


@cache_app.command("clear")
def cache_clear():
    """Clear all cached book metadata."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        deleted_count = await clear_cache_db(db_manager)
        console.print(f"[green]Metadata cache cleared. Removed {deleted_count} items.[/green]")

    asyncio.run(_run())


@cache_app.command("stats")
def cache_stats():
    """View metadata cache statistics."""
    async def _run():
        db_manager = DatabaseManager(str(DB_PATH))
        await db_manager.initialize()

        stats = await get_cache_db_stats(db_manager)
        console.print(Panel(
            f"Total Cached Books: [green]{stats['total_items']}[/green]\n"
            f"Oldest Record: [yellow]{stats['oldest_item']}[/yellow]\n"
            f"Newest Record: [yellow]{stats['newest_item']}[/yellow]",
            title="Metadata Cache Statistics",
            border_style="cyan"
        ))

    asyncio.run(_run())


# Config subcommand group
config_app = typer.Typer(help="Manage configuration settings.")
app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config_main(ctx: typer.Context):
    """Show current settings configuration or manage parameters."""
    if ctx.invoked_subcommand is not None:
        return

    config = load_config()
    table = Table(title="BookCLI Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Download Directory", config.download_dir)
    table.add_row("Cache TTL (seconds)", str(config.cache_ttl_seconds))
    table.add_row("Timeout (seconds)", str(config.timeout_seconds))
    table.add_row("Theme", config.theme)
    table.add_row("Google Books Enabled", str(config.providers.google_books))
    table.add_row("Open Library Enabled", str(config.providers.openlibrary))
    table.add_row("Project Gutenberg Enabled", str(config.providers.gutenberg))
    table.add_row("Internet Archive Enabled", str(config.providers.internet_archive))

    console.print(table)
    console.print("[dim]Use 'book config set <key> <value>' to modify settings.[/dim]")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Setting key (e.g., download-dir, cache-ttl, timeout, theme, provider)"),
    value: str = typer.Argument(..., help="Setting value"),
    provider_name: Optional[str] = typer.Argument(None, help="Provider key name (only when modifying 'provider')")
):
    """Modify a configuration setting."""
    config = load_config()
    key = key.lower().replace("_", "-")

    if key == "download-dir":
        config.download_dir = value
        os.makedirs(value, exist_ok=True)
    elif key == "cache-ttl":
        if not value.isdigit():
            console.print("[red]Cache TTL must be an integer.[/red]")
            raise typer.Exit(code=1)
        config.cache_ttl_seconds = int(value)
    elif key == "timeout":
        if not value.isdigit():
            console.print("[red]Timeout must be an integer.[/red]")
            raise typer.Exit(code=1)
        config.timeout_seconds = int(value)
    elif key == "theme":
        config.theme = value
    elif key == "provider":
        if not provider_name:
            console.print("[red]Error: You must specify a provider name. E.g. 'book config set provider true google-books'[/red]")
            raise typer.Exit(code=1)
        
        prov_key = provider_name.lower().replace("-", "_")
        bool_val = value.lower() in ("true", "1", "yes", "on")

        if hasattr(config.providers, prov_key):
            setattr(config.providers, prov_key, bool_val)
        else:
            console.print(f"[red]Error: Unknown provider '{provider_name}'.[/red]")
            raise typer.Exit(code=1)
    else:
        console.print(f"[red]Error: Unknown config key '{key}'.[/red]")
        raise typer.Exit(code=1)

    try:
        save_config(config)
        console.print(f"[green]Successfully updated configuration setting '{key}' to '{value}'.[/green]")
    except Exception as e:
        console.print(f"[red]Error saving configuration: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
