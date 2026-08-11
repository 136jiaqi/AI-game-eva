# XMODhub AI 评估系统交接记录

更新时间：2026-08-05

## 当前页面对应关系

- 用户看的 AI 免费评估页面：`/h5/index.html`
- 后台统一页面：`/backend/index.html`
- 备用后台页面：`/admin/index.html`
- 本地后台文件：`C:\Users\13648\Documents\定制开发评估系统\frontend\index.html`

## 当前线上域名

```text
https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site
```

用户页：

```text
https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site/h5/index.html
```

后台页：

```text
https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site/backend/index.html
```

## 已打包代码

```text
C:\Users\13648\Documents\定制开发评估系统\xmodhub-ai-evaluation-site\xmodhub-ai-evaluation-full-stack-clean-20260804-184552.zip
```

该包包含前端、后端 Worker、数据库 schema/migration、Streamlit 入口，不包含 `node_modules`、构建产物、历史部署包、`.env` 或 SteamDB 密钥。

## Streamlit 变量

如果 Streamlit 只是临时展示前端页面，并继续调用当前线上后端，只需要：

```toml
XMODHUB_API_BASE = "https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
```

含义：告诉 Streamlit 页面里的前端代码去请求哪个后端 API。

## 后端 Worker 变量

如果你把后端 Worker 也一起部署到新环境，需要配置：

```toml
STEAMDB_API_URL = "http://47.79.16.6:8080/api/v1/games/search"
STEAMDB_API_KEY = "后端提供的 X-API-Key"
XMOD_LOGIN_CREDENTIAL = "XMOD 客户端接口登录凭证"
```

可选变量：

```toml
STEAM_CC = "cn"
STEAM_LANGUAGE = "schinese"
```

说明：

- `STEAMDB_API_URL`：SteamDB 查询接口基础地址，不带 `app_id` 参数。
- `STEAMDB_API_KEY`：调用 SteamDB 接口的 `X-API-Key`，不要提交到 GitHub。
- `XMOD_LOGIN_CREDENTIAL`：查询 XMOD 客户端游戏状态使用。缺少时，客户端状态/客户端开发状态无法准确参与规则判断。
- `STEAM_CC`、`STEAM_LANGUAGE`：Steam 商店接口区域和语言，缺省分别是 `cn`、`schinese`。

## 数据库

当前项目使用 Cloudflare D1 绑定：

```text
DB
```

数据库迁移文件在：

```text
drizzle/
```

最新迁移：

```text
drizzle/0004_loving_albert_cleary.sql
```

## 重启后恢复

进入项目目录：

```powershell
cd "C:\Users\13648\Documents\定制开发评估系统\xmodhub-ai-evaluation-site\xmodhub-ai-evaluation-site"
```

本地 Streamlit 测试：

```powershell
pip install -r requirements.txt
$env:XMODHUB_API_BASE="https://xmodhub-ai-evaluation.lijiaqi13648060.chatgpt.site"
streamlit run streamlit_app.py
```

本地前端后台文件：

```text
C:\Users\13648\Documents\定制开发评估系统\frontend\index.html
```
