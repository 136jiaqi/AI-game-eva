const DEPLOYED_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site";
const API_BASE = window.location.protocol === "file:" ? DEPLOYED_API_BASE : window.location.origin;
const HISTORY_KEY = "xmodhub_ai_evaluate_history";
const SYNCED_HISTORY_KEY = "xmodhub_ai_evaluate_history_synced";
const PHONE_KEY = "xmodhub_ai_evaluate_phone";
const VISITOR_KEY = "xmodhub_ai_evaluate_visitor_id";
const PAYMENT_URL = "https://www.xmodhub.cn/acticlustr/promotion/pc/49b75353f2374de991b15a03425cd6a9";
const INVALID_STEAM_LINK_MESSAGE = "该链接无法进行评估，请确保输入正确的 Steam 商店页面链接，或联系 XMODhub 官方客服。";

const knownGames = [
  { appid: 900001, name: "test1", nameZh: "test1", pass: true },
  { appid: 900002, name: "test2", nameZh: "test2", pass: false },
  { appid: 1868140, name: "DAVE THE DIVER", nameZh: "DAVE THE DIVER", pass: true },
  { appid: 3628950, name: "Succubus Successor: Delilah's Juicy Journey", nameZh: "Succubus Successor: Delilah's Juicy Journey", pass: true },
  { appid: 1623730, name: "Palworld", nameZh: "幻兽帕鲁", pass: true },
  { appid: 2358720, name: "Black Myth: Wukong", nameZh: "黑神话：悟空", pass: true },
  { appid: 1091500, name: "Cyberpunk 2077", nameZh: "赛博朋克 2077", pass: true },
  { appid: 730, name: "Counter-Strike 2", nameZh: "反恐精英 2", pass: false }
];

const state = {
  selectedGame: null,
  isSearching: false,
  isEvaluating: false,
  visibleHistoryCount: 20,
  currentRecordPromise: null,
  currentRecordId: null,
  visitorId: ""
};

const $ = (id) => document.getElementById(id);

const els = {
  form: $("evaluateForm"),
  gameInput: $("gameInput"),
  gameSearchStatus: $("gameSearchStatus"),
  matchBox: $("matchBox"),
  gameError: $("gameError"),
  requirementsInput: $("requirementsInput"),
  requirementsCounter: $("requirementsCounter"),
  requirementsError: $("requirementsError"),
  phoneInput: $("phoneInput"),
  phoneError: $("phoneError"),
  clearPhone: $("clearPhone"),
  submitBtn: $("submitBtn"),
  submitText: $("submitText"),
  resultEmpty: $("resultEmpty"),
  resultContent: $("resultContent"),
  historySearch: $("historySearch"),
  historyList: $("historyList"),
  loadMoreBtn: $("loadMoreBtn"),
  clearHistoryBtn: $("clearHistoryBtn")
};

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTime(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function maskPhone(phone) {
  return phone.replace(/^(\d{3})\d{4}(\d{4})$/, "$1****$2");
}

function createVisitorId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `visitor_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

function getVisitorId() {
  let visitorId = localStorage.getItem(VISITOR_KEY) || "";
  if (!/^[a-zA-Z0-9_-]{8,80}$/.test(visitorId)) {
    visitorId = createVisitorId();
    localStorage.setItem(VISITOR_KEY, visitorId);
  }
  state.visitorId = visitorId;
  return visitorId;
}

async function trackExposure() {
  try {
    await fetchJson(`${API_BASE}/api/exposure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visitor_id: getVisitorId(),
        path: `${window.location.pathname}${window.location.search}`,
        referrer: document.referrer || ""
      })
    });
  } catch (error) {
    console.warn("Failed to track exposure:", error);
  }
}

