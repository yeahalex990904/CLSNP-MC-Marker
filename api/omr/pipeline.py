"""End-to-end: PDF + answer key → coloured xlsx bytes/path."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .build_xlsx import build_results_xlsx
from .classify import classify_page, colour_role
from .header import read_header
from .key_parse import parse_answer_key
from .measure import measure_page
from .pdf_pages import pdf_to_gray_pages

log = logging.getLogger("clsnp-mc-marker")


def mark_page(im: np.ndarray, key: list[str], page_index: int) -> dict[str, Any]:
    """OMR one page image. Raises on hard failure (no border / bad grid)."""
    n = len(key)
    im2, q, measures, bw = measure_page(im)
    classified, Lm, Lk = classify_page(measures, n_questions=n)
    header = read_header(im2, q=q)

    answers = []
    for qn in range(1, n + 1):
        info = classified[qn]
        colour = colour_role(info["ans"], info["status"], key[qn - 1])
        answers.append(
            {
                "ans": info["ans"],
                "status": info["status"],
                "colour": colour,
                "note": info.get("note") or "",
            }
        )

    return {
        "page_index": page_index,
        "class_code": header.get("class_code") or "UNKNOWN",
        "class_no": header.get("class_no"),
        "name": "",  # handwriting OCR not in MVP — leave blank
        "header_status": header.get("status"),
        "header_note": header.get("note") or "",
        "answers": answers,
        "Lm": Lm,
        "Lk": Lk,
        "bw": bw,
    }


def mark_pdf(
    pdf_path: str | Path,
    key_text: str,
    title: str = "CLSNP MC",
    out_path: str | Path | None = None,
    dpi: int = 200,
) -> tuple[Path, dict]:
    """
    Full pipeline. Returns (xlsx_path, meta).
    Refuses to invent marks: every student row comes from a real PDF page.
    """
    key = parse_answer_key(key_text)
    if not key:
        raise ValueError("answer key is empty")
    if len(key) > 100:
        raise ValueError("answer key longer than 100 questions")

    pages = pdf_to_gray_pages(pdf_path, dpi=dpi)
    students: list[dict] = []
    errors: list[dict] = []

    for i, im in enumerate(pages):
        try:
            students.append(mark_page(im, key, page_index=i + 1))
        except Exception as exc:
            log.exception("page %s failed", i + 1)
            errors.append({"page": i + 1, "error": str(exc)})
            # Still record a yellow placeholder row so page is not silently dropped
            students.append(
                {
                    "page_index": i + 1,
                    "class_code": "UNKNOWN",
                    "class_no": None,
                    "name": f"(page {i + 1} OMR failed)",
                    "header_status": "ERROR",
                    "header_note": str(exc),
                    "answers": [
                        {"ans": "?", "status": "UNCLEAR", "colour": "yellow", "note": "page error"}
                        for _ in key
                    ],
                }
            )

    if out_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        out_path = Path(tmp.name)
        tmp.close()
    else:
        out_path = Path(out_path)

    summary = build_results_xlsx(students, key, title=title or "CLSNP MC", out_path=str(out_path))
    meta = {
        "title": title,
        "n_questions": len(key),
        "n_pages": len(pages),
        "n_students": len(students),
        "n_errors": len(errors),
        "errors": errors,
        "summary": summary,
        "key": key,
    }
    return out_path, meta
