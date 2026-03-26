import json
import subprocess
from pathlib import Path

from calibre_pdf_analyzer.models import BookSuggestion, PdfMetadata

# Custom column definitions: (lookup_name, display_name, datatype)
CUSTOM_COLUMNS = [
    ("pdf_tagged", "Tagged", "bool"),
    ("pdf_outlines", "Outlines", "bool"),
    ("pdf_images", "Images", "bool"),
    ("pdf_form_annotations", "Forms", "bool"),
    ("pdf_link_annotations", "Links", "bool"),
    ("pdf_version", "Version", "text"),
    ("pdf_lang", "Language", "text"),
    ("pdf_pages", "Pages", "int"),
    ("pdf_layout", "Layout", "text"),
    # Catalog features
    ("pdf_page_labels", "Page Labels", "text"),
    ("pdf_names", "Names", "bool"),
    ("pdf_dests", "Dests", "bool"),
    ("pdf_viewer_prefs", "Viewer Prefs", "bool"),
    ("pdf_threads", "Threads", "bool"),
    ("pdf_open_action", "Open Action", "bool"),
    ("pdf_aa", "Actions", "bool"),
    ("pdf_uri", "URI", "bool"),
    ("pdf_acroform", "AcroForm", "bool"),
    ("pdf_metadata_stream", "Metadata", "bool"),
    ("pdf_oc_properties", "Opt Content", "bool"),
    ("pdf_piece_info", "Piece Info", "bool"),
    ("pdf_legal", "Legal", "bool"),
    ("pdf_page_mode", "Page Mode", "text"),
    # Page-level features
    ("pdf_last_modified", "Modified", "text"),
    ("pdf_cropbox", "CropBox", "text"),
    ("pdf_artbox", "ArtBox", "text"),
    ("pdf_bleedbox", "BleedBox", "text"),
    ("pdf_rotations", "Rotations", "bool"),
    ("pdf_thumbnails", "Thumbnails", "bool"),
    ("pdf_annotations", "Annotations", "bool"),
    ("pdf_user_unit", "UserUnit", "bool"),
    ("pdf_paths", "Paths", "bool"),
    # Document-level features
    ("pdf_embedded_fonts", "Fonts", "bool"),
    ("pdf_attachments", "Attachments", "bool"),
]


def _build_cmd(args: list[str], library: Path | str) -> list[str]:
    """Build a calibredb command list."""
    lib_str = str(library)
    if lib_str.startswith("http://") or lib_str.startswith("https://"):
        return ["calibredb"] + args + ["--with-library", lib_str]
    else:
        return ["calibredb"] + args + ["--library-path", lib_str]


def _run_calibredb(args: list[str], library: Path | str) -> subprocess.CompletedProcess:
    """Run a calibredb command against the given library."""
    cmd = _build_cmd(args, library)
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_columns(library: Path | str, *, dry_run: bool = False) -> None:
    """Create custom columns if they don't already exist."""
    # Get existing custom columns
    result = _run_calibredb(["custom_columns"], library)
    existing = result.stdout if result.returncode == 0 else ""

    for lookup, display, datatype in CUSTOM_COLUMNS:
        # calibredb custom_columns output includes the lookup name
        if f"#{lookup}" in existing or f"*{lookup}" in existing:
            continue
        add_args = ["add_custom_column", lookup, display, datatype]
        if dry_run:
            print(f"  [dry-run] {' '.join(_build_cmd(add_args, library))}")
            continue
        print(f"  Creating custom column #{lookup} ({display}, {datatype})")
        r = _run_calibredb(add_args, library)
        if r.returncode != 0:
            print(f"  Warning: failed to create #{lookup}: {r.stderr.strip()}")


def list_books_with_pdfs(library: Path | str, library_path: Path | None = None) -> list[tuple[int, Path]]:
    """Return (book_id, pdf_path) for every book that has a PDF format.

    When connecting via server, formats are returned as names (e.g. "PDF") not paths.
    In that case we need library_path to locate the actual files on disk.
    """
    result = _run_calibredb(
        ["list", "--fields", "formats", "--for-machine"],
        library,
    )
    if result.returncode != 0:
        raise RuntimeError(f"calibredb list failed: {result.stderr}")

    books = json.loads(result.stdout)
    pdf_books = []
    for book in books:
        formats = book.get("formats", "")
        if not formats:
            continue
        # formats may be a list (--for-machine via server) or comma-separated string
        if isinstance(formats, list):
            entries = formats
        else:
            entries = [p.strip() for p in formats.split(",")]

        has_pdf = False
        for entry in entries:
            if entry.upper() == "PDF":
                has_pdf = True
                break
            elif entry.lower().endswith(".pdf"):
                pdf_books.append((book["id"], Path(entry)))
                has_pdf = True
                break

        # If we got just the format name, find the PDF on disk
        if has_pdf and library_path:
            pdf_path = _find_pdf_for_book(library_path, book["id"])
            if pdf_path:
                pdf_books.append((book["id"], pdf_path))

    return pdf_books


def _find_pdf_for_book(library_path: Path, book_id: int) -> Path | None:
    """Find the PDF file for a book by searching the library directory structure."""
    # Calibre stores metadata.db at the library root; books are in subdirectories.
    # Each book directory contains the book_id in its path as "Title (id)".
    # Glob for any PDF in a directory ending with (book_id)
    pattern = f"*/*({book_id})/*.pdf"
    matches = list(library_path.glob(pattern))
    return matches[0] if matches else None


