"""
CLSNP MC Marker — FastAPI service.

POST /api/mark  multipart: exam_name?, answer_key, pdf
GET  /api/health
Serves static UI from ../web when present.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from omr.key_parse import parse_answer_key
from omr.pipeline import mark_pdf
from omr.solution_key import SolutionKeyError, extract_key_from_pdf

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("clsnp-mc-marker")

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR.parent / "web"

app = FastAPI(title="CLSNP MC Marker", version="1.0.0")

# Colleagues may host UI on Vercel and API on Railway/Fly
_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "CLSNP MC Marker",
        "omr": "ported-f6-ut2",
        "version": "1.0.0",
    }


@app.post("/api/mark")
async def mark(
    answer_key: str = Form(..., description="MC key e.g. 1A 2B 3C…"),
    pdf: UploadFile = File(..., description="Whole-class scanned PDF"),
    exam_name: str = Form(""),
):
    if not pdf.filename:
        raise HTTPException(400, "PDF file required")
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF uploads are accepted")

    try:
        key = parse_answer_key(answer_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    data = await pdf.read()
    if not data:
        raise HTTPException(400, "Empty PDF upload")
    # Soft size guard (~80 MB)
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(400, "PDF too large (max 80 MB)")

    title = (exam_name or "").strip() or "CLSNP MC"
    safe = re.sub(r"[^\w\- .]+", "_", title)[:60].strip() or "CLSNP_MC"

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "scan.pdf"
        pdf_path.write_bytes(data)
        out_path = Path(tmp) / f"{safe} MC Results.xlsx"
        try:
            xlsx_path, meta = mark_pdf(pdf_path, answer_key, title=title, out_path=out_path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            log.exception("mark failed")
            raise HTTPException(500, f"OMR failed: {exc}") from exc

        # Copy out of temp dir before it is deleted
        final = Path(tempfile.gettempdir()) / f"clsnp-mc-{os.getpid()}-{safe}.xlsx"
        final.write_bytes(xlsx_path.read_bytes())

    headers = {
        "X-CLSNP-Pages": str(meta["n_pages"]),
        "X-CLSNP-Students": str(meta["n_students"]),
        "X-CLSNP-Errors": str(meta["n_errors"]),
        "X-CLSNP-Questions": str(meta["n_questions"]),
    }
    return FileResponse(
        path=str(final),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{safe} MC Results.xlsx",
        headers=headers,
    )


@app.post("/api/parse-key")
async def parse_key(
    answer_key: str = Form(""),
    pdf: UploadFile | None = File(None),
):
    """Parse a pasted key, or extract one from an official solution PDF.

    PDF responses may be partial: ``key`` slots are ``""`` and ``review`` lists
    the question numbers the teacher must check. Answers are never guessed.
    """
    filename = (pdf.filename or "").strip() if pdf is not None else ""
    if filename:
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF solution files are accepted")
        data = await pdf.read()
        if not data:
            raise HTTPException(400, "Empty solution PDF")
        if len(data) > 30 * 1024 * 1024:
            raise HTTPException(400, "Solution PDF too large (max 30 MB)")
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "File is not a PDF")
        try:
            extracted = extract_key_from_pdf(data)
        except SolutionKeyError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            log.exception("parse-key pdf failed")
            raise HTTPException(
                422,
                "未能讀取答案 PDF。請改用人手輸入，系統不會猜測答案。"
                f" Could not read the solution PDF ({exc}).",
            ) from exc
        return extracted.as_dict()

    if not (answer_key or "").strip():
        raise HTTPException(400, "Provide an answer key or a solution PDF")
    try:
        key = parse_answer_key(answer_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "n": len(key),
        "key": key,
        "review": [],
        "warnings": [],
        "partial": False,
        "source": "text",
    }


# Static UI last so /api/* wins
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:

    @app.get("/")
    def root():
        return JSONResponse(
            {
                "service": "CLSNP MC Marker",
                "hint": "web/ UI missing; use POST /api/mark",
            }
        )
