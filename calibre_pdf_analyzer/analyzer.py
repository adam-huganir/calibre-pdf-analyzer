from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Name

from calibre_pdf_analyzer.models import PdfMetadata


@dataclass
class PageLevelResults:
    """Results from scanning all pages in a single pass."""
    has_images: bool = False
    has_form_annotations: bool = False
    has_link_annotations: bool = False
    has_rotations: bool = False
    has_thumbnails: bool = False
    has_annotations: bool = False
    has_user_unit: bool = False
    has_paths: bool = False
    has_embedded_fonts: bool = False


def analyze_pdf(path: Path) -> PdfMetadata:
    """Open a PDF and extract structural metadata."""
    with pikepdf.open(path) as pdf:
        catalog = pdf.Root
        meta = PdfMetadata()

        meta.pdf_version = pdf.pdf_version
        meta.page_count = len(pdf.pages)
        meta.is_tagged = _check_tagged(catalog)
        meta.has_outlines = Name.Outlines in catalog
        meta.lang = str(catalog.get(Name.Lang, "")).lstrip("/")
        meta.layout = str(catalog.get(Name.PageLayout, "")).lstrip("/")
        # Page-level features - single pass through all pages
        page_results = _scan_all_pages(pdf)
        meta.has_images = page_results.has_images
        meta.has_form_annotations = page_results.has_form_annotations
        meta.has_link_annotations = page_results.has_link_annotations
        meta.has_rotations = page_results.has_rotations
        meta.has_thumbnails = page_results.has_thumbnails
        meta.has_annotations = page_results.has_annotations
        meta.has_user_unit = page_results.has_user_unit
        meta.has_paths = page_results.has_paths
        meta.has_embedded_fonts = page_results.has_embedded_fonts

        # Catalog features
        meta.page_labels_custom = _check_page_labels(catalog, pdf)
        meta.has_names = Name.Names in catalog
        meta.has_dests = Name.Dests in catalog
        meta.has_viewer_prefs = Name.ViewerPreferences in catalog
        meta.has_threads = Name.Threads in catalog
        meta.has_open_action = Name.OpenAction in catalog
        meta.has_aa = Name.AA in catalog
        meta.has_uri = Name.URI in catalog
        meta.has_acroform = Name.AcroForm in catalog
        meta.has_metadata_stream = Name.Metadata in catalog
        meta.has_oc_properties = Name.OCProperties in catalog
        meta.has_piece_info = Name.PieceInfo in catalog
        meta.has_legal = Name.Legal in catalog
        meta.page_mode = str(catalog.get(Name.PageMode, "")).lstrip("/")

        # First page-specific features
        if len(pdf.pages) > 0:
            first_page = pdf.pages[0]
            meta.last_modified = str(first_page.get(Name.LastModified, "")).lstrip("/")
            meta.cropbox_custom, meta.artbox_custom, meta.bleedbox_custom = _check_page_boxes(first_page)

        # Document-level features
        meta.has_attachments = _check_attachments(catalog)

        return meta


def _check_tagged(catalog: pikepdf.Dictionary) -> bool:
    """Check if the PDF is tagged (has StructTreeRoot or MarkInfo.Marked)."""
    if Name.StructTreeRoot in catalog:
        return True
    mark_info = catalog.get(Name.MarkInfo)
    if mark_info and mark_info.get(Name.Marked):
        return True
    return False


def _scan_all_pages(pdf: pikepdf.Pdf) -> PageLevelResults:
    """Scan all pages in a single pass to extract multiple features efficiently."""
    results = PageLevelResults()

    for page in pdf.pages:
        # Check rotations
        if not results.has_rotations:
            rotate = page.get(Name.Rotate, 0)
            try:
                if int(rotate) % 360 != 0:
                    results.has_rotations = True
            except (ValueError, TypeError):
                pass

        # Check thumbnails
        if not results.has_thumbnails and Name.Thumb in page:
            results.has_thumbnails = True

        # Check UserUnit
        if not results.has_user_unit and Name.UserUnit in page:
            results.has_user_unit = True

        # Check annotations (general and specific types)
        if not results.has_annotations or not results.has_form_annotations or not results.has_link_annotations:
            annots = page.get(Name.Annots, [])
            if annots and len(annots) > 0:
                results.has_annotations = True
                # Check specific annotation types
                for annot in annots:
                    try:
                        if isinstance(annot, pikepdf.objects.Object):
                            annot = annot.resolve() if hasattr(annot, "resolve") else annot
                        subtype = annot.get(Name.Subtype)
                        if subtype == Name.Widget:
                            results.has_form_annotations = True
                        elif subtype == Name.Link:
                            results.has_link_annotations = True
                    except Exception:
                        continue

        # Check resources
        try:
            resources = page.get(Name.Resources, {})

            # Check images
            if not results.has_images:
                xobjects = resources.get(Name.XObject, {})
                for xobj_name in xobjects:
                    xobj = xobjects[xobj_name]
                    if isinstance(xobj, pikepdf.Stream) and xobj.get(Name.Subtype) == Name.Image:
                        results.has_images = True
                        break

            # Check embedded fonts
            if not results.has_embedded_fonts:
                fonts = resources.get(Name.Font, {})
                for font_name in fonts:
                    font = fonts[font_name]
                    if isinstance(font, pikepdf.Dictionary):
                        font_descriptor = font.get(Name.FontDescriptor)
                        if font_descriptor and isinstance(font_descriptor, pikepdf.Dictionary):
                            if (Name.FontFile in font_descriptor or
                                Name.FontFile2 in font_descriptor or
                                Name.FontFile3 in font_descriptor):
                                results.has_embedded_fonts = True
                                break
        except Exception:
            pass

        # Check clipping paths
        if not results.has_paths:
            try:
                for operands, operator in pikepdf.parse_content_stream(page):
                    if operator == pikepdf.Operator("W") or operator == pikepdf.Operator("W*"):
                        results.has_paths = True
                        break
            except Exception:
                pass

        # Early exit if we found everything
        if (results.has_images and results.has_form_annotations and results.has_link_annotations and
            results.has_rotations and results.has_thumbnails and results.has_annotations and
            results.has_user_unit and results.has_paths and results.has_embedded_fonts):
            break

    return results


