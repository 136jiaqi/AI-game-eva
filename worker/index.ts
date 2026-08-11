import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  XMOD_LOGIN_CREDENTIAL?: string;
  STEAMDB_API_URL?: string;
  STEAMDB_API_KEY?: string;
  STEAM_LANGUAGE?: string;
  STEAM_CC?: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

type RecordPayload = {
  submitted_at?: string;
  submitTime?: string;
  store_url?: string;
  storeUrl?: string;
  game_name?: string;
  gameName?: string;
  steam_game_name?: string;
  steamGameName?: string;
  appid?: string | number;
  appId?: string | number;
  phone?: string;
  requirements?: string;
  result?: string;
  passed?: boolean;
  reason?: string;
  result_title?: string;
  resultTitle?: string;
  result_detail?: string;
  resultDetail?: string;
  auto_passed?: boolean;
  autoPassed?: boolean;
  manual_passed?: boolean | null;
  manualPassed?: boolean | null;
  manual_reason?: string;
  manualReason?: string;
  app_type?: string;
  appType?: string;
  technologies?: string;
  release_date?: string;
  releaseDate?: string;
  categories?: string;
  tag?: string;
  screenshots?: string;
  visitor_id?: string;
  visitorId?: string;
};

type ExposurePayload = {
  visitor_id?: string;
  visitorId?: string;
  phone?: string;
  path?: string;
  referrer?: string;
};

type EvaluationWhitelistRecord = {
  name: string;
  normalized_name?: string;
  appid?: string | number | null;
  steam_name?: string | null;
  rating?: number | string | null;
  price?: number | string | null;
  positive_rating?: number | string | null;
  release?: string | null;
  follows?: number | string | null;
  online?: number | string | null;
  peak?: number | string | null;
  type?: string | null;
  technologies?: string | null;
};

type SteamDbGame = {
  appid: string;
  game_name_en: string;
  game_name_zh: string;
  app_type: string;
  technologies: string;
  release_date: string;
  categories: string;
  tag: string;
  screenshots: string;
  players_right_now: string;
  peak_24h: string;
  all_time_peak: string;
  languages: string;
  raw: Record<string, unknown>;
};

type XmodStatus = {
  matched: boolean;
  xmod_game_id?: string | null;
  xmod_title?: string | null;
  xmod_title_cn?: string | null;
  client_development_status: string;
  client_development_status_raw?: string | null;
  client_status: string;
  client_status_raw?: boolean | null;
  is_block?: boolean | null;
  reason?: string;
};

type EvaluationDecision = {
  passed: boolean;
  result: "pass" | "fail";
  title: string;
  detail: string;
  reason: string;
  basis: string[];
  auto_passed: boolean;
  manual_passed: boolean | null;
  manual_reason: string;
};

let whitelistPromise: Promise<EvaluationWhitelistRecord[]> | null = null;

const xmodDevelopmentStatusLabels: Record<string, string> = {
  PUBLISHED: "已上线",
  QUEUED: "开发排队中",
  UNDEVELOPED: "未开发",
  NOT_STARTED: "未开发",
  NOT_DEVELOPED: "未开发",
  PRIORITY: "优先开发",
  PRIORITY_DEVELOPMENT: "优先开发",
  DEVELOPING: "开发中",
  IN_DEVELOPMENT: "开发中",
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...corsHeaders,
    },
  });
}

function textValue(value: unknown): string {
  return String(value ?? "").trim();
}

function isPassed(payload: RecordPayload): boolean {
  if (typeof payload.passed === "boolean") return payload.passed;
  return ["pass", "passed", "true", "1", "通过", "已通过"].includes(textValue(payload.result).toLowerCase());
}

function sqlLike(value: string): string {
  return `%${value.replace(/[\\%_]/g, "\\$&")}%`;
}

function dateParam(url: URL, name: string): string {
  const value = textValue(url.searchParams.get(name));
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "";
}

async function addColumnIfMissing(db: D1Database, sql: string): Promise<void> {
  try {
    await db.prepare(sql).run();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.toLowerCase().includes("duplicate column")) throw error;
  }
}

async function ensureEvaluationTable(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS evaluation_records (
      id TEXT PRIMARY KEY,
      submitted_at TEXT NOT NULL,
      store_url TEXT NOT NULL DEFAULT '',
      game_name TEXT NOT NULL DEFAULT '',
      steam_game_name TEXT NOT NULL DEFAULT '',
      appid TEXT NOT NULL DEFAULT '',
      phone TEXT NOT NULL DEFAULT '',
      visitor_id TEXT NOT NULL DEFAULT '',
      requirements TEXT NOT NULL DEFAULT '',
      result TEXT NOT NULL DEFAULT 'fail',
      passed INTEGER NOT NULL DEFAULT 0,
      payment_clicked INTEGER NOT NULL DEFAULT 0,
      payment_clicked_at TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      result_title TEXT NOT NULL DEFAULT '',
      result_detail TEXT NOT NULL DEFAULT '',
      auto_passed INTEGER,
      manual_passed INTEGER,
      manual_reason TEXT NOT NULL DEFAULT '',
      app_type TEXT NOT NULL DEFAULT '',
      technologies TEXT NOT NULL DEFAULT '',
      release_date TEXT NOT NULL DEFAULT '',
      categories TEXT NOT NULL DEFAULT '',
      tag TEXT NOT NULL DEFAULT '',
      screenshots TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_submitted_at_idx ON evaluation_records (submitted_at)"),
    db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_phone_idx ON evaluation_records (phone)"),
    db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_visitor_id_idx ON evaluation_records (visitor_id)"),
    db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_appid_idx ON evaluation_records (appid)"),
    db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_game_name_idx ON evaluation_records (game_name)"),
  ]);
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN visitor_id TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN result_title TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN result_detail TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN auto_passed INTEGER");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN manual_passed INTEGER");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN manual_reason TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN app_type TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN technologies TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN release_date TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN categories TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN tag TEXT NOT NULL DEFAULT ''");
  await addColumnIfMissing(db, "ALTER TABLE evaluation_records ADD COLUMN screenshots TEXT NOT NULL DEFAULT ''");
  await db.prepare("CREATE INDEX IF NOT EXISTS evaluation_records_visitor_id_idx ON evaluation_records (visitor_id)").run();
}

