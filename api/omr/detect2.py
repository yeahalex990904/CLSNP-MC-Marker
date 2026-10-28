"""Least-squares bubble grid fit + cell centre solver (F6 UT2 detect2)."""
from __future__ import annotations

import cv2
import numpy as np

from .detect import detect


def fit(im: np.ndarray):
    im, q, X, Y, bw, n = detect(im)
    if len(X) < 16 or len(Y) < 25:
        # pad / trim to expected topology when close
        if len(X) != 16 or len(Y) != 25:
            raise ValueError(
                f"unexpected grid topology: {len(X)} cols × {len(Y)} rows "
                f"(need 16×25 for 100-Q A–D)"
            )
    # use first 16 / 25 if extras
    X = X[:16]
    Y = Y[:25]
    x0, y0 = q[0]
    x1, y1 = q[2]
    th = (im < 170).astype(np.uint8)
    _n, _lab, st, _cen = cv2.connectedComponentsWithStats(th)
    sel = [
        s
        for s in st[1:]
        if s[0] > x0 + 5
        and s[1] > y0 + 5
        and s[0] + s[2] < x1 - 5
        and s[1] + s[3] < y1 - 5
        and 26 <= s[2] <= 36
        and 15 <= s[3] <= 36
    ]
    pts = []
    for s in sel:
        cx = s[0] + s[2] / 2
        b = s[1] + s[3]
        c = int(np.argmin([abs(cx - x) for x in X]))
        r = int(np.argmin([abs(b - y) for y in Y]))
        if abs(cx - X[c]) < 10 and abs(b - Y[r]) < 10:
            pts.append((r, c, cx, b))
    if len(pts) < 100:
        raise ValueError(f"too few matched bubble points ({len(pts)})")
    pts = np.array(pts)
    R = pts[:, 0].astype(int)
    C = pts[:, 1].astype(int)
    cx = pts[:, 2]
    b = pts[:, 3]
    A = np.zeros((len(pts), 17))
    A[np.arange(len(pts)), C] = 1
    A[:, 16] = b - 1300
    solx, *_ = np.linalg.lstsq(A, cx, rcond=None)
    B = np.zeros((len(pts), 26))
    B[np.arange(len(pts)), R] = 1
    B[:, 25] = cx - 1000
    soly, *_ = np.linalg.lstsq(B, b, rcond=None)
    rx = cx - A @ solx
    ry = b - B @ soly
    return im, q, solx, soly, bw, len(pts), float(np.abs(rx).max()), float(np.abs(ry).max())


def cellpos(solx, soly, r, c):
    Xc, s = solx[c], solx[16]
    Yr, t = soly[r], soly[25]
    y = Yr
    for _ in range(5):
        x = Xc + s * (y - 1300)
        y = Yr + t * (x - 1000)
    return x, y