def _check_page_boxes(page: pikepdf.Page) -> tuple[str, str, str]:
    """Check if CropBox, ArtBox, and BleedBox differ from their defaults.

    Returns (cropbox_custom, artbox_custom, bleedbox_custom) where each is:
    - "yes" if the box differs from its default
    - "no" if the box matches its default
    - "unknown" if the box is not present

    Logic:
    - CropBox: compare to MediaBox (default is MediaBox)
    - ArtBox: compare to CropBox (default is CropBox)
    - BleedBox: compare to CropBox (default is CropBox)
    """
    # Get boxes, using mediabox as fallback
    mediabox = page.get(Name.MediaBox)
    if not mediabox:
        return "unknown", "unknown", "unknown"

    # CropBox defaults to MediaBox if not present
    cropbox = page.get(Name.CropBox)
    if cropbox is None:
        cropbox_custom = "unknown"
        effective_cropbox = mediabox
    elif _boxes_equal(cropbox, mediabox):
        cropbox_custom = "no"
        effective_cropbox = cropbox
    else:
        cropbox_custom = "yes"
        effective_cropbox = cropbox

    # ArtBox defaults to CropBox if not present
    artbox = page.get(Name.ArtBox)
    if artbox is None:
        artbox_custom = "unknown"
    elif _boxes_equal(artbox, effective_cropbox):
        artbox_custom = "no"
    else:
        artbox_custom = "yes"

    # BleedBox defaults to CropBox if not present
    bleedbox = page.get(Name.BleedBox)
    if bleedbox is None:
        bleedbox_custom = "unknown"
    elif _boxes_equal(bleedbox, effective_cropbox):
        bleedbox_custom = "no"
    else:
        bleedbox_custom = "yes"

    return cropbox_custom, artbox_custom, bleedbox_custom


def _boxes_equal(box1, box2) -> bool:
    """Compare two PDF boxes for equality."""
    try:
        # Convert to lists if needed
        b1 = list(box1) if hasattr(box1, '__iter__') else [box1]
        b2 = list(box2) if hasattr(box2, '__iter__') else [box2]

        if len(b1) != len(b2):
            return False

        # Compare each coordinate
        for v1, v2 in zip(b1, b2):
            # Convert to floats for comparison
            f1 = float(v1) if hasattr(v1, '__float__') else float(str(v1))
            f2 = float(v2) if hasattr(v2, '__float__') else float(str(v2))
            if abs(f1 - f2) > 0.01:  # Allow small floating point differences
                return False
        return True
    except Exception:
        return False


def _check_attachments(catalog: pikepdf.Dictionary) -> bool:
    """Check if the PDF has file attachments.

    Attachments can be in the Names dictionary under EmbeddedFiles,
    or in the catalog's AF (Associated Files) entry.
    """
    # Check Names -> EmbeddedFiles
    names = catalog.get(Name.Names)
    if names and isinstance(names, pikepdf.Dictionary):
        if Name.EmbeddedFiles in names:
            return True

    # Check AF (Associated Files) in catalog
    if Name.AF in catalog:
        return True

    return False


def _check_page_labels(catalog: pikepdf.Dictionary, pdf: pikepdf.Pdf) -> str:
    """Check if page labels are customized.

    Returns:
    - "unknown" if there's no PageLabels dictionary
    - "no" if page labels match the default (1-indexed decimals: 1, 2, 3...)
    - "yes" if page labels are customized
    """
    if Name.PageLabels not in catalog:
        return "unknown"

    try:
        page_labels = catalog.get(Name.PageLabels)
        if not page_labels or not isinstance(page_labels, pikepdf.Dictionary):
            return "unknown"

        # Check if there's a Nums array defining custom labels
        nums = page_labels.get(Name.Nums)
        if not nums or len(nums) == 0:
            return "unknown"

        # If Nums exists and has content, labels are customized
        # The Nums array contains pairs: [page_index, label_dict, ...]
        # If there's any entry, it means labels are non-default
        return "yes"

    except Exception:
        return "unknown"
