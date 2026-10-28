(function () {
  const apiBase = (window.CLSNP_API_BASE || "").replace(/\/$/, "");
  const form = document.getElementById("mark-form");
  const statusEl = document.getElementById("status");
  const keyPreview = document.getElementById("key-preview");
  const submitBtn = document.getElementById("submit-btn");
  const parseBtn = document.getElementById("parse-btn");

  function showStatus(msg, kind) {
    statusEl.hidden = false;
    statusEl.className = "status" + (kind ? " " + kind : "");
    statusEl.textContent = msg;
  }

  parseBtn.addEventListener("click", async () => {
    const answer_key = document.getElementById("answer_key").value;
    const fd = new FormData();
    fd.append("answer_key", answer_key);
    try {
      const res = await fetch(apiBase + "/api/parse-key", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        keyPreview.hidden = true;
        showStatus(data.detail || data.message || "Key parse failed", "error");
        return;
      }
      keyPreview.hidden = false;
      keyPreview.textContent =
        "Q1–Q" + data.n + " (" + data.n + "):\n" + data.key.join(" ");
      showStatus("答案共 " + data.n + " 題 · Parsed " + data.n + " answers.", "ok");
    } catch (err) {
      showStatus("Network error: " + err.message, "error");
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const pdfInput = document.getElementById("pdf");
    if (!pdfInput.files || !pdfInput.files[0]) {
      showStatus("請上載 PDF · Please upload a PDF.", "error");
      return;
    }
    const fd = new FormData();
    fd.append("exam_name", document.getElementById("exam_name").value);
    fd.append("answer_key", document.getElementById("answer_key").value);
    fd.append("pdf", pdfInput.files[0]);

    submitBtn.disabled = true;
    parseBtn.disabled = true;
    showStatus("批改中… OMR running (may take a minute for large classes)…");

    try {
      const res = await fetch(apiBase + "/api/mark", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = "Marking failed";
        try {
          const j = await res.json();
          detail = j.detail || detail;
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
      const m = /filename="?([^"]+)"?/i.exec(disp);
      if (m) filename = m[1];

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
      parseBtn.disabled = false;
    }
  });
})();