async function ensureSteamGameTables(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS steam_game_queries (
      id TEXT PRIMARY KEY,
      appid TEXT NOT NULL,
      game_name_en TEXT NOT NULL DEFAULT '',
      game_name_zh TEXT NOT NULL DEFAULT '',
      app_type TEXT NOT NULL DEFAULT '',
      technologies TEXT NOT NULL DEFAULT '',
      release_date TEXT NOT NULL DEFAULT '',
      categories TEXT NOT NULL DEFAULT '',
      tag TEXT NOT NULL DEFAULT '',
      screenshots TEXT NOT NULL DEFAULT '',
      players_right_now TEXT NOT NULL DEFAULT '',
      peak_24h TEXT NOT NULL DEFAULT '',
      all_time_peak TEXT NOT NULL DEFAULT '',
      languages TEXT NOT NULL DEFAULT '',
      client_status TEXT NOT NULL DEFAULT '',
      client_development_status TEXT NOT NULL DEFAULT '',
      auto_passed INTEGER NOT NULL DEFAULT 0,
      final_passed INTEGER NOT NULL DEFAULT 0,
      manual_passed INTEGER,
      manual_reason TEXT NOT NULL DEFAULT '',
      result_title TEXT NOT NULL DEFAULT '',
      result_detail TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      raw_json TEXT NOT NULL DEFAULT '',
      queried_at TEXT NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS steam_game_queries_appid_idx ON steam_game_queries (appid)"),
    db.prepare("CREATE INDEX IF NOT EXISTS steam_game_queries_queried_at_idx ON steam_game_queries (queried_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS steam_game_overrides (
      appid TEXT PRIMARY KEY,
      manual_passed INTEGER,
      manual_reason TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL
    )`),
  ]);
}

async function ensureExposureTable(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS page_exposures (
      id TEXT PRIMARY KEY,
      visitor_id TEXT NOT NULL,
      phone TEXT NOT NULL DEFAULT '',
      path TEXT NOT NULL DEFAULT '',
      referrer TEXT NOT NULL DEFAULT '',
      user_agent TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS page_exposures_created_at_idx ON page_exposures (created_at)"),
    db.prepare("CREATE INDEX IF NOT EXISTS page_exposures_visitor_id_idx ON page_exposures (visitor_id)"),
    db.prepare("CREATE INDEX IF NOT EXISTS page_exposures_phone_idx ON page_exposures (phone)"),
  ]);
}

function buildWhere(url: URL): { whereSql: string; bindings: string[] } {
  const phone = textValue(url.searchParams.get("phone"));
  const gameName = textValue(url.searchParams.get("game_name"));
  const appid = textValue(url.searchParams.get("appid"));
  const visitorId = textValue(url.searchParams.get("visitor_id"));
  const exactDate = dateParam(url, "date");
  const startDate = exactDate || dateParam(url, "start_date");
  const endDate = exactDate || dateParam(url, "end_date");
  const clauses: string[] = [];
  const bindings: string[] = [];

  if (phone) {
    clauses.push("phone LIKE ? ESCAPE '\\'");
    bindings.push(sqlLike(phone));
  }
  if (appid) {
    clauses.push("appid LIKE ? ESCAPE '\\'");
    bindings.push(sqlLike(appid));
  }
  if (visitorId) {
    clauses.push("visitor_id LIKE ? ESCAPE '\\'");
    bindings.push(sqlLike(visitorId));
  }
  if (gameName) {
    clauses.push("(game_name LIKE ? ESCAPE '\\' OR steam_game_name LIKE ? ESCAPE '\\' OR store_url LIKE ? ESCAPE '\\')");
    const value = sqlLike(gameName);
    bindings.push(value, value, value);
  }
  if (startDate) {
    clauses.push("substr(created_at, 1, 10) >= ?");
    bindings.push(startDate);
  }
  if (endDate) {
    clauses.push("substr(created_at, 1, 10) <= ?");
    bindings.push(endDate);
  }

  return {
    whereSql: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "",
    bindings,
  };
}

function buildExposureWhere(url: URL): { whereSql: string; bindings: string[] } {
  const phone = textValue(url.searchParams.get("phone"));
  const visitorId = textValue(url.searchParams.get("visitor_id"));
  const exactDate = dateParam(url, "date");
  const startDate = exactDate || dateParam(url, "start_date");
  const endDate = exactDate || dateParam(url, "end_date");
  const clauses: string[] = [];
  const bindings: string[] = [];

  if (phone) {
    clauses.push("phone LIKE ? ESCAPE '\\'");
    bindings.push(sqlLike(phone));
  }
  if (visitorId) {
    clauses.push("visitor_id LIKE ? ESCAPE '\\'");
    bindings.push(sqlLike(visitorId));
  }
  if (startDate) {
    clauses.push("substr(created_at, 1, 10) >= ?");
    bindings.push(startDate);
  }
  if (endDate) {
    clauses.push("substr(created_at, 1, 10) <= ?");
    bindings.push(endDate);
  }

  return {
    whereSql: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "",
    bindings,
  };
}

function buildRecordDateWhere(url: URL): { whereSql: string; bindings: string[] } {
  const exactDate = dateParam(url, "date");
  const startDate = exactDate || dateParam(url, "start_date");
  const endDate = exactDate || dateParam(url, "end_date");
  const clauses: string[] = [];
  const bindings: string[] = [];

  if (startDate) {
    clauses.push("substr(records.created_at, 1, 10) >= ?");
    bindings.push(startDate);
  }
  if (endDate) {
    clauses.push("substr(records.created_at, 1, 10) <= ?");
    bindings.push(endDate);
  }

  return {
    whereSql: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "",
    bindings,
  };
}

function normalizeDbRecord(row: Record<string, unknown>): Record<string, unknown> {
  return {
    id: row.id,
    submitted_at: row.submitted_at,
    store_url: row.store_url,
    game_name: row.game_name,
    steam_game_name: row.steam_game_name,
    appid: row.appid,
    phone: row.phone,
    visitor_id: row.visitor_id,
    requirements: row.requirements,
    result: row.result,
    passed: Boolean(row.passed),
    payment_clicked: Boolean(row.payment_clicked),
    payment_clicked_at: row.payment_clicked_at,
    reason: row.reason,
    result_title: row.result_title,
    result_detail: row.result_detail,
    auto_passed: row.auto_passed === null || row.auto_passed === undefined ? null : Boolean(row.auto_passed),
    manual_passed: row.manual_passed === null || row.manual_passed === undefined ? null : Boolean(row.manual_passed),
    manual_reason: row.manual_reason,
    app_type: row.app_type,
    technologies: row.technologies,
    release_date: row.release_date,
    categories: row.categories,
    tag: row.tag,
    screenshots: row.screenshots,
  };
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function normalizeVisitorId(value: unknown): string {
  const id = textValue(value);
  return /^[a-zA-Z0-9_-]{8,80}$/.test(id) ? id : "";
}

function normalizePhone(value: unknown): string {
  const phone = textValue(value).replace(/\D/g, "").slice(0, 11);
  return /^1\d{10}$/.test(phone) ? phone : "";
}

function normalizeName(value: string): string {
  return value.toLowerCase().trim().replace(/\s+/g, " ");
}

async function loadWhitelist(env: Env, requestUrl: string): Promise<EvaluationWhitelistRecord[]> {
  if (!whitelistPromise) {
    whitelistPromise = env.ASSETS.fetch(new Request(new URL("/data/evaluation_whitelist.json", requestUrl)))
      .then(async (response) => {
        if (!response.ok) throw new Error(`Failed to load evaluation whitelist: HTTP ${response.status}`);
        return response.json() as Promise<EvaluationWhitelistRecord[]>;
      });
  }
  return whitelistPromise;
}

function findEvaluationRecord(items: EvaluationWhitelistRecord[], query: string): EvaluationWhitelistRecord | null {
  const normalized = normalizeName(query);
  if (/^\d+$/.test(normalized)) {
    const targetAppid = normalized;
    return items.find((item) => String(item.appid ?? "") === targetAppid) || null;
  }
  return items.find((item) => (item.normalized_name || normalizeName(item.name)) === normalized) || null;
}

function extractAppid(value: string): string {
  const text = textValue(value);
  if (/^\d+$/.test(text)) return text;
  try {
    const parsed = new URL(text);
    const match = parsed.pathname.match(/\/app\/(\d+)/i);
    if (match?.[1]) return match[1];
  } catch {
    const match = text.match(/(?:steamcommunity\.com|store\.steampowered\.com)\/app\/(\d+)/i);
    if (match?.[1]) return match[1];
  }
  return "";
}

function stringField(value: unknown): string {
  return textValue(value).replace(/\s+/g, " ");
}

function containsToken(value: string, token: string): boolean {
  return value.toLowerCase().includes(token.toLowerCase());
}

function normalizeSteamDbGame(payload: Record<string, unknown>): SteamDbGame {
  const appid = stringField(payload.app_id ?? payload.appid ?? payload.AppID);
  return {
    appid,
    game_name_en: stringField(payload.game_name_en ?? payload.name ?? payload.steam_name),
    game_name_zh: stringField(payload.game_name_zh ?? payload.name_zh ?? payload.game_name_en),
    app_type: stringField(payload.app_type ?? payload["App Type"] ?? payload.type),
    technologies: stringField(payload.technologies ?? payload.Technologies),
    release_date: stringField(payload.release_date ?? payload["Release Date"] ?? payload.release),
    categories: stringField(payload.categories ?? payload.Categories),
    tag: stringField(payload.tag ?? payload.Tag ?? payload.tags),
    screenshots: stringField(payload.screenshots ?? payload.Screenshots),
    players_right_now: stringField(payload.players_right_now ?? payload["players right now"]),
    peak_24h: stringField(payload.peak_24h ?? payload["24-hour peak"]),
    all_time_peak: stringField(payload.all_time_peak ?? payload["all-time peak"]),
    languages: stringField(payload.languages ?? payload.Languages),
    raw: payload,
  };
}

async function fetchSteamDbGame(appid: string, env: Env): Promise<SteamDbGame> {
  const apiUrl = textValue(env.STEAMDB_API_URL);
  const apiKey = textValue(env.STEAMDB_API_KEY);
  if (!apiUrl) throw new Error("STEAMDB_API_URL is not configured");
  if (!apiKey) throw new Error("STEAMDB_API_KEY is not configured");

  const url = new URL(apiUrl);
  url.searchParams.set("app_id", appid);
  const response = await fetch(url.toString(), {
    headers: {
      "X-API-Key": apiKey,
      "User-Agent": "XMODhub-Backend/1.0",
      "Accept": "application/json",
    },
  });
  const body = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (!response.ok) throw new Error(`SteamDB API HTTP ${response.status}`);
  if (!body) throw new Error("SteamDB API returned invalid JSON");
  if (Number(body.code) !== 200) throw new Error(textValue(body.message) || "SteamDB API returned non-200 code");
  const data = body.data as Record<string, unknown> | undefined;
  const game = data?.game as Record<string, unknown> | undefined;
  if (!game) throw new Error("SteamDB API response missing data.game");
  const normalized = normalizeSteamDbGame(game);
  if (!normalized.appid) normalized.appid = appid;
  return normalized;
}

function parseReleaseDate(value: string): { accurate: boolean; futureMoreThanFiveDays: boolean; reason: string } {
  const raw = textValue(value);
  if (!raw) return { accurate: false, futureMoreThanFiveDays: false, reason: "发行日期为空" };
  if (/to be announced|coming soon|^tba$|待定|即将上线|季度|q[1-4]/i.test(raw)) {
    return { accurate: false, futureMoreThanFiveDays: false, reason: "发行日期为即将上线或非标准日期" };
  }
  if (/^\d{4}$/.test(raw.trim())) return { accurate: false, futureMoreThanFiveDays: false, reason: "发行日期仅显示年份" };
  const normalized = raw.replace(/\//g, "-").replace("T", " ");
  const match = normalized.match(/(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (!match) return { accurate: false, futureMoreThanFiveDays: false, reason: "发行日期格式无法解析" };
  const release = new Date(Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4] || 0),
    Number(match[5] || 0),
    Number(match[6] || 0),
  ));
  if (Number.isNaN(release.getTime())) return { accurate: false, futureMoreThanFiveDays: false, reason: "发行日期格式无法解析" };
  const diffDays = (release.getTime() - Date.now()) / 86400000;
  return { accurate: true, futureMoreThanFiveDays: diffDays > 5, reason: "" };
}

function failDecision(title: string, detail: string, basis: string[]): EvaluationDecision {
  return { passed: false, result: "fail", title, detail, reason: detail, basis, auto_passed: false, manual_passed: null, manual_reason: "" };
}

function passDecision(game: SteamDbGame, basis: string[]): EvaluationDecision {
  return {
    passed: true,
    result: "pass",
    title: "AI评估通过",
    detail: "经评估，该游戏符合优先开发赞助条件。完成支付后，XMODhub 将根据需求复杂度安排技术评估和开发排期。",
    reason: "游戏符合优先开发赞助条件",
    basis,
    auto_passed: true,
    manual_passed: null,
    manual_reason: "",
  };
}

function calculateSteamDbEvaluation(game: SteamDbGame, xmodStatus: XmodStatus): EvaluationDecision {
  const clientStatus = xmodStatus.client_status || "查询中";
  const developmentStatus = xmodStatus.client_development_status || "查询中";
  const categories = game.categories || "";
  const technologies = game.technologies || "";

  if (clientStatus === "生效中" && developmentStatus === "已上线") {
    return failDecision(
      "该游戏修改器已上线",
      "抱歉，这款游戏的修改器已经在 XMODhub 客户端上线，无需参与优先开发赞助。如您希望增加更多修改功能，或当前修改器存在失效、未更新等问题，请前往 XMODhub 客户端－该游戏详情页－催更 提交反馈。",
      ["客户端状态 = 生效中", "客户端开发状态 = 已上线"],
    );
  }
  if (clientStatus === "生效中" && developmentStatus === "未开发") {
    return failDecision(
      "该游戏暂不支持优先开发",
      "经 XMODhub 技术评估，该游戏可能涉及技术限制、强联网、多人联机或其他无法稳定支持的情况，因此暂不支持开发修改器。 后续如游戏技术条件发生变化，XMODhub 将重新评估其开发可行性。",
      ["客户端状态 = 生效中", "客户端开发状态 = 未开发"],
    );
  }
  if (clientStatus === "已下线") {
    return failDecision(
      "该游戏当前已停止支持",
      "我们暂不支持该游戏。可能与游戏技术条件、服务调整、合规风险或其他原因有关。",
      ["客户端状态 = 已下线"],
    );
  }

  const sponsorshipDetail = "经评估，该游戏暂时无法被赞助。别气馁！建议您前往 XMODhub客户端为该游戏投上宝贵的一票。当投票热度达到标准后，我们的运营团队会再次介入人工专项评估！";
  if (!containsToken(categories, "Single-player")) {
    return failDecision("该游戏暂不支持赞助", sponsorshipDetail, [`categories 不包含 Single-player：${categories || "-"}`]);
  }
  for (const blockedCategory of ["MMO", "In-App Purchases", "Adult Only"]) {
    if (containsToken(categories, blockedCategory)) {
      return failDecision("该游戏暂不支持赞助", sponsorshipDetail, [`categories 包含 Single-player`, `categories 包含 ${blockedCategory}`]);
    }
  }
  if (technologies && !containsToken(technologies, "Unity")) {
    return failDecision("该游戏暂不支持赞助", sponsorshipDetail, [`Technologies = ${technologies}`, "能够查询到引擎且不包含 Unity"]);
  }

  const release = parseReleaseDate(game.release_date);
  if (!release.accurate || release.futureMoreThanFiveDays) {
    return failDecision(
      "该游戏还未正式发售",
      "经评估，该游戏在Steam商店还没正式发售，因此暂不支持直接参与赞助。请在游戏正式上线后重新提交评估。您可以前往 XMODhub 客户端为该游戏投票。XMODhub 将根据投票数量、游戏热度及技术可行性评估后续开发安排。",
      [release.reason || `发行日期 ${game.release_date} 距查询日期超过 5 天`],
    );
  }

  return passDecision(game, [
    "未命中已上线、未开发、已下线等客户端状态拦截规则",
    `categories 包含 Single-player，且未包含 MMO / In-App Purchases / Adult Only：${categories}`,
    technologies ? `Technologies 包含 Unity：${technologies}` : "未查询到引擎，不按引擎拦截",
    `发行日期已通过校验：${game.release_date}`,
  ]);
}

async function loadManualOverride(db: D1Database, appid: string): Promise<{ manual_passed: boolean | null; manual_reason: string }> {
  const row = await db.prepare("SELECT manual_passed, manual_reason FROM steam_game_overrides WHERE appid = ?")
    .bind(appid)
    .first<Record<string, unknown>>();
  if (!row || row.manual_passed === null || row.manual_passed === undefined) return { manual_passed: null, manual_reason: "" };
  return { manual_passed: Boolean(row.manual_passed), manual_reason: textValue(row.manual_reason) };
}

function applyManualOverride(decision: EvaluationDecision, override: { manual_passed: boolean | null; manual_reason: string }): EvaluationDecision {
  if (override.manual_passed === null) return decision;
  const passed = override.manual_passed;
  return {
    ...decision,
    passed,
    result: passed ? "pass" : "fail",
    manual_passed: passed,
    manual_reason: override.manual_reason,
    reason: override.manual_reason || decision.reason,
    title: passed ? "人工评估通过" : "人工评估不通过",
    detail: override.manual_reason || decision.detail,
    basis: [...decision.basis, `人工编辑结果优先：${passed ? "通过" : "不通过"}`],
  };
}

async function saveSteamGameQuery(db: D1Database, game: SteamDbGame, xmodStatus: XmodStatus, decision: EvaluationDecision): Promise<void> {
  await db.prepare(`INSERT INTO steam_game_queries
    (id, appid, game_name_en, game_name_zh, app_type, technologies, release_date, categories, tag, screenshots,
     players_right_now, peak_24h, all_time_peak, languages, client_status, client_development_status,
     auto_passed, final_passed, manual_passed, manual_reason, result_title, result_detail, reason, raw_json, queried_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(
      crypto.randomUUID(),
      game.appid,
      game.game_name_en,
      game.game_name_zh,
      game.app_type,
      game.technologies,
      game.release_date,
      game.categories,
      game.tag,
      game.screenshots,
      game.players_right_now,
      game.peak_24h,
      game.all_time_peak,
      game.languages,
      xmodStatus.client_status,
      xmodStatus.client_development_status,
      decision.auto_passed ? 1 : 0,
      decision.passed ? 1 : 0,
      decision.manual_passed === null ? null : decision.manual_passed ? 1 : 0,
      decision.manual_reason,
      decision.title,
      decision.detail,
      decision.reason,
      JSON.stringify(game.raw),
      new Date().toISOString(),
    )
    .run();
}

async function evaluateSteamApp(appid: string, env: Env): Promise<{
  query: string;
  appid: string;
  game: SteamDbGame;
  record: EvaluationWhitelistRecord & Record<string, unknown>;
  xmod_status: XmodStatus;
  client_status: string;
  client_development_status: string;
} & EvaluationDecision> {
  await ensureSteamGameTables(env.DB);
  const game = await fetchSteamDbGame(appid, env);
  const xmodStatus = await fetchXmodStatus(game.game_name_en || game.game_name_zh || appid, env);
  const autoDecision = calculateSteamDbEvaluation(game, xmodStatus);
  const decision = applyManualOverride(autoDecision, await loadManualOverride(env.DB, game.appid));
  await saveSteamGameQuery(env.DB, game, xmodStatus, decision);
  return {
    query: appid,
    appid: game.appid,
    game,
    record: steamRecordFromGame(game),
    xmod_status: xmodStatus,
    client_status: xmodStatus.client_status,
    client_development_status: xmodStatus.client_development_status,
    ...decision,
  };
}

function steamRecordFromGame(game: SteamDbGame): EvaluationWhitelistRecord & Record<string, unknown> {
  return {
    name: game.game_name_en || game.game_name_zh || `Steam App ${game.appid}`,
    normalized_name: normalizeName(game.game_name_en || game.game_name_zh || ""),
    appid: game.appid,
    steam_name: game.game_name_en,
    type: game.app_type,
    technologies: game.technologies,
    release: game.release_date,
    app_type: game.app_type,
    game_name_en: game.game_name_en,
    game_name_zh: game.game_name_zh,
    release_date: game.release_date,
    categories: game.categories,
    tag: game.tag,
    screenshots: game.screenshots,
  };
}

async function fetchSteamChineseName(appid: string | number | null | undefined, env: Env): Promise<string | null> {
  if (!appid) return null;
  try {
    const params = new URLSearchParams({
      appids: String(appid),
      cc: env.STEAM_CC || "cn",
      l: env.STEAM_LANGUAGE || "schinese",
      filters: "basic",
    });
    const response = await fetch(`https://store.steampowered.com/api/appdetails?${params.toString()}`, {
      headers: { "user-agent": "Steam-Asset-Evaluation/1.0" },
    });
    if (!response.ok) return null;
    const payload = await response.json() as Record<string, { success?: boolean; data?: { name?: string } }>;
    const envelope = payload[String(appid)];
    return envelope?.success ? envelope.data?.name || null : null;
  } catch {
    return null;
  }
}

function xmodHeaders(env: Env): HeadersInit {
  return {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "cache-control": "no-cache",
    "login-credential": env.XMOD_LOGIN_CREDENTIAL || "",
    "origin": "http://cms.qiyou.cn:3120",
    "pragma": "no-cache",
    "referer": "http://cms.qiyou.cn:3120/",
    "saas-app-id": "GAME_TOOL",
    "saas-platform": "pc",
    "saas-product-line": "XMOD",
    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Microsoft Edge";v="150"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "sec-fetch-storage-access": "active",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
  };
}

function clientStatusLabel(isActive: unknown, isBlock: unknown): string {
  if (isBlock === true) return "已下线";
  if (isActive === true) return "生效中";
  return "未生效";
}

function selectXmodMatch(gameName: string, games: Array<Record<string, unknown>>): Record<string, unknown> | null {
  const target = normalizeName(gameName);
  if (!games.length) return null;

  for (const item of games) {
    const game = item.game as Record<string, unknown> | undefined;
    const title = game?.title as Record<string, unknown> | undefined;
    if (normalizeName(String(title?.name || "")) === target) return item;
  }

  for (const item of games) {
    const game = item.game as Record<string, unknown> | undefined;
    const title = game?.title as Record<string, unknown> | undefined;
    if (normalizeName(String(title?.translate || "")) === target) return item;
  }

  return games[0];
}

async function fetchXmodStatus(gameName: string, env: Env): Promise<XmodStatus> {
  if (!env.XMOD_LOGIN_CREDENTIAL) {
    return {
      matched: false,
      client_development_status: "查询中",
      client_status: "查询中",
      reason: "XMOD login credential is not configured",
    };
  }

  try {
    const params = new URLSearchParams({ like_game_title: gameName, page_size: "20", page: "1" });
    const response = await fetch(`https://gtabff.xmodhub.cn/api/game_tool_admin_bff/v1/xmod_resource/games?${params.toString()}`, {
      headers: xmodHeaders(env),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json() as { games?: Array<Record<string, unknown>> };
    const selected = selectXmodMatch(gameName, payload.games || []);
    if (!selected) {
      return {
        matched: false,
        client_development_status: "查询中",
        client_status: "查询中",
        reason: "No matching XMOD game found",
      };
    }
    const game = selected.game as Record<string, unknown>;
    const title = game.title as Record<string, unknown> | undefined;
    const rawDevelopmentStatus = String(game.development_status || "");
    return {
      matched: true,
      xmod_game_id: String(game.game_id || ""),
      xmod_title: String(title?.name || ""),
      xmod_title_cn: String(title?.translate || ""),
      client_development_status: xmodDevelopmentStatusLabels[rawDevelopmentStatus] || rawDevelopmentStatus || "查询中",
      client_development_status_raw: rawDevelopmentStatus || null,
      client_status: clientStatusLabel(game.is_active, game.is_block),
      client_status_raw: typeof game.is_active === "boolean" ? game.is_active : null,
      is_block: typeof game.is_block === "boolean" ? game.is_block : null,
    };
  } catch (error) {
    return {
      matched: false,
      client_development_status: "查询中",
      client_status: "查询中",
      reason: error instanceof Error ? error.message : "XMOD request failed",
    };
  }
}

function calculateEvaluationResult(record: EvaluationWhitelistRecord | null, xmodStatus?: XmodStatus): { passed: boolean; reason: string } {
  if (!record) {
    return { passed: false, reason: "游戏名或 APP ID 不在评估名单中" };
  }
  if (!xmodStatus || !xmodStatus.matched) {
    return { passed: true, reason: "游戏在评估名单中，客户端状态和客户端开发状态为查询中" };
  }
  const clientStatus = xmodStatus.client_status || "查询中";
  const developmentStatus = xmodStatus.client_development_status || "查询中";
  if (clientStatus === "查询中" || developmentStatus === "查询中") {
    return { passed: true, reason: "游戏在评估名单中，客户端状态或客户端开发状态为查询中" };
  }
  if (clientStatus === "已下线") {
    return { passed: false, reason: "游戏在评估名单中，但客户端状态为已下线" };
  }
  if (clientStatus !== "生效中") {
    return { passed: false, reason: `游戏在评估名单中，但客户端状态为${clientStatus}` };
  }
  if (developmentStatus === "未开发" || developmentStatus === "已上线") {
    return { passed: false, reason: `游戏在评估名单中，客户端状态为生效中，但客户端开发状态为${developmentStatus}` };
  }
  if (["优先开发", "开发中", "开发排队中"].includes(developmentStatus)) {
    return { passed: true, reason: `游戏在评估名单中，客户端状态为生效中，客户端开发状态为${developmentStatus}` };
  }
  return { passed: false, reason: `游戏在评估名单中，但客户端开发状态为${developmentStatus}` };
}

async function handleWhitelistEvaluationApi(request: Request, env: Env, url: URL): Promise<Response | null> {
  if (request.method === "OPTIONS" && (url.pathname.startsWith("/api/evaluation") || url.pathname.startsWith("/api/xmod"))) {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (url.pathname === "/api/evaluation" && request.method === "GET") {
    await ensureSteamGameTables(env.DB);
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") || 50)));
    const offset = (page - 1) * pageSize;
    const countResult = await env.DB.prepare("SELECT COUNT(DISTINCT appid) AS total FROM steam_game_queries")
      .first<{ total: number }>();
    const rows = await env.DB.prepare(`SELECT latest.*
      FROM steam_game_queries latest
      INNER JOIN (
        SELECT appid, MAX(queried_at) AS queried_at
        FROM steam_game_queries
        GROUP BY appid
      ) picked ON picked.appid = latest.appid AND picked.queried_at = latest.queried_at
      ORDER BY latest.queried_at DESC
      LIMIT ? OFFSET ?`)
      .bind(pageSize, offset)
      .all();
    return jsonResponse({
      page,
      page_size: pageSize,
      total: countResult?.total || 0,
      items: rows.results.map((row: Record<string, unknown>) => ({
        name: row.game_name_en || row.game_name_zh || `Steam App ${row.appid}`,
        steam_name: row.game_name_en,
        game_name_en: row.game_name_en,
        game_name_zh: row.game_name_zh,
        appid: row.appid,
        app_type: row.app_type,
        type: row.app_type,
        technologies: row.technologies,
        release: row.release_date,
        release_date: row.release_date,
        categories: row.categories,
        tag: row.tag,
        screenshots: row.screenshots,
        client_status: row.client_status,
        client_development_status: row.client_development_status,
        passed: Boolean(row.final_passed),
        auto_passed: Boolean(row.auto_passed),
        manual_passed: row.manual_passed === null || row.manual_passed === undefined ? null : Boolean(row.manual_passed),
        manual_reason: row.manual_reason,
        result_title: row.result_title,
        result_detail: row.result_detail,
        reason: row.reason,
        queried_at: row.queried_at,
      })),
    });
  }

  if (url.pathname === "/api/xmod/status" && request.method === "GET") {
    const query = textValue(url.searchParams.get("q"));
    if (!query) return jsonResponse({ detail: "Missing q" }, 400);
    return jsonResponse(await fetchXmodStatus(query, env));
  }

  if (url.pathname === "/api/evaluation/assets/check" && request.method === "GET") {
    const query = textValue(url.searchParams.get("q"));
    if (!query) return jsonResponse({ detail: "Missing q" }, 400);
    const appid = extractAppid(query);
    if (!appid) return jsonResponse({ detail: "请输入 Steam 商店链接或 APP ID" }, 400);
    return jsonResponse(await evaluateSteamApp(appid, env));
  }

  const manualMatch = url.pathname.match(/^\/api\/evaluation\/assets\/(\d+)\/manual-result$/);
  if (manualMatch && request.method === "PATCH") {
    await ensureSteamGameTables(env.DB);
    const payload = await request.json().catch(() => null) as { manual_passed?: boolean | null; manual_reason?: string } | null;
    if (!payload) return jsonResponse({ detail: "Invalid JSON body" }, 400);
    const appid = manualMatch[1];
    const now = new Date().toISOString();
    const manualPassed = payload.manual_passed === null || payload.manual_passed === undefined ? null : Boolean(payload.manual_passed);
    await env.DB.prepare(`INSERT INTO steam_game_overrides (appid, manual_passed, manual_reason, updated_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(appid) DO UPDATE SET manual_passed = excluded.manual_passed, manual_reason = excluded.manual_reason, updated_at = excluded.updated_at`)
      .bind(appid, manualPassed === null ? null : manualPassed ? 1 : 0, textValue(payload.manual_reason), now)
      .run();
    return jsonResponse({ appid, manual_passed: manualPassed, manual_reason: textValue(payload.manual_reason), updated_at: now });
  }

  if (url.pathname === "/api/evaluation/check" && request.method === "GET") {
    const query = textValue(url.searchParams.get("q"));
    if (!query) return jsonResponse({ detail: "Missing q" }, 400);
    const appid = extractAppid(query);
    if (!appid) return jsonResponse({ detail: "请输入 Steam 商店链接或 APP ID" }, 400);
    return jsonResponse(await evaluateSteamApp(appid, env));
  }

  if (url.pathname === "/api/evaluation/check-legacy" && request.method === "GET") {
    const query = textValue(url.searchParams.get("q"));
    if (!query) return jsonResponse({ detail: "Missing q" }, 400);
    const items = await loadWhitelist(env, request.url);
    const record = findEvaluationRecord(items, query);
    if (!record) {
      const result = calculateEvaluationResult(null);
      return jsonResponse({ query, ...result, record: null });
    }
    const [gameCnName, xmodStatus] = await Promise.all([
      fetchSteamChineseName(record.appid, env),
      fetchXmodStatus(record.name, env),
    ]);
    const result = calculateEvaluationResult(record, xmodStatus);
    return jsonResponse({
      query,
      ...result,
      appid: record.appid,
      game_cn_name: gameCnName,
      client_development_status: xmodStatus.client_development_status,
      client_status: xmodStatus.client_status,
      xmod_status: xmodStatus,
      record,
    });
  }

  return null;
}

async function handleExposureApi(request: Request, env: Env, url: URL): Promise<Response | null> {
  if (!url.pathname.startsWith("/api/exposure")) return null;
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });

  await ensureExposureTable(env.DB);

  if (url.pathname === "/api/exposure" && request.method === "POST") {
    const payload = await request.json().catch(() => null) as ExposurePayload | null;
    if (!payload) return jsonResponse({ detail: "Invalid JSON body" }, 400);

    const visitorId = normalizeVisitorId(payload.visitor_id || payload.visitorId);
    if (!visitorId) return jsonResponse({ detail: "Invalid visitor_id" }, 400);

    const phone = normalizePhone(payload.phone);
    const now = new Date().toISOString();
    const record = {
      id: crypto.randomUUID(),
      visitor_id: visitorId,
      phone,
      path: textValue(payload.path).slice(0, 300),
      referrer: textValue(payload.referrer).slice(0, 500),
      user_agent: textValue(request.headers.get("user-agent")).slice(0, 260),
      created_at: now,
    };

    await env.DB.prepare(`INSERT INTO page_exposures
      (id, visitor_id, phone, path, referrer, user_agent, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)`)
      .bind(record.id, record.visitor_id, record.phone, record.path, record.referrer, record.user_agent, record.created_at)
      .run();

    return jsonResponse(record);
  }

  if (url.pathname === "/api/exposure/identify" && request.method === "POST") {
    const payload = await request.json().catch(() => null) as ExposurePayload | null;
    if (!payload) return jsonResponse({ detail: "Invalid JSON body" }, 400);

    const visitorId = normalizeVisitorId(payload.visitor_id || payload.visitorId);
    const phone = normalizePhone(payload.phone);
    if (!visitorId) return jsonResponse({ detail: "Invalid visitor_id" }, 400);
    if (!phone) return jsonResponse({ detail: "Invalid phone" }, 400);

    await env.DB.prepare("UPDATE page_exposures SET phone = ? WHERE visitor_id = ? AND phone = ''")
      .bind(phone, visitorId)
      .run();

    return jsonResponse({ visitor_id: visitorId, phone, associated: true });
  }

  if (url.pathname === "/api/exposure/stats" && request.method === "GET") {
    const { whereSql, bindings } = buildExposureWhere(url);
    const summary = await env.DB.prepare(`SELECT
        COUNT(*) AS exposure_count,
        COUNT(DISTINCT visitor_id) AS visitor_count,
        COUNT(DISTINCT CASE WHEN phone != '' THEN visitor_id END) AS identified_visitor_count,
        COUNT(DISTINCT CASE WHEN phone != '' THEN phone END) AS phone_count
      FROM page_exposures
      ${whereSql}`)
      .bind(...bindings)
      .first<Record<string, unknown>>();

    const daily = await env.DB.prepare(`SELECT
        substr(created_at, 1, 10) AS date,
        COUNT(*) AS exposure_count,
        COUNT(DISTINCT visitor_id) AS visitor_count,
        COUNT(DISTINCT CASE WHEN phone != '' THEN visitor_id END) AS identified_visitor_count
      FROM page_exposures
      ${whereSql}
      GROUP BY substr(created_at, 1, 10)
      ORDER BY date DESC
      LIMIT 30`)
      .bind(...bindings)
      .all();

    return jsonResponse({
      exposure_count: Number(summary?.exposure_count || 0),
      visitor_count: Number(summary?.visitor_count || 0),
      identified_visitor_count: Number(summary?.identified_visitor_count || 0),
      phone_count: Number(summary?.phone_count || 0),
      daily: daily.results,
    });
  }

  if (url.pathname === "/api/exposure/activity-stats" && request.method === "GET") {
    await ensureEvaluationTable(env.DB);
    const { whereSql, bindings } = buildExposureWhere(url);
    const { whereSql: recordWhereSql, bindings: recordBindings } = buildRecordDateWhere(url);
    const visitorWhereSql = whereSql ? `${whereSql} AND visitor_id != ''` : "WHERE visitor_id != ''";
    const summary = await env.DB.prepare(`WITH exposed_visitors AS (
        SELECT DISTINCT visitor_id
        FROM page_exposures
        ${visitorWhereSql}
      )
      SELECT
        (SELECT COUNT(*) FROM page_exposures ${whereSql}) AS exposure_count,
        (SELECT COUNT(*) FROM exposed_visitors) AS visitor_count,
        (SELECT COUNT(*)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql}
        ) AS evaluation_click_count,
        (SELECT COUNT(DISTINCT records.visitor_id)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql}
        ) AS evaluation_click_visitor_count,
        (SELECT COUNT(*)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql ? `${recordWhereSql} AND records.passed = 1` : "WHERE records.passed = 1"}
        ) AS passed_evaluation_count,
        (SELECT COUNT(DISTINCT records.visitor_id)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql ? `${recordWhereSql} AND records.passed = 1` : "WHERE records.passed = 1"}
        ) AS passed_evaluation_visitor_count,
        (SELECT COUNT(*)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql ? `${recordWhereSql} AND records.passed = 1 AND records.payment_clicked = 1` : "WHERE records.passed = 1 AND records.payment_clicked = 1"}
        ) AS passed_payment_clicked_count,
        (SELECT COUNT(DISTINCT records.visitor_id)
          FROM evaluation_records records
          INNER JOIN exposed_visitors exposure ON exposure.visitor_id = records.visitor_id
          ${recordWhereSql ? `${recordWhereSql} AND records.passed = 1 AND records.payment_clicked = 1` : "WHERE records.passed = 1 AND records.payment_clicked = 1"}
        ) AS passed_payment_clicked_visitor_count`)
      .bind(...bindings, ...bindings, ...recordBindings, ...recordBindings, ...recordBindings, ...recordBindings, ...recordBindings, ...recordBindings)
      .first<Record<string, unknown>>();

    const daily = await env.DB.prepare(`WITH daily_exposures AS (
        SELECT
          substr(created_at, 1, 10) AS date,
          COUNT(*) AS exposure_count,
          COUNT(DISTINCT visitor_id) AS visitor_count
        FROM page_exposures
        ${whereSql}
        GROUP BY substr(created_at, 1, 10)
      ),
      daily_exposed_visitors AS (
        SELECT DISTINCT
          substr(created_at, 1, 10) AS date,
          visitor_id
        FROM page_exposures
        ${visitorWhereSql}
      )
      SELECT
        daily.date,
        daily.exposure_count,
        daily.visitor_count,
        COUNT(records.id) AS evaluation_click_count,
        COUNT(DISTINCT CASE WHEN records.id IS NOT NULL THEN records.visitor_id END) AS evaluation_click_visitor_count,
        SUM(CASE WHEN records.passed = 1 THEN 1 ELSE 0 END) AS passed_evaluation_count,
        COUNT(DISTINCT CASE WHEN records.passed = 1 THEN records.visitor_id END) AS passed_evaluation_visitor_count,
        SUM(CASE WHEN records.passed = 1 AND records.payment_clicked = 1 THEN 1 ELSE 0 END) AS passed_payment_clicked_count,
        COUNT(DISTINCT CASE WHEN records.passed = 1 AND records.payment_clicked = 1 THEN records.visitor_id END) AS passed_payment_clicked_visitor_count,
        CASE
          WHEN COUNT(DISTINCT CASE WHEN records.passed = 1 THEN records.visitor_id END) = 0 THEN 0
          ELSE ROUND(
            CAST(COUNT(DISTINCT CASE WHEN records.passed = 1 AND records.payment_clicked = 1 THEN records.visitor_id END) AS REAL)
            / COUNT(DISTINCT CASE WHEN records.passed = 1 THEN records.visitor_id END),
            4
          )
        END AS payment_click_rate
      FROM daily_exposures daily
      LEFT JOIN daily_exposed_visitors exposure ON exposure.date = daily.date
      LEFT JOIN evaluation_records records
        ON records.visitor_id = exposure.visitor_id
        AND substr(records.created_at, 1, 10) = daily.date
      GROUP BY daily.date, daily.exposure_count, daily.visitor_count
      ORDER BY daily.date DESC`)
      .bind(...bindings, ...bindings)
      .all();

    return jsonResponse({
      exposure_count: Number(summary?.exposure_count || 0),
      visitor_count: Number(summary?.visitor_count || 0),
      evaluation_click_count: Number(summary?.evaluation_click_count || 0),
      evaluation_click_visitor_count: Number(summary?.evaluation_click_visitor_count || 0),
      passed_evaluation_count: Number(summary?.passed_evaluation_count || 0),
      passed_evaluation_visitor_count: Number(summary?.passed_evaluation_visitor_count || 0),
      passed_payment_clicked_count: Number(summary?.passed_payment_clicked_count || 0),
      passed_payment_clicked_visitor_count: Number(summary?.passed_payment_clicked_visitor_count || 0),
      payment_click_rate: Number(summary?.passed_evaluation_visitor_count || 0) === 0
        ? 0
        : Number(summary?.passed_payment_clicked_visitor_count || 0) / Number(summary?.passed_evaluation_visitor_count || 0),
      daily: daily.results,
    });
  }

  if (url.pathname === "/api/exposure/visitors" && request.method === "GET") {
    await ensureEvaluationTable(env.DB);
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") || 50)));
    const offset = (page - 1) * pageSize;
    const { whereSql, bindings } = buildExposureWhere(url);
    const countResult = await env.DB.prepare(`SELECT COUNT(*) AS total FROM (
        SELECT visitor_id FROM page_exposures ${whereSql} GROUP BY visitor_id
      )`)
      .bind(...bindings)
      .first<{ total: number }>();

    const rowsResult = await env.DB.prepare(`SELECT
        exposure.visitor_id,
        exposure.phone,
        exposure.exposure_count,
        exposure.first_seen_at,
        exposure.last_seen_at,
        COALESCE(records.evaluation_count, 0) AS evaluation_count,
        COALESCE(records.passed_count, 0) AS passed_count,
        COALESCE(records.failed_count, 0) AS failed_count,
        COALESCE(records.payment_clicked_count, 0) AS payment_clicked_count
      FROM (
        SELECT
          visitor_id,
          COALESCE(MAX(NULLIF(phone, '')), '') AS phone,
          COUNT(*) AS exposure_count,
          MIN(created_at) AS first_seen_at,
          MAX(created_at) AS last_seen_at
        FROM page_exposures
        ${whereSql}
        GROUP BY visitor_id
      ) exposure
      LEFT JOIN (
        SELECT
          visitor_id,
          COUNT(*) AS evaluation_count,
          SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed_count,
          SUM(CASE WHEN passed = 1 THEN 0 ELSE 1 END) AS failed_count,
          SUM(CASE WHEN passed = 1 AND payment_clicked = 1 THEN 1 ELSE 0 END) AS payment_clicked_count
        FROM evaluation_records
        WHERE visitor_id != ''
        GROUP BY visitor_id
      ) records ON records.visitor_id = exposure.visitor_id
      ORDER BY exposure.last_seen_at DESC
      LIMIT ? OFFSET ?`)
      .bind(...bindings, pageSize, offset)
      .all();

    return jsonResponse({
      page,
      page_size: pageSize,
      total: countResult?.total || 0,
      items: rowsResult.results,
    });
  }

  return jsonResponse({ detail: "Not found" }, 404);
}

async function handleEvaluationApi(request: Request, env: Env, url: URL): Promise<Response | null> {
  if (!url.pathname.startsWith("/api/evaluation/records")) return null;
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });

  await ensureEvaluationTable(env.DB);

  const paymentClickMatch = url.pathname.match(/^\/api\/evaluation\/records\/([^/]+)\/payment-click$/);
  if (paymentClickMatch && request.method === "POST") {
    const id = decodeURIComponent(paymentClickMatch[1]);
    const clickedAt = new Date().toISOString();
    await env.DB.prepare("UPDATE evaluation_records SET payment_clicked = 1, payment_clicked_at = ? WHERE id = ? AND passed = 1")
      .bind(clickedAt, id)
      .run();
    return jsonResponse({ id, payment_clicked: true, payment_clicked_at: clickedAt });
  }

  if (url.pathname === "/api/evaluation/records" && request.method === "POST") {
    const payload = await request.json().catch(() => null) as RecordPayload | null;
    if (!payload) return jsonResponse({ detail: "Invalid JSON body" }, 400);

    const passed = isPassed(payload);
    const now = new Date().toISOString();
    const record = {
      id: crypto.randomUUID(),
      submitted_at: textValue(payload.submitted_at || payload.submitTime) || now,
      store_url: textValue(payload.store_url || payload.storeUrl),
      game_name: textValue(payload.game_name || payload.gameName),
      steam_game_name: textValue(payload.steam_game_name || payload.steamGameName),
      appid: textValue(payload.appid ?? payload.appId),
      phone: textValue(payload.phone),
      visitor_id: normalizeVisitorId(payload.visitor_id || payload.visitorId),
      requirements: textValue(payload.requirements),
      result: passed ? "pass" : "fail",
      passed,
      payment_clicked: false,
      payment_clicked_at: "",
      reason: textValue(payload.reason),
      result_title: textValue(payload.result_title || payload.resultTitle),
      result_detail: textValue(payload.result_detail || payload.resultDetail),
      auto_passed: typeof (payload.auto_passed ?? payload.autoPassed) === "boolean" ? Boolean(payload.auto_passed ?? payload.autoPassed) : passed,
      manual_passed: typeof (payload.manual_passed ?? payload.manualPassed) === "boolean" ? Boolean(payload.manual_passed ?? payload.manualPassed) : null,
      manual_reason: textValue(payload.manual_reason || payload.manualReason),
      app_type: textValue(payload.app_type || payload.appType),
      technologies: textValue(payload.technologies),
      release_date: textValue(payload.release_date || payload.releaseDate),
      categories: textValue(payload.categories),
      tag: textValue(payload.tag),
      screenshots: textValue(payload.screenshots),
      created_at: now,
    };

    await env.DB.prepare(`INSERT INTO evaluation_records
      (id, submitted_at, store_url, game_name, steam_game_name, appid, phone, visitor_id, requirements, result, passed, payment_clicked, payment_clicked_at, reason,
       result_title, result_detail, auto_passed, manual_passed, manual_reason, app_type, technologies, release_date, categories, tag, screenshots, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(
        record.id,
        record.submitted_at,
        record.store_url,
        record.game_name,
        record.steam_game_name,
        record.appid,
        record.phone,
        record.visitor_id,
        record.requirements,
        record.result,
        record.passed ? 1 : 0,
        0,
        "",
        record.reason,
        record.result_title,
        record.result_detail,
        record.auto_passed ? 1 : 0,
        record.manual_passed === null ? null : record.manual_passed ? 1 : 0,
        record.manual_reason,
        record.app_type,
        record.technologies,
        record.release_date,
        record.categories,
        record.tag,
        record.screenshots,
        record.created_at,
      )
      .run();

    return jsonResponse(record);
  }

  if (url.pathname === "/api/evaluation/records/stats" && request.method === "GET") {
    const { whereSql, bindings } = buildWhere(url);
    const result = await env.DB.prepare(`SELECT
        COALESCE(NULLIF(game_name, ''), NULLIF(steam_game_name, ''), '-') AS game_name,
        COALESCE(NULLIF(appid, ''), '-') AS appid,
        COUNT(*) AS total_count,
        SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed_count,
        SUM(CASE WHEN passed = 1 THEN 0 ELSE 1 END) AS failed_count,
        SUM(CASE WHEN passed = 1 AND payment_clicked = 1 THEN 1 ELSE 0 END) AS payment_clicked_count,
        CASE
          WHEN SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) = 0 THEN 0
          ELSE ROUND(
            CAST(SUM(CASE WHEN passed = 1 AND payment_clicked = 1 THEN 1 ELSE 0 END) AS REAL)
            / SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END),
            4
          )
        END AS payment_click_rate
      FROM evaluation_records
      ${whereSql}
      GROUP BY COALESCE(NULLIF(appid, ''), '-'), COALESCE(NULLIF(game_name, ''), NULLIF(steam_game_name, ''), '-')
      ORDER BY total_count DESC, game_name ASC`)
      .bind(...bindings)
      .all();
    return jsonResponse({ total: result.results.length, items: result.results });
  }

  if (url.pathname === "/api/evaluation/records/export" && request.method === "GET") {
    const { whereSql, bindings } = buildWhere(url);
    const result = await env.DB.prepare(`SELECT * FROM evaluation_records ${whereSql} ORDER BY submitted_at DESC`)
      .bind(...bindings)
      .all();
    const headers = ["提交日期时间", "商店链接", "游戏名称", "APP ID", "手机号", "Visitor ID", "修改需求", "评估结果", "是否点击返回活动页", "点击时间", "评估标题", "评估详情", "评估原因", "App Type", "Technologies", "Release Date", "categories", "Tag", "screenshots"];
    const lines = [
      headers.map(csvCell).join(","),
      ...result.results.map((row: Record<string, unknown>) => [
        row.submitted_at,
        row.store_url,
        row.game_name || row.steam_game_name,
        row.appid,
        row.phone,
        row.visitor_id,
        row.requirements,
        row.passed ? "通过" : "不通过",
        row.payment_clicked ? "是" : "否",
        row.payment_clicked_at,
        row.result_title,
        row.result_detail,
        row.reason,
        row.app_type,
        row.technologies,
        row.release_date,
        row.categories,
        row.tag,
        row.screenshots,
      ].map(csvCell).join(",")),
    ];
    return new Response(`\ufeff${lines.join("\r\n")}`, {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="evaluation-records.csv"',
        ...corsHeaders,
      },
    });
  }

  if (url.pathname === "/api/evaluation/records" && request.method === "GET") {
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") || 50)));
    const offset = (page - 1) * pageSize;
    const { whereSql, bindings } = buildWhere(url);
    const countResult = await env.DB.prepare(`SELECT COUNT(*) AS total FROM evaluation_records ${whereSql}`)
      .bind(...bindings)
      .first<{ total: number }>();
    const rowsResult = await env.DB.prepare(`SELECT * FROM evaluation_records ${whereSql} ORDER BY submitted_at DESC LIMIT ? OFFSET ?`)
      .bind(...bindings, pageSize, offset)
      .all();
    return jsonResponse({
      page,
      page_size: pageSize,
      total: countResult?.total || 0,
      items: rowsResult.results.map((row: unknown) => normalizeDbRecord(row as Record<string, unknown>)),
    });
  }

  return jsonResponse({ detail: "Not found" }, 404);
}

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const exposureApiResponse = await handleExposureApi(request, env, url);
    if (exposureApiResponse) return exposureApiResponse;

    const whitelistApiResponse = await handleWhitelistEvaluationApi(request, env, url);
    if (whitelistApiResponse) return whitelistApiResponse;

    const apiResponse = await handleEvaluationApi(request, env, url);
    if (apiResponse) return apiResponse;

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;