async function identifyVisitor(phone) {
  if (!/^1\d{10}$/.test(phone)) return;
  try {
    await fetchJson(`${API_BASE}/api/exposure/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visitor_id: getVisitorId(),
        phone
      })
    });
  } catch (error) {
    console.warn("Failed to identify visitor:", error);
  }
}

const debouncedIdentifyVisitor = debounce(() => {
  identifyVisitor(els.phoneInput.value.trim());
}, 500);

function parseSteamStoreLink(value) {
  const rawValue = String(value).trim();
  try {
    const url = new URL(rawValue);
    const hostValid = url.hostname.toLowerCase() === "store.steampowered.com";
    const match = url.pathname.match(/^\/app\/(\d+)(?:\/([^/?#]+))?/i);
    if (!hostValid || !match) return null;
    const appid = Number(match[1]);
    const slug = match[2] ? decodeURIComponent(match[2]).replace(/[_-]+/g, " ").trim() : "";
    return { appid, name: slug && slug !== "_" ? slug : `Steam App ${appid}`, url: rawValue };
  } catch {
    return null;
  }
}

async function fetchJson(url, options = {}) {
  const timeoutMs = options.timeoutMs || 10000;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const requestOptions = { ...options, signal: options.signal || controller.signal };
  delete requestOptions.timeoutMs;
  const response = await fetch(url, requestOptions).finally(() => window.clearTimeout(timeoutId));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function gameFromParsedLink(parsedLink) {
  const known = knownGames.find((game) => Number(game.appid) === parsedLink.appid);
  if (known) {
    return {
      ...known,
      cover: `https://cdn.cloudflare.steamstatic.com/steam/apps/${known.appid}/header.jpg`,
      storeUrl: parsedLink.url
    };
  }
  return {
    appid: parsedLink.appid,
    name: parsedLink.name,
    nameZh: parsedLink.name,
    cover: `https://cdn.cloudflare.steamstatic.com/steam/apps/${parsedLink.appid}/header.jpg`,
    storeUrl: parsedLink.url,
    pass: true
  };
}

async function resolveSteamGame(parsedLink) {
  const fallback = gameFromParsedLink(parsedLink);
  try {
    const detail = await fetchJson(`${API_BASE}/api/steam-app/${encodeURIComponent(parsedLink.appid)}`, { timeoutMs: 5000 });
    return {
      ...fallback,
      name: detail.name || fallback.name,
      nameZh: detail.nameZh || detail.name || fallback.nameZh,
      cover: detail.cover || fallback.cover,
      releaseDate: detail.releaseDate || fallback.releaseDate,
      storeUrl: parsedLink.url
    };
  } catch (error) {
    console.warn("Failed to resolve Steam game:", error);
    return fallback;
  }
}

function setSelectedGame(game, message = "已完成 Steam 游戏匹配。") {
  state.selectedGame = game;
  els.gameError.textContent = "";
  els.gameSearchStatus.textContent = message;
  els.gameSearchStatus.classList.remove("is-hidden");
  renderMatchedGame(game);
  validateForm();
}

function renderMatchedGame(game) {
  els.matchBox.classList.remove("is-hidden");
  els.matchBox.innerHTML = `
    <div class="match-card">
      <img
        class="match-cover"
        src="${escapeHtml(game.cover)}"
        alt="${escapeHtml(game.nameZh)} 封面"
        onerror="this.classList.add('is-hidden');this.nextElementSibling.classList.remove('is-hidden');"
      />
      <div class="match-cover match-cover-placeholder is-hidden">XMODhub<br />游戏封面</div>
      <div>
        <div class="match-kicker">✓ 已匹配</div>
        <div class="match-name">${escapeHtml(game.nameZh)}</div>
        <div class="match-meta">
          ${escapeHtml(game.name)}<br />
          APP ID：${escapeHtml(game.appid)}
        </div>
      </div>
    </div>
  `;
}

