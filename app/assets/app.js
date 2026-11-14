const EXAMPLES = window.MATH_SOLVER_EXAMPLES;

const problemInput = document.getElementById("problem");
const solveStatus = document.getElementById("solveStatus");
const uploadBtn = document.getElementById("uploadBtn");
const imageInput = document.getElementById("imageInput");
const previewRow = document.getElementById("previewRow");
const previewImage = document.getElementById("imagePreview");
const previewName = document.getElementById("previewName");
const previewNote = document.getElementById("previewNote");
const padBtn = document.getElementById("padBtn");
const padModal = document.getElementById("padModal");
const padCanvas = document.getElementById("pad");
const padCtx = padCanvas.getContext("2d");
const padStatus = document.getElementById("padStatus");
let previewUrl = null;
let padStrokes = [];
let padStroke = null;
let padDrawing = false;
let padWidth = 0;
let padHeight = 0;

function make(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function resetPreview() {
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  previewImage.removeAttribute("src");
  previewName.textContent = "";
  previewNote.textContent = "";
  previewRow.classList.add("hidden");
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

async function recognizeImage(file) {
  if (file.size > 15 * 1024 * 1024) {
    solveStatus.textContent = "图片过大，请压缩到 15MB 以内";
    return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewName.textContent = file.name;
  previewNote.textContent = "正在识别…";
  previewRow.classList.remove("hidden");

  const solveButton = document.getElementById("solveBtn");
  uploadBtn.disabled = true;
  padBtn.disabled = true;
  solveButton.disabled = true;
  uploadBtn.textContent = "识别中…";
  solveStatus.textContent = "正在识别图片…（首次加载视觉模型可能较慢）";
  try {
    const image = await fileToBase64(file);
    const response = await fetch("/api/ocr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
    problemInput.value = data.text;
    problemInput.focus();
    previewNote.textContent = "识别完成 · " + data.model;
    solveStatus.textContent = "已填入识别结果，请核对后求解";
  } catch (error) {
    previewNote.textContent = "识别失败";
    solveStatus.textContent = "识别失败: " + error.message;
  } finally {
    uploadBtn.disabled = false;
    padBtn.disabled = false;
    solveButton.disabled = false;
    uploadBtn.textContent = "上传图片";
  }
}

function drawPad() {
  const dpr = window.devicePixelRatio || 1;
  padCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  padCtx.clearRect(0, 0, padWidth, padHeight);
  padCtx.fillStyle = "#ffffff";
  padCtx.fillRect(0, 0, padWidth, padHeight);

  if (!padStrokes.length) {
    padCtx.fillStyle = "#c3cbd8";
    padCtx.font = '15px "Segoe UI", "Microsoft YaHei", sans-serif';
    padCtx.textAlign = "center";
    padCtx.textBaseline = "middle";
    padCtx.fillText("在这里写下题目，例如 x**2 - 5*x + 6 = 0", padWidth / 2, padHeight / 2);
    return;
  }

  padCtx.strokeStyle = "#1b2333";
  padCtx.fillStyle = "#1b2333";
  padCtx.lineWidth = 3.5;
  padCtx.lineCap = "round";
  padCtx.lineJoin = "round";
  padStrokes.forEach((stroke) => {
    if (stroke.length === 1) {
      padCtx.beginPath();
      padCtx.arc(stroke[0].x, stroke[0].y, 1.9, 0, Math.PI * 2);
      padCtx.fill();
      return;
    }
    padCtx.beginPath();
    padCtx.moveTo(stroke[0].x, stroke[0].y);
    for (let i = 1; i < stroke.length - 1; i += 1) {
      const midX = (stroke[i].x + stroke[i + 1].x) / 2;
      const midY = (stroke[i].y + stroke[i + 1].y) / 2;
      padCtx.quadraticCurveTo(stroke[i].x, stroke[i].y, midX, midY);
    }
    const last = stroke[stroke.length - 1];
    padCtx.lineTo(last.x, last.y);
    padCtx.stroke();
  });
}

function resizePad() {
  const rect = padCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = padWidth ? rect.width / padWidth : 1;
  padWidth = rect.width;
  padHeight = rect.height;
  if (ratio !== 1) {
    padStrokes.forEach((stroke) => {
      stroke.forEach((point) => { point.x *= ratio; });
    });
  }
  const dpr = window.devicePixelRatio || 1;
  padCanvas.width = Math.round(padWidth * dpr);
  padCanvas.height = Math.round(padHeight * dpr);
  drawPad();
}

function padPoint(event) {
  const rect = padCanvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

padCanvas.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  if (!padWidth) resizePad();
  padDrawing = true;
  padStroke = [padPoint(event)];
  padStrokes.push(padStroke);
  padCanvas.setPointerCapture(event.pointerId);
  drawPad();
});

padCanvas.addEventListener("pointermove", (event) => {
  if (!padDrawing || !padStroke) return;
  event.preventDefault();
  const point = padPoint(event);
  const last = padStroke[padStroke.length - 1];
  if (Math.hypot(point.x - last.x, point.y - last.y) < 1.2) return;
  padStroke.push(point);
  drawPad();
});

function endPadStroke(event) {
  if (!padDrawing) return;
  padDrawing = false;
  padStroke = null;
  if (event && padCanvas.hasPointerCapture(event.pointerId)) {
    padCanvas.releasePointerCapture(event.pointerId);
  }
}

padCanvas.addEventListener("pointerup", endPadStroke);
padCanvas.addEventListener("pointercancel", endPadStroke);

function openPad() {
  padStatus.textContent = "按住鼠标或触控笔写下题目";
  padModal.classList.remove("hidden");
  requestAnimationFrame(() => resizePad());
}

function closePad() {
  padModal.classList.add("hidden");
}

padBtn.addEventListener("click", openPad);
document.getElementById("padCancel").addEventListener("click", closePad);
padModal.addEventListener("click", (event) => {
  if (event.target === padModal) closePad();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !padModal.classList.contains("hidden")) closePad();
});
window.addEventListener("resize", () => {
  if (!padModal.classList.contains("hidden")) resizePad();
});

document.getElementById("padUndo").addEventListener("click", () => {
  padStrokes.pop();
  drawPad();
});

document.getElementById("padClear").addEventListener("click", () => {
  padStrokes = [];
  drawPad();
});

document.getElementById("padRecognize").addEventListener("click", () => {
  if (!padStrokes.length) {
    padStatus.textContent = "请先写下题目再识别";
    return;
  }
  const button = document.getElementById("padRecognize");
  button.disabled = true;
  padCanvas.toBlob((blob) => {
    button.disabled = false;
    if (!blob) {
      padStatus.textContent = "导出图片失败，请重试";
      return;
    }
    closePad();
    recognizeImage(new File([blob], "手写题目.png", { type: "image/png" }));
  }, "image/png");
});

const exampleChips = document.getElementById("exampleChips");
EXAMPLES.forEach(([name, text]) => {
  const chip = make("button", "chip", name);
  chip.type = "button";
  chip.title = text;
  chip.addEventListener("click", () => {
    problemInput.value = text;
    problemInput.focus();
  });
  exampleChips.appendChild(chip);
});

function renderMath(element, tex, fallback, display) {
  if (tex && typeof katex !== "undefined") {
    try {
      katex.render(tex, element, {
        throwOnError: false,
        strict: false,
        displayMode: Boolean(display),
      });
      return;
    } catch (error) { /* 渲染失败则退回纯文本 */ }
  }
  element.textContent = fallback;
}

function renderResult(data) {
  const box = document.getElementById("result");
  box.innerHTML = "";
  const wrap = make("div", "result");

  const plannerLabels = { rule: "规则命中", llm: "Ollama 兜底", spec: "结构化任务" };
  const metrics = make("div", "metrics");
  [
    ["题型", data.route_label],
    ["规划", plannerLabels[data.planner] || data.planner || "规则"],
    ["耗时", data.elapsed_ms + " ms"],
  ].forEach(([key, value]) => {
    const metric = make("div", "metric");
    metric.appendChild(make("span", null, key));
    metric.appendChild(make("b", null, value));
    metrics.appendChild(metric);
  });
  wrap.appendChild(metrics);

  const banner = make("div", "answer " + (data.ok ? "ok" : "fail"));
  if (data.ok) {
    banner.appendChild(make("div", "answer-label", "答案"));
    const answer = make("div", "answer-math");
    if (data.answer_latex) {
      renderMath(answer, data.answer_latex, String(data.answer), true);
    } else {
      answer.classList.add("answer-text");
      answer.textContent = String(data.answer);
    }
    banner.appendChild(answer);
  } else {
    banner.appendChild(make("div", "answer-label", "未能求解"));
    banner.appendChild(make("div", "answer-fail-text", data.error || "未知错误"));
    if (data.planner === "llm") {
      banner.appendChild(make("p", "answer-tip", "如果这是应用题，请确认本地 Ollama 服务已启动（ollama serve）。"));
    }
  }
  wrap.appendChild(banner);

  if (data.ok && data.steps && data.steps.length) {
    const card = make("div", "card block");
    card.appendChild(make("h3", null, "解题过程"));
    const list = make("ol", "steps");
    data.steps.forEach((step) => list.appendChild(make("li", null, step)));
    card.appendChild(list);
    wrap.appendChild(card);
  }

  const meta = document.createElement("details");
  meta.className = "card meta";
  meta.appendChild(make("summary", null, "求解明细"));
  const body = make("div", "meta-body");
  const rows = [
    ["归一化", data.normalized || "(空)"],
    ["题型路由", data.route_label + (data.hint ? " · " + data.hint : "")],
    ["求解后端", data.backend || "-"],
  ];
  if (data.task) {
    rows.push(["规划任务", JSON.stringify(data.task)]);
  }
  rows.forEach(([key, value]) => {
    const row = make("div", "row");
    row.appendChild(make("span", "k", key));
    row.appendChild(make("span", "v", String(value)));
    body.appendChild(row);
  });
  meta.appendChild(body);
  wrap.appendChild(meta);

  box.appendChild(wrap);
}

async function solve() {
  const problem = problemInput.value.trim();
  const button = document.getElementById("solveBtn");
  if (!problem) {
    solveStatus.textContent = "请输入题目";
    problemInput.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "求解中…";
  solveStatus.textContent = "正在计算…";
  try {
    const response = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
    renderResult(data);
    solveStatus.textContent = "";
  } catch (error) {
    solveStatus.textContent = "请求失败: " + error.message;
  } finally {
    button.disabled = false;
    button.textContent = "求解";
  }
}

document.getElementById("solveBtn").addEventListener("click", solve);

document.getElementById("clearBtn").addEventListener("click", () => {
  problemInput.value = "";
  document.getElementById("result").innerHTML = "";
  solveStatus.textContent = "";
  resetPreview();
  problemInput.focus();
});

uploadBtn.addEventListener("click", () => imageInput.click());

imageInput.addEventListener("change", async () => {
  const file = imageInput.files && imageInput.files[0];
  if (!file) return;
  await recognizeImage(file);
  imageInput.value = "";
});

document.getElementById("removeImage").addEventListener("click", () => {
  resetPreview();
  solveStatus.textContent = "";
});

problemInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") solve();
});
