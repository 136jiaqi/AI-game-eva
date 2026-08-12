from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "public" / "admin" / "index.html"
DEFAULT_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"


def configured_api_base() -> str:
    secret_value = ""
    try:
        secret_value = st.secrets.get("XMODHUB_API_BASE", "")
    except Exception:
        secret_value = ""
    return (os.getenv("XMODHUB_API_BASE") or secret_value or DEFAULT_API_BASE).rstrip("/")


def build_admin_page() -> str:
    html = ADMIN_HTML.read_text(encoding="utf-8")
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


def main() -> None:
    st.set_page_config(
        page_title="AI 免费评估记录后台",
        page_icon="X",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
          #MainMenu, header, footer, [data-testid="stSidebar"] { display: none !important; }
          .stApp { background: #f6f7fb; }
          .block-container {
            max-width: none;
            padding: 0;
          }
          iframe {
            display: block;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    components.html(build_admin_page(), height=1600, scrolling=True)


if __name__ == "__main__":
    main()
