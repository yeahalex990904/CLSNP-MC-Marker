"""Measure fill/dark/mid for each Q×option cell."""
from __future__ import annotations

import numpy as np

from .detect2 import cellpos, fit
from .refine import refine_cell


def page_boxes(im):
    im, q, sx, sy, bw, *_ = fit(im)
    B = im < 170
    boxes = {}
    for r in range(25):
        for c in range(16):
            x, y = cellpos(sx, sy, r, c)
            res = refine_cell(B, x, y)
            ok = (
                res is not None
                and 26 <= res[2] - res[0] + 1 <= 36
                and 16 <= res[3] - res[1] + 1 <= 21
            )
            boxes[(r, c)] = (x, y, res if ok else None)
    for c in range(16):
        dl, dt, dr, db = [], [], [], []
        for r in range(25):
            x, y, res = boxes[(r, c)]
            if res:
                dl.append(res[0] - x)
                dr.append(res[2] - x)
                dt.append(res[1] - y)
                db.append(res[3] - y)
        if not dl:
            # fall back to nominal inset box from bw
            for r in range(25):
                x, y, _ = boxes[(r, c)]
                boxes[(r, c)] = (
                    x,
                    y,
                    (x - bw / 2 + 5, y - 15, x + bw / 2 - 5, y - 4),
                    "nominal",
                )
            continue
        md = [np.median(v) for v in (dl, dt, dr, db)]
        for r in range(25):
            x, y, res = boxes[(r, c)]
            if res is None:
                boxes[(r, c)] = (x, y, (x + md[0], y + md[1], x + md[2], y + md[3]), "interp")
            else:
                boxes[(r, c)] = (x, y, res, "edge")
    return im, q, boxes, bw


def qcell(qn, opt):
    col = (qn - 1) // 25
    row = (qn - 1) % 25
    return row, col * 4 + opt


def measure_page(im, shrink=5):
    im, q, boxes, bw = page_boxes(im)
    out = {}
    for qn in range(1, 101):
        for o in range(4):
            r, c = qcell(qn, o)
            x, y, (l, t, rr, b), how = boxes[(r, c)]
            l, t, rr, b = [int(round(v)) for v in (l, t, rr, b)]
            # clamp
            h, w = im.shape[:2]
            l = max(0, l)
            t = max(0, t)
            rr = min(w - 1, rr)
            b = min(h - 1, b)
            ya, yb = t + shrink, b - shrink + 1
            xa, xb = l + shrink, rr - shrink + 1
            if yb <= ya or xb <= xa:
                p = np.full((1, 1), 255.0)
            else:
                p = im[ya:yb, xa:xb].astype(float)
            out[(qn, o)] = dict(
                fill=float((p < 170).mean()),
                dark=float((255 - p).mean() / 255),
                mid=float((p < 215).mean()),
                box=(l, t, rr, b),
                how=how,
            )
    return im, q, out, bw
