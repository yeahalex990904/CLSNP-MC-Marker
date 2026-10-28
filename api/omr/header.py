"""
Class / Class No bubble OMR for the new CLSNP sheet.

Uses BUBBLE_LAYOUT.md geometry at the template DPI, mapped onto each scan
via the found MC border (affine from template blank MC quad → scan MC quad).
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .grid import find_border

_TMPL = json.loads((Path(__file__).with_name("template.json")).read_text())


def _tmpl_mc_quad():
    x, y, w, h = _TMPL["mc_border_px"]
    return np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def _affine_from_mc(q_scan: np.ndarray):
    """3×2 affine mapping template → scan using MC corners (TL,TR,BL)."""
    src = _tmpl_mc_quad()
    # use tl, tr, bl
    M = cv2.getAffineTransform(src[[0, 1, 3]], q_scan[[0, 1, 3]])
    return M


def _map_xy(M, x, y):
    p = M @ np.array([x, y, 1.0])
    return float(p[0]), float(p[1])


def _fill_box(im, x_tl, y_tl, bw, bh, inset=0.22):
    """Dark / mid fill inside inset box. Returns (fill, dark, mid)."""
    ix = bw * inset
    iy = bh * inset
    xa = int(round(x_tl + ix))
    xb = int(round(x_tl + bw - ix))
    ya = int(round(y_tl + iy))
    yb = int(round(y_tl + bh - iy))
    h, w = im.shape[:2]
    xa, ya = max(0, xa), max(0, ya)
    xb, yb = min(w, xb), min(h, yb)
    if xb <= xa or yb <= ya:
        return 0.0, 0.0, 0.0
    p = im[ya:yb, xa:xb].astype(float)
    fill = float((p < 170).mean())
    dark = float((255 - p).mean() / 255)
    mid = float((p < 215).mean())
    return fill, dark, mid


def _pick_column(scores, labels, mid_thresh=0.25, dark_thresh=0.12):
    """
    scores: list of (mid, dark) per bubble.
    Return (label_or_None, status) where status is OK|BLANK|MULTIPLE|UNCLEAR.
    """
    marked = [
        i
        for i, (m, d) in enumerate(scores)
        if m >= mid_thresh and d >= dark_thresh
    ]
    faint = [
        i
        for i, (m, d) in enumerate(scores)
        if i not in marked and (m >= 0.12 or d >= 0.06)
    ]
    if len(marked) == 1:
        return labels[marked[0]], "OK"
    if len(marked) >= 2:
        return "/".join(labels[i] for i in marked), "MULTIPLE"
    if faint:
        return "?", "UNCLEAR"
    return None, "BLANK"


def read_header(im: np.ndarray, q=None) -> dict:
    """
    Read Class (form+letter) and Class No (tens+ones) from header bubbles.
    Returns dict with class_code, class_no, status flags, raw picks.
    """
    if q is None:
        q = find_border(im)
    if q is None:
        return {
            "class_code": "UNKNOWN",
            "class_no": None,
            "form": None,
            "letter": None,
            "tens": None,
            "ones": None,
            "status": "NO_BORDER",
            "note": "MC border missing; cannot map header",
        }

    M = _affine_from_mc(q)
    H = _TMPL["header"]
    bw, bh = H["bw"], H["bh"]
    pitch = H["pitch"]
    y0 = H["y_tl0"]

    def col_scores(x_tl, n):
        out = []
        for i in range(n):
            x, y = _map_xy(M, x_tl, y0 + i * pitch)
            # x_tl in template; mapped point is top-left of bubble
            # Actually _map_xy maps the TL corner; measure from there
            _f, d, m = _fill_box(im, x, y, bw * (M[0, 0] if abs(M[0, 0]) > 0.1 else 1),
                                 bh * (M[1, 1] if abs(M[1, 1]) > 0.1 else 1))
            # scale bw/bh by average scale of affine
            out.append((m, d))
        return out

    # Better: scale bubble size by affine scale
    scale = float(np.sqrt(abs(np.linalg.det(M[:, :2]))))
    bw_s, bh_s = bw * scale, bh * scale

    def col_scores2(x_tl, n):
        out = []
        for i in range(n):
            x, y = _map_xy(M, x_tl, y0 + i * pitch)
            _f, d, m = _fill_box(im, x, y, bw_s, bh_s)
            out.append((m, d))
        return out

    form_s = col_scores2(H["form_x_tl"], 6)
    let_s = col_scores2(H["letter_x_tl"], 5)
    tens_s = col_scores2(H["tens_x_tl"], 10)
    ones_s = col_scores2(H["ones_x_tl"], 10)

    form, fs = _pick_column(form_s, H["form_labels"])
    letter, ls = _pick_column(let_s, H["letter_labels"])
    tens, ts = _pick_column(tens_s, H["digit_labels"])
    ones, os_ = _pick_column(ones_s, H["digit_labels"])

    notes = []
    if fs != "OK":
        notes.append(f"form:{fs}")
    if ls != "OK":
        notes.append(f"letter:{ls}")
    if ts != "OK":
        notes.append(f"tens:{ts}")
    if os_ != "OK":
        notes.append(f"ones:{os_}")

    if form and letter and "/" not in form and "/" not in letter and form != "?" and letter != "?":
        class_code = f"{form}{letter}"
    else:
        class_code = "UNKNOWN"

    class_no = None
    if (
        tens is not None
        and ones is not None
        and tens not in ("?",)
        and ones not in ("?",)
        and "/" not in str(tens)
        and "/" not in str(ones)
    ):
        try:
            class_no = int(tens) * 10 + int(ones)
        except ValueError:
            class_no = None

    all_blank = {fs, ls, ts, os_} == {"BLANK"}
    if all_blank:
        status = "BLANK"
    elif not notes:
        status = "OK"
    elif class_code != "UNKNOWN" or class_no is not None:
        status = "PARTIAL"
    else:
        status = "UNCLEAR"
    return {
        "class_code": class_code,
        "class_no": class_no,
        "form": form,
        "letter": letter,
        "tens": tens,
        "ones": ones,
        "status": status,
        "note": "; ".join(notes),
    }
