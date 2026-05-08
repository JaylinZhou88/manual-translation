from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
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


AUTH_COOKIE = "manual_translation_auth"


def _auth_password() -> str | None:
    return os.getenv("APP_PASSWORD")


def _secure_cookie() -> bool:
    return bool(os.getenv("VERCEL"))


def _auth_token() -> str:
    password = _auth_password() or "local-dev"
    signature = hmac.new(password.encode("utf-8"), b"manual-translation", "sha256").hexdigest()
    return f"{secrets.token_urlsafe(12)}.{signature}"


def _valid_token(token: str | None) -> bool:
    password = _auth_password()
    if not password:
        return True
    if not token or "." not in token:
        return False
    signature = token.rsplit(".", 1)[1]
    expected = hmac.new(password.encode("utf-8"), b"manual-translation", "sha256").hexdigest()
    return hmac.compare_digest(signature, expected)


def require_auth(request: Request) -> None:
    if not _valid_token(request.cookies.get(AUTH_COOKIE)):
        raise HTTPException(status_code=401, detail="Password required.")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "frontend" / "index.html")


@app.get("/api/auth/status")
def auth_status(request: Request):
    return {"authenticated": _valid_token(request.cookies.get(AUTH_COOKIE))}


@app.post("/api/auth/login")
async def auth_login(request: Request, response: Response):
    password = _auth_password()
    if not password:
        response.set_cookie(AUTH_COOKIE, _auth_token(), httponly=True, samesite="lax")
        return {"authenticated": True}

    body = await request.json()
    submitted = str(body.get("password", ""))
    if not hmac.compare_digest(submitted, password):
        raise HTTPException(status_code=401, detail="Password is incorrect.")

    response.set_cookie(
        AUTH_COOKIE,
        _auth_token(),
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(),
        max_age=60 * 60 * 24 * 30,
    )
    return {"authenticated": True}


@app.get("/api/translation-config")
def translation_config(_: None = Depends(require_auth)):
    return get_bailian_status()


@app.post("/api/projects")
async def create_project(_: None = Depends(require_auth), file: UploadFile = File(...)):
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
def get_pages(project_id: str, _: None = Depends(require_auth)):
    try:
        return load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.") from None


@app.patch("/api/projects/{project_id}/blocks/{block_id}")
def update_block(project_id: str, block_id: str, update: BlockUpdate, _: None = Depends(require_auth)):
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
def translate_page(project_id: str, page_number: int, _: None = Depends(require_auth)):
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
def export_pdf(project_id: str, _: None = Depends(require_auth)):
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
