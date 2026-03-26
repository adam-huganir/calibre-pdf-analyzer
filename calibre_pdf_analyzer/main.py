#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from calibre_pdf_analyzer.analyzer import analyze_pdf
from calibre_pdf_analyzer.calibre import (
    ensure_columns,
    get_book_metadata,
    get_book_pdf_path,
    list_books_with_pdfs,
    set_native_metadata,
    set_pdf_metadata,
)
from calibre_pdf_analyzer.enricher import suggest_metadata
from calibre_pdf_analyzer.text_extract import extract_text


def cmd_create_columns(args: argparse.Namespace) -> None:
    """Create custom columns in Calibre. Requires Calibre to be closed."""
    library: Path = args.library
    if not library.is_dir():
        print(f"Error: library path does not exist: {library}", file=sys.stderr)
        sys.exit(1)

    print("Creating custom columns (Calibre must not be running)...")
    ensure_columns(library, dry_run=args.dry_run)
    print("Done.")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze PDFs and populate custom columns."""
    library: Path = args.library
    if not library.is_dir():
        print(f"Error: library path does not exist: {library}", file=sys.stderr)
        sys.exit(1)

    calibre_lib: Path | str = args.server if args.server else library
    dry_run: bool = args.dry_run
    book_id_filter: int | None = args.book_id

    # If book_id is specified, process only that book
    if book_id_filter is not None:
        pdf_path = get_book_pdf_path(calibre_lib, book_id_filter, library_path=library)
        if not pdf_path:
            print(f"Error: Book {book_id_filter} not found or has no PDF format", file=sys.stderr)
            sys.exit(1)
        books = [(book_id_filter, pdf_path)]
    else:
        print("Listing books with PDF formats...")
        books = list_books_with_pdfs(calibre_lib, library_path=library)
        print(f"Found {len(books)} book(s) with PDF formats.")

    for i, (book_id, pdf_path) in enumerate(books, 1):
        print(f"[{i}/{len(books)}] Book {book_id}: {pdf_path.name}")
        if not pdf_path.exists():
            print(f"  Warning: file not found, skipping")
            continue
        try:
            meta = analyze_pdf(pdf_path)
            print(f"  v{meta.pdf_version}, {meta.page_count}p, tagged={meta.is_tagged}, "
                  f"outlines={meta.has_outlines}, images={meta.has_images}, "
                  f"forms={meta.has_form_annotations}, links={meta.has_link_annotations}, "
                  f"lang={meta.lang!r}, layout={meta.layout!r}")
            set_pdf_metadata(calibre_lib, book_id, meta, dry_run=dry_run)
        except Exception as e:
            print(f"  Error: {e}")

    print("Done.")


def cmd_enrich(args: argparse.Namespace) -> None:
    """Use Claude to suggest and optionally apply improved metadata."""
    library: Path = args.library
    if not library.is_dir():
        print(f"Error: library path does not exist: {library}", file=sys.stderr)
        sys.exit(1)

    calibre_lib: Path | str = args.server if args.server else library
    api_key: str | None = args.api_key
    max_pages: int = args.max_pages
    dry_run: bool = args.dry_run
    confirm: bool = args.confirm
    book_id_filter: int | None = args.book_id

    # If book_id is specified, process only that book
    if book_id_filter is not None:
        pdf_path = get_book_pdf_path(calibre_lib, book_id_filter, library_path=library)
        if not pdf_path:
            print(f"Error: Book {book_id_filter} not found or has no PDF format", file=sys.stderr)
            sys.exit(1)
        books = [(book_id_filter, pdf_path)]
    else:
        print("Listing books with PDF formats...")
        books = list_books_with_pdfs(calibre_lib, library_path=library)
        print(f"Found {len(books)} book(s) with PDF formats.")

    for i, (book_id, pdf_path) in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] Book {book_id}: {pdf_path.name}")
        if not pdf_path.exists():
            print(f"  Warning: file not found, skipping")
            continue

        try:
            # Get current metadata
            print("  Fetching current metadata...")
            existing = get_book_metadata(calibre_lib, book_id)
            print(f"    Current title: {existing['title']}")
            print(f"    Current authors: {', '.join(existing['authors']) or 'None'}")
            print(f"    Current tags: {', '.join(existing['tags']) or 'None'}")

            # Extract text from PDF
            print(f"  Extracting text from first {max_pages} page(s)...")
            text = extract_text(pdf_path, max_pages=max_pages)
            print(f"    Extracted {len(text)} characters")

            # Get Claude's suggestions
            print("  Asking Claude for suggestions...")
            suggestion = suggest_metadata(existing, text, api_key)

            # Display suggestions
            print("\n  Claude's suggestions:")
            if suggestion.title:
                print(f"    Title: {suggestion.title}")
            if suggestion.authors:
                print(f"    Authors: {', '.join(suggestion.authors)}")
            if suggestion.tags:
                print(f"    Tags: {', '.join(suggestion.tags)}")
            if suggestion.comments:
                print(f"    Comments: {suggestion.comments[:100]}{'...' if len(suggestion.comments) > 100 else ''}")

            # Apply if confirmed
            if confirm:
                print("  Applying suggestions...")
                set_native_metadata(calibre_lib, book_id, suggestion, dry_run=dry_run)
                if not dry_run:
                    print("  ✓ Metadata updated")
            else:
                print("  (not applying - use --confirm to auto-apply)")

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze PDFs in a Calibre library and populate custom columns."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- create-columns ---
    p_create = subparsers.add_parser(
        "create-columns",
        help="Create custom columns in Calibre (requires Calibre to be closed).",
    )
    p_create.add_argument(
        "--library", type=Path, required=True,
        help="Path to the Calibre library directory",
    )
    p_create.add_argument(
        "--dry-run", action="store_true",
        help="Print calibredb commands instead of executing them.",
    )
    p_create.set_defaults(func=cmd_create_columns)

    # --- analyze ---
    p_analyze = subparsers.add_parser(
        "analyze",
        help="Analyze PDFs and store metadata in custom columns.",
    )
    p_analyze.add_argument(
        "--library", type=Path, required=True,
        help="Path to the Calibre library directory (used to locate PDF files on disk)",
    )
    p_analyze.add_argument(
        "--server", type=str, default=None,
        help="URL of running Calibre content server (e.g. http://localhost:8080).",
    )
    p_analyze.add_argument(
        "--dry-run", action="store_true",
        help="Print calibredb commands instead of executing them (still reads PDFs).",
    )
    p_analyze.add_argument(
        "--book-id", type=int, default=None,
        help="Process only this specific book ID (default: process all books with PDFs).",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    # --- enrich ---
    p_enrich = subparsers.add_parser(
        "enrich",
        help="Use Claude AI to suggest improved metadata for books.",
    )
    p_enrich.add_argument(
        "--library", type=Path, required=True,
        help="Path to the Calibre library directory (used to locate PDF files on disk)",
    )
    p_enrich.add_argument(
        "--server", type=str, default=None,
        help="URL of running Calibre content server (e.g. http://localhost:8080).",
    )
    p_enrich.add_argument(
        "--api-key", type=str, default=None,
        help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
    )
    p_enrich.add_argument(
        "--max-pages", type=int, default=3,
        help="Number of pages to extract text from (default: 3).",
    )
    p_enrich.add_argument(
        "--dry-run", action="store_true",
        help="Print calibredb commands instead of executing them.",
    )
    p_enrich.add_argument(
        "--confirm", action="store_true",
        help="Auto-apply Claude's suggestions (default: print only).",
    )
    p_enrich.add_argument(
        "--book-id", type=int, default=None,
        help="Process only this specific book ID (default: process all books with PDFs).",
    )
    p_enrich.set_defaults(func=cmd_enrich)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
