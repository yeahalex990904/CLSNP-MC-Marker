"""Render PDF pages to grayscale numpy arrays (PyMuPDF)."""
from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np


def pdf_to_gray_pages(pdf_path: str | Path, dpi: int = 200) -> list[np.ndarray]:
    """
    Render each page at `dpi` to a single-channel uint8 image.
    Raises if PDF has no pages or cannot be opened.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))
    doc = fitz.open(pdf_path)
    if doc.page_count < 1:
        doc.close()
        raise ValueError("PDF has no pages")
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pages = []
    try:
        for i in range(doc.page_count):
            pix = doc.load_page(i).get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            pages.append(arr.copy())
    finally:
        doc.close()
    return pages


def load_gray_image(path: str | Path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise FileNotFoundError(str(path))
    return im