def get_book_pdf_path(library: Path | str, book_id: int, library_path: Path | None = None) -> Path | None:
    """Get the PDF path for a specific book ID.

    Args:
        library: Calibre library (path or server URL)
        book_id: The book ID to get the PDF for
        library_path: Physical library path (required if library is a server URL)

    Returns:
        Path to the PDF file, or None if not found or book doesn't have PDF format
    """
    result = _run_calibredb(
        ["list", "--fields", "formats", "--for-machine", f"--search", f"id:{book_id}"],
        library,
    )
    if result.returncode != 0:
        return None

    books = json.loads(result.stdout)
    if not books:
        return None

    book = books[0]
    formats = book.get("formats", "")
    if not formats:
        return None

    # formats may be a list (--for-machine via server) or comma-separated string
    if isinstance(formats, list):
        entries = formats
    else:
        entries = [p.strip() for p in formats.split(",")]

    for entry in entries:
        if entry.lower().endswith(".pdf"):
            return Path(entry)
        elif entry.upper() == "PDF":
            # Format name only - need to find on disk
            if library_path:
                return _find_pdf_for_book(library_path, book_id)

    return None


def set_pdf_metadata(library: Path | str, book_id: int, meta: PdfMetadata, *, dry_run: bool = False) -> None:
    """Write extracted PDF metadata into Calibre custom columns."""
    values = {
        "pdf_tagged": str(meta.is_tagged).lower(),
        "pdf_outlines": str(meta.has_outlines).lower(),
        "pdf_images": str(meta.has_images).lower(),
        "pdf_form_annotations": str(meta.has_form_annotations).lower(),
        "pdf_link_annotations": str(meta.has_link_annotations).lower(),
        "pdf_version": meta.pdf_version,
        "pdf_lang": meta.lang,
        "pdf_pages": str(meta.page_count),
        "pdf_layout": meta.layout,
        # Catalog features
        "pdf_page_labels": meta.page_labels_custom,
        "pdf_names": str(meta.has_names).lower(),
        "pdf_dests": str(meta.has_dests).lower(),
        "pdf_viewer_prefs": str(meta.has_viewer_prefs).lower(),
        "pdf_threads": str(meta.has_threads).lower(),
        "pdf_open_action": str(meta.has_open_action).lower(),
        "pdf_aa": str(meta.has_aa).lower(),
        "pdf_uri": str(meta.has_uri).lower(),
        "pdf_acroform": str(meta.has_acroform).lower(),
        "pdf_metadata_stream": str(meta.has_metadata_stream).lower(),
        "pdf_oc_properties": str(meta.has_oc_properties).lower(),
        "pdf_piece_info": str(meta.has_piece_info).lower(),
        "pdf_legal": str(meta.has_legal).lower(),
        "pdf_page_mode": meta.page_mode,
        # Page-level features
        "pdf_last_modified": meta.last_modified,
        "pdf_cropbox": meta.cropbox_custom,
        "pdf_artbox": meta.artbox_custom,
        "pdf_bleedbox": meta.bleedbox_custom,
        "pdf_rotations": str(meta.has_rotations).lower(),
        "pdf_thumbnails": str(meta.has_thumbnails).lower(),
        "pdf_annotations": str(meta.has_annotations).lower(),
        "pdf_user_unit": str(meta.has_user_unit).lower(),
        "pdf_paths": str(meta.has_paths).lower(),
        # Document-level features
        "pdf_embedded_fonts": str(meta.has_embedded_fonts).lower(),
        "pdf_attachments": str(meta.has_attachments).lower(),
    }

    for col, val in values.items():
        set_args = ["set_custom", f"{col}", str(book_id), val]
        if dry_run:
            print(f"  [dry-run] {' '.join(_build_cmd(set_args, library))}")
            continue
        r = _run_calibredb(set_args, library)
        if r.returncode != 0:
            print(f"  Warning: set_custom #{col} for book {book_id} failed: {r.stderr.strip()}")


def get_book_metadata(library: Path | str, book_id: int) -> dict:
    """Get current native metadata for a book (title, authors, tags, comments)."""
    result = _run_calibredb(
        ["show_metadata", str(book_id), "--for-machine"],
        library,
    )
    if result.returncode != 0:
        raise RuntimeError(f"calibredb show_metadata failed: {result.stderr}")

    metadata = json.loads(result.stdout)
    return {
        "title": metadata.get("title", ""),
        "authors": metadata.get("authors", []),
        "tags": metadata.get("tags", []),
        "comments": metadata.get("comments", ""),
    }


def set_native_metadata(
    library: Path | str,
    book_id: int,
    suggestion: BookSuggestion,
    *,
    dry_run: bool = False,
) -> None:
    """Apply Claude's suggested metadata to a book's native Calibre fields."""
    updates = []

    if suggestion.title:
        updates.extend(["--field", f"title:{suggestion.title}"])

    if suggestion.authors:
        # Authors need to be comma-separated
        authors_str = " & ".join(suggestion.authors)
        updates.extend(["--field", f"authors:{authors_str}"])

    if suggestion.tags:
        # Tags need to be comma-separated
        tags_str = ",".join(suggestion.tags)
        updates.extend(["--field", f"tags:{tags_str}"])

    if suggestion.comments:
        updates.extend(["--field", f"comments:{suggestion.comments}"])

    if not updates:
        return

    set_args = ["set_metadata", str(book_id)] + updates

    if dry_run:
        print(f"  [dry-run] {' '.join(_build_cmd(set_args, library))}")
        return

    r = _run_calibredb(set_args, library)
    if r.returncode != 0:
        print(f"  Warning: set_metadata for book {book_id} failed: {r.stderr.strip()}")