const debouncedSearch = debounce(() => {
  const parsedLink = parseSteamStoreLink(els.gameInput.value);
  state.selectedGame = null;
  els.matchBox.classList.add("is-hidden");
  els.matchBox.innerHTML = "";

  if (!els.gameInput.value.trim()) {
    els.gameSearchStatus.textContent = "";
    els.gameSearchStatus.classList.add("is-hidden");
    els.gameError.textContent = "";
    validateForm();
    return;
  }

  if (!parsedLink) {
    els.gameSearchStatus.textContent = "";
    els.gameSearchStatus.classList.add("is-hidden");
    els.gameError.textContent = INVALID_STEAM_LINK_MESSAGE;
    validateForm();
    return;
  }

  const fallbackGame = gameFromParsedLink(parsedLink);
  state.isSearching = false;
  setSelectedGame(fallbackGame, `已识别 Steam APP ID：${parsedLink.appid}，正在获取游戏名称...`);
  els.gameSearchStatus.textContent = `已识别 Steam APP ID：${parsedLink.appid}，正在获取游戏名称...`;
  els.gameSearchStatus.classList.remove("is-hidden");
  els.gameError.textContent = "";
  validateForm();

  window.setTimeout(async () => {
    const latestParsedLink = parseSteamStoreLink(els.gameInput.value);
    if (!latestParsedLink || latestParsedLink.appid !== parsedLink.appid) {
      state.isSearching = false;
      validateForm();
      return;
    }
    const resolvedGame = await resolveSteamGame(parsedLink);
    state.isSearching = false;
    const hasResolvedName = resolvedGame.name !== fallbackGame.name || resolvedGame.nameZh !== fallbackGame.nameZh;
    setSelectedGame(
      resolvedGame,
      hasResolvedName
        ? "已完成 Steam 游戏匹配。"
        : `已识别 Steam APP ID：${parsedLink.appid}，暂未获取到 Steam 游戏名称，可继续提交评估。`
    );
  }, 350);
}, 350);

function validateForm(showErrors = false) {
  const gameText = els.gameInput.value.trim();
  const requirements = els.requirementsInput.value.trim();
  const phone = els.phoneInput.value.trim();
  const phoneValid = /^1\d{10}$/.test(phone);
  const requirementsValid = requirements.length >= 1 && requirements.length <= 200;
  const gameValid = Boolean(gameText && state.selectedGame);

  if (showErrors && !gameText) els.gameError.textContent = "请输入 Steam 商店页面链接。";
  els.requirementsError.textContent = showErrors && !requirementsValid ? "修改需求需填写 1~200 字。" : "";
  els.phoneError.textContent = phone && !phoneValid ? "请输入正确的手机号。" : "";
  if (showErrors && !phone) els.phoneError.textContent = "请输入正确的手机号。";

  els.submitBtn.disabled = !(gameValid && requirementsValid && phoneValid) || state.isEvaluating || state.isSearching;
  return gameValid && requirementsValid && phoneValid;
}

function evaluateGame(game) {
  const passed = game.pass !== false;
  return {
    result: passed ? "pass" : "fail",
    reason: passed ? "游戏基础信息符合优先开发评估规则。" : "该游戏暂不符合优先开发评估规则。"
  };
}

function isMissingGameInfoResponse(evaluation) {
  const reason = String(evaluation?.reason || evaluation?.detail || "");
  return !evaluation?.game && !evaluation?.record && /评估名单|未获取到|not found|not configured/i.test(reason);
}

