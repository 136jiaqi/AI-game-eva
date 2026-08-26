from __future__ import annotations

import base64
import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).parent
H5_ROOT = ROOT / "public" / "h5"
ADMIN_ROOT = ROOT / "public" / "admin"
DEFAULT_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
DEFAULT_STEAMDB_API_URL = "http://47.79.16.6:8080/api/v1/games/search"
DEFAULT_XMOD_STATUS_API_URL = "https://gtabff.xmodhub.cn/api/game_tool_admin_bff/v1/xmod_resource/games"
PAYMENT_URL = "https://www.xmodhub.cn/acticlustr/promotion/pc/49b75353f2374de991b15a03425cd6a9"
DB_PATH = ROOT / "streamlit_data.db"
BEIJING_TZ = timezone(timedelta(hours=8))
ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "}U[5O+p8{N,9N_PMdJZ?!iCB:wTRX(Xe"

SPONSORSHIP_REJECT_DETAIL = "经评估，该游戏暂时无法被赞助。别气馁！建议您前往 XMODhub客户端为该游戏投上宝贵的一票。当投票热度达到标准后，我们的运营团队会再次介入人工专项评估！"
CLIENT_ONLINE_DETAIL = "抱歉，这款游戏的修改器已经在 XMODhub 客户端上线，无需参与优先开发赞助。如您希望增加更多修改功能，或当前修改器存在失效、未更新等问题，请前往 XMODhub 客户端－该游戏详情页－催更 提交反馈。"
CLIENT_UNSUPPORTED_DETAIL = "经 XMODhub 技术评估，该游戏可能涉及技术限制、强联网、多人联机或其他无法稳定支持的情况，因此暂不支持开发修改器。 后续如游戏技术条件发生变化，XMODhub 将重新评估其开发可行性。"
CLIENT_OFFLINE_DETAIL = "我们暂不支持该游戏。可能与游戏技术条件、服务调整、合规风险或其他原因有关。"
FAILURE_DETAIL_OPTIONS = [
    SPONSORSHIP_REJECT_DETAIL,
    CLIENT_ONLINE_DETAIL,
    CLIENT_UNSUPPORTED_DETAIL,
    CLIENT_OFFLINE_DETAIL,
]
PASS_DETAIL = "经评估，该游戏符合优先开发赞助条件。完成支付后，XMODhub 将根据需求复杂度安排技术评估和开发排期。"

