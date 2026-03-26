from dataclasses import dataclass, field


@dataclass
class PdfMetadata:
    """Extracted metadata from a single PDF file."""

    is_tagged: bool = False
    has_outlines: bool = False
    has_images: bool = False
    has_form_annotations: bool = False
    has_link_annotations: bool = False
    pdf_version: str = ""
    lang: str = ""
    page_count: int = 0
    layout: str = ""
    # Catalog features
    page_labels_custom: str = ""  # "yes", "no", "unknown"
    has_names: bool = False
    has_dests: bool = False
    has_viewer_prefs: bool = False
    has_threads: bool = False
    has_open_action: bool = False
    has_aa: bool = False
    has_uri: bool = False
    has_acroform: bool = False
    has_metadata_stream: bool = False
    has_oc_properties: bool = False
    has_piece_info: bool = False
    has_legal: bool = False
    page_mode: str = ""
    # Page-level features
    last_modified: str = ""
    cropbox_custom: str = ""  # "yes", "no", "unknown"
    artbox_custom: str = ""  # "yes", "no", "unknown"
    bleedbox_custom: str = ""  # "yes", "no", "unknown"
    has_rotations: bool = False
    has_thumbnails: bool = False
    has_annotations: bool = False
    has_user_unit: bool = False
    has_paths: bool = False
    # Document-level features
    has_embedded_fonts: bool = False
    has_attachments: bool = False


@dataclass
class BookSuggestion:
    """Claude-suggested metadata for a Calibre book."""

    title: str | None = None
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    comments: str | None = None
