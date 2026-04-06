const $ = (sel, root = document) => root.querySelector(sel);

const els = {
  resultsSection: $("#results-section"),
  resultsIdle: $("#results-idle"),
  loading: $("#results-loading"),
  error: $("#results-error"),
  errorBody: $("#results-error-body"),
  empty: $("#results-empty"),
  data: $("#results-data"),
  scoreCard: $("#score-card"),
  score: $("#out-score"),
  advantage: $("#out-advantage"),
  source: $("#out-source"),
  fen: $("#out-fen"),
  board: $("#out-board"),
  reasoning: $("#out-reasoning"),
  btnCopyFen: $("#btn-copy-fen"),
  btnHealth: $("#btn-health"),
  toast: $("#toast"),
};

const PIECE_DISPLAY = {
  P: "♙",
  N: "♘",
  B: "♗",
  R: "♖",
  Q: "♕",
  K: "♔",
  p: "♟",
  n: "♞",
  b: "♝",
  r: "♜",
  q: "♛",
  k: "♚",
};

function apiUrl(path) {
  const base = (window.API_BASE || "").replace(/\/$/, "");
  return `${base}${path}`;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    els.toast.hidden = true;
  }, 2200);
}

function setBusy(busy) {
  els.resultsSection.setAttribute("aria-busy", busy ? "true" : "false");
  els.loading.hidden = !busy;
  if (busy) {
    els.error.hidden = true;
    els.empty.hidden = true;
    els.resultsIdle.textContent = "처리 중";
  }
}

function showError(message) {
  els.error.hidden = false;
  els.errorBody.textContent = message;
  els.data.hidden = true;
  els.empty.hidden = true;
  els.resultsIdle.textContent = "오류";
}

function resetToEmpty() {
  els.error.hidden = true;
  els.data.hidden = true;
  els.empty.hidden = false;
  els.resultsIdle.textContent = "대기 중";
}

function formatScore(n) {
  const s = Number(n);
  const sign = s > 0 ? "+" : "";
  return `${sign}${s.toFixed(1)}`;
}

function renderBoard(matrix) {
  els.board.replaceChildren();
  if (!matrix || matrix.length !== 8) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "보드 매트릭스 없음";
    els.board.appendChild(p);
    return;
  }
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const cell = document.createElement("div");
      const isLight = (r + c) % 2 === 0;
      cell.className = `board__cell ${isLight ? "board__cell--light" : "board__cell--dark"}`;
      const raw = matrix[r][c];
      const ch = raw === "." ? "·" : PIECE_DISPLAY[raw] || raw;
      cell.textContent = ch;
      if (raw === ".") cell.classList.add("board__cell--empty");
      cell.title = `행 ${r + 1}, 열 ${c + 1}`;
      els.board.appendChild(cell);
    }
  }
}

function applyAdvantageStyles(advantage) {
  els.scoreCard.classList.remove("score-card--white", "score-card--black", "score-card--equal");
  els.advantage.classList.remove("chip--white", "chip--black", "chip--equal");
  if (advantage === "white") {
    els.scoreCard.classList.add("score-card--white");
    els.advantage.classList.add("chip--white");
    els.advantage.textContent = "백 우세";
  } else if (advantage === "black") {
    els.scoreCard.classList.add("score-card--black");
    els.advantage.classList.add("chip--black");
    els.advantage.textContent = "흑 우세";
  } else {
    els.scoreCard.classList.add("score-card--equal");
    els.advantage.classList.add("chip--equal");
    els.advantage.textContent = "균형";
  }
}

function renderResult(payload) {
  els.empty.hidden = true;
  els.error.hidden = true;
  els.data.hidden = false;
  els.resultsIdle.textContent = "완료";

  els.score.textContent = formatScore(payload.score);
  applyAdvantageStyles(payload.advantage);
  els.source.textContent = `출처: ${payload.source}`;
  els.fen.textContent = payload.fen ?? "—";
  els.reasoning.textContent = payload.reasoning || "—";
  renderBoard(payload.board_matrix);
}

async function parseError(res) {
  const ct = res.headers.get("content-type") || "";
  try {
    if (ct.includes("application/json")) {
      const j = await res.json();
      if (typeof j.detail === "string") return j.detail;
      if (Array.isArray(j.detail)) return JSON.stringify(j.detail, null, 2);
      return JSON.stringify(j, null, 2);
    }
    return await res.text();
  } catch {
    return res.statusText || "Unknown error";
  }
}

