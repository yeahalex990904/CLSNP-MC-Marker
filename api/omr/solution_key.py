"""Extract an MC answer key from an official solution PDF.

Reads digital text (and Tesseract OCR when the PDF is a scan and the
``tesseract`` binary is installed). Typical CLSNP / HKDSE layouts:

- numbered lines ``1. C`` / ``1) C`` / ``Q1: C`` / ``第1題：C`` / ``1. Answer: D``
- several pairs on one line ``1. C  2. D  3. A``
- a table: a row of question numbers above a row of A–D
- a labelled letter list ``Answers: C D A B`` (question numbers are inferred)

Nothing is guessed. Conflicting letters, holes, and unnumbered lists come
back blank or flagged for the teacher to edit. A document that does not
contain a clear key raises ``SolutionKeyError``.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz

log = logging.getLogger("clsnp-mc-marker")

MAX_Q = 100
_FW = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "Ａ": "A",
        "Ｂ": "B",
        "Ｃ": "C",
        "Ｄ": "D",
        "ａ": "a",
        "ｂ": "b",
        "ｃ": "c",
        "ｄ": "d",
        "．": ".",
        "（": "(",
        "）": ")",
        "：": ":",
        "，": ",",
    }
)

# Number, then a real separator (punctuation or whitespace — not glued "1A"),
# then an optional "Answer:" label, then one letter. Parentheses allowed.
_PAIR = re.compile(
    r"(?:(?:Q(?:uestion)?|第)\s*)?"
    r"(?<!\d)(\d{1,3})(?!\d)"
    r"\s*題?\s*"
    r"(?:[.):、,]|(?=\s))"
    r"\s*"
    r"(?:(?:the\s+)?(?:correct\s+)?(?:answer|ans|答案|正確答案)\s*(?:is|為)?\s*:?\s*)?"
    r"\(?"
    r"\s*([A-Da-d])\s*"
    r"\)?"
    r"\.?"
    r"(?=\s|$|[,;/])",
    re.IGNORECASE,
)
_GLUED_LINE = re.compile(r"(?:\d{1,3}[A-Da-d]\s+){1,}\d{1,3}[A-Da-d]\s*")
_GLUED_ONE = re.compile(r"(\d{1,3})([A-Da-d])")
_BARE_Q = re.compile(r"(\d{1,3})")
_BARE_A = re.compile(r"\(?([A-Da-d])\)?\.?")
_Q_ONLY = re.compile(
    r"(?:(?:Q(?:uestion)?|第)\s*)?(\d{1,3})\s*題?\s*[.):、]\s*",
    re.IGNORECASE,
)
_ANS_ONLY = re.compile(
    r"(?:(?:the\s+)?(?:correct\s+)?(?:answer|ans|答案|正確答案)\s*(?:is|為)?\s*:?\s*)?"
    r"\(?([A-Da-d])\)?\.?",
    re.IGNORECASE,
)
_HEADING = re.compile(
    r"^(?:"
    r"multiple[- ]choice(?:\s+questions?)?(?:\s+answers?)?"
    r"|answers?(?:\s+to\s+(?:the\s+)?(?:mcq?|multiple[- ]choice))?"
    r"|answer\s+key"
    r"|mcq?\s+answers?"
    r"|paper\s*[12]\s+(?:mc\s+)?answers?"
    r"|section\s+a\s+answers?"
    r"|選擇題答案|多項選擇題答案|選擇題的答案|答案表|mc\s*答案"
    r")\s*:?\s*$",
    re.IGNORECASE,
)
_INLINE_SEQ = re.compile(
    r"^(?:answers?|answer\s*key|選擇題答案|答案)\s*:\s*"
    r"([A-Da-d](?:[\s,;/]+[A-Da-d]){2,}|[A-Da-d]{4,})\s*$",
    re.IGNORECASE,
)
_LETTER_LINE = re.compile(r"^[A-Da-d](?:[\s,;/]+[A-Da-d]){2,}$|^[A-Da-d]{4,}$", re.IGNORECASE)
_NUM_LINE = re.compile(r"^\d{1,3}(?:\s+\d{1,3}){2,}$")
_MARKS_TAIL = re.compile(
    r"\s*[\[(]\s*\d+\s*(?:marks?|分)?\s*[\])]\s*$",
    re.IGNORECASE,
)
_PAREN_LOWER = re.compile(r"\([a-d]\)")


class SolutionKeyError(ValueError):
    """The PDF did not yield a key. The message is safe to show to teachers."""


@dataclass
class KeyExtract:
    n: int
    key: list[str]
    review: list[int]
    warnings: list[str]
    partial: bool
    source: str

    def as_dict(self) -> dict:
        return {
            "ok": True,
            "n": self.n,
            "key": self.key,
            "review": self.review,
            "warnings": self.warnings,
            "partial": self.partial,
            "source": self.source,
        }


@dataclass
class _Hit:
    q: int
    letter: str | None
    source: str


@dataclass
class _Tok:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float


@dataclass
class _Gather:
    hits: list[_Hit] = field(default_factory=list)
    had_heading: bool = False
    had_table: bool = False
    n_lines: int = 0
    ignored_sequence: str | None = None


def extract_key_from_pdf(data: bytes) -> KeyExtract:
    """Extract a key from PDF bytes. Raises SolutionKeyError if none is defensible."""
    if not data:
        raise SolutionKeyError(_NO_TEXT)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise SolutionKeyError(
            "未能開啟這份 PDF（可能已加密）。請改用人手輸入。"
            " Could not open this PDF (it may be encrypted). Enter the key manually."
        ) from exc

    try:
        if doc.page_count < 1:
            raise SolutionKeyError(_NO_TEXT)
        if doc.is_encrypted and not doc.authenticate(""):
            raise SolutionKeyError(
                "這份 PDF 已加密，讀不到文字。請改用人手輸入。"
                " This PDF is encrypted. Enter the key manually."
            )

        pages = min(doc.page_count, 40)
        chunks: list[str] = []
        page_toks: list[list[_Tok]] = []
        for i in range(pages):
            page = doc.load_page(i)
            chunks.append(page.get_text("text") or "")
            page_toks.append(_page_tokens(page))
        text = "\n".join(chunks)
        alnum = sum(ch.isalnum() for ch in text)
        source = "pdf-text"
        # A short official key ("1. C" …) is only a handful of characters.
        # Image-only scans have none, so the cutoff stays at 2 — not a large page.
        if alnum < 2:
            ocr_text = _ocr_document(doc, limit_pages=min(pages, 6))
            if not ocr_text or sum(ch.isalnum() for ch in ocr_text) < 2:
                if shutil.which("tesseract"):
                    raise SolutionKeyError(_OCR_FAIL)
                raise SolutionKeyError(_NO_TEXT)
            text = ocr_text
            page_toks = []
            source = "pdf-ocr"
    finally:
        doc.close()

    gathered = _gather(text, page_toks)
    return _build(gathered, source)


def extract_key_from_text(text: str, *, source: str = "pdf-text") -> KeyExtract:
    """Parse an already-extracted solution transcript. Used by tests and OCR."""
    return _build(_gather(text or "", []), source)


def _gather(text: str, page_toks: list[list[_Tok]]) -> _Gather:
    g = _Gather()
    norm = _normalize_block(text)
    lines = [ln.strip() for ln in norm.splitlines()]
    g.n_lines = sum(1 for ln in lines if ln)
    g.hits.extend(_hits_from_lines(lines, g))
    for toks in page_toks:
        g.hits.extend(_hits_from_tokens(toks, g))
    return g


def _build(g: _Gather, source: str) -> KeyExtract:
    hits = list(g.hits)
    numbered = [h for h in hits if h.source != "sequence"]
    sequences = [h for h in hits if h.source == "sequence"]
    warnings: list[str] = []

    if numbered and sequences:
        seq_letters = "".join(h.letter or "" for h in sequences)
        if g.ignored_sequence and g.ignored_sequence != seq_letters:
            seq_letters = g.ignored_sequence
        if seq_letters:
            warnings.append(
                "另有一列沒有題號的答案，未採用，請核對題數。"
                " An extra unnumbered answer list was ignored; please check how many questions there are."
            )
        hits = numbered
    elif sequences and not numbered:
        letters = [h.letter for h in sequences if h.letter]
        if len(letters) < 3:
            raise SolutionKeyError(_NO_KEY)
        n = len(letters)
        warnings.append(
            "答案沒有題號，已由左至右當作 Q1 起，請逐格核對。"
            " No question numbers were printed; letters were read left to right as Q1 onward. Please check each box."
        )
        return KeyExtract(
            n=n,
            key=letters,
            review=list(range(1, n + 1)),
            warnings=warnings,
            partial=True,
            source=source,
        )

    by_q: dict[int, set[str]] = {}
    seen: set[int] = set()
    table_qs: set[int] = set()
    for h in hits:
        if h.q < 1 or h.q > MAX_Q:
            continue
        seen.add(h.q)
        if h.source == "table":
            table_qs.add(h.q)
        if h.letter:
            by_q.setdefault(h.q, set()).add(h.letter)

    keep = _drop_far_singletons(seen, protect=table_qs)
    if keep != seen:
        dropped = sorted(seen - keep)
        log.info("dropped isolated question numbers %s", dropped[:12])
        seen = keep
        by_q = {q: letters for q, letters in by_q.items() if q in keep}

    if not seen:
        raise SolutionKeyError(_NO_KEY)

    span = max(seen) - min(seen) + 1
    dense = len(seen) / span if span else 0
    if (
        not g.had_table
        and not g.had_heading
        and dense < 0.5
        and len(seen) < 10
    ):
        raise SolutionKeyError(_WEAK)
    if not g.had_table and not g.had_heading and _too_sparse_for_length(seen, g.n_lines):
        raise SolutionKeyError(_WEAK)

    n = max(seen)
    # A key that does not start at Q1 is suspicious unless it is a dense block
    # we actually saw (for example MC items numbered 21–40).
    if min(seen) > 1:
        missing_head = min(seen) - 1
        if missing_head > 0 and not g.had_table and missing_head > len(seen):
            raise SolutionKeyError(_WEAK)

    key = [""] * n
    review: list[int] = []
    conflicts: list[int] = []
    missing: list[int] = []
    for q in range(1, n + 1):
        letters = by_q.get(q) or set()
        if q not in seen or not letters:
            missing.append(q)
            review.append(q)
            continue
        if len(letters) > 1:
            conflicts.append(q)
            review.append(q)
            continue
        key[q - 1] = next(iter(letters))

    if conflicts:
        shown = ", ".join(f"Q{q}" for q in conflicts[:8])
        extra = "" if len(conflicts) <= 8 else f" …共 {len(conflicts)} 題"
        warnings.append(
            f"{shown}{extra} 出現多於一個答案，已留空，請核對。"
            " Those items had conflicting letters and were left blank."
        )
    if missing:
        shown = ", ".join(str(q) for q in missing[:12])
        extra = "" if len(missing) <= 12 else f" …共 {len(missing)} 題"
        warnings.append(
            f"未能讀取題號 {shown}{extra}，已留空請填寫。"
            " Those question numbers were missing and left blank."
        )

    if not any(key) and not g.had_table:
        raise SolutionKeyError(_NO_KEY)

    partial = bool(review)
    return KeyExtract(
        n=n,
        key=key,
        review=review,
        warnings=warnings,
        partial=partial,
        source=source,
    )


def _too_sparse_for_length(seen: set[int], n_lines: int) -> bool:
    """Reject one or two accidental matches inside a long write-up."""
    if len(seen) >= 5:
        return False
    if len(seen) >= 3 and min(seen) == 1 and max(seen) <= len(seen) + 1:
        return False
    if n_lines > 30 and len(seen) < 5:
        return True
    if n_lines > 12 and len(seen) < 3:
        return True
    return False


def _drop_far_singletons(seen: set[int], *, protect: set[int]) -> set[int]:
    """Drop a lone Q45-style hit sitting far from the main run of questions.

    Question numbers that came from an answer table are kept: those rows are
    explicit, not a stray page number.
    """
    if len(seen) < 4:
        return set(seen)
    qs = sorted(seen)
    runs: list[list[int]] = [[qs[0]]]
    for q in qs[1:]:
        if q - runs[-1][-1] <= 2:
            runs[-1].append(q)
        else:
            runs.append([q])
    long = [r for r in runs if len(r) >= 3]
    if not long:
        return set(seen)
    keep: set[int] = set()
    for r in long:
        keep.update(r)
    for r in runs:
        if len(r) >= 3:
            continue
        if any(q in protect for q in r):
            keep.update(r)
            continue
        anchor = min(
            min(abs(q - end) for end in (run[0], run[-1])) for run in long for q in r
        )
        if anchor <= 8:
            keep.update(r)
    return keep or set(seen)


def _hits_from_lines(lines: list[str], g: _Gather) -> list[_Hit]:
    hits: list[_Hit] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw:
            i += 1
            continue
        if _HEADING.match(raw):
            g.had_heading = True
            nxt = _next_nonempty(lines, i + 1)
            if nxt and _LETTER_LINE.match(nxt):
                hits.extend(_sequence_hits(nxt))
                i += 1
                while i < len(lines) and lines[i] != nxt:
                    i += 1
            i += 1
            continue

        seq = _INLINE_SEQ.match(raw)
        if seq:
            g.had_heading = True
            body = seq.group(1)
            hits.extend(_sequence_hits(body))
            g.ignored_sequence = _letters_of(body)
            i += 1
            continue

        glued = _glued_pairs(raw)
        if glued:
            hits.extend(_Hit(q, letter, "line") for q, letter in glued)
            i += 1
            continue

        pairs = _pairs_on_line(raw)
        if pairs:
            hits.extend(_Hit(q, letter, "line") for q, letter in pairs)
            i += 1
            continue

        zipped = _number_row_then_letters(lines, i)
        if zipped:
            g.had_table = True
            hits.extend(_Hit(q, letter, "table") for q, letter in zipped)
            i += 2
            continue

        q_only = _Q_ONLY.fullmatch(raw)
        if q_only and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            ans = _ANS_ONLY.fullmatch(nxt) if nxt else None
            if ans and not _PAREN_LOWER.fullmatch(nxt.replace(" ", "")):
                q = int(q_only.group(1))
                if 1 <= q <= MAX_Q:
                    hits.append(_Hit(q, ans.group(1).upper(), "line"))
                    i += 2
                    continue

        i += 1

    vertical = _vertical_runs(lines)
    if vertical:
        g.had_table = True
        hits.extend(vertical)
    return hits


def _hits_from_tokens(toks: list[_Tok], g: _Gather) -> list[_Hit]:
    if not toks:
        return []
    rows = _cluster_rows(toks)
    hits: list[_Hit] = []
    consumed_letter_rows: set[int] = set()
    for idx, row in enumerate(rows):
        alt = _alternating_row(row)
        if len(alt) >= 2:
            g.had_table = True
            hits.extend(_Hit(q, letter, "table") for q, letter in alt)
            continue
        nums = _number_centers(row)
        if len(nums) < 3 or not _strictly_consecutive([q for q, _x in nums]):
            continue
        letter_idx = _find_letter_row(rows, idx, consumed_letter_rows)
        if letter_idx is None:
            continue
        paired, ok = _align_numbers_to_letters(nums, rows[letter_idx])
        if not ok:
            continue
        g.had_table = True
        consumed_letter_rows.add(letter_idx)
        for q, letter in paired:
            hits.append(_Hit(q, letter, "table"))
    return hits


def _page_tokens(page: fitz.Page) -> list[_Tok]:
    out: list[_Tok] = []
    for w in page.get_text("words") or []:
        text = _normalize_inline(str(w[4]))
        if not text:
            continue
        out.append(_Tok(text=text, x0=float(w[0]), x1=float(w[2]), y0=float(w[1]), y1=float(w[3])))
    return out


def _cluster_rows(toks: list[_Tok]) -> list[list[_Tok]]:
    ordered = sorted(toks, key=lambda t: ((t.y0 + t.y1) / 2, t.x0))
    rows: list[list[_Tok]] = []
    for tok in ordered:
        yc = (tok.y0 + tok.y1) / 2
        if rows:
            prev = rows[-1]
            prev_yc = sum((p.y0 + p.y1) / 2 for p in prev) / len(prev)
            if abs(yc - prev_yc) <= 4.0:
                prev.append(tok)
                continue
        rows.append([tok])
    for row in rows:
        row.sort(key=lambda t: t.x0)
    return rows


def _number_centers(row: list[_Tok]) -> list[tuple[int, float]]:
    found: list[tuple[int, float]] = []
    for tok in row:
        if not _BARE_Q.fullmatch(tok.text):
            # Allow a row that is mostly numbers; skip junk labels.
            q = _as_q_token(tok.text)
            if q is None or not re.fullmatch(r"\d{1,3}[.)]?", tok.text):
                continue
        else:
            q = int(tok.text)
        if q is None or not 1 <= q <= MAX_Q:
            continue
        found.append((q, (tok.x0 + tok.x1) / 2))
    if len(found) < 3:
        return []
    # Reject rows that are mostly not numbers (a prose line that mentions "2").
    if len(found) < max(3, int(0.7 * len(row))):
        return []
    return found


def _find_letter_row(
    rows: list[list[_Tok]], num_idx: int, consumed: set[int]
) -> int | None:
    num_yc = sum((t.y0 + t.y1) / 2 for t in rows[num_idx]) / len(rows[num_idx])
    best = None
    best_dist = 1e9
    for j in range(num_idx + 1, min(num_idx + 4, len(rows))):
        if j in consumed:
            continue
        letters = [t for t in rows[j] if _as_letter_token(t.text)]
        if len(letters) < 3:
            continue
        if len(letters) < max(3, int(0.7 * len(rows[j]))):
            continue
        yc = sum((t.y0 + t.y1) / 2 for t in rows[j]) / len(rows[j])
        dist = yc - num_yc
        if dist <= 0 or dist > 36:
            continue
        if dist < best_dist:
            best = j
            best_dist = dist
    return best


def _align_numbers_to_letters(
    nums: list[tuple[int, float]], letter_row: list[_Tok]
) -> tuple[list[tuple[int, str | None]], bool]:
    letters = []
    for tok in letter_row:
        letter = _as_letter_token(tok.text)
        if letter:
            letters.append((letter, (tok.x0 + tok.x1) / 2))
    if len(letters) < 3:
        return [], False
    gaps = [b[1] - a[1] for a, b in zip(nums, nums[1:]) if b[1] > a[1]]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 40.0
    limit = max(18.0, median_gap * 0.55)
    used: set[int] = set()
    paired: list[tuple[int, str | None]] = []
    matched = 0
    for q, x in nums:
        best_i = None
        best_d = limit
        for i, (_letter, lx) in enumerate(letters):
            if i in used:
                continue
            d = abs(lx - x)
            if d <= best_d:
                best_d = d
                best_i = i
        if best_i is None:
            paired.append((q, None))
        else:
            used.add(best_i)
            paired.append((q, letters[best_i][0]))
            matched += 1
    if matched < max(3, int(0.6 * len(nums))):
        return [], False
    return paired, True


def _alternating_row(row: list[_Tok]) -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    i = 0
    while i < len(row) - 1:
        q = _as_q_token(row[i].text)
        letter = _as_letter_token(row[i + 1].text)
        if q and letter and (row[i + 1].x0 - row[i].x1) < 48:
            pairs.append((q, letter))
            i += 2
            continue
        i += 1
    if len(pairs) < 2:
        return []
    qs = [q for q, _a in pairs]
    if len(set(qs)) != len(qs):
        return []
    return pairs


def _number_row_then_letters(lines: list[str], i: int) -> list[tuple[int, str]] | None:
    if i + 1 >= len(lines):
        return None
    num_line = lines[i].strip()
    let_line = lines[i + 1].strip()
    if not _NUM_LINE.fullmatch(num_line) or not _LETTER_LINE.fullmatch(let_line):
        return None
    nums = [int(x) for x in num_line.split()]
    letters = _letters_of(let_line)
    if not _strictly_consecutive(nums):
        return None
    if abs(len(nums) - len(letters)) > 1:
        return None
    count = min(len(nums), len(letters))
    if count < 3:
        return None
    return [(nums[k], letters[k]) for k in range(count)]


def _vertical_runs(lines: list[str]) -> list[_Hit]:
    """Column-major text often comes out as ``1`` / ``C`` / ``2`` / ``D``."""
    hits: list[_Hit] = []
    run: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal run
        if len(run) >= 3 and _almost_consecutive([q for q, _a in run]):
            hits.extend(_Hit(q, letter, "table") for q, letter in run)
        run = []

    i = 0
    while i < len(lines) - 1:
        q_m = _BARE_Q.fullmatch(lines[i])
        a_m = _BARE_A.fullmatch(lines[i + 1]) if lines[i + 1] else None
        if (
            q_m
            and a_m
            and not _PAREN_LOWER.fullmatch(lines[i + 1].replace(" ", ""))
        ):
            q = int(q_m.group(1))
            if 1 <= q <= MAX_Q:
                run.append((q, a_m.group(1).upper()))
                i += 2
                continue
        flush()
        i += 1
    flush()
    return hits


def _pairs_on_line(line: str) -> list[tuple[int, str]] | None:
    raw = _prepare_line(line)
    if not raw or len(raw) > 240:
        return None
    matches = []
    for m in _PAIR.finditer(raw):
        token = m.group(0)
        if _PAREN_LOWER.search(token):
            continue
        q = int(m.group(1))
        if not 1 <= q <= MAX_Q:
            continue
        matches.append((q, m.group(2).upper(), m.start(), m.end()))
    if not matches:
        return None
    leftover = raw
    for _q, _a, start, end in reversed(matches):
        leftover = leftover[:start] + " " + leftover[end:]
    leftover = re.sub(
        r"\b(?:answer|answers|ans|mcq?|paper|section|key|答案|選擇題|正確答案)\b",
        " ",
        leftover,
        flags=re.IGNORECASE,
    )
    leftover = re.sub(r"[\s,;/·•*+:.\-]+", "", leftover)
    if leftover:
        return None
    # Lone glued-style match without punctuation is handled elsewhere.
    pairs = [(q, a) for q, a, _s, _e in matches]
    if len(set(q for q, _a in pairs)) != len(pairs):
        # Same line disagrees with itself — caller treats this as conflict
        # only across lines. Keep both by emitting each; build() will blank.
        return pairs
    return pairs


def _glued_pairs(line: str) -> list[tuple[int, str]] | None:
    raw = _prepare_line(line)
    if not raw or not _GLUED_LINE.fullmatch(raw):
        return None
    pairs = []
    for m in _GLUED_ONE.finditer(raw):
        q = int(m.group(1))
        if 1 <= q <= MAX_Q:
            pairs.append((q, m.group(2).upper()))
    if len(pairs) < 2:
        return None
    return pairs


def _sequence_hits(body: str) -> list[_Hit]:
    letters = _letters_of(body)
    return [_Hit(i + 1, letter, "sequence") for i, letter in enumerate(letters)]


def _letters_of(body: str) -> list[str]:
    compact = re.sub(r"[\s,;/]+", "", body)
    if re.fullmatch(r"[A-Da-d]{3,}", compact):
        return [c.upper() for c in compact]
    return [c.upper() for c in re.findall(r"[A-Da-d]", body)]


def _prepare_line(line: str) -> str:
    s = _normalize_inline(line)
    s = s.replace("|", " ").replace("│", " ")
    s = _MARKS_TAIL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_block(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    return text.translate(_FW)


def _normalize_inline(text: str) -> str:
    return text.replace("\u00a0", " ").translate(_FW).strip()


def _as_q_token(text: str) -> int | None:
    m = re.fullmatch(r"(?:Q(?:uestion)?)?(\d{1,3})[.)]?", text, re.IGNORECASE)
    if not m:
        return None
    q = int(m.group(1))
    if 1 <= q <= MAX_Q:
        return q
    return None


def _as_letter_token(text: str) -> str | None:
    if _PAREN_LOWER.fullmatch(text.replace(" ", "")):
        return None
    m = re.fullmatch(r"\(?([A-Da-d])\)?\.?", text)
    if not m:
        return None
    return m.group(1).upper()


def _strictly_consecutive(nums: list[int]) -> bool:
    if len(nums) < 3:
        return False
    return all(b - a == 1 for a, b in zip(nums, nums[1:])) and len(set(nums)) == len(nums)


def _almost_consecutive(nums: list[int]) -> bool:
    if len(nums) < 3:
        return False
    if nums != sorted(nums) or len(set(nums)) != len(nums):
        return False
    return all(b - a == 1 for a, b in zip(nums, nums[1:]))


def _next_nonempty(lines: list[str], start: int) -> str | None:
    for j in range(start, len(lines)):
        if lines[j].strip():
            return lines[j].strip()
    return None


def _ocr_document(doc: fitz.Document, limit_pages: int) -> str:
    if not shutil.which("tesseract"):
        return ""
    parts: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(min(doc.page_count, limit_pages)):
                pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                png = root / f"p{i}.png"
                pix.save(str(png))
                proc = subprocess.run(
                    ["tesseract", str(png), "stdout", "-l", "eng", "--psm", "6"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc.returncode == 0 and proc.stdout:
                    parts.append(proc.stdout)
                else:
                    log.info("tesseract page %s failed: %s", i + 1, (proc.stderr or "")[:200])
    except Exception:
        log.exception("solution PDF OCR failed")
        return ""
    return "\n".join(parts)


_NO_TEXT = (
    "這份 PDF 抽不到文字（可能是掃描圖片）。請改用人手輸入，系統不會猜測答案。"
    " No extractable text (it may be a scan). Enter the key manually — nothing was guessed."
)
_OCR_FAIL = (
    "已嘗試 OCR，仍讀不到選擇題答案。請改用人手輸入，系統不會猜測答案。"
    " OCR could not read an MC key. Enter it manually — nothing was guessed."
)
_NO_KEY = (
    "找到文字，但未能確定選擇題答案（需要題號加 A–D，或答案表格）。請改用人手輸入，系統不會猜測答案。"
    " No clear MC answer key was found. Enter it manually — nothing was guessed."
)
_WEAK = (
    "只看到零散題號，不敢當成答案表。請改用人手輸入或檢查 PDF，系統不會猜測答案。"
    " Only scattered question numbers were found, so no key was filled."
)
