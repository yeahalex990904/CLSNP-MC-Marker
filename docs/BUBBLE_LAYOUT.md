# CLSNP MC answer sheet — bubble layout for OMR calibration

Sources: `/workspace/mc-sheet/FINAL_METHOD.txt`, `build_final_overlay.py`,  
F6 UT2 pipeline `/workspace/f6-ut2-mc/{grid,measure}.json` + `code/detect2.py`  
(Page: A4 **595.32 × 841.92 pt**. Coordinates below are **top-left origin, y-down**, unless noted.)

**Primary PDF:** `/workspace/mc-sheet/CLSNP_MC_AnsSheet_final.pdf` (also v11 flat).

---

## 1. Shared bubble shape (Class / Class No / 100-Q options)

| Property | Value |
|----------|-------|
| Outer W × H | **11.51 × 6.11 pt** |
| Border strip | **0.67 pt** (four filled H/V strips; sharp corners; not round) |
| Aspect outer W/H | ~1.88 |
| Fill detection (prior OMR) | Dark / mid fill ratio inside inset box; threshold ~170 gray |

These are **horizontal rectangles**, not classic ovals — OMR templates must use rect ROIs.

---

## 2. Header ID band (Class + Class No OMR)

After Name widen (+28.346 pt = 1 cm on Name only):

| Landmark | pt (TL) |
|----------|---------|
| ID frame L / R / T / B | 31.08 / **342.94** / 82.56 / **235.00** |
| Name \| Class divider | x = **154.13** |
| Class \| Class No divider | x = **248.72** |
| Label H-divider (HDIV) | y = **113.10** |
| Marks box | (444.5, 82.5)–(560.3, 150.9) |
| Dashed rule / MC start | ~**240.8** (MC grid below; do not use header for Q bubbles) |

### Class bubbles — Form **1–6** | letter **A–E** (11 bubbles)

- Two columns; Form digits left, A–E right (A–E on first 5 rows of same pitch).  
- Bubble outer-left anchors (approx): **177.80** (Form col), **215.97** (letter col).  
- First bubble outer-top: **y_tl = 118.60** (HDIV + 5.5).  
- Row pitch: **~11.810 pt** (gap ~5.70).  
- Write-in boxes above HDIV (handwriting fallback): 20.4 × 13 pt centered on same column centers — **OMR should prefer bubbles**, not write boxes.

### Class No bubbles — **0–9 × 2 columns** (tens | ones = 20 bubbles)

- Bubble outer-left anchors (approx): **271.63** (tens), **309.53** (ones).  
- Same first-y and pitch as Class.  
- Sheet tip: single-digit Class No → fill **07** (tens=0, ones=7).  
- Last bubble outer-bottom ≈ 231.00 (above ID_BOTTOM 235).

**Total header OMR bubbles:** 11 + 20 = **31**.

---

## 3. MC grid Q1–100 (A–D)

- Sits **below** dashed rule (~y ≥ 242). Untouched by header overlay work.  
- **100 questions × 4 options (A–D)** in a bordered grid (Word-style filled border frames, same 11.51×6.11 bubble family).  
- Exact per-cell centres for the **new** final sheet should be re-measured from `CLSNP_MC_AnsSheet_final.pdf` at a fixed render DPI (recommend 150 or 200) into a `template.json` before production OMR.  
- Prior **old-sheet** F6 UT2 calibration (for pipeline shape only, **not** drop-in for new sheet):

```
grid.json (pixel centres at scan render used in Oct 2026):
  X: 16 option-column centres (4 blocks × A–D)
  Y: 25 question-row baselines
  border: [453, 732, 1128, 1208]  # template crop box
```

New sheet = new `template.json`. Do not reuse F6 UT2 pixel grid blindly.

**Suggested grid topology for new sheet (to confirm by measure):**  
Likely **4 vertical blocks × 25 questions** (Q1–25, 26–50, 51–75, 76–100), each question one row of A B C D — match printed final PDF.

---

## 4. OMR pipeline lessons (F6 UT2)

1. Find MC outer border → perspective / affine align.  
2. Fit bubble column/row model (least squares on detected ink blobs).  
3. Per option: `fill` (binary dark fraction) + `dark` (mean darkness).  
4. Status: single letter | `BLANK` | `MULTIPLE` (X/Y) | `UNCLEAR` → review.  
5. Score: only exact key match = correct; blank/double/unclear = 0 (red).  
6. Names were often weak OCR — prefer Class+No + roster; mark `(?)` when uncertain.

---

## 5. Results sheet columns + colours (target)

`Class | Class No. | Name | Q1…Qn | Total (/N)`  
+ Correct answer row + `% correct` + `Class average (/N)`  

| Role | Fill |
|------|------|
| Header | `#1F4E78` |
| Correct-answer row | `#FFF2CC` |
| Sure correct | **GREEN** `#C6EFCE` |
| Sure wrong / blank / double | **RED** `#FFC7CE` (score 0) |
| OMR unsure (colleague types in) | **YELLOW** `#FFEB9C` |

Match key case-insensitively (`B`/`b`). See repo root **COLOUR RULES** in `ARCHITECTURE.md` / `README.md`.

---

## 6. Calibration checklist before production OMR

- [ ] Render final PDF at fixed DPI; record px/pt scale  
- [ ] Export centres for 31 header bubbles + 400 MC option cells  
- [ ] Scan 5 filled sample sheets (flatbed); measure skew residual  
- [ ] Tune fill thresholds; build review list for doubles  
- [ ] Confirm Class encoding: e.g. Form `6` + `C` → class code `6C`
