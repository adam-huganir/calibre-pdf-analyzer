from pathlib import Path

import pikepdf


def extract_text(path: Path, max_pages: int = 3) -> str:
    """Extract text from the first N pages of a PDF.

    Note: pikepdf doesn't have built-in text extraction, so we use a simple
    approach that parses text operations from the content stream. This won't
    handle all PDF text encoding scenarios but works for most common PDFs.
    """
    with pikepdf.open(path) as pdf:
        pages_to_extract = min(max_pages, len(pdf.pages))
        extracted_text = []

        for i in range(pages_to_extract):
            page = pdf.pages[i]
            page_text = _extract_page_text(page)
            if page_text:
                extracted_text.append(page_text)

        # Join all pages and cap at ~4000 characters to avoid token bloat
        full_text = "\n\n".join(extracted_text)
        return full_text[:4000] if len(full_text) > 4000 else full_text


def _extract_page_text(page: pikepdf.Page) -> str:
    """Extract text from a single page by parsing the content stream."""
    text_parts = []

    try:
        # Parse the page's content stream to find text operations
        for operands, operator in pikepdf.parse_content_stream(page):
            if operator == pikepdf.Operator("Tj"):
                # Simple text show operation
                if operands:
                    text_parts.append(_decode_text_string(operands[0]))
            elif operator == pikepdf.Operator("TJ"):
                # Array of text/positioning - extract strings
                if operands and isinstance(operands[0], list):
                    for item in operands[0]:
                        if isinstance(item, (str, bytes, pikepdf.String)):
                            text_parts.append(_decode_text_string(item))
    except Exception:
        # If we can't parse the content stream, return what we have
        pass

    return " ".join(text_parts)


def _decode_text_string(text_obj) -> str:
    """Decode a PDF text string object into a Python string."""
    if isinstance(text_obj, pikepdf.String):
        # pikepdf.String has proper decoding
        return str(text_obj)
    elif isinstance(text_obj, bytes):
        # Try UTF-8, fall back to latin-1
        try:
            return text_obj.decode("utf-8")
        except UnicodeDecodeError:
            return text_obj.decode("latin-1", errors="ignore")
    elif isinstance(text_obj, str):
        return text_obj
    return ""