async function evaluateGameWithBackend(game) {
  const evaluation = await fetchJson(`${API_BASE}/api/evaluation/check?q=${encodeURIComponent(game.appid || game.nameZh || game.name)}`);
  const record = evaluation.record || {};
  const steamDbGame = evaluation.game || {};
  if (isMissingGameInfoResponse(evaluation)) {
    return {
      result: "pending",
      title: "暂未获取到游戏信息",
      detail: `系统已识别 Steam APP ID：${game.appid}，但暂未从游戏数据接口获取到完整信息，当前不能给出通过或不通过结论。请稍后重新提交评估。`,
      reason: evaluation.reason || "游戏信息暂未获取成功",
      raw: evaluation,
      game
    };
  }
  const passed = Boolean(evaluation.passed);
  const gameName = steamDbGame.game_name_zh || evaluation.game_cn_name || record.game_name_zh || record.name || record.steam_name || game.nameZh || game.name;
  return {
    result: passed ? "pass" : "fail",
    title: evaluation.title || (passed ? "AI评估通过" : "该游戏暂不支持赞助"),
    detail: evaluation.detail || evaluation.reason || (passed ? "游戏符合优先开发评估规则。" : "该游戏暂不符合优先开发赞助规则。"),
    reason: evaluation.reason || evaluation.detail || (passed ? "游戏符合优先开发评估规则。" : "该游戏暂不符合优先开发赞助规则。"),
    raw: evaluation,
    game: {
      ...game,
      appid: evaluation.appid || steamDbGame.appid || record.appid || game.appid,
      name: steamDbGame.game_name_en || record.steam_name || record.name || game.name,
      nameZh: gameName,
      appType: steamDbGame.app_type || record.app_type || "",
      technologies: steamDbGame.technologies || record.technologies || "",
      releaseDate: steamDbGame.release_date || record.release_date || record.release || "",
      categories: steamDbGame.categories || record.categories || "",
      tag: steamDbGame.tag || record.tag || "",
      screenshots: steamDbGame.screenshots || record.screenshots || ""
    }
  };
}

async function saveEvaluationRecord(record) {
  try {
    const saved = await fetchJson(`${API_BASE}/api/evaluation/records`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record)
    });
    if (record.syncKey) markSyncedHistory(record.syncKey);
    if (saved?.id) state.currentRecordId = saved.id;
    return saved;
  } catch (error) {
    console.warn("Failed to save evaluation record:", error);
    return null;
  }
}

async function markPaymentClicked(recordId) {
  if (!recordId) return;
  try {
    await fetchJson(`${API_BASE}/api/evaluation/records/${encodeURIComponent(recordId)}/payment-click`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
  } catch (error) {
    console.warn("Failed to mark payment click:", error);
  }
}

function renderResult(evaluation, game) {
  const result = typeof evaluation === "string" ? evaluation : evaluation.result;
  els.resultEmpty.classList.add("is-hidden");
  els.resultContent.classList.remove("is-hidden", "pass", "fail", "pending");
  els.resultContent.classList.add(result);

  if (result === "pass") {
    els.resultContent.innerHTML = `
      <div class="result-icon">✓</div>
      <h2>AI评估通过！<br />该游戏允许被赞助优先开发。</h2>
      <div class="result-copy">
        <p>游戏名称：${escapeHtml(game.nameZh)}<br />APP ID：${escapeHtml(game.appid)}</p>
        <div class="divider"></div>
        <p>${escapeHtml(evaluation.detail || "完成支付后，你的游戏将进入开发排期。我们会根据需求复杂度安排技术评估和开发交付。")}</p>
      </div>
      <a class="result-action" href="${PAYMENT_URL}" rel="noopener">前往活动页，完成支付</a>
    `;
  } else if (result === "pending") {
    els.resultContent.innerHTML = `
      <div class="result-icon">!</div>
      <h2>${escapeHtml(evaluation.title || "暂未获取到游戏信息")}</h2>
      <div class="result-copy">
        <p>游戏名称：${escapeHtml(game.nameZh || game.name || `Steam App ${game.appid}`)}<br />APP ID：${escapeHtml(game.appid)}</p>
        <div class="divider"></div>
        <p>${escapeHtml(evaluation.detail || "系统暂未获取到该游戏的完整信息，当前不能给出评估结论。请稍后重新提交评估。")}</p>
      </div>
    `;
  } else {
    els.resultContent.innerHTML = `
      <div class="result-icon">×</div>
      <h2>${escapeHtml(evaluation.title || "该游戏暂不支持赞助")}</h2>
      <div class="result-copy">
        <p>${escapeHtml(evaluation.detail || "经评估，该游戏暂时无法被赞助。建议您前往 XMODhub 客户端为该游戏投票。")}</p>
      </div>
    `;
  }
}

function readHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
}

function readSyncedHistory() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SYNCED_HISTORY_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function writeSyncedHistory(items) {
  localStorage.setItem(SYNCED_HISTORY_KEY, JSON.stringify([...items].slice(-500)));
}

