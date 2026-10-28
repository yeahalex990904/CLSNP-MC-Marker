"""Classify per-question answers from fill measurements (F6 UT2 classify2)."""
from __future__ import annotations

import numpy as np

LETTERS = "ABCD"


def classify_page(measures: dict, n_questions: int = 100) -> dict:
    """
    measures: {(qn, opt): {mid, dark, ...}} for qn 1..100, opt 0..3
    Returns {qn: {ans, status, note, mid, dark}} for qn 1..100
    """
    M = np.array([[measures[(q, o)]["mid"] for o in range(4)] for q in range(1, 101)])
    K = np.array([[measures[(q, o)]["dark"] for o in range(4)] for q in range(1, 101)])
    n = max(1, min(n_questions, 100))
    tm = M[:n].max(1)
    tk = K[:n].max(1)
    Lm = float(np.median(tm[tm > 0.25])) if (tm > 0.25).sum() > 5 else 0.8
    Lk = float(np.median(tk[tm > 0.25])) if (tm > 0.25).sum() > 5 else 0.3
    res = {}
    for i in range(100):
        q = i + 1
        m = M[i]
        k = K[i]
        mark = [o for o in range(4) if m[o] >= 0.5 * Lm and k[o] >= 0.45 * Lk]
        faint = [o for o in range(4) if o not in mark and (m[o] >= 0.12 or k[o] >= 0.06)]
        note = ""
        if len(mark) == 1:
            a = LETTERS[mark[0]]
            status = "OK"
            if faint:
                note = "faint mark at " + ",".join(LETTERS[o] for o in faint)
                status = (
                    "DOMINANT"
                    if max(m[o] for o in faint) < 0.6 * m[mark[0]]
                    and max(k[o] for o in faint) < 0.5 * k[mark[0]]
                    else "CHECK"
                )
        elif len(mark) >= 2:
            a = "/".join(LETTERS[o] for o in mark)
            status = "MULTIPLE"
        else:
            if faint:
                a = "?"
                status = "UNCLEAR"
                note = "faint mark at " + ",".join(LETTERS[o] for o in faint)
            else:
                a = "BLANK"
                status = "BLANK"
        res[q] = dict(
            ans=a,
            status=status,
            note=note,
            mid=[round(float(x), 2) for x in m],
            dark=[round(float(x), 2) for x in k],
        )
    return res, Lm, Lk


def colour_role(ans: str, status: str, key_letter: str) -> str:
    """
    Return 'green' | 'red' | 'yellow' for Excel fill.
    B/b accepted via uppercasing key and single-letter ans.
    """
    key_u = (key_letter or "").strip().upper()
    if status in ("UNCLEAR", "CHECK") or ans == "?":
        return "yellow"
    if status == "DOMINANT":
        # treat dominant single as readable
        a = ans.strip().upper()
        if len(a) == 1 and a == key_u:
            return "green"
        return "red"
    if status in ("BLANK", "MULTIPLE"):
        return "red"
    if status == "OK":
        a = ans.strip().upper()
        if len(a) == 1 and a == key_u:
            return "green"
        return "red"
    return "yellow"