async function postJson(path, body) {
  const res = await fetchWithTimeout(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

async function postForm(path, formData) {
  const res = await fetchWithTimeout(apiUrl(path), {
    method: "POST",
    headers: { Accept: "application/json" },
    body: formData,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

function setupTabs() {
  const buttons = document.querySelectorAll(".tabs__btn");
  const panels = {
    combined: $("#panel-combined"),
    fen: $("#panel-fen"),
    image: $("#panel-image"),
  };
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.tab;
      buttons.forEach((b) => {
        b.classList.toggle("is-active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      Object.entries(panels).forEach(([key, panel]) => {
        const on = key === name;
        panel.hidden = !on;
        panel.classList.toggle("is-active", on);
      });
    });
  });
}

function setupDropzone(drop, input, preview) {
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });

  const showPreview = (file) => {
    if (!file || !file.type.startsWith("image/")) {
      preview.hidden = true;
      preview.replaceChildren();
      return;
    }
    const url = URL.createObjectURL(file);
    preview.replaceChildren();
    const img = document.createElement("img");
    img.src = url;
    img.alt = "선택한 이미지 미리보기";
    img.onload = () => URL.revokeObjectURL(url);
    preview.appendChild(img);
    preview.hidden = false;
  };

  input.addEventListener("change", () => {
    const file = input.files?.[0];
    showPreview(file);
  });
}

function bindForms() {
  const fileCombined = $("#file-combined");
  const fenCombined = $("#fen-combined");
  $("#form-combined").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fen = fenCombined.value.trim();
    const file = fileCombined.files?.[0];
    if (!fen && !file) {
      showToast("이미지 또는 FEN 중 하나 이상 입력하세요.");
      return;
    }
    const fd = new FormData();
    if (file) fd.append("image", file);
    if (fen) fd.append("fen", fen);
    setBusy(true);
    try {
      const data = await postForm("/analyze", fd);
      renderResult(data);
    } catch (err) {
      const msg = err?.name === "AbortError" ? "요청 시간이 초과되었습니다. 다시 시도하세요." : String(err.message || err);
      showError(msg);
    } finally {
      setBusy(false);
    }
  });

  const fenOnly = $("#fen-only");
  $("#form-fen").addEventListener("submit", async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await postJson("/analyze/fen", { fen: fenOnly.value.trim() });
      renderResult(data);
    } catch (err) {
      const msg = err?.name === "AbortError" ? "요청 시간이 초과되었습니다. 다시 시도하세요." : String(err.message || err);
      showError(msg);
    } finally {
      setBusy(false);
    }
  });

  const fileImage = $("#file-image");
  $("#form-image").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = fileImage.files?.[0];
    if (!file) {
      showToast("이미지를 선택하세요.");
      return;
    }
    const fd = new FormData();
    fd.append("image", file);
    setBusy(true);
    try {
      const data = await postForm("/analyze/image", fd);
      renderResult(data);
    } catch (err) {
      const msg = err?.name === "AbortError" ? "요청 시간이 초과되었습니다. 다시 시도하세요." : String(err.message || err);
      showError(msg);
    } finally {
      setBusy(false);
    }
  });

  setupDropzone($("#drop-combined"), fileCombined, $("#preview-combined"));
  setupDropzone($("#drop-image"), fileImage, $("#preview-image"));
}

els.btnCopyFen.addEventListener("click", async () => {
  const text = els.fen.textContent?.trim();
  if (!text || text === "—") {
    showToast("복사할 FEN이 없습니다.");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast("FEN을 복사했습니다.");
  } catch {
    showToast("복사에 실패했습니다.");
  }
});

els.btnHealth.addEventListener("click", async () => {
  try {
    const res = await fetchWithTimeout(apiUrl("/health"), {}, 10000);
    const j = await res.json();
    showToast(j.status === "ok" ? "헬스: 정상" : "헬스 응답 이상");
  } catch {
    showToast("헬스 확인 실패");
  }
});

window.addEventListener("unhandledrejection", (event) => {
  showError(String(event.reason?.message || event.reason || "알 수 없는 오류"));
  setBusy(false);
});

window.addEventListener("error", (event) => {
  if (event?.error) {
    showError(String(event.error.message || event.error));
    setBusy(false);
  }
});

setupTabs();
bindForms();
resetToEmpty();