function makeHistorySyncKey(record) {
  return [record.submitTime, record.appId, record.phone, record.result].join("|");
}

function markSyncedHistory(key) {
  const synced = readSyncedHistory();
  synced.add(key);
  writeSyncedHistory(synced);
}

function addHistory(record) {
  const items = readHistory();
  items.unshift(record);
  writeHistory(items.slice(0, 200));
  state.visibleHistoryCount = 20;
  renderHistory();
}

async function syncLocalHistoryToBackend() {
  const synced = readSyncedHistory();
  const items = readHistory().slice().reverse();
  for (const item of items) {
    const syncKey = makeHistorySyncKey(item);
    if (synced.has(syncKey)) continue;
    await saveEvaluationRecord({
      syncKey,
      submitted_at: item.submitTime,
      store_url: String(item.inputGameName || "").startsWith("http") ? item.inputGameName : "",
      game_name: item.steamGameName || item.inputGameName || "",
      steam_game_name: item.steamGameName || "",
      appid: item.appId,
      phone: item.phone || "",
      visitor_id: getVisitorId(),
      requirements: item.requirements || "",
      result: item.result,
      passed: item.result === "pass",
      reason: "由浏览器本地历史同步"
    });
  }
}

function truncateRequirement(value = "") {
  return value.length > 10 ? `${value.slice(0, 10)}...` : value;
}

function renderHistory() {
  const keyword = els.historySearch.value.trim().toLowerCase();
  const items = readHistory().filter((item) => {
    if (!keyword) return true;
    return [item.inputGameName, item.steamGameName, item.appId].join(" ").toLowerCase().includes(keyword);
  });
  const visibleItems = items.slice(0, state.visibleHistoryCount);

  if (!visibleItems.length) {
    els.historyList.innerHTML = `<div class="history-empty">暂无评估记录，快来评估第一款游戏吧。</div>`;
  } else {
    els.historyList.innerHTML = visibleItems.map((item) => `
      <div class="history-row">
        <div><span class="history-label">提交日期</span><span class="history-muted">${escapeHtml(item.submitTime.slice(0, 16))}</span></div>
        <div><span class="history-label">游戏名称</span><span class="history-main">${escapeHtml(item.inputGameName)}</span></div>
        <div><span class="history-label">Steam游戏名称</span><span class="history-muted">${escapeHtml(item.steamGameName)}</span></div>
        <div><span class="history-label">APP ID</span><span class="history-muted">${escapeHtml(item.appId)}</span></div>
        <div title="${escapeHtml(item.requirements)}"><span class="history-label">修改需求</span><span class="history-muted">${escapeHtml(truncateRequirement(item.requirements))}</span></div>
        <div><span class="result-badge ${item.result}">${item.result === "pass" ? "已通过" : "未通过"}</span></div>
      </div>
    `).join("");
  }

  els.loadMoreBtn.classList.toggle("is-hidden", items.length <= state.visibleHistoryCount);
  els.clearHistoryBtn.classList.toggle("is-hidden", readHistory().length === 0);
}

els.gameInput.addEventListener("input", () => {
  debouncedSearch();
  validateForm();
});

els.requirementsInput.addEventListener("input", () => {
  els.requirementsCounter.textContent = `${els.requirementsInput.value.length} / 200`;
  validateForm();
});

els.phoneInput.addEventListener("input", () => {
  els.phoneInput.value = els.phoneInput.value.replace(/\D/g, "").slice(0, 11);
  els.phoneInput.parentElement.classList.toggle("has-value", Boolean(els.phoneInput.value));
  localStorage.setItem(PHONE_KEY, els.phoneInput.value);
  debouncedIdentifyVisitor();
  validateForm();
});

els.clearPhone.addEventListener("click", () => {
  els.phoneInput.value = "";
  els.phoneInput.parentElement.classList.remove("has-value");
  localStorage.removeItem(PHONE_KEY);
  validateForm();
  els.phoneInput.focus();
});

