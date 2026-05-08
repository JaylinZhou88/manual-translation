from __future__ import annotations

import html
import os
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import fitz

from .models import BlockStatus, PageModel, Project, TextBlock
from .storage import project_dir, save_project
from .translation import translate_to_vietnamese

ARIAL_FONT = Path("C:/Windows/Fonts/arial.ttf")
ARIAL_BOLD_FONT = Path("C:/Windows/Fonts/arialbd.ttf")


def _is_useful_text(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    visible = sum(not ch.isspace() for ch in text)
    return visible >= 2 and letters / max(visible, 1) > 0.25


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _span_is_bold(span: dict) -> bool:
    font = str(span.get("font", "")).lower()
    flags = int(span.get("flags", 0))
    return bool(flags & 16) or any(token in font for token in ("bold", "black", "heavy", "semibold"))


def _span_color(span: dict) -> tuple[float, float, float]:
    color = int(span.get("color", 0))
    return (
        round(((color >> 16) & 255) / 255, 4),
        round(((color >> 8) & 255) / 255, 4),
        round((color & 255) / 255, 4),
    )


def _detect_role(text: str, font_size: float, is_bold: bool, bbox: tuple[float, float, float, float]) -> str:
    width = bbox[2] - bbox[0]
    short_text = len(text) <= 80
    roman_heading = re.match(r"^(?:[IVX]+\.|\d+(?:\.\d+)*\.?)\s+\S+", text.strip())
    mostly_caps = text.upper() == text and any(ch.isalpha() for ch in text)
    if "warning" in text.lower():
        return "warning"
    if font_size >= 14 and short_text:
        return "title"
    if roman_heading or (font_size >= 10 and is_bold and short_text) or (mostly_caps and width > 40):
        return "section_title"
    return "body"


def _extract_pdf_blocks(page: fitz.Page, page_number: int, *, translate: bool) -> list[TextBlock]:
    data = page.get_text("dict", sort=True)
    blocks: list[TextBlock] = []
    counter = 0

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _normalize_text(" ".join(span.get("text", "") for span in spans))
            if not _is_useful_text(text):
                continue
            bbox = tuple(float(v) for v in line.get("bbox", block.get("bbox")))
            first_span = spans[0] if spans else {}
            font_size = max(6.0, min(22.0, float(first_span.get("size", 9.0)) if spans else 9.0))
            is_bold = any(_span_is_bold(span) for span in spans)
            font_name = str(first_span.get("font", "")) or None
            color = _span_color(first_span) if spans else (0.0, 0.0, 0.0)
            role = _detect_role(text, font_size, is_bold, bbox)
            if translate:
                translated, note = translate_to_vietnamese(text)
            else:
                translated = text
                note = "Not translated yet; use Translate Page."
            blocks.append(
                TextBlock(
                    id=f"p{page_number}-b{counter}",
                    page_number=page_number,
                    bbox=bbox,
                    source_text=text,
                    translated_text=translated,
                    font_size=font_size,
                    font_name=font_name,
                    is_bold=is_bold or role in ("title", "section_title", "warning"),
                    color=color,
                    role=role,
                    status=BlockStatus.NEEDS_REVIEW,
                    extraction_method="pdf_text",
                    note=note,
                )
            )
            counter += 1
    return blocks


def _render_preview(page: fitz.Page, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pix.save(output_path)


def create_project_from_pdf(source_pdf: Path, original_filename: str) -> Project:
    project_id = uuid4().hex
    out_dir = project_dir(project_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stored_pdf = out_dir / "source.pdf"
    stored_pdf.write_bytes(source_pdf.read_bytes())

    project = Project(
        id=project_id,
        filename=original_filename,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="processing",
        source_pdf=str(stored_pdf),
    )
    save_project(project)

    try:
        doc = fitz.open(stored_pdf)
        pages: list[PageModel] = []
        for index, page in enumerate(doc):
            page_number = index + 1
            preview_name = f"page-{page_number:03d}.png"
            _render_preview(page, out_dir / "previews" / preview_name)
            auto_translate = os.getenv("AUTO_TRANSLATE_ON_UPLOAD", "false").lower() == "true"
            blocks = _extract_pdf_blocks(page, page_number, translate=auto_translate)
            pages.append(
                PageModel(
                    page_number=page_number,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    preview_url=f"/data/projects/{project_id}/previews/{preview_name}",
                    extraction_status="ok" if blocks else "needs_ocr",
                    blocks=blocks,
                )
            )

        project.pages = pages
        project.status = "ready"
        empty_pages = sum(1 for page in pages if not page.blocks)
        if empty_pages:
            project.message = (
                f"{empty_pages} page(s) need OCR/manual text marking. "
                "Install OCR support in a later version for scanned pages."
            )
        save_project(project)
        return project
    except Exception as exc:
        project.status = "failed"
        project.message = str(exc)
        save_project(project)
        raise


def export_project_pdf(project: Project) -> Path:
    doc = fitz.open(project.source_pdf)

    for page_model in project.pages:
        page = doc[page_model.page_number - 1]
        for block in page_model.blocks:
            if not block.translated_text.strip():
                continue
            rect = fitz.Rect(block.bbox)
            pad = 1.2
            cover = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
            page.draw_rect(cover, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
            role = _effective_role(block)
            extra_height = 34 if role in ("title", "section_title") else 18
            text_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1 + extra_height)
            font_size = _export_font_size(block, role)
            _insert_textbox_fit(
                page,
                text_rect,
                block.translated_text,
                font_size,
                bold=block.is_bold or role in ("title", "section_title", "warning"),
                color=_readable_color(block.color),
            )

    out_path = project_dir(project.id) / "exports" / "manual-vi.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return out_path


def _effective_role(block: TextBlock) -> str:
    if block.role != "body":
        return block.role
    return _detect_role(block.source_text, block.font_size, block.is_bold, block.bbox)


def _export_font_size(block: TextBlock, role: str) -> float:
    if role == "title":
        return max(10.0, min(block.font_size * 0.96, 18.0))
    if role in ("section_title", "warning"):
        return max(7.2, min(block.font_size * 0.94, 13.0))
    return max(5.2, min(block.font_size * 0.88, 10.5))


def _readable_color(color: tuple[float, float, float]) -> tuple[float, float, float]:
    brightness = (color[0] * 0.299) + (color[1] * 0.587) + (color[2] * 0.114)
    return (0.0, 0.0, 0.0) if brightness > 0.82 else color


def _font_kwargs(bold: bool) -> dict[str, str]:
    if bold and ARIAL_BOLD_FONT.exists():
        return {"fontname": "ManualArialBold", "fontfile": str(ARIAL_BOLD_FONT)}
    if ARIAL_FONT.exists():
        return {"fontname": "ManualArial", "fontfile": str(ARIAL_FONT)}
    return {"fontname": "helv"}


def _insert_textbox_fit(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    font_size: float,
    *,
    bold: bool,
    color: tuple[float, float, float],
) -> None:
    size = font_size
    expanded = fitz.Rect(rect.x0, rect.y0, min(page.rect.x1, rect.x1 + 22), min(page.rect.y1, rect.y1 + 30))
    safe_text = html.unescape(text)
    font_kwargs = _font_kwargs(bold)
    while size >= 4.5:
        result = page.insert_textbox(
            expanded,
            safe_text,
            fontsize=size,
            color=color,
            align=fitz.TEXT_ALIGN_LEFT,
            overlay=True,
            **font_kwargs,
        )
        if result >= 0:
            return
        page.draw_rect(expanded, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
        size -= 0.5

    fallback = "\n".join(textwrap.wrap(safe_text, width=28))[:500]
    page.insert_textbox(
        expanded,
        fallback,
        fontsize=4.5,
        color=color if color != (1.0, 1.0, 1.0) else (0.0, 0.0, 0.0),
        align=fitz.TEXT_ALIGN_LEFT,
        overlay=True,
        **font_kwargs,
    )
