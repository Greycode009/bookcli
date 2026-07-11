"""Unit tests for the ranking and deduplication service."""

from bookcli.models import BookMetadata
from bookcli.services.ranking import (
    normalize_isbn,
    is_duplicate,
    merge_books,
    calculate_score,
    rank_and_deduplicate
)


def test_normalize_isbn():
    """Test ISBN normalizer strips characters properly."""
    assert normalize_isbn("978-3-16-148410-0") == "9783161484100"
    assert normalize_isbn(" 978 3 16 148410 0 ") == "9783161484100"
    assert normalize_isbn(None) is None
    assert normalize_isbn("") is None


def test_is_duplicate():
    """Test duplicate detection via ISBN and fuzzy similarity."""
    book1 = BookMetadata(
        id="google:1",
        title="Atomic Habits",
        authors=["James Clear"],
        isbn="9780735211292",
        source="google_books"
    )
    # Different provider ID, same ISBN
    book2 = BookMetadata(
        id="openlibrary:OL123M",
        title="Atomic Habits",
        authors=["James Clear"],
        isbn="978-0-7352-1129-2",
        source="openlibrary"
    )
    # Similar title and author, no ISBN
    book3 = BookMetadata(
        id="gutenberg:2",
        title="Atomic Habits: An Easy & Proven Way to Build Good Habits",
        authors=["James Clear"],
        source="gutenberg"
    )
    # Totally different book
    book4 = BookMetadata(
        id="gutenberg:3",
        title="Clean Code",
        authors=["Robert C. Martin"],
        source="gutenberg"
    )

    assert is_duplicate(book1, book2) is True
    assert is_duplicate(book1, book3) is True
    assert is_duplicate(book1, book4) is False


def test_merge_books():
    """Test merging metadata from duplicates."""
    book1 = BookMetadata(
        id="google:1",
        title="Atomic Habits",
        authors=["James Clear"],
        isbn="9780735211292",
        source="google_books",
        download_availability=False
    )
    book2 = BookMetadata(
        id="openlibrary:OL123M",
        title="Atomic Habits",
        authors=["James Clear"],
        source="openlibrary",
        download_availability=True,
        download_url="https://example.com/download.epub",
        file_format="epub"
    )

    merged = merge_books(book1, book2)
    # Should prioritize the downloadable edition
    assert merged.download_availability is True
    assert merged.download_url == "https://example.com/download.epub"
    assert merged.isbn == "9780735211292"
    assert "google_books" in merged.source
    assert "openlibrary" in merged.source


def test_calculate_score():
    """Test ranking scoring algorithm."""
    book = BookMetadata(
        id="google:1",
        title="Clean Code",
        authors=["Robert C. Martin"],
        isbn="9780132350884",
        source="google_books",
        download_availability=True
    )

    # Score with exact ISBN query
    isbn_score = calculate_score(book, query="", isbn="978-0-1323-5088-4")
    # Score with exact title query
    title_score = calculate_score(book, query="Clean Code")
    # Score with unrelated query
    unrelated_score = calculate_score(book, query="Atomic Habits")

    assert isbn_score > title_score
    assert title_score > unrelated_score


def test_rank_and_deduplicate():
    """Test rank_and_deduplicate resolves and ranks lists correctly."""
    book1 = BookMetadata(
        id="google:1",
        title="Clean Code",
        authors=["Robert C. Martin"],
        isbn="9780132350884",
        source="google_books"
    )
    book2 = BookMetadata(
        id="openlibrary:1",
        title="Clean Code",
        authors=["Robert Martin"],
        isbn="9780132350884",
        source="openlibrary"
    )
    book3 = BookMetadata(
        id="google:2",
        title="Clean Architecture",
        authors=["Robert C. Martin"],
        source="google_books"
    )

    books = [book1, book2, book3]
    results = rank_and_deduplicate(books, query="Clean Code", author="Robert Martin")
    
    # book1 and book2 are duplicates and should be merged
    assert len(results) == 2
    # Clean Code should be ranked first for "Clean Code" query
    assert results[0].title == "Clean Code"
