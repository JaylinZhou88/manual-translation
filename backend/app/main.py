from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import BlockStatus, BlockUpdate, ExportResponse
from .pdf_service import create_project_from_pdf, export_project_pdf
from .storage import DATA_DIR, ROOT_DIR, ensure_storage, load_project, save_project
from .translation import get_bailian_status, translate_to_vietnamese


app = FastAPI(title="Manual Translation Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_storage()
app.mount("/static", StaticFiles(directory=ROOT_DIR / "frontend"), name="static")
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "frontend" / "index.html")


@app.get("/api/translation-config")
def translation_config():
    return get_bailian_status()


@app.post("/api/projects")
async def create_project(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(await file.read())

    try:
        return create_project_from_pdf(tmp_path, file.filename)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/projects/{project_id}/pages")
def get_pages(project_id: str):
    try:
        return load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.") from None


@app.patch("/api/projects/{project_id}/blocks/{block_id}")
def update_block(project_id: str, block_id: str, update: BlockUpdate):
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.") from None

    for page in project.pages:
        for block in page.blocks:
            if block.id == block_id:
                if update.translated_text is not None:
                    block.translated_text = update.translated_text
                if update.reviewed is not None:
                    block.status = BlockStatus.REVIEWED if update.reviewed else BlockStatus.NEEDS_REVIEW
                save_project(project)
                return block

    raise HTTPException(status_code=404, detail="Block not found.")


@app.post("/api/projects/{project_id}/pages/{page_number}/translate")
def translate_page(project_id: str, page_number: int):
    status = get_bailian_status()
    if not status["configured"]:
        raise HTTPException(
            status_code=400,
            detail="DASHSCOPE_API_KEY is not visible to the running backend process.",
        )

    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.") from None

    page = next((item for item in project.pages if item.page_number == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")

    translated = 0
    failed = 0
    for block in page.blocks:
        if block.status == BlockStatus.REVIEWED:
            continue
        translated_text, note = translate_to_vietnamese(block.source_text)
        block.translated_text = translated_text
        block.note = note
        block.status = BlockStatus.FAILED if note else BlockStatus.NEEDS_REVIEW
        if note:
            failed += 1
        else:
            translated += 1

    save_project(project)
    return {
        "project_id": project_id,
        "page_number": page_number,
        "translated": translated,
        "failed": failed,
        "skipped_reviewed": sum(1 for block in page.blocks if block.status == BlockStatus.REVIEWED),
    }


@app.post("/api/projects/{project_id}/export", response_model=ExportResponse)
def export_pdf(project_id: str):
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.") from None

    out_path = export_project_pdf(project)
    blocks = [block for page in project.pages for block in page.blocks]
    reviewed = sum(1 for block in blocks if block.status == BlockStatus.REVIEWED)
    return ExportResponse(
        project_id=project_id,
        pdf_url=f"/data/projects/{project_id}/exports/{out_path.name}",
        reviewed_blocks=reviewed,
        total_blocks=len(blocks),
    )