els.resultContent.addEventListener("click", async (event) => {
  const action = event.target.closest(".result-action");
  if (!action) return;
  event.preventDefault();
  action.textContent = "正在前往活动页...";
  action.style.pointerEvents = "none";
  const saved = state.currentRecordPromise ? await state.currentRecordPromise : null;
  const recordId = state.currentRecordId || saved?.id;
  await markPaymentClicked(recordId);
  window.location.href = action.href;
});

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateForm(true)) return;

  const game = state.selectedGame;
  const requirements = els.requirementsInput.value.trim();
  const phone = els.phoneInput.value.trim();

  state.isEvaluating = true;
  state.currentRecordId = null;
  state.currentRecordPromise = null;
  els.submitBtn.classList.add("is-loading");
  els.submitText.textContent = "正在评估，请稍候...";
  validateForm();

  await new Promise((resolve) => window.setTimeout(resolve, 1200));
  let evaluation;
  try {
    evaluation = await evaluateGameWithBackend(game);
  } catch (error) {
    state.isEvaluating = false;
    els.submitBtn.classList.remove("is-loading");
    els.submitText.textContent = "一键评估";
    els.gameError.textContent = "评估接口暂时无法返回结果，请稍后再试。";
    validateForm();
    console.warn("Failed to evaluate game:", error);
    return;
  }
  const evaluatedGame = evaluation.game || game;
  state.selectedGame = evaluatedGame;
  renderMatchedGame(evaluatedGame);

  state.isEvaluating = false;
  els.submitBtn.classList.remove("is-loading");
  els.submitText.textContent = "一键评估";
  validateForm();

  if (evaluation.result !== "pending") {
    const submitTime = formatTime();
    const historyRecord = {
      submitTime,
      inputGameName: els.gameInput.value.trim(),
      steamGameName: evaluatedGame.name,
      appId: evaluatedGame.appid,
      requirements,
      phone: maskPhone(phone),
      result: evaluation.result
    };
    addHistory(historyRecord);
    state.currentRecordPromise = saveEvaluationRecord({
      syncKey: makeHistorySyncKey(historyRecord),
      submitted_at: submitTime,
      store_url: els.gameInput.value.trim(),
      game_name: evaluatedGame.nameZh || evaluatedGame.name,
      steam_game_name: evaluatedGame.name,
      appid: evaluatedGame.appid,
      phone,
      visitor_id: getVisitorId(),
      requirements,
      result: evaluation.result,
      passed: evaluation.result === "pass",
      reason: evaluation.reason,
      result_title: evaluation.title,
      result_detail: evaluation.detail,
      auto_passed: evaluation.raw?.auto_passed,
      manual_passed: evaluation.raw?.manual_passed,
      manual_reason: evaluation.raw?.manual_reason,
      app_type: evaluatedGame.appType,
      technologies: evaluatedGame.technologies,
      release_date: evaluatedGame.releaseDate,
      categories: evaluatedGame.categories,
      tag: evaluatedGame.tag,
      screenshots: evaluatedGame.screenshots
    });
  }
  renderResult(evaluation, evaluatedGame);
  localStorage.setItem(PHONE_KEY, phone);
  identifyVisitor(phone);
});

els.historySearch.addEventListener("input", () => {
  state.visibleHistoryCount = 20;
  renderHistory();
});

els.loadMoreBtn.addEventListener("click", () => {
  state.visibleHistoryCount += 20;
  renderHistory();
});

els.clearHistoryBtn.addEventListener("click", () => {
  writeHistory([]);
  renderHistory();
});

function restoreSavedPhone() {
  const savedPhone = localStorage.getItem(PHONE_KEY) || "";
  if (!savedPhone) return;
  els.phoneInput.value = savedPhone.replace(/\D/g, "").slice(0, 11);
  els.phoneInput.parentElement.classList.toggle("has-value", Boolean(els.phoneInput.value));
  validateForm();
}

restoreSavedPhone();
getVisitorId();
trackExposure();
identifyVisitor(els.phoneInput.value.trim());
renderHistory();
syncLocalHistoryToBackend();
