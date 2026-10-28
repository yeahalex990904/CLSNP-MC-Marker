"""Find the outer MC grid border on a grayscale page image."""
from __future__ import annotations

import cv2
import numpy as np


def find_border(im: np.ndarray):
    """Return float32 quad [tl, tr, br, bl] or None."""
    th = cv2.adaptiveThreshold(
        im, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 51, 25
    )
    h = cv2.morphologyEx(
        th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (150, 1))
    )
    v = cv2.morphologyEx(
        th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 150))
    )
    lines = cv2.bitwise_or(h, v)
    lines = cv2.dilate(lines, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        x, y, w, h_ = cv2.boundingRect(c)
        if w > 700 and h_ > 700 and 0.8 < w / h_ < 1.1:
            if best is None or w * h_ > best[1]:
                best = (c, w * h_)
    if best is None:
        return None
    c = best[0]
    pts = c.reshape(-1, 2).astype(np.float32)
    s = pts.sum(1)
    d = pts[:, 0] - pts[:, 1]
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(d)]
    bl = pts[np.argmin(d)]
    return np.float32([tl, tr, br, bl])
