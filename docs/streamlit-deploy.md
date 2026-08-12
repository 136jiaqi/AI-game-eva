# Streamlit 临时部署说明

## 入口

Streamlit 入口文件是项目根目录的 `streamlit_app.py`。

- 默认展示用户侧 AI 免费评估页。
- 访问时带 `?admin=1` 可展示后台页。
- `pages/admin.py` 也保留为 Streamlit 多页面后台入口。

## 必填配置

不要把密钥写入代码或提交到 GitHub。请在 Streamlit Secrets 或部署环境变量中配置：

```toml
XMODHUB_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
```

如果同一个部署环境也承载后端 Worker，请额外配置：

```toml
STEAMDB_API_URL = "http://47.79.16.6:8080/api/v1/games/search"
STEAMDB_API_KEY = "后端提供的 X-API-Key"
XMOD_STATUS_API_URL = "https://gtabff.xmodhub.cn/api/game_tool_admin_bff/v1/xmod_resource/games"
XMOD_LOGIN_CREDENTIAL = "后端提供的 login-credential"
```

## 本地运行

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

本地如需指定 API：

```powershell
$env:XMODHUB_API_BASE="https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
streamlit run streamlit_app.py
```
