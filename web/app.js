(function () {
  const apiBase = (window.CLSNP_API_BASE || "").replace(/\/$/, "");
  const form = document.getElementById("mark-form");
  const statusEl = document.getElementById("status");
  const submitBtn = document.getElementById("submit-btn");
  const extractBtn = document.getElementById("extract-btn");
  const nInput = document.getElementById("n_questions");
  const boxesEl = document.getElementById("key-boxes");
  const summaryEl = document.getElementById("key-summary");
  const reviewLegend = document.getElementById("review-legend");
  const manualPanel = document.getElementById("mode-manual");
  const pdfPanel = document.getElementById("mode-pdf");
  const LETTERS = ["A", "B", "C", "D"];

  let answers = [];
  let review = new Set();
  let nTimer = null;

  function showStatus(msg, kind) {
    statusEl.hidden = false;
    statusEl.className = "status" + (kind ? " " + kind : "");
    statusEl.textContent = msg;
  }

  function detailOf(data) {
    if (!data) return "";
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || String(d)).join("; ");
    }
    return data.message || "";
  }

  function normalizeLetter(value) {
    const letter = String(value || "").trim().toUpperCase();
    return LETTERS.indexOf(letter) >= 0 ? letter : "";
  }

  function syncMode() {
    const mode = document.querySelector('input[name="key_mode"]:checked');
    const pdf = mode && mode.value === "pdf";
    pdfPanel.hidden = !pdf;
    manualPanel.hidden = pdf;
  }

  document.querySelectorAll('input[name="key_mode"]').forEach((el) => {
    el.addEventListener("change", syncMode);
  });

  function updateSummary() {
    if (!answers.length) {
      summaryEl.hidden = true;
      reviewLegend.hidden = true;
      return;
    }
    const filled = answers.filter(Boolean).length;
    summaryEl.hidden = false;
    summaryEl.textContent =
      "已填 " +
      filled +
      " / " +
      answers.length +
      " · " +
      answers.map((a) => a || "·").join(" ");
    reviewLegend.hidden = review.size === 0;
  }

  function paintBoxes() {
    const cells = boxesEl.querySelectorAll(".qcell");
    if (cells.length !== answers.length) return false;
    answers.forEach((letter, index) => {
      const cell = cells[index];
      cell.classList.toggle("review", review.has(index + 1));
      cell.querySelectorAll("button").forEach((btn) => {
        btn.setAttribute("aria-pressed", btn.textContent === letter ? "true" : "false");
      });
    });
    updateSummary();
    return true;
  }

  function renderBoxes() {
    if (!answers.length) {
      boxesEl.hidden = true;
      boxesEl.replaceChildren();
      summaryEl.hidden = true;
      reviewLegend.hidden = true;
      return;
    }
    boxesEl.hidden = false;
    if (paintBoxes()) return;
    const frag = document.createDocumentFragment();
    answers.forEach((letter, index) => {
      const q = index + 1;
      const cell = document.createElement("div");
      cell.className = "qcell" + (review.has(q) ? " review" : "");
      const num = document.createElement("span");
      num.className = "qnum";
      num.textContent = "Q" + q;
      const group = document.createElement("div");
      group.className = "choices";
      group.setAttribute("role", "radiogroup");
      group.setAttribute("aria-label", "Q" + q);
      LETTERS.forEach((choice) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = choice;
        btn.setAttribute("aria-pressed", letter === choice ? "true" : "false");
        btn.addEventListener("click", () => {
          if (answers[index] === choice) {
            answers[index] = "";
            review.add(q);
          } else {
            answers[index] = choice;
            review.delete(q);
          }
          renderBoxes();
          if (statusEl.classList.contains("error") && answers.every(Boolean)) {
            statusEl.hidden = true;
          }
        });
        group.appendChild(btn);
      });
      cell.appendChild(num);
      cell.appendChild(group);
      frag.appendChild(cell);
    });
    boxesEl.replaceChildren(frag);
    updateSummary();
  }

  function resizeN(n) {
    const next = new Array(n).fill("");
    for (let i = 0; i < Math.min(n, answers.length); i += 1) next[i] = answers[i];
    answers = next;
    review = new Set([...review].filter((q) => q <= n && !answers[q - 1]));
    renderBoxes();
  }

  function applyNFromInput() {
    const raw = nInput.value.trim();
    if (!raw) return;
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 1 || n > 100) {
      showStatus("題數須為 1–100。 Number of questions must be 1–100.", "error");
      return;
    }
    resizeN(n);
  }

  nInput.addEventListener("input", () => {
    clearTimeout(nTimer);
    nTimer = setTimeout(applyNFromInput, 250);
  });
  nInput.addEventListener("change", () => {
    clearTimeout(nTimer);
    applyNFromInput();
  });
  nInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      clearTimeout(nTimer);
      applyNFromInput();
    }
  });

  function applyExtracted(data) {
    const n = Number(data.n);
    const key = Array.isArray(data.key) ? data.key : [];
    if (!Number.isInteger(n) || n < 1 || n > 100 || key.length !== n) {
      showStatus(
        "答案 PDF 的題數不正確，未填入任何答案。 The PDF key could not be applied.",
        "error"
      );
      return false;
    }
    answers = key.map(normalizeLetter);
    review = new Set(
      (data.review || [])
        .map((q) => Number(q))
        .filter((q) => Number.isInteger(q) && q >= 1 && q <= n)
    );
    answers.forEach((letter, index) => {
      if (!letter) review.add(index + 1);
    });
    nInput.value = String(n);
    renderBoxes();
    return true;
  }

  extractBtn.addEventListener("click", async () => {
    const input = document.getElementById("solution_pdf");
    const file = input.files && input.files[0];
    if (!file) {
      showStatus("請先選擇答案 PDF。 Choose a solution PDF first.", "error");
      return;
    }
    const fd = new FormData();
    fd.append("pdf", file);
    extractBtn.disabled = true;
    submitBtn.disabled = true;
    showStatus("正在讀取答案… Reading the solution PDF…");
    try {
      const res = await fetch(apiBase + "/api/parse-key", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showStatus(detailOf(data) || "Could not read the solution PDF.", "error");
        return;
      }
      if (!applyExtracted(data)) return;
      const warnings = (data.warnings || []).filter(Boolean).join("\n");
      if (data.partial) {
        showStatus(
          warnings || "部分題目未能確定，請核對黃格。 Some items were left blank for review.",
          "warn"
        );
      } else {
        showStatus(
          "已讀取 " +
            data.n +
            " 題，請核對後可修改。 Extracted " +
            data.n +
            " answers — edit any box if needed." +
            (warnings ? "\n" + warnings : ""),
          "ok"
        );
      }
    } catch (err) {
      showStatus("Network error: " + err.message, "error");
    } finally {
      extractBtn.disabled = false;
      submitBtn.disabled = false;
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!answers.length) {
      showStatus(
        "請先輸入題數，或上載答案 PDF。 Set the number of questions, or upload a solution PDF.",
        "error"
      );
      return;
    }
    const missing = answers.map((letter, i) => (letter ? null : i + 1)).filter(Boolean);
    if (missing.length) {
      const shown = missing.slice(0, 12).map((q) => "Q" + q).join(", ");
      showStatus(
        "尚有未填答案（" +
          shown +
          "）。請填寫後再批改，系統不會猜測。 Some answers are still blank.",
        "error"
      );
      return;
    }
    const pdfInput = document.getElementById("pdf");
    if (!pdfInput.files || !pdfInput.files[0]) {
      showStatus("請上載掃描 PDF。 Please upload the scanned PDF.", "error");
      return;
    }
    const fd = new FormData();
    fd.append("exam_name", document.getElementById("exam_name").value);
    fd.append("answer_key", answers.map((letter, i) => i + 1 + letter).join(" "));
    fd.append("pdf", pdfInput.files[0]);

    submitBtn.disabled = true;
    extractBtn.disabled = true;
    showStatus("批改中… OMR running (may take a minute for large classes)…");

    try {
      const res = await fetch(apiBase + "/api/mark", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = "Marking failed";
        try {
          detail = detailOf(await res.json()) || detail;
        } catch (_) {
          detail = (await res.text()) || detail;
        }
        showStatus(detail, "error");
        return;
      }
      const blob = await res.blob();
      const pages = res.headers.get("X-CLSNP-Pages") || "?";
      const students = res.headers.get("X-CLSNP-Students") || "?";
      const errors = res.headers.get("X-CLSNP-Errors") || "0";
      const disp =
        res.headers.get("Content-Disposition") ||
        'attachment; filename="CLSNP MC Results.xlsx"';
      let filename = "CLSNP MC Results.xlsx";
      const matched = /filename="?([^"]+)"?/i.exec(disp);
      if (matched) filename = matched[1];

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      showStatus(
        "完成 Done — " +
          pages +
          " page(s), " +
          students +
          " student row(s)" +
          (errors !== "0" ? ", " + errors + " page error(s)" : "") +
          ". Excel downloaded.",
        "ok"
      );
    } catch (err) {
      showStatus("Network error: " + err.message, "error");
    } finally {
      submitBtn.disabled = false;
      extractBtn.disabled = false;
    }
  });

  syncMode();
})();
