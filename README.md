# BookCLI

BookCLI is a production-ready, clean-architecture command-line interface application built in Python 3.12+. It allows users to search multiple legal book sources concurrently, merge and rank results dynamically using fuzzy string matching, and safely download books when legally provided by the API source.

---

## Features

- **Concurrent Multi-Provider Search**: Queries Google Books, Open Library, Project Gutenberg, and the Internet Archive concurrently.
- **Advanced Deduplication & Ranking**: Automatically filters duplicate search entries using fuzzy title and author string comparison via `RapidFuzz` and sorts results based on metadata completeness and direct download availability.
- **Safe & Legal Downloads**: Only attempts downloads when the source explicitly provides a free/public-domain download link.
- **Custom Download Paths**: Allows downloading to custom directories or specific files via CLI arguments, search explorer prompts, or global configurations.
- **Download Resumption**: Supports HTTP range requests to resume interrupted downloads.
- **Rich Terminal UI**: Displays tabular results, dynamic progress bars, speed, ETA, and styled metadata panel screens utilizing `Rich`.
- **Offline Mode & Metadata Caching**: Implements local caching in SQLite to preserve previously fetched results, allowing details to be checked offline.
- **Short Session Indexing**: Supports referring to book search results by their simple short IDs (1, 2, 3...) in follow-up commands like `info`, `download`, `open`, and `favorite`.
- **Search History & Favorites**: Saves queries and favorites locally.
- **Configurable Options**: Change default download directory, cache TTL, client timeout, and disable/enable specific providers.

---

## Directory Architecture

The project adheres to Clean Architecture principles:

```text
bookcli/
│
├── database/            # Database initialization and migrations
│   └── migrations.py
│
├── providers/           # API clients for external book metadata providers
│   ├── base.py
│   ├── google_books.py
│   ├── gutenberg.py
│   ├── internet_archive.py
│   └── openlibrary.py
│
├── services/            # Core business services
│   ├── history.py
│   ├── ranking.py
│   └── search.py
│
├── cache.py             # SQLite metadata cache implementation
├── cli.py               # Typer CLI application entry point and commands
├── config.py            # Pydantic configuration loader and validator
├── downloader.py        # Async downloader with range-resume and Rich progress
├── exceptions.py        # Custom exceptions for uniform error handling
├── opener.py            # OS-specific default application file opener
├── settings.py          # Configuration defaults and directory paths
└── utils.py             # Formatting and filename utilities
```

---

## Installation

Ensure you have Python 3.12+ installed. Install BookCLI locally in editable mode:

```bash
git clone https://github.com/your-username/bookcli.git
cd bookcli
pip install -e .
```

Once installed, the CLI tool is available globally as `book`. If the script directory is not on your PATH, you can use the provided script wrappers in the project root:
- On Windows (CMD/PowerShell): `.\book.bat <command>`
- On Unix/macOS/Git Bash: `./book <command>`
- Or directly via Python module: `python -m bookcli.cli <command>`

> [!NOTE]
> On Windows, running `.\book.bat` without any command starts the **Interactive Search Explorer** loop, which also includes a menu option to update your default download directory.

---

## Usage

### 1. Search for Books
Query multiple providers concurrently. Results will display in a styled table containing short session IDs.

```bash
# General search
book search "Atomic Habits"

# Filtered search
book search "Clean Code" --author "Robert C. Martin"
book search "Relativity" --subject "Physics"
```

#### Interactive Explorer Mode
When running search inside a terminal (TTY mode), you enter an interactive prompt:
- Enter `i <ID>` to see details.
- Enter `f <ID>` to favorite a book.
- Enter `o <ID>` to open a downloaded book.
- Enter `<ID>` to download a book to your default download directory.
- Enter `<ID> -o <path>` or `<ID> --output <path>` to download a book to a **custom path** (e.g. `1 -o C:\downloads` or `1 -o mybook.epub`).
- Enter `q` to quit.

### 2. View Detailed Metadata
Examine pages, publishers, description, ISBN, and download status of a book by using its short index ID (from your last search) or exact provider ID.

```bash
book info 1
```

### 3. Legal Download with Progress Bar
Download the book with a progress bar. You can choose to download to your default configured directory or specify a custom path (either a directory or exact file path).

```bash
# Download to the default configured download directory
book download 1

# Download to a custom directory (automatically creates it if missing)
book download 1 --output "/path/to/my_downloads/"
book download 1 -o "C:\my_downloads\"

# Download to a specific custom filename
book download 1 --output "/path/to/my_books/clean_code.epub"
```

### 4. Open File in OS Default Viewer
Open the downloaded book (EPUB, PDF, TXT) immediately in your operating system's default book reader.

```bash
book open 1
```

### 5. Managing Favorites
Bookmark books to read later.

```bash
# Add to favorites
book favorite add 1

# List all favorites
book favorite list

# Remove from favorites
book favorite remove gutenberg:1342
```

### 6. Configuration Settings
List all configuration options or update parameters:

```bash
# View configuration
book config

# Set default download directory (can also use 'download-path' alias)
book config set download-dir "/path/to/downloads"
book config set download-path "/path/to/downloads"

# Set client requests timeout
book config set timeout 10

# Disable a provider (e.g. internet_archive)
book config set provider false internet-archive
```

### 7. Cache Management
View statistics or clear cached metadata:

```bash
book cache stats
book cache clear
```

### 8. Query History
View your search history logs:

```bash
book history
```

---

## Testing & Code Quality

BookCLI includes a comprehensive test suite of unit and integration tests with **80%+ code coverage**.

### Run Tests
```bash
python -m pytest --cov=bookcli
```
