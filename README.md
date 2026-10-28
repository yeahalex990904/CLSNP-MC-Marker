# CLSNP MC Marker

Standalone web app for CLSNP maths colleagues: enter an MC answer key (or upload the official solution PDF), upload a **whole-class scanned PDF** of CLSNP MC bubble sheets, download a coloured Excel (`.xlsx`).

**No Google Cloud, no Grok Bot, no secrets required for colleagues** — they open the public URL and mark.

Branding / title: **CLSNP MC Marker**.

## What you get

| Input | Output |
|-------|--------|
| Answer key: N boxes of A/B/C/D, **or** an official solution PDF | Coloured `.xlsx` |
| Whole-class scan PDF | One sheet per class (or one sheet if single class) |

## Answer key

Teachers choose one way to enter the key:

1. **Manual.** Type the number of questions. The page shows that many A/B/C/D boxes.
2. **Solution PDF.** Upload the official solution. `POST /api/parse-key` (file field `pdf`) reads numbered answers (`1. C`, `1C 2D`, `第1題：C`) or an answer table and returns:

```json
{"n": 4, "key": ["C", "D", "", "A"], "review": [3], "warnings": ["未能讀取題號 3，已留空請填寫。 …"], "partial": true}
```

Empty strings and `review` are items to check. Conflicting, missing, or unnumbered letters are left blank for editing — the app does not guess. Text-based solution PDFs are read directly. A scan with no text layer is rejected, or OCR'd when the `tesseract` binary is installed, instead of guessing. A pasted `answer_key` form field still parses as before. After the boxes are complete, upload the class scan and download Excel. Scoring still treats `B` and `b` as the same letter.

Excel columns (F6 UT2 style): **Class | Class No. | Name | Q1…Qn | Total (/N)**  
+ correct-answer row + **% correct** + **class average**.

| Colour | Meaning |
|--------|---------|
| Green `#C6EFCE` | Matches key (`B`/`b` OK) |
| Red `#FFC7CE` | Wrong / blank / double (scores 0) |
| Yellow `#FFEB9C` | OMR unclear — type A–D by hand |

Name is left blank in MVP (handwriting OCR not ported). Class / Class No come from header bubbles on the **new** CLSNP sheet; old handwritten-header sheets still get MC answers with Class=`UNKNOWN`.

## Layout

```
clsnp-mc-marker/
  README.md
  Dockerfile          ← UI + API (preferred)
  .env.example
  .gitignore
  docs/BUBBLE_LAYOUT.md
  web/                ← static bilingual UI
    index.html
    style.css
    app.js
  api/
    main.py           ← FastAPI
    requirements.txt
    Dockerfile        ← API-only
    omr/              ← ported F6 UT2 OpenCV pipeline
      grid.py detect.py detect2.py refine.py
      measure.py classify.py header.py
      pdf_pages.py key_parse.py solution_key.py build_xlsx.py
      pipeline.py template.json
```

## Run locally

```bash
cd /path/to/clsnp-mc-marker
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# from api/ so `omr` imports resolve
cd api
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Open **http://127.0.0.1:8080/** — UI is served by FastAPI from `../web`.

Health: `curl http://127.0.0.1:8080/api/health`

CLI dry-run (no server):

```bash
cd api
python -c "
from omr.pipeline import mark_pdf
p, meta = mark_pdf('/path/to/scans.pdf', '1A 2B 3C', title='Demo', out_path='/tmp/out.xlsx')
print(p, meta['n_pages'], meta['n_students'], meta['n_errors'])
"
```

**No PDF ⇒ no marks.** The app refuses to invent student answers.

## Deploy (recommended split)

Heavy OpenCV OMR can exceed Vercel serverless limits — use **Option B**:

### A. API on Railway or Fly.io

```bash
# Railway: new project from this repo, Dockerfile at root (or api/)
# Set start command automatically via Dockerfile CMD.
# Optional env: CORS_ORIGINS=https://your-frontend.vercel.app

# Fly
fly launch --dockerfile Dockerfile --name clsnp-mc-marker
fly deploy
```

Note public API base, e.g. `https://clsnp-mc-marker.up.railway.app`.

### B. Frontend on Vercel (optional)

`web/` is static. Point it at the API:

1. Deploy `web/` as a Vercel static site (or any static host).
2. Before `app.js`, set the API base:

```html
<script>window.CLSNP_API_BASE = "https://YOUR-API.example.com";</script>
```

3. On the API host set `CORS_ORIGINS=https://your-app.vercel.app`.

### C. Single container (simplest for colleagues)

Build root `Dockerfile` and host on Railway/Fly/Render — UI and API on one URL. **This is enough; Vercel is optional.**

```bash
docker build -t clsnp-mc-marker .
docker run --rm -p 8080:8080 clsnp-mc-marker
```

## Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `PORT` | `8080` | Listen port |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins |

No API keys. Keep secrets out of the repo (see `.gitignore`).

## OMR status

**Ported from** `/workspace/f6-ut2-mc/code/` (detect / detect2 / grid / refine / measure / classify2 / build_xlsx):

- PDF → page PNGs @ 200 DPI (PyMuPDF)
- MC outer border → bubble grid fit → fill/dark ratios
- Status: single letter / `BLANK` / `MULTIPLE` / `UNCLEAR`
- Coloured openpyxl workbook

**Header Class / Class No:** new geometry from `docs/BUBBLE_LAYOUT.md`, mapped via MC-border affine from the blank CLSNP sheet template. Prefer new CLSNP bubble sheets; old handwritten headers → `UNKNOWN` class.

**Not in MVP:** handwriting name OCR, roster lookup, interactive yellow-cell recolour web editor (Excel itself is editable).

## Once GitHub is connected

Suggested repo: **`CLSNP-MC-Marker`** under **`yeahalex990904`**.

```bash
cd /path/to/clsnp-mc-marker   # already git init'd
git remote add origin git@github.com:yeahalex990904/CLSNP-MC-Marker.git
git push -u origin main
```

Then connect Railway/Fly to that repo. Do **not** commit `.venv`, PDFs, or result xlsx.

## Colour / key rules (colleagues)

- Match is case-insensitive (`b` ≡ `B`).
- Only green cells count in totals.
- Yellow = please type the letter; then recolour manually in Excel if desired.
