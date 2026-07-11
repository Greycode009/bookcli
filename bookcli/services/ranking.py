"""Service for ranking and deduplicating book search results."""

import re
from typing import List, Optional
from rapidfuzz import fuzz

from bookcli.models import BookMetadata


def normalize_isbn(isbn: Optional[str]) -> Optional[str]:
    """Strips dashes, spaces, and lowercase 'x' to normalize ISBN."""
    if not isbn:
        return None
    cleaned = re.sub(r"[- \s]", "", isbn).strip()
    return cleaned.upper() if cleaned else None


def is_duplicate(book1: BookMetadata, book2: BookMetadata) -> bool:
    """Determines if two books are duplicates based on ISBN or Title+Author similarity."""
    # Check ISBN match
    isbn1 = normalize_isbn(book1.isbn)
    isbn2 = normalize_isbn(book2.isbn)
    if isbn1 and isbn2 and isbn1 == isbn2:
        return True

    # Check Title + Author similarity
    # We use fuzz.token_set_ratio for comparison to support subtitle variations
    title_sim = fuzz.token_set_ratio(book1.title.lower(), book2.title.lower())
    
    # Compare authors
    authors1 = " ".join(book1.authors).lower()
    authors2 = " ".join(book2.authors).lower()
    
    if authors1 and authors2:
        author_sim = fuzz.token_sort_ratio(authors1, authors2)
    elif not authors1 and not authors2:
        author_sim = 100.0  # both have no authors
    else:
        author_sim = 0.0

    # If title similarity is very high and author matches reasonably well
    if title_sim >= 85 and author_sim >= 80:
        return True

    return False


def merge_books(book1: BookMetadata, book2: BookMetadata) -> BookMetadata:
    """Merges two duplicate books, prioritizing the one with download availability and richer metadata."""
    # Determine primary book (prefer download availability, then longer description, then presence of cover)
    if book1.download_availability and not book2.download_availability:
        primary, secondary = book1, book2
    elif book2.download_availability and not book1.download_availability:
        primary, secondary = book2, book1
    else:
        desc1_len = len(book1.description or "")
        desc2_len = len(book2.description or "")
        if desc1_len >= desc2_len:
            primary, secondary = book1, book2
        else:
            primary, secondary = book2, book1

    # Merge fields
    merged_authors = list(primary.authors)
    for auth in secondary.authors:
        if auth not in merged_authors:
            merged_authors.append(auth)

    return BookMetadata(
        id=primary.id,
        title=primary.title,
        subtitle=primary.subtitle or secondary.subtitle,
        authors=merged_authors,
        description=primary.description or secondary.description,
        language=primary.language or secondary.language,
        publisher=primary.publisher or secondary.publisher,
        published_year=primary.published_year or secondary.published_year,
        pages=primary.pages or secondary.pages,
        isbn=primary.isbn or secondary.isbn,
        cover_url=primary.cover_url or secondary.cover_url,
        download_url=primary.download_url or secondary.download_url,
        source=f"{primary.source}, {secondary.source}" if primary.source != secondary.source else primary.source,
        download_availability=primary.download_availability or secondary.download_availability,
        file_format=primary.file_format or secondary.file_format
    )


def calculate_score(
    book: BookMetadata,
    query: str,
    author: Optional[str] = None,
    isbn: Optional[str] = None
) -> float:
    """Calculates a relevance score for a book based on search query and filters."""
    score = 0.0

    # 1. Exact ISBN Match (Max weight)
    if isbn:
        norm_query_isbn = normalize_isbn(isbn)
        norm_book_isbn = normalize_isbn(book.isbn)
        if norm_query_isbn and norm_book_isbn and norm_query_isbn == norm_book_isbn:
            score += 200.0

    # 2. Fuzzy Title Match
    if query.strip():
        # Title token sort ratio
        title_ratio = fuzz.token_sort_ratio(query.lower(), book.title.lower())
        # Title partial ratio (helps when query is a substring)
        title_partial = fuzz.partial_ratio(query.lower(), book.title.lower())
        score += (title_ratio * 0.6) + (title_partial * 0.4)

    # 3. Fuzzy Author Match
    book_authors_str = " ".join(book.authors).lower()
    if author and book_authors_str:
        author_ratio = fuzz.token_sort_ratio(author.lower(), book_authors_str)
        score += author_ratio * 0.8
    elif query.strip() and book_authors_str:
        # Check if the query itself matches the author name
        author_query_ratio = fuzz.token_sort_ratio(query.lower(), book_authors_str)
        # If query matches author, add a moderate weight
        if author_query_ratio > 70:
            score += author_query_ratio * 0.4

    # 4. Download Availability Bonus
    if book.download_availability:
        score += 15.0

    # 5. Publisher Match (bonus if publisher was in query terms)
    if query.strip() and book.publisher:
        pub_ratio = fuzz.partial_ratio(query.lower(), book.publisher.lower())
        if pub_ratio > 80:
            score += 5.0

    return score


def rank_and_deduplicate(
    books: List[BookMetadata],
    query: str,
    author: Optional[str] = None,
    isbn: Optional[str] = None
) -> List[BookMetadata]:
    """Deduplicates and ranks a list of book metadata objects."""
    # Deduplicate in-memory
    unique_books: List[BookMetadata] = []
    
    for book in books:
        found_dup_idx = -1
        for idx, u_book in enumerate(unique_books):
            if is_duplicate(book, u_book):
                found_dup_idx = idx
                break
        
        if found_dup_idx >= 0:
            # Merge duplicate
            unique_books[found_dup_idx] = merge_books(unique_books[found_dup_idx], book)
        else:
            unique_books.append(book)

    # Calculate score and sort
    # We sort descending by score
    scored_books = [
        (calculate_score(book, query, author, isbn), book)
        for book in unique_books
    ]
    
    scored_books.sort(key=lambda x: x[0], reverse=True)
    
    return [book for _, book in scored_books]
