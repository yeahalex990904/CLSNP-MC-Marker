"""Coarse bubble column/row detection inside the MC border."""
from __future__ import annotations

import cv2
import numpy as np

from .grid import find_border


def clus(v, gap):
    idx = np.argsort(v)
    v = np.array(v)[idx]
    g = [[v[0]]]
    for a in v[1:]:
        if a - g[-1][-1] < gap:
            g[-1].append(a)
        else:
            g.append([a])
    return g


def detect(im: np.ndarray):
    """Return (im, border_quad, X, Y, bw, n_blobs). Raises if border missing."""
    q = find_border(im)
    if q is None:
        raise ValueError("MC grid border not found")
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
        and 24 <= s[2] <= 40
        and 15 <= s[3] <= 38
    ]
    if len(sel) < 50:
        raise ValueError(f"too few bubble blobs inside MC border ({len(sel)})")
    cx = [s[0] + s[2] / 2 for s in sel]
    bot = [s[1] + s[3] for s in sel]
    gx = [g for g in clus(cx, 12) if len(g) >= 8]
    gy = [g for g in clus(bot, 12) if len(g) >= 4]
    X = [float(np.median(g)) for g in gx]
    Y = [float(np.median(g)) for g in gy]
    bw = float(np.median([s[2] for s in sel]))
    return im, q, X, Y, bw, len(sel)
