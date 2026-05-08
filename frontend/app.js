let project = null;
let currentPage = null;
let activeBlockId = null;

const loginScreen = document.querySelector("#loginScreen");
const appShell = document.querySelector("#appShell");
const loginForm = document.querySelector("#loginForm");
const passwordInput = document.querySelector("#passwordInput");
const loginMessage = document.querySelector("#loginMessage");
const uploadForm = document.querySelector("#uploadForm");
const pdfFile = document.querySelector("#pdfFile");
const statusBox = document.querySelector("#status");
const configStatus = document.querySelector("#configStatus");
const pageList = document.querySelector("#pageList");
const pageStage = document.querySelector("#pageStage");
const blockList = document.querySelector("#blockList");
const editorTitle = document.querySelector("#editorTitle");
const editorMeta = document.querySelector("#editorMeta");
const exportBtn = document.querySelector("#exportBtn");
const translatePageBtn = document.querySelector("#translatePageBtn");

checkAuth();

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginMessage.textContent = "正在验证。";
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: passwordInput.value }),
  });
  if (!response.ok) {
    loginMessage.textContent = "密码不正确。";
    return;
  }
  showApp();
});

async function checkAuth() {
  try {
    const response = await fetch("/api/auth/status");
    const data = await response.json();
    if (data.authenticated) {
      showApp();
    } else {
      showLogin();
    }
  } catch (error) {
    showLogin();
  }
}

function showLogin() {
  loginScreen.hidden = false;
  appShell.hidden = true;
  passwordInput.focus();
}

function showApp() {
  loginScreen.hidden = true;
  appShell.hidden = false;
  loginMessage.textContent = "";
  loadTranslationConfig();
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pdfFile.files.length) {
    setStatus("请先选择一个 PDF 文件。");
    return;
  }

  const formData = new FormData();
  formData.append("file", pdfFile.files[0]);
  setStatus("正在上传、识别和生成预览，请稍等。页数多时可能需要一两分钟。");
  exportBtn.disabled = true;

  const response = await fetch("/api/projects", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    setStatus(error.detail || "上传失败。");
    return;
  }

  project = await response.json();
  currentPage = project.pages[0] || null;
  renderProject();
});

exportBtn.addEventListener("click", async () => {
  if (!project) return;
  setStatus("正在导出越南语 PDF。");
  const response = await fetch(`/api/projects/${project.id}/export`, { method: "POST" });
  if (!response.ok) {
    setStatus("导出失败，请检查文字块是否过长。");
    return;
  }
  const result = await response.json();
  setStatus(`导出完成：已校对 ${result.reviewed_blocks}/${result.total_blocks} 个文字块。`);
  window.open(result.pdf_url, "_blank");
});

translatePageBtn.addEventListener("click", async () => {
  if (!project || !currentPage) return;
  translatePageBtn.disabled = true;
  setStatus(`正在调用百炼重新翻译第 ${currentPage.page_number} 页。`);
  const response = await fetch(
    `/api/projects/${project.id}/pages/${currentPage.page_number}/translate`,
    { method: "POST" }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    setStatus(error.detail || "重新翻译失败，请先确认后端能读到 DASHSCOPE_API_KEY。");
    await loadTranslationConfig();
    translatePageBtn.disabled = false;
    return;
  }
  const result = await response.json();
  setStatus(
    `第 ${result.page_number} 页翻译完成：成功 ${result.translated} 个，失败 ${result.failed} 个，已校对跳过 ${result.skipped_reviewed} 个。`
  );
  await refreshProject();
});

function setStatus(message) {
  statusBox.textContent = message;
}

async function loadTranslationConfig() {
  try {
    const response = await fetch("/api/translation-config");
    const config = await response.json();
    if (config.configured) {
      configStatus.textContent = `百炼已连接：${config.model}，Key ${config.key_hint}`;
      translatePageBtn.disabled = !project || !currentPage;
    } else {
      configStatus.textContent =
        "百炼未连接：当前后端进程没有读到 DASHSCOPE_API_KEY。请设置后重启服务。";
      translatePageBtn.disabled = true;
    }
  } catch (error) {
    configStatus.textContent = "百炼配置检测失败。";
    translatePageBtn.disabled = true;
  }
}

