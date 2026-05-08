from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BlockStatus(str, Enum):
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    FAILED = "failed"


class TextBlock(BaseModel):
    id: str
    page_number: int
    bbox: tuple[float, float, float, float]
    source_text: str
    translated_text: str
    font_size: float
    font_name: str | None = None
    is_bold: bool = False
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    role: Literal["body", "title", "section_title", "warning", "table"] = "body"
    status: BlockStatus = BlockStatus.NEEDS_REVIEW
    extraction_method: Literal["pdf_text", "ocr", "manual"] = "pdf_text"
    note: str | None = None


class PageModel(BaseModel):
    page_number: int
    width: float
    height: float
    preview_url: str
    extraction_status: Literal["ok", "needs_ocr", "failed"]
    blocks: list[TextBlock] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    filename: str
    created_at: str
    status: Literal["processing", "ready", "failed"]
    source_pdf: str
    pages: list[PageModel] = Field(default_factory=list)
    message: str | None = None


class BlockUpdate(BaseModel):
    translated_text: str | None = None
    reviewed: bool | None = None


class ExportResponse(BaseModel):
    project_id: str
    pdf_url: str
    reviewed_blocks: int
    total_blocks: int