XMOD_DEVELOPMENT_STATUS_LABELS = {
    "PUBLISHED": "已上线",
    "QUEUED": "开发排队中",
    "UNDEVELOPED": "未开发",
    "NOT_STARTED": "未开发",
    "NOT_DEVELOPED": "未开发",
    "PRIORITY": "优先开发",
    "PRIORITY_DEVELOPMENT": "优先开发",
    "DEVELOPING": "开发中",
    "IN_DEVELOPMENT": "开发中",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def image_data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def now_text() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evaluation_records (
              id TEXT PRIMARY KEY,
              submitted_at TEXT NOT NULL,
              store_url TEXT NOT NULL DEFAULT '',
              game_name_zh TEXT NOT NULL DEFAULT '',
              appid TEXT NOT NULL DEFAULT '',
              phone TEXT NOT NULL DEFAULT '',
              visitor_id TEXT NOT NULL DEFAULT '',
              requirements TEXT NOT NULL DEFAULT '',
              result TEXT NOT NULL DEFAULT '',
              passed INTEGER NOT NULL DEFAULT 0,
              payment_clicked INTEGER NOT NULL DEFAULT 0,
              payment_clicked_at TEXT NOT NULL DEFAULT '',
              result_title TEXT NOT NULL DEFAULT '',
              result_detail TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity_events (
              id TEXT PRIMARY KEY,
              event_date TEXT NOT NULL,
              event_type TEXT NOT NULL,
              visitor_id TEXT NOT NULL DEFAULT '',
              record_id TEXT NOT NULL DEFAULT '',
              appid TEXT NOT NULL DEFAULT '',
              passed INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS game_queries (
              appid TEXT PRIMARY KEY,
              game_name_zh TEXT NOT NULL DEFAULT '',
              game_name_en TEXT NOT NULL DEFAULT '',
              app_type TEXT NOT NULL DEFAULT '',
              technologies TEXT NOT NULL DEFAULT '',
              release_date TEXT NOT NULL DEFAULT '',
              categories TEXT NOT NULL DEFAULT '',
              tag TEXT NOT NULL DEFAULT '',
              screenshots TEXT NOT NULL DEFAULT '',
              client_status TEXT NOT NULL DEFAULT '',
              client_development_status TEXT NOT NULL DEFAULT '',
              evaluation_result TEXT NOT NULL DEFAULT '',
              auto_passed INTEGER NOT NULL DEFAULT 0,
              manual_result TEXT NOT NULL DEFAULT '自动',
              failure_detail TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              basis TEXT NOT NULL DEFAULT '',
              query_count INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(game_queries)").fetchall()}
        if "failure_detail" not in columns:
            conn.execute("ALTER TABLE game_queries ADD COLUMN failure_detail TEXT NOT NULL DEFAULT ''")


def get_visitor_id() -> str:
    if "visitor_id" not in st.session_state:
        st.session_state.visitor_id = uuid.uuid4().hex
    return st.session_state.visitor_id


def add_activity_event(event_type: str, visitor_id: str | None = None, record_id: str = "", appid: str = "", passed: bool = False) -> None:
    init_db()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO activity_events (id, event_date, event_type, visitor_id, record_id, appid, passed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, today_text(), event_type, visitor_id or get_visitor_id(), record_id, appid, 1 if passed else 0, now_text()),
        )


def record_exposure_once() -> None:
    if st.session_state.get("exposure_recorded"):
        return
    add_activity_event("exposure")
    st.session_state.exposure_recorded = True


def save_game_query(game: dict, xmod_status: dict, decision: dict) -> None:
    init_db()
    appid = text_value(game.get("appid") or game.get("app_id"))
    if not appid:
        return
    now = now_text()
    with db_connect() as conn:
        existing = conn.execute("SELECT manual_result, failure_detail, note, query_count FROM game_queries WHERE appid = ?", (appid,)).fetchone()
        manual_result = existing["manual_result"] if existing else "自动"
        existing_failure_detail = allowed_failure_detail(existing["failure_detail"]) if existing else ""
        failure_detail = existing_failure_detail or (allowed_failure_detail(decision.get("detail"), SPONSORSHIP_REJECT_DETAIL) if not decision.get("passed") else "")
        note = existing["note"] if existing else ""
        query_count = int(existing["query_count"] if existing else 0) + 1
        conn.execute(
            """
            INSERT INTO game_queries (
              appid, game_name_zh, game_name_en, app_type, technologies, release_date, categories, tag, screenshots,
              client_status, client_development_status, evaluation_result, auto_passed, manual_result, failure_detail, note, basis, query_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(appid) DO UPDATE SET
              game_name_zh=excluded.game_name_zh,
              game_name_en=excluded.game_name_en,
              app_type=excluded.app_type,
              technologies=excluded.technologies,
              release_date=excluded.release_date,
              categories=excluded.categories,
              tag=excluded.tag,
              screenshots=excluded.screenshots,
              client_status=excluded.client_status,
              client_development_status=excluded.client_development_status,
              evaluation_result=excluded.evaluation_result,
              auto_passed=excluded.auto_passed,
              manual_result=excluded.manual_result,
              failure_detail=excluded.failure_detail,
              note=excluded.note,
              basis=excluded.basis,
              query_count=excluded.query_count,
              updated_at=excluded.updated_at
            """,
            (
                appid,
                text_value(game.get("game_name_zh") or game.get("name_zh") or game.get("game_name_en")),
                text_value(game.get("game_name_en")),
                text_value(game.get("app_type")),
                text_value(game.get("technologies")),
                text_value(game.get("release_date")),
                text_value(game.get("categories")),
                text_value(game.get("tag")),
                text_value(game.get("screenshots")),
                text_value(xmod_status.get("client_status")),
                text_value(xmod_status.get("client_development_status")),
                "通过" if decision.get("passed") else "不通过",
                1 if decision.get("passed") else 0,
                manual_result,
                failure_detail,
                note,
                "\n".join(text_value(item) for item in decision.get("basis", [])),
                query_count,
                now,
            ),
        )


def final_passed_for_app(appid: str, auto_passed: bool) -> bool:
    init_db()
    with db_connect() as conn:
        row = conn.execute("SELECT manual_result FROM game_queries WHERE appid = ?", (appid,)).fetchone()
    if not row or row["manual_result"] == "自动":
        return auto_passed
    return row["manual_result"] == "通过"


def manual_overrides_for_app(appid: str) -> dict:
    init_db()
    with db_connect() as conn:
        row = conn.execute("SELECT manual_result, failure_detail FROM game_queries WHERE appid = ?", (appid,)).fetchone()
    if not row:
        return {"manual_result": "自动", "failure_detail": ""}
    return {
        "manual_result": text_value(row["manual_result"]) or "自动",
        "failure_detail": allowed_failure_detail(row["failure_detail"]),
    }


def daily_submission_count(phone: str) -> int:
    init_db()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM evaluation_records
            WHERE phone = ? AND substr(submitted_at, 1, 10) = ?
            """,
            (phone, today_text()),
        ).fetchone()
    return int(row["total"] if row else 0)


def save_evaluation_record(payload: dict) -> str:
    init_db()
    record_id = uuid.uuid4().hex
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO evaluation_records (
              id, submitted_at, store_url, game_name_zh, appid, phone, visitor_id, requirements,
              result, passed, result_title, result_detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                payload["submitted_at"],
                payload["store_url"],
                payload["game_name_zh"],
                payload["appid"],
                payload["phone"],
                payload["visitor_id"],
                payload["requirements"],
                payload["result"],
                1 if payload["passed"] else 0,
                payload["result_title"],
                payload["result_detail"],
                now_text(),
            ),
        )
    return record_id


def mark_payment_clicked(record_id: str) -> None:
    if not record_id:
        return
    init_db()
    clicked_at = now_text()
    with db_connect() as conn:
        row = conn.execute("SELECT visitor_id, appid, passed FROM evaluation_records WHERE id = ?", (record_id,)).fetchone()
        conn.execute(
            "UPDATE evaluation_records SET payment_clicked = 1, payment_clicked_at = ? WHERE id = ?",
            (clicked_at, record_id),
        )
    if row:
        add_activity_event("payment_click", row["visitor_id"], record_id, row["appid"], bool(row["passed"]))


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    init_db()
    with db_connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def editor_records(value: object) -> list[dict]:
    if hasattr(value, "to_dict"):
        return value.to_dict("records")
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def render_admin_table(rows: list[dict], empty_text: str = "暂无数据") -> None:
    if not rows:
        st.markdown(f'<div class="admin-empty">{html.escape(empty_text)}</div>', unsafe_allow_html=True)
        return
    headers = list(rows[0].keys())
    header_html = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_html = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(text_value(row.get(header)))}</td>" for header in headers)
        body_html.append(f"<tr>{cells}</tr>")
    st.markdown(
        f"""
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{''.join(body_html)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def configured_api_base() -> str:
    secret_value = ""
    try:
        secret_value = st.secrets.get("XMODHUB_API_BASE", "")
    except Exception:
        secret_value = ""
    return (os.getenv("XMODHUB_API_BASE") or secret_value or DEFAULT_API_BASE).rstrip("/")


def configured_secret(name: str, default: str = "") -> str:
    secret_value = ""
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(os.getenv(name) or secret_value or default).strip()


def configured_admin_password() -> str:
    return configured_secret("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)


def require_admin_login() -> None:
    if st.session_state.get("admin_authenticated") is True:
        return

    st.markdown(
        """
        <style>
          #MainMenu, header, footer { display: none !important; }
          .stApp { background: #f6f7fb !important; color: #101828 !important; }
          .block-container { max-width: 460px; padding: 96px 24px; }
          .login-title { font-size: 30px; font-weight: 900; color: #061733; margin-bottom: 8px; }
          .login-subtitle { color: #667085; margin-bottom: 24px; }
        </style>
        <div class="login-title">AI 免费评估后台登录</div>
        <div class="login-subtitle">请输入后台账号和密码后继续访问。</div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("admin_login_form"):
        username = st.text_input("登录账号")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
    if submitted:
        username_ok = hmac.compare_digest(username.strip(), ADMIN_USERNAME)
        password_ok = hmac.compare_digest(password, configured_admin_password())
        if username_ok and password_ok:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("账号或密码错误")
    st.stop()


def parse_steam_appid(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{2,12}", text):
        return text
    try:
        parsed = urlparse(text)
        match = re.search(r"/app/(\d+)", parsed.path, re.IGNORECASE)
        return match.group(1) if match else ""
    except Exception:
        return ""


def text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(text_value(item) for item in value if text_value(item))
    return str(value).strip()


def allowed_failure_detail(value: object, default: str = "") -> str:
    detail = text_value(value)
    if detail in FAILURE_DETAIL_OPTIONS:
        return detail
    return default


def contains_token(value: str, token: str) -> bool:
    return token.lower() in text_value(value).lower()


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", text_value(value).lower()).strip()


def fetch_steamdb_game(appid: str) -> dict:
    api_url = configured_secret("STEAMDB_API_URL", DEFAULT_STEAMDB_API_URL).rstrip("?")
    api_key = configured_secret("STEAMDB_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 STEAMDB_API_KEY")

    separator = "&" if "?" in api_url else "?"
    request_url = f"{api_url}{separator}{urlencode({'app_id': appid})}"
    request = Request(
        request_url,
        headers={
            "User-Agent": "XMODhub-Streamlit/1.0",
            "X-API-Key": api_key,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"SteamDB 接口返回 HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"SteamDB 接口请求失败：{error.reason}") from error

    game = (payload.get("data") or {}).get("game") if isinstance(payload, dict) else None
    if not isinstance(game, dict):
        raise RuntimeError("SteamDB 接口未返回 data.game")
    game["appid"] = text_value(game.get("app_id") or game.get("appid") or appid)
    return game


def extract_steamdb_games(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    candidates = [
        data.get("games") if isinstance(data, dict) else None,
        data.get("list") if isinstance(data, dict) else None,
        data.get("items") if isinstance(data, dict) else None,
        payload.get("games"),
        payload.get("list"),
        payload.get("items"),
    ]
    game = data.get("game") if isinstance(data, dict) else None
    if isinstance(game, dict):
        candidates.insert(0, [game])
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def fetch_steamdb_games_by_name(query: str) -> list[dict]:
    api_url = configured_secret("STEAMDB_API_URL", DEFAULT_STEAMDB_API_URL).rstrip("?")
    api_key = configured_secret("STEAMDB_API_KEY")
    if not api_key:
        return []

    separator = "&" if "?" in api_url else "?"
    for param_name in ["game_name", "name", "keyword", "q", "search"]:
        request_url = f"{api_url}{separator}{urlencode({param_name: query})}"
        request = Request(
            request_url,
            headers={
                "User-Agent": "XMODhub-Streamlit/1.0",
                "X-API-Key": api_key,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue
        games = extract_steamdb_games(payload)
        if games:
            for game in games:
                game["appid"] = text_value(game.get("app_id") or game.get("appid"))
            return games
    return []


def fetch_demo_steamdb_game(game: dict) -> dict | None:
    names = [
        text_value(game.get("game_name_en")),
        text_value(game.get("game_name_zh")),
    ]
    seen_queries: set[str] = set()
    for name in names:
        if not name:
            continue
        query = f"{name} Demo"
        normalized_query = normalize_name(query)
        if normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        games = fetch_steamdb_games_by_name(query)
        for candidate in games:
            candidate_name = " ".join(
                value
                for value in [
                    text_value(candidate.get("game_name_en")),
                    text_value(candidate.get("game_name_zh")),
                    text_value(candidate.get("name")),
                ]
                if value
            )
            app_type = text_value(candidate.get("app_type"))
            if "demo" in normalize_name(candidate_name) or "demo" in normalize_name(app_type):
                return candidate
    return None


def xmod_client_status_label(is_active: object, is_block: object) -> str:
    if is_block is True:
        return "已下线"
    if is_active is True:
        return "生效中"
    return "未生效"


def xmod_headers() -> dict[str, str]:
    credential = configured_secret("XMOD_LOGIN_CREDENTIAL")
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "login-credential": credential,
        "origin": "http://cms.qiyou.cn:3120",
        "pragma": "no-cache",
        "referer": "http://cms.qiyou.cn:3120/",
        "saas-app-id": "GAME_TOOL",
        "saas-platform": "pc",
        "saas-product-line": "XMOD",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    }


def extract_xmod_games(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    candidates = [
        payload.get("games"),
        (payload.get("data") or {}).get("games") if isinstance(payload.get("data"), dict) else None,
        (payload.get("data") or {}).get("list") if isinstance(payload.get("data"), dict) else None,
        payload.get("list"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def select_xmod_match(game_name: str, games: list[dict]) -> dict | None:
    target = normalize_name(game_name)
    if not games:
        return None
    for item in games:
        game = item.get("game") if isinstance(item.get("game"), dict) else item
        title = game.get("title") if isinstance(game.get("title"), dict) else {}
        if normalize_name(text_value(title.get("name"))) == target:
            return item
    for item in games:
        game = item.get("game") if isinstance(item.get("game"), dict) else item
        title = game.get("title") if isinstance(game.get("title"), dict) else {}
        if normalize_name(text_value(title.get("translate"))) == target:
            return item
    return games[0]


def normalize_xmod_status(selected: dict, query: str) -> dict:
    game = selected.get("game") if isinstance(selected.get("game"), dict) else selected
    title = game.get("title") if isinstance(game.get("title"), dict) else {}
    raw_development_status = text_value(game.get("development_status"))
    return {
        "matched": True,
        "query": query,
        "xmod_game_id": text_value(game.get("game_id")),
        "xmod_title": text_value(title.get("name")),
        "xmod_title_cn": text_value(title.get("translate")),
        "client_development_status": XMOD_DEVELOPMENT_STATUS_LABELS.get(raw_development_status, raw_development_status or "查询中"),
        "client_development_status_raw": raw_development_status,
        "client_status": xmod_client_status_label(game.get("is_active"), game.get("is_block")),
        "client_status_raw": game.get("is_active") if isinstance(game.get("is_active"), bool) else None,
        "is_block": game.get("is_block") if isinstance(game.get("is_block"), bool) else None,
    }


def fetch_xmod_status_once(game_name: str) -> dict:
    if not configured_secret("XMOD_LOGIN_CREDENTIAL"):
        return {
            "matched": False,
            "client_development_status": "查询中",
            "client_status": "查询中",
            "reason": "未配置 XMOD_LOGIN_CREDENTIAL",
        }
    api_url = configured_secret("XMOD_STATUS_API_URL", DEFAULT_XMOD_STATUS_API_URL).rstrip("?")
    separator = "&" if "?" in api_url else "?"
    request_url = f"{api_url}{separator}{urlencode({'like_game_title': game_name, 'page_size': '20', 'page': '1'})}"
    request = Request(request_url, headers=xmod_headers(), method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return {
            "matched": False,
            "client_development_status": "查询中",
            "client_status": "查询中",
            "reason": f"XMOD 接口返回 HTTP {error.code}",
        }
    except URLError as error:
        return {
            "matched": False,
            "client_development_status": "查询中",
            "client_status": "查询中",
            "reason": f"XMOD 接口请求失败：{error.reason}",
        }

    selected = select_xmod_match(game_name, extract_xmod_games(payload))
    if not selected:
        return {
            "matched": False,
            "client_development_status": "查询中",
            "client_status": "查询中",
            "reason": "No matching XMOD game found",
        }
    return normalize_xmod_status(selected, game_name)


def is_blocking_xmod_status(status: dict) -> bool:
    client_status = text_value(status.get("client_status"))
    development_status = text_value(status.get("client_development_status"))
    return (
        client_status == "已下线"
        or (client_status == "生效中" and development_status in {"已上线", "未开发"})
    )


def fetch_xmod_status(game_names: list[str]) -> dict:
    names = []
    for name in game_names:
        normalized = text_value(name)
        if normalized and normalized not in names:
            names.append(normalized)
    if not names:
        return {"matched": False, "client_development_status": "查询中", "client_status": "查询中", "reason": "Missing game name"}
    first_result: dict | None = None
    first_matched: dict | None = None
    for name in names:
        result = fetch_xmod_status_once(name)
        if first_result is None:
            first_result = result
        if result.get("matched") and first_matched is None:
            first_matched = result
        if result.get("matched") and is_blocking_xmod_status(result):
            return result
    return first_matched or first_result or {"matched": False, "client_development_status": "查询中", "client_status": "查询中"}


def parse_release_date(value: str) -> tuple[bool, bool, str]:
    raw = text_value(value)
    if not raw:
        return False, False, "发行日期为空"
    if re.search(r"to be announced|coming soon|^tba$|待定|即将上线|季度|q[1-4]", raw, re.IGNORECASE):
        return False, False, "发行日期为即将上线或非标准日期"
    if re.fullmatch(r"\d{4}", raw):
        return False, False, "发行日期仅显示年份"
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if not match:
        return False, False, "发行日期格式无法解析"
    release = datetime(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        tzinfo=timezone.utc,
    )
    diff_days = (release - datetime.now(timezone.utc)).total_seconds() / 86400
    return True, diff_days > 5, ""


def evaluate_steamdb_game(game: dict, xmod_status: dict | None = None, demo_game: dict | None = None) -> dict:
    xmod_status = xmod_status or {"client_status": "查询中", "client_development_status": "查询中"}
    client_status = text_value(xmod_status.get("client_status")) or "查询中"
    development_status = text_value(xmod_status.get("client_development_status")) or "查询中"
    categories = text_value(game.get("categories"))
    technologies = text_value(game.get("technologies"))
    release_date = text_value(game.get("release_date") or game.get("Release Date"))
    demo_categories = text_value((demo_game or {}).get("categories"))
    demo_technologies = text_value((demo_game or {}).get("technologies"))
    demo_name = text_value((demo_game or {}).get("game_name_zh") or (demo_game or {}).get("game_name_en") or (demo_game or {}).get("name"))
    demo_appid = text_value((demo_game or {}).get("appid") or (demo_game or {}).get("app_id"))
    category_sources = [("游戏", categories)]
    if demo_game:
        category_sources.append(("Demo", demo_categories))

    if client_status == "生效中" and development_status == "已上线":
        return {
            "passed": False,
            "title": "该游戏修改器已上线",
            "detail": CLIENT_ONLINE_DETAIL,
            "basis": ["客户端状态 = 生效中", "客户端开发状态 = 已上线"],
        }
    if client_status == "生效中" and development_status == "未开发":
        return {
            "passed": False,
            "title": "该游戏暂不支持优先开发",
            "detail": CLIENT_UNSUPPORTED_DETAIL,
            "basis": ["客户端状态 = 生效中", "客户端开发状态 = 未开发"],
        }
    if client_status == "已下线":
        return {
            "passed": False,
            "title": "该游戏当前已停止支持",
            "detail": CLIENT_OFFLINE_DETAIL,
            "basis": ["客户端状态 = 已下线"],
        }

    for source_name, source_categories in category_sources:
        if not contains_token(source_categories, "Single-player"):
            return {
                "passed": False,
                "title": "该游戏暂不支持赞助",
                "detail": SPONSORSHIP_REJECT_DETAIL,
                "basis": [f"{source_name} categories 不包含 Single-player：{source_categories or '-'}"],
            }
        for blocked in ["MMO", "In-App Purchases", "Adult Only"]:
            if contains_token(source_categories, blocked):
                return {
                    "passed": False,
                    "title": "该游戏暂不支持赞助",
                    "detail": SPONSORSHIP_REJECT_DETAIL,
                    "basis": [f"{source_name} categories 包含 Single-player", f"{source_name} categories 包含 {blocked}"],
                }

    if technologies:
        if contains_token(technologies, "Unity"):
            return {
                "passed": True,
                "title": "AI评估通过",
                "detail": PASS_DETAIL,
                "basis": [
                    "未命中已上线、未开发、已下线等客户端状态拦截规则",
                    f"categories 包含 Single-player：{categories}",
                    f"Technologies 包含 Unity：{technologies}",
                    f"发行日期不参与评估判断：{release_date or '-'}",
                ],
            }
        return {"passed": False, "title": "该游戏暂不支持赞助", "detail": SPONSORSHIP_REJECT_DETAIL, "basis": [f"Technologies = {technologies}", "Technologies 有值且不包含 Unity"]}

    if demo_technologies:
        if contains_token(demo_technologies, "Unity"):
            return {
                "passed": True,
                "title": "AI评估通过",
                "detail": PASS_DETAIL,
                "basis": [
                    "主游戏 Technologies 为空",
                    f"Demo：{demo_name or '-'} / APP ID：{demo_appid or '-'}",
                    f"Demo Technologies 包含 Unity：{demo_technologies}",
                    f"发行日期不参与评估判断：{release_date or '-'}",
                ],
            }
        return {
            "passed": False,
            "title": "该游戏暂不支持赞助",
            "detail": SPONSORSHIP_REJECT_DETAIL,
            "basis": [
                "主游戏 Technologies 为空",
                f"Demo：{demo_name or '-'} / APP ID：{demo_appid or '-'}",
                f"Demo Technologies 有值且不包含 Unity：{demo_technologies}",
            ],
        }

    return {
        "passed": False,
        "title": "该游戏暂不支持赞助",
        "detail": SPONSORSHIP_REJECT_DETAIL,
        "basis": ["主游戏 Technologies 为空", "未查询到 Demo 或 Demo Technologies 为空"],
    }


def render_streamlit_activity_page() -> None:
    st.markdown(
        """
        <style>
          .stApp {
            background:
              radial-gradient(circle at 74% 14%, rgba(255, 168, 40, .18), transparent 34%),
              repeating-linear-gradient(135deg, rgba(255, 170, 36, .08) 0 1px, transparent 1px 13px),
              #070b12;
          }
          .block-container { max-width: 1120px; padding: 28px 24px 56px; }
          .stApp, .stApp * { text-rendering: geometricPrecision; }
          .hero-title,
          .stApp h1,
          div[data-testid="stMarkdownContainer"] h1 {
            text-align: center !important;
            color: #fff7e8 !important;
            -webkit-text-fill-color: #fff7e8 !important;
            text-shadow: 0 2px 16px rgba(255, 214, 138, .24), 0 1px 2px rgba(0, 0, 0, .72);
            font-size: 38px !important;
            font-weight: 900 !important;
            margin-bottom: 8px !important;
          }
          .hero-copy {
            text-align: center;
            color: #ffd36a !important;
            -webkit-text-fill-color: #ffd36a !important;
            text-shadow: 0 1px 2px rgba(0, 0, 0, .72);
            font-weight: 800;
            margin-bottom: 24px;
            font-size: 14px;
          }
          .step-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 18px; }
          .step-card {
            border: 1px solid rgba(255, 166, 39, .62);
            border-radius: 8px;
            padding: 18px 18px 20px;
            min-height: 92px;
            background: radial-gradient(circle at 92% 70%, rgba(255, 174, 45, .18), transparent 24%), rgba(12, 17, 27, .88);
            color: #fff;
          }
          .step-tag { display: inline-flex; padding: 6px 10px; border-radius: 6px; background: #ffad23; color: #171009; font-size: 12px; font-weight: 900; margin-bottom: 13px; }
          .step-title { font-size: 16px; font-weight: 900; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
          .result-shell {
            border: 1px solid rgba(255, 166, 39, .5);
            border-radius: 8px;
            background: #101a2b;
            padding: 28px;
            min-height: 286px;
            color: #eaf2ff;
          }
          .result-empty { min-height: 220px; display: grid; place-items: center; text-align: center; color: #a9bad8; }
          .result-empty h2 { margin: 0 0 8px; color: #fff; font-size: 22px; }
          .result-card { color: #e8eefc !important; }
          .result-icon {
            display: inline-grid;
            place-items: center;
            width: 52px;
            height: 52px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-weight: 900;
            font-size: 26px;
          }
          .result-icon.pass { color: #31d083; background: rgba(49, 208, 131, .14); }
          .result-icon.fail { color: #ff8585; background: rgba(255, 98, 98, .14); }
          .result-title.pass { color: #31d083; }
          .result-title.fail { color: #ff8585; }
          .game-card {
            border: 1px solid rgba(49, 208, 131, .58);
            border-radius: 8px;
            padding: 14px;
            margin: 10px 0 18px;
            background: rgba(17, 62, 65, .42);
            color: #eafff6;
          }
          .game-title { font-size: 17px; font-weight: 900; margin-bottom: 4px; color: #f8fbff !important; -webkit-text-fill-color: #f8fbff !important; }
          .muted { color: #c7d7f2 !important; -webkit-text-fill-color: #c7d7f2 !important; font-size: 13px; line-height: 1.55; }
          .statement { color: #c7d7f2 !important; -webkit-text-fill-color: #c7d7f2 !important; font-size: 12px; line-height: 1.65; margin: 16px 0 24px; }
          .lookup-status {
            border: 1px solid rgba(49, 208, 131, .58);
            border-radius: 8px;
            padding: 12px 14px;
            margin: 10px 0 18px;
            background: rgba(17, 62, 65, .42);
            color: #eafff6;
          }
          .lookup-error {
            border-color: rgba(255, 98, 98, .65);
            background: rgba(90, 28, 38, .36);
            color: #ffd7dc;
          }
          .history-panel {
            margin-top: 18px;
            border: 1px solid rgba(255, 166, 39, .38);
            border-radius: 8px;
            background: #101a2b;
            padding: 18px;
            color: #eaf2ff;
          }
          .history-empty { border: 1px dashed rgba(159, 176, 204, .32); border-radius: 8px; padding: 28px; text-align: center; color: #a9bad8; }
          div[data-testid="stForm"] {
            border: 1px solid rgba(255, 166, 39, .5);
            border-radius: 8px;
            background: linear-gradient(135deg, rgba(16, 27, 47, .98), rgba(10, 15, 25, .98));
            padding: 20px;
            min-height: 540px;
          }
          div[data-testid="InputInstructions"] { display: none !important; }
          label, .stMarkdown p { color: #eef5ff !important; -webkit-text-fill-color: #eef5ff !important; }
          .stTextArea textarea, .stTextInput input {
            background: #202a3b !important;
            color: #fff !important;
            border: 1px solid #3b4a63 !important;
            border-radius: 8px !important;
          }
          .stTextArea textarea::placeholder, .stTextInput input::placeholder { color: #9ba9bf !important; opacity: 1; }
          .stButton button, .stFormSubmitButton button {
            width: 100%;
            height: 48px;
            border: 0;
            border-radius: 8px;
            background: linear-gradient(90deg, #ffd36a, #ff9f1a);
            color: #171009;
            font-weight: 900;
          }
          .stButton button:disabled, .stFormSubmitButton button:disabled {
            background: #777b82;
            color: #151515;
          }
          .stAlert { border-radius: 8px; }
          .pay-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            min-height: 48px;
            margin-top: 24px;
            padding: 0 18px;
            border-radius: 8px;
            background: linear-gradient(90deg, #ffd36a, #ff9f1a);
            color: #171009 !important;
            font-weight: 900;
            text-decoration: none !important;
            box-shadow: 0 14px 28px rgba(255, 159, 26, .18);
          }
          .pay-action-wrap {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid rgba(159, 176, 204, .18);
          }
          @media (max-width: 860px) { .step-grid { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<h1 class="hero-title">AI免费评估</h1>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-copy">提交你的单机游戏修改器需求，AI 将实时评估是否允许被赞助优先开发。 评估通过并支付赞助费后，立即进入开发流程。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="step-grid">
          <div class="step-card"><div class="step-tag">第1步</div><div class="step-title">输入游戏链接，AI免费评估</div></div>
          <div class="step-card"><div class="step-tag">第2步</div><div class="step-title">AI评估通过，前往支付页面</div></div>
          <div class="step-card"><div class="step-tag">第3步</div><div class="step-title">完成支付，等待修改器上线</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    init_db()
    record_exposure_once()

    if "streamlit_eval_result" not in st.session_state:
        st.session_state.streamlit_eval_result = None
    if "streamlit_eval_history" not in st.session_state:
        st.session_state.streamlit_eval_history = []
    if "steam_lookup_appid" not in st.session_state:
        st.session_state.steam_lookup_appid = ""
    if "steam_lookup_result" not in st.session_state:
        st.session_state.steam_lookup_result = None
    if "steam_link_value" not in st.session_state:
        st.session_state.steam_link_value = ""

    left, right = st.columns([1.35, 1], gap="medium")
    with left:
        steam_link = st.text_area("提交游戏，输入Steam商店链接", placeholder="例如：https://store.steampowered.com/app/3167920/_/", height=92)
        if steam_link != st.session_state.steam_link_value:
            st.session_state.steam_link_value = steam_link
            st.session_state.streamlit_eval_result = None
        parsed_appid = parse_steam_appid(steam_link)
        lookup_result = None
        if steam_link.strip():
            if not parsed_appid:
                lookup_result = {"status": "error", "message": "未找到游戏"}
                st.session_state.steam_lookup_appid = ""
                st.session_state.steam_lookup_result = lookup_result
            elif st.session_state.steam_lookup_appid == parsed_appid and st.session_state.steam_lookup_result:
                lookup_result = st.session_state.steam_lookup_result
            else:
                with st.spinner(f"已识别 APP ID：{parsed_appid}，正在查询游戏信息..."):
                    try:
                        lookup_game = fetch_steamdb_game(parsed_appid)
                        lookup_name_zh = text_value(lookup_game.get("game_name_zh") or lookup_game.get("name_zh") or lookup_game.get("game_name_en") or f"Steam App {parsed_appid}")
                        lookup_name_en = text_value(lookup_game.get("game_name_en"))
                        lookup_result = {
                            "status": "ok",
                            "appid": parsed_appid,
                            "game": lookup_game,
                            "name_zh": lookup_name_zh,
                            "name_en": lookup_name_en,
                        }
                    except Exception:
                        lookup_result = {"status": "error", "appid": parsed_appid, "message": "查询无结果，请重新输入"}
                    st.session_state.steam_lookup_appid = parsed_appid
                    st.session_state.steam_lookup_result = lookup_result

        if lookup_result:
            if lookup_result.get("status") == "ok":
                st.markdown(
                    f"""
                    <div class="lookup-status">
                      <div class="game-title">{html.escape(lookup_result["name_zh"])}</div>
                      <div class="muted">{html.escape(lookup_result["name_en"])}</div>
                      <div class="muted">APP ID：{html.escape(lookup_result["appid"])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="lookup-status lookup-error">{html.escape(lookup_result["message"])}</div>',
                    unsafe_allow_html=True,
                )

        requirements = st.text_area("你需要的修改功能", placeholder="例如：\n无限生命\n编辑金钱\n一击必杀\n设置游戏速度等", max_chars=200, height=170)
        st.markdown(
            '<div class="statement">*声明：本“AI免费评估”仅针对游戏本体基础框架。您在此处提交的具体功能需求将作为技术团队研发参考，最终上线修改项以技术团队实际交付内容为准。本通道仅支持单机游戏、游戏单人模式，不支持内购数值、网络联机游戏。本活动最终解释权归 XMODhub 所有。</div>',
            unsafe_allow_html=True,
        )
        phone = st.text_input("请输入手机号", placeholder="请输入XMODhub注册手机号，以便第一时间发送上线通知", max_chars=11)
        submitted = st.button("一键评估")

    result_payload = st.session_state.streamlit_eval_result

    if submitted:
        add_activity_event("evaluate_click")
        appid = parsed_appid
        current_lookup = lookup_result or st.session_state.steam_lookup_result
        if not appid:
            result_payload = {"status": "error", "message": "未找到游戏"}
        elif not current_lookup or current_lookup.get("status") != "ok":
            result_payload = {"status": "error", "message": "查询无结果，请重新输入"}
        elif not requirements.strip():
            result_payload = {"status": "error", "message": "请填写修改需求。"}
        elif not re.fullmatch(r"1\d{10}", phone.strip()):
            result_payload = {"status": "error", "message": "请输入11位XMODhub注册手机号。"}
        elif daily_submission_count(phone.strip()) >= 20:
            result_payload = {"status": "error", "message": "网络繁忙，请稍后再试"}
        else:
            with st.spinner("正在评估，请稍候..."):
                try:
                    game = current_lookup["game"]
                    name_zh = current_lookup["name_zh"]
                    name_en = current_lookup["name_en"]
                    demo_game = fetch_demo_steamdb_game(game) if not text_value(game.get("technologies")) else None
                    demo_name_zh = text_value((demo_game or {}).get("game_name_zh"))
                    demo_name_en = text_value((demo_game or {}).get("game_name_en"))
                    xmod_status = fetch_xmod_status([name_zh, name_en, demo_name_zh, demo_name_en])
                    decision = evaluate_steamdb_game(game, xmod_status, demo_game)
                    save_game_query(game, xmod_status, decision)
                    overrides = manual_overrides_for_app(appid)
                    final_passed = overrides["manual_result"] == "通过" if overrides["manual_result"] != "自动" else bool(decision["passed"])
                    if final_passed != bool(decision["passed"]):
                        decision = {
                            **decision,
                            "passed": final_passed,
                            "title": "人工结果：通过" if final_passed else "人工结果：不通过",
                            "detail": PASS_DETAIL if final_passed else allowed_failure_detail(decision["detail"], SPONSORSHIP_REJECT_DETAIL),
                        }
                    if not final_passed and overrides["failure_detail"]:
                        decision = {
                            **decision,
                            "detail": overrides["failure_detail"],
                        }
                    if final_passed:
                        decision = {
                            **decision,
                            "detail": PASS_DETAIL,
                        }
                    record_id = save_evaluation_record({
                        "submitted_at": now_text(),
                        "store_url": steam_link.strip(),
                        "game_name_zh": name_zh,
                        "appid": appid,
                        "phone": phone.strip(),
                        "visitor_id": get_visitor_id(),
                        "requirements": requirements.strip(),
                        "result": "通过" if final_passed else "不通过",
                        "passed": final_passed,
                        "result_title": decision["title"],
                        "result_detail": decision["detail"],
                    })
                    result_payload = {
                        "status": "ok",
                        "record_id": record_id,
                        "appid": appid,
                        "game": game,
                        "xmod_status": xmod_status,
                        "name_zh": name_zh,
                        "name_en": name_en,
                        "decision": decision,
                    }
                    st.session_state.streamlit_eval_history.insert(0, {
                        "time": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M"),
                        "name": name_zh,
                        "appid": appid,
                        "result": "通过" if final_passed else "不通过",
                        "requirements": requirements.strip(),
                        "phone": phone.strip(),
                    })
                    st.session_state.streamlit_eval_history = st.session_state.streamlit_eval_history[:20]
                except Exception as error:
                    result_payload = {"status": "error", "message": f"未找到游戏：{error}"}
        st.session_state.streamlit_eval_result = result_payload

    with right:
        if not result_payload:
            st.markdown('<div class="result-shell"><div class="result-empty"><div><h2>评估结果</h2><p>完成左侧表单后，系统将在数秒内给出评估结果。</p></div></div></div>', unsafe_allow_html=True)
        elif result_payload.get("status") == "error":
            st.markdown(
                f'<div class="result-shell"><div class="result-card"><div class="result-icon fail">×</div><h2 class="result-title fail">{html.escape(result_payload["message"])}</h2></div></div>',
                unsafe_allow_html=True,
            )
        else:
            decision = result_payload["decision"]
            state_class = "pass" if decision["passed"] else "fail"
            icon = "✓" if decision["passed"] else "×"
            result_title = "评估通过" if decision["passed"] else "评估不通过"
            st.markdown(
                f"""
                <div class="result-shell">
                  <div class="result-card">
                    <div class="result-icon {state_class}">{icon}</div>
                    <h2 class="result-title {state_class}">{result_title}</h2>
                    <div class="game-card">
                      <div class="game-title">{html.escape(result_payload["name_zh"])}</div>
                      <div class="muted">Steam APP ID：{html.escape(result_payload["appid"])}</div>
                    </div>
                    <p class="muted">{html.escape(decision["detail"])}</p>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if decision["passed"]:
                st.markdown(
                    f"""
                    <div class="pay-action-wrap">
                      <a class="pay-link" href="{html.escape(PAYMENT_URL)}" target="_blank" rel="noopener noreferrer">
                        前往支付
                      </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                mark_payment_clicked(result_payload.get("record_id", ""))

    st.markdown('<div class="history-panel"><h3>评估记录</h3><p class="muted">记录当前浏览器的提交历史。</p>', unsafe_allow_html=True)
    if not st.session_state.streamlit_eval_history:
        st.markdown('<div class="history-empty">暂无评估记录，快来评估第一款游戏吧。</div>', unsafe_allow_html=True)
    else:
        for item in st.session_state.streamlit_eval_history:
            st.markdown(
                f'<div class="game-card"><div class="game-title">{html.escape(item["name"])}</div><div class="muted">Steam APP ID：{html.escape(item["appid"])} · 评估日期：{html.escape(item["time"])} · 是否通过：{html.escape(item["result"])}<br />修改需求：{html.escape(item.get("requirements", ""))}<br />手机号：{html.escape(item.get("phone", ""))}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def build_activity_page() -> str:
    html = read_text(H5_ROOT / "index.html")
    css = read_text(H5_ROOT / "styles.css")
    js = read_text(H5_ROOT / "app.js")

    api_base = configured_api_base()
    js = js.replace(
        'const DEPLOYED_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site";\n'
        'const API_BASE = window.location.protocol === "file:" ? DEPLOYED_API_BASE : window.location.origin;',
        f"const DEPLOYED_API_BASE = {json.dumps(api_base)};\n"
        "const API_BASE = DEPLOYED_API_BASE;",
    )

    guide_image = image_data_uri(H5_ROOT / "assets" / "steam-store-link-guide.png")
    html = html.replace("./assets/steam-store-link-guide.png", guide_image)
    html = html.replace('<link rel="stylesheet" href="./styles.css?v=20260805-pending-result" />', f"<style>{css}</style>")
    html = html.replace('<link rel="stylesheet" href="./styles.css?v=20260728-steps" />', f"<style>{css}</style>")
    html = html.replace('<link rel="stylesheet" href="./styles.css" />', f"<style>{css}</style>")
    html = html.replace('<script src="./app.js?v=20260805-pending-result"></script>', f"<script>{js}</script>")
    html = html.replace('<script src="./app.js?v=20260805-steam-link-feedback"></script>', f"<script>{js}</script>")
    html = html.replace('<script src="./app.js?v=20260804-steamdb-evaluation"></script>', f"<script>{js}</script>")
    html = html.replace('<script src="./app.js?v=20260721-payment-click"></script>', f"<script>{js}</script>")
    html = html.replace('<script src="./app.js"></script>', f"<script>{js}</script>")
    return html


def build_admin_page() -> str:
    html = read_text(ADMIN_ROOT / "index.html")
    api_base = configured_api_base()
    html = html.replace(
        'const DEPLOYED_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site";\n'
        '    const API_BASE = window.location.protocol === "file:" ? DEPLOYED_API_BASE : window.location.origin;',
        f"const DEPLOYED_API_BASE = {json.dumps(api_base)};\n"
        "    const API_BASE = DEPLOYED_API_BASE;",
    )
    html = html.replace(
        "API: 当前站点后端",
        f"API: {api_base.replace('https://', '').replace('http://', '')}",
    )
    return html


def render_streamlit_admin_page() -> None:
    init_db()
    st.markdown(
        """
        <style>
          .stApp { background: #f6f7fb !important; color: #101828 !important; }
          .block-container { max-width: 1460px; padding: 44px 36px 64px; }
          h1, h2, h3, label, p, span, div[data-testid="stMarkdownContainer"] {
            color: #101828 !important;
          }
          button[role="tab"] p, button[role="tab"] span {
            color: #344054 !important;
            font-weight: 800;
          }
          button[role="tab"][aria-selected="true"] p, button[role="tab"][aria-selected="true"] span {
            color: #2563eb !important;
          }
          .stTextInput input, .stDateInput input {
            background: #ffffff !important;
            color: #101828 !important;
            border: 1px solid #d0d5dd !important;
          }
          .admin-table-wrap {
            width: 100%;
            overflow-x: auto;
            border: 1px solid #d0d5dd;
            border-radius: 8px;
            background: #ffffff;
            box-shadow: 0 10px 24px rgba(16, 24, 40, .06);
            margin-top: 14px;
          }
          .admin-table {
            width: 100%;
            border-collapse: collapse;
            min-width: 1080px;
            color: #101828;
            font-size: 13px;
          }
          .admin-table th {
            position: sticky;
            top: 0;
            z-index: 1;
            background: #f2f4f7;
            color: #475467;
            text-align: left;
            font-weight: 800;
            padding: 11px 12px;
            border-bottom: 1px solid #d0d5dd;
            white-space: nowrap;
          }
          .admin-table td {
            padding: 12px;
            border-bottom: 1px solid #eaecf0;
            vertical-align: top;
            color: #101828;
            background: #ffffff;
            max-width: 280px;
            white-space: normal;
            word-break: break-word;
          }
          .admin-table tr:nth-child(even) td {
            background: #fbfcfe;
          }
          .admin-empty {
            margin-top: 14px;
            border: 1px dashed #d0d5dd;
            border-radius: 8px;
            background: #ffffff;
            color: #667085 !important;
            padding: 28px;
            text-align: center;
          }
          .stButton button {
            border-radius: 8px;
            border: 1px solid #d0d5dd;
            background: #ffffff;
            color: #101828;
          }
          .stButton button[kind="primary"], .stDownloadButton button {
            background: #2563eb !important;
            color: #ffffff !important;
            border-color: #2563eb !important;
          }
          .metric-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; background: #fff; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    title_col, logout_col = st.columns([1, 0.16])
    title_col.title("AI 免费评估记录后台")
    if logout_col.button("退出登录"):
        st.session_state.admin_authenticated = False
        st.rerun()
    tab_records, tab_stats, tab_activity, tab_assets = st.tabs(["评估记录", "数据统计", "活动页统计", "评估后台"])

    with tab_records:
        c1, c2, c3 = st.columns(3)
        phone_kw = c1.text_input("搜索手机号", key="admin_phone")
        game_kw = c2.text_input("搜索游戏中文名", key="admin_game")
        appid_kw = c3.text_input("搜索 Steam APP ID", key="admin_appid")
        where = []
        params: list[str] = []
        if phone_kw.strip():
            where.append("phone LIKE ?")
            params.append(f"%{phone_kw.strip()}%")
        if game_kw.strip():
            where.append("game_name_zh LIKE ?")
            params.append(f"%{game_kw.strip()}%")
        if appid_kw.strip():
            where.append("appid LIKE ?")
            params.append(f"%{appid_kw.strip()}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = db_rows(
            f"""
            SELECT submitted_at AS 提交日期时间, store_url AS 商店链接, game_name_zh AS 游戏中文名,
                   appid AS "Steam APP ID", phone AS 手机号, visitor_id AS "Visitor ID",
                   requirements AS 修改需求, result AS 评估结果,
                   CASE WHEN payment_clicked = 1 THEN '是' ELSE '否' END AS 是否点击支付,
                   payment_clicked_at AS 支付点击时间
            FROM evaluation_records {where_sql}
            ORDER BY submitted_at DESC
            """,
            tuple(params),
        )
        render_admin_table(rows, "暂无评估记录")

    with tab_stats:
        rows = db_rows(
            """
            SELECT game_name_zh AS 游戏中文名,
                   appid AS "Steam APP ID",
                   COUNT(*) AS 评估总次数,
                   SUM(CASE WHEN passed = 1 AND payment_clicked = 1 THEN 1 ELSE 0 END) AS 评估通过并点击支付的次数,
                   printf('%.2f%%', 100.0 * SUM(CASE WHEN passed = 1 AND payment_clicked = 1 THEN 1 ELSE 0 END) / COUNT(*)) AS 点击支付率
            FROM evaluation_records
            GROUP BY appid, game_name_zh
            ORDER BY 评估总次数 DESC
            """
        )
        render_admin_table(rows, "暂无统计数据")

    with tab_activity:
        rows = db_rows(
            """
            WITH dates AS (
              SELECT event_date AS day FROM activity_events
              UNION
              SELECT substr(submitted_at, 1, 10) AS day FROM evaluation_records
            )
            SELECT dates.day AS 日期,
                   (SELECT COUNT(*) FROM activity_events e WHERE e.event_date = dates.day AND e.event_type = 'exposure') AS 活动页曝光次数,
                   (SELECT COUNT(DISTINCT visitor_id) FROM activity_events e WHERE e.event_date = dates.day AND e.event_type = 'exposure') AS 活动页曝光人数,
                   (SELECT COUNT(*) FROM activity_events e WHERE e.event_date = dates.day AND e.event_type = 'evaluate_click') AS 点击评估次数,
                   (SELECT COUNT(DISTINCT visitor_id) FROM activity_events e WHERE e.event_date = dates.day AND e.event_type = 'evaluate_click') AS 点击评估人数,
                   (SELECT COUNT(*) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1) AS 点击评估中通过的次数,
                   (SELECT COUNT(DISTINCT visitor_id) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1) AS 点击评估中通过的人数,
                   (SELECT COUNT(*) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1 AND r.payment_clicked = 1) AS 点击评估并通过并点击支付的次数,
                   (SELECT COUNT(DISTINCT visitor_id) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1 AND r.payment_clicked = 1) AS 点击评估并通过并点击支付的人数,
                   CASE
                     WHEN (SELECT COUNT(DISTINCT visitor_id) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1) = 0 THEN '0.00%'
                     ELSE printf('%.2f%%',
                       100.0 * (SELECT COUNT(DISTINCT visitor_id) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1 AND r.payment_clicked = 1)
                       / (SELECT COUNT(DISTINCT visitor_id) FROM evaluation_records r WHERE substr(r.submitted_at, 1, 10) = dates.day AND r.passed = 1)
                     )
                   END AS 支付点击率
            FROM dates
            ORDER BY dates.day DESC
            """
        )
        render_admin_table(rows, "暂无活动页统计数据")

    with tab_assets:
        rows = db_rows(
            """
            SELECT evaluation_result AS 评估结果,
                   manual_result AS 人工结果,
                   failure_detail AS 不通过文案,
                   game_name_zh AS 游戏中文名,
                   appid AS "APP ID",
                   client_status AS 客户端状态,
                   client_development_status AS 客户端开发状态,
                   app_type AS "APP TYPE",
                   technologies AS Technologies,
                   release_date AS "Release Date",
                   categories AS categories,
                   tag AS Tag,
                   updated_at AS 更新时间,
                   note AS 备注,
                   basis AS 判断依据
            FROM game_queries
            ORDER BY updated_at DESC
            """
        )
        for row in rows:
            row["不通过文案"] = allowed_failure_detail(row.get("不通过文案"))
        edited = st.data_editor(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "人工结果": st.column_config.SelectboxColumn("人工结果", options=["自动", "通过", "不通过"]),
                "不通过文案": st.column_config.SelectboxColumn("不通过文案", options=[""] + FAILURE_DETAIL_OPTIONS),
                "备注": st.column_config.TextColumn("备注"),
            },
            disabled=[col for col in (rows[0].keys() if rows else []) if col not in {"人工结果", "不通过文案", "备注"}],
            key="asset_editor",
        )
        if st.button("保存人工结果/不通过文案/备注"):
            init_db()
            with db_connect() as conn:
                for row in editor_records(edited):
                    conn.execute(
                        "UPDATE game_queries SET manual_result = ?, failure_detail = ?, note = ?, updated_at = ? WHERE appid = ?",
                        (
                            text_value(row.get("人工结果")) or "自动",
                            allowed_failure_detail(row.get("不通过文案")),
                            text_value(row.get("备注")),
                            now_text(),
                            text_value(row.get("APP ID")),
                        ),
                    )
            st.success("已保存")


def is_admin_view() -> bool:
    try:
        value = st.query_params.get("admin", "")
    except Exception:
        value = ""
    return str(value).lower() in {"1", "true", "yes"}


def is_embedded_h5_view() -> bool:
    try:
        value = st.query_params.get("h5", "")
    except Exception:
        value = ""
    return str(value).lower() in {"1", "true", "yes"}


def handle_payment_redirect() -> None:
    try:
        record_id = text_value(st.query_params.get("pay_click", ""))
        should_redirect = str(st.query_params.get("redirect", "")).lower() in {"1", "true", "yes"}
    except Exception:
        record_id = ""
        should_redirect = False
    if not record_id:
        return
    mark_payment_clicked(record_id)
    if should_redirect:
        st.markdown(
            """
            <style>
              #MainMenu, header, footer { display: none !important; }
              .stApp { background: #090f19; color: #eaf2ff; }
              .block-container { max-width: 720px; padding: 64px 24px; }
            </style>
            <h2>正在前往支付页面...</h2>
            """,
            unsafe_allow_html=True,
        )
        components.html(
            f"""
            <script>
              window.open({json.dumps(PAYMENT_URL)}, "_self");
            </script>
            """,
            height=0,
        )
        st.stop()


def main() -> None:
    admin_view = is_admin_view()
    st.set_page_config(
        page_title="AI 免费评估记录后台" if admin_view else "XMODhub AI免费评估",
        page_icon="X",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    handle_payment_redirect()

    background = "#f6f7fb" if admin_view else "#090f19"
    st.markdown(
        f"""
        <style>
          #MainMenu, header, footer {{ display: none !important; }}
          .stApp {{ background: {background}; }}
          .block-container {{
            max-width: none;
            padding: 0;
          }}
          iframe {{
            display: block;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    if admin_view:
        require_admin_login()
        render_streamlit_admin_page()
    elif is_embedded_h5_view():
        components.html(build_activity_page(), height=1450, scrolling=True)
    else:
        render_streamlit_activity_page()


if __name__ == "__main__":
    main()