function renderProject() {
  const totalBlocks = project.pages.reduce((sum, page) => sum + page.blocks.length, 0);
  const reviewed = project.pages.reduce(
    (sum, page) => sum + page.blocks.filter((block) => block.status === "reviewed").length,
    0
  );
  setStatus(
    `${project.filename}\n共 ${project.pages.length} 页，识别 ${totalBlocks} 个文字块，已校对 ${reviewed} 个。${
      project.message ? "\n" + project.message : ""
    }`
  );
  exportBtn.disabled = false;
  loadTranslationConfig();
  renderPages();
  renderCurrentPage();
}

function renderPages() {
  pageList.innerHTML = "";
  project.pages.forEach((page) => {
    const button = document.createElement("button");
    button.className = `page-button ${currentPage?.page_number === page.page_number ? "active" : ""}`;
    button.innerHTML = `<span>第 ${page.page_number} 页</span><span class="badge">${page.blocks.length}</span>`;
    button.addEventListener("click", () => {
      currentPage = page;
      activeBlockId = null;
      renderProject();
    });
    pageList.appendChild(button);
  });
}

function renderCurrentPage() {
  if (!currentPage) {
    pageStage.innerHTML = '<div class="empty-state">没有页面</div>';
    blockList.innerHTML = "";
    return;
  }

  editorTitle.textContent = `第 ${currentPage.page_number} 页文字块`;
  editorMeta.textContent = `${currentPage.blocks.length} 个文字块，状态：${currentPage.extraction_status}`;
  pageStage.innerHTML = "";
  const img = document.createElement("img");
  img.src = currentPage.preview_url;
  img.addEventListener("load", () => renderOverlays(img));
  pageStage.appendChild(img);
  renderBlocks();
}

function renderOverlays(img) {
  const scaleX = img.clientWidth / currentPage.width;
  const scaleY = img.clientHeight / currentPage.height;
  currentPage.blocks.forEach((block) => {
    const [x0, y0, x1, y1] = block.bbox;
    const overlay = document.createElement("button");
    overlay.className = `overlay-block ${block.status}`;
    overlay.title = block.source_text;
    overlay.style.left = `${x0 * scaleX}px`;
    overlay.style.top = `${y0 * scaleY}px`;
    overlay.style.width = `${Math.max(8, (x1 - x0) * scaleX)}px`;
    overlay.style.height = `${Math.max(8, (y1 - y0) * scaleY)}px`;
    overlay.addEventListener("click", () => focusBlock(block.id));
    pageStage.appendChild(overlay);
  });
}

function renderBlocks() {
  blockList.innerHTML = "";
  currentPage.blocks.forEach((block) => {
    const card = document.createElement("article");
    card.className = `block-card ${activeBlockId === block.id ? "active" : ""}`;
    card.id = `block-${block.id}`;

    const source = document.createElement("div");
    source.className = "source";
    source.textContent = block.source_text;

    const textarea = document.createElement("textarea");
    textarea.value = block.translated_text;
    textarea.addEventListener("change", () => saveBlock(block.id, { translated_text: textarea.value }));

    const actions = document.createElement("div");
    actions.className = "block-actions";
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = block.status === "reviewed";
    checkbox.addEventListener("change", () => saveBlock(block.id, { reviewed: checkbox.checked }));
    label.append(checkbox, "已校对");

    const note = document.createElement("span");
    note.className = "note";
    note.textContent = block.note || "";
    actions.append(label, note);
    card.append(source, textarea, actions);
    blockList.appendChild(card);
  });
}

function focusBlock(blockId) {
  activeBlockId = blockId;
  renderBlocks();
  document.querySelector(`#block-${CSS.escape(blockId)}`)?.scrollIntoView({
    block: "center",
    behavior: "smooth",
  });
}

async function saveBlock(blockId, payload) {
  const response = await fetch(`/api/projects/${project.id}/blocks/${blockId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    setStatus("保存文字块失败。");
    return;
  }
  await refreshProject();
}

async function refreshProject() {
  const response = await fetch(`/api/projects/${project.id}/pages`);
  project = await response.json();
  currentPage = project.pages.find((page) => page.page_number === currentPage.page_number) || project.pages[0];
  renderProject();
}
