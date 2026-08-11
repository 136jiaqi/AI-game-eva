from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).parent
H5_ROOT = ROOT / "public" / "h5"
ADMIN_ROOT = ROOT / "public" / "admin"
DEFAULT_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
DEFAULT_STEAMDB_API_URL = "http://47.79.16.6:8080/api/v1/games/search"
DEFAULT_XMOD_STATUS_API_URL = "https://gtabff.xmodhub.cn/api/game_tool_admin_bff/v1/xmod_resource/games"

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


def fetch_xmod_status(game_names: list[str]) -> dict:
    names = []
    for name in game_names:
        normalized = text_value(name)
        if normalized and normalized not in names:
            names.append(normalized)
    if not names:
        return {"matched": False, "client_development_status": "查询中", "client_status": "查询中", "reason": "Missing game name"}
    first_result: dict | None = None
    for name in names:
        result = fetch_xmod_status_once(name)
        if first_result is None:
            first_result = result
        if result.get("matched"):
            return result
    return first_result or {"matched": False, "client_development_status": "查询中", "client_status": "查询中"}


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


def evaluate_steamdb_game(game: dict, xmod_status: dict | None = None) -> dict:
    xmod_status = xmod_status or {"client_status": "查询中", "client_development_status": "查询中"}
    client_status = text_value(xmod_status.get("client_status")) or "查询中"
    development_status = text_value(xmod_status.get("client_development_status")) or "查询中"
    categories = text_value(game.get("categories"))
    technologies = text_value(game.get("technologies"))
    release_date = text_value(game.get("release_date") or game.get("Release Date"))

    if client_status == "生效中" and development_status == "已上线":
        return {
            "passed": False,
            "title": "该游戏修改器已上线",
            "detail": "抱歉，这款游戏的修改器已经在 XMODhub 客户端上线，无需参与优先开发赞助。如您希望增加更多修改功能，或当前修改器存在失效、未更新等问题，请前往 XMODhub 客户端－该游戏详情页－催更 提交反馈。",
            "basis": ["客户端状态 = 生效中", "客户端开发状态 = 已上线"],
        }
    if client_status == "生效中" and development_status == "未开发":
        return {
            "passed": False,
            "title": "该游戏暂不支持优先开发",
            "detail": "经 XMODhub 技术评估，该游戏可能涉及技术限制、强联网、多人联机或其他无法稳定支持的情况，因此暂不支持开发修改器。 后续如游戏技术条件发生变化，XMODhub 将重新评估其开发可行性。",
            "basis": ["客户端状态 = 生效中", "客户端开发状态 = 未开发"],
        }
    if client_status == "已下线":
        return {
            "passed": False,
            "title": "该游戏当前已停止支持",
            "detail": "我们暂不支持该游戏。可能与游戏技术条件、服务调整、合规风险或其他原因有关。",
            "basis": ["客户端状态 = 已下线"],
        }

    sponsorship_detail = "经评估，该游戏暂时无法被赞助。别气馁！建议您前往 XMODhub客户端为该游戏投上宝贵的一票。当投票热度达到标准后，我们的运营团队会再次介入人工专项评估！"
    if not contains_token(categories, "Single-player"):
        return {"passed": False, "title": "该游戏暂不支持赞助", "detail": sponsorship_detail, "basis": [f"categories 不包含 Single-player：{categories or '-'}"]}
    for blocked in ["MMO", "In-App Purchases", "Adult Only"]:
        if contains_token(categories, blocked):
            return {"passed": False, "title": "该游戏暂不支持赞助", "detail": sponsorship_detail, "basis": ["categories 包含 Single-player", f"categories 包含 {blocked}"]}
    if technologies and not contains_token(technologies, "Unity"):
        return {"passed": False, "title": "该游戏暂不支持赞助", "detail": sponsorship_detail, "basis": [f"Technologies = {technologies}", "能够查询到引擎且不包含 Unity"]}

    accurate, future_more_than_five_days, release_reason = parse_release_date(release_date)
    if not accurate or future_more_than_five_days:
        return {
            "passed": False,
            "title": "该游戏还未正式发售",
            "detail": "经评估，该游戏在Steam商店还没正式发售，因此暂不支持直接参与赞助。请在游戏正式上线后重新提交评估。您可以前往 XMODhub 客户端为该游戏投票。XMODhub 将根据投票数量、游戏热度及技术可行性评估后续开发安排。",
            "basis": [release_reason or f"发行日期 {release_date} 距查询日期超过 5 天"],
        }

    return {
        "passed": True,
        "title": "AI评估通过",
        "detail": "经评估，该游戏符合优先开发赞助条件。完成支付后，XMODhub 将根据需求复杂度安排技术评估和开发排期。",
        "basis": [
            "未命中已上线、未开发、已下线等客户端状态拦截规则",
            f"categories 包含 Single-player：{categories}",
            technologies and f"Technologies 包含 Unity：{technologies}" or "未查询到引擎，不按引擎拦截",
            f"发行日期已通过校验：{release_date}",
        ],
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
          h1 { text-align: center; color: #fff6e6; font-size: 38px !important; margin-bottom: 8px !important; }
          .hero-copy { text-align: center; color: #f6d184; font-weight: 700; margin-bottom: 24px; font-size: 14px; }
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
          .step-title { font-size: 16px; font-weight: 900; }
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
          .result-card { color: #e8eefc; }
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
          .game-title { font-size: 17px; font-weight: 900; margin-bottom: 4px; }
          .muted { color: #9fb0cc; font-size: 13px; line-height: 1.55; }
          .statement { color: #a9bad8; font-size: 12px; line-height: 1.65; margin: 16px 0 24px; }
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
          label, .stMarkdown p { color: #dbe8ff !important; }
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
          @media (max-width: 860px) { .step-grid { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<h1>AI免费评估</h1>", unsafe_allow_html=True)
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
        else:
            with st.spinner("正在评估，请稍候..."):
                try:
                    game = current_lookup["game"]
                    name_zh = current_lookup["name_zh"]
                    name_en = current_lookup["name_en"]
                    xmod_status = fetch_xmod_status([name_zh, name_en])
                    decision = evaluate_steamdb_game(game, xmod_status)
                    result_payload = {
                        "status": "ok",
                        "appid": appid,
                        "game": game,
                        "xmod_status": xmod_status,
                        "name_zh": name_zh,
                        "name_en": name_en,
                        "decision": decision,
                    }
                    st.session_state.streamlit_eval_history.insert(0, {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "name": name_zh,
                        "appid": appid,
                        "result": "通过" if decision["passed"] else "未通过",
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
            game = result_payload["game"]
            xmod_status = result_payload.get("xmod_status") or {}
            state_class = "pass" if decision["passed"] else "fail"
            icon = "✓" if decision["passed"] else "×"
            st.markdown(
                f"""
                <div class="result-shell">
                  <div class="result-card">
                    <div class="result-icon {state_class}">{icon}</div>
                    <h2 class="result-title {state_class}">{html.escape(decision["title"])}</h2>
                    <div class="game-card">
                      <div class="game-title">{html.escape(result_payload["name_zh"])}</div>
                      <div class="muted">{html.escape(result_payload["name_en"])}</div>
                      <div class="muted">APP ID：{html.escape(result_payload["appid"])}</div>
                    </div>
                    <p class="muted">{html.escape(decision["detail"])}</p>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("接口返回字段"):
                st.json({
                    "app_id": result_payload["appid"],
                    "game_name_en": result_payload["name_en"],
                    "game_name_zh": result_payload["name_zh"],
                    "客户端状态": text_value(xmod_status.get("client_status")),
                    "客户端开发状态": text_value(xmod_status.get("client_development_status")),
                    "XMOD匹配游戏": text_value(xmod_status.get("xmod_title_cn") or xmod_status.get("xmod_title")),
                    "App Type": text_value(game.get("app_type")),
                    "Technologies": text_value(game.get("technologies")),
                    "Release Date": text_value(game.get("release_date")),
                    "categories": text_value(game.get("categories")),
                    "Tag": text_value(game.get("tag")),
                    "screenshots": text_value(game.get("screenshots")),
                })
            with st.expander("判断依据"):
                for item in decision["basis"]:
                    st.write(f"- {item}")

    st.markdown('<div class="history-panel"><h3>评估记录</h3><p class="muted">记录当前浏览器的提交历史。</p>', unsafe_allow_html=True)
    if not st.session_state.streamlit_eval_history:
        st.markdown('<div class="history-empty">暂无评估记录，快来评估第一款游戏吧。</div>', unsafe_allow_html=True)
    else:
        for item in st.session_state.streamlit_eval_history:
            st.markdown(
                f'<div class="game-card"><div class="game-title">{html.escape(item["name"])}</div><div class="muted">{html.escape(item["time"])} · APP ID：{html.escape(item["appid"])} · {html.escape(item["result"])}</div></div>',
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


def main() -> None:
    admin_view = is_admin_view()
    st.set_page_config(
        page_title="AI 免费评估记录后台" if admin_view else "XMODhub AI免费评估",
        page_icon="X",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

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
        components.html(build_admin_page(), height=1600, scrolling=True)
    elif is_embedded_h5_view():
        components.html(build_activity_page(), height=1450, scrolling=True)
    else:
        render_streamlit_activity_page()


if __name__ == "__main__":
    main()
