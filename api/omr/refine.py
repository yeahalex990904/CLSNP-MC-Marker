"""Per-cell border refine from local dark edges (F6 UT2 refine)."""
from __future__ import annotations

import numpy as np


def runs(mask):
    r = []
    s = None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        if not v and s is not None:
            r.append((s, i - 1))
            s = None
    if s is not None:
        r.append((s, len(mask) - 1))
    return r


def refine_cell(B, x, y):
    """B = binary dark (bool). Return (left, top, right, bot) or None."""
    X0 = int(x - 30)
    Y0 = int(y - 26)
    W = B[Y0 : Y0 + 34, X0 : X0 + 60]
    if W.shape[0] < 30 or W.shape[1] < 50:
        return None
    cen = W[:, 20:40]
    rf = cen.mean(1)
    rr = [t for t in runs(rf > 0.75)]
    if not rr:
        return None
    rr = [t for t in rr if 18 <= t[1] <= 32]
    if not rr:
        return None
    bot = rr[-1][1]
    top = None
    for t in runs(rf > 0.75):
        if t[1] == bot and t[1] - t[0] >= 10:
            top = bot - 18 if t[1] - t[0] > 22 else t[0]
            break
    if top is None:
        cands = [t for t in runs(rf > 0.75) if 12 <= bot - t[0] <= 22 and t[1] < bot - 4]
        if not cands:
            return None
        top = cands[0][0]
    mid = W[top + 4 : bot - 3, :]
    if mid.size == 0:
        return None
    cf = mid.mean(0)
    cr = runs(cf > 0.75)
    if not cr:
        return None
    lc = [t for t in cr if t[0] <= 24]
    rc = [t for t in cr if t[1] >= 36]
    if not lc or not rc:
        return None
    lt = min(lc, key=lambda t: abs((t[0] + t[1]) / 2 - 16))
    rt = min(rc, key=lambda t: abs((t[0] + t[1]) / 2 - 44))
    left = lt[0]
    right = rt[1]
    if lt == rt:
        left, right = lt[0], lt[1]
    return X0 + left, Y0 + top, X0 + right, Y0 + bot
