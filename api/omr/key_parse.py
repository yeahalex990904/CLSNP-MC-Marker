"""Parse MC answer keys from free-text paste formats."""
from __future__ import annotations

import re


_PAIR = re.compile(r"(?i)(?:^|[\s,;|/]+)(\d{1,3})\s*[.:)：\-]?\s*([A-Da-d])\b")
_LETTERS_ONLY = re.compile(r"(?i)^[\s,;|/]*([A-Da-d](?:[\s,;|/]+[A-Da-d])*)[\s,;|/]*$")
_CSV_LETTER = re.compile(r"(?i)^(?:\d{1,3}\s*[,:\t ]\s*)?([A-Da-d])\s*$")


def parse_answer_key(text: str) -> list[str]:
    """
    Accept:
      - '1C 2D 3A …' / '1.C, 2.D' / '1:C'
      - CSV lines '1,C' or just 'C'
      - a single line of letters 'C D A B …' or 'CDAB…' (contiguous)
    Returns list of uppercase A–D in question order (index 0 = Q1).
    Raises ValueError if empty / invalid.
    """
    if text is None:
        raise ValueError("answer key is empty")
    raw = text.strip()
    if not raw:
        raise ValueError("answer key is empty")

    # Contiguous block of only A–D letters (no digits): treat as Q1..Qn
    compact = re.sub(r"[\s,;|/]+", "", raw)
    if re.fullmatch(r"[A-Da-d]+", compact) and not re.search(r"\d", raw):
        return [c.upper() for c in compact]

    pairs = _PAIR.findall(raw)
    if pairs:
        by_q: dict[int, str] = {}
        for qs, a in pairs:
            q = int(qs)
            if q < 1 or q > 100:
                raise ValueError(f"question number out of range: {q}")
            by_q[q] = a.upper()
        n = max(by_q)
        missing = [i for i in range(1, n + 1) if i not in by_q]
        if missing:
            raise ValueError(f"answer key missing question(s): {missing[:10]}")
        return [by_q[i] for i in range(1, n + 1)]

    # Line-per-answer (CSV or plain letter)
    letters = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("question"):
            continue
        m = _CSV_LETTER.match(line)
        if m:
            letters.append(m.group(1).upper())
            continue
        # maybe '1,C' already handled by pairs; try last token
        toks = re.split(r"[\s,;|\t]+", line)
        found = None
        for t in reversed(toks):
            if re.fullmatch(r"[A-Da-d]", t):
                found = t.upper()
                break
        if found:
            letters.append(found)
        else:
            raise ValueError(f"cannot parse answer key line: {line!r}")
    if letters:
        return letters

    # Space-separated letters
    m = _LETTERS_ONLY.match(raw)
    if m:
        return [c.upper() for c in re.findall(r"[A-Da-d]", m.group(1))]

    raise ValueError(
        "unrecognised answer key format — try '1A 2B 3C…' or a line of letters"
    )
