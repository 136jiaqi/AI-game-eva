# SteamDB 接口环境变量

后端通过服务器端环境变量调用 SteamDB 查询接口，前端页面不直接调用该接口。

需要配置：

```text
STEAMDB_API_URL=http://47.79.16.6:8080/api/v1/games/search
STEAMDB_API_KEY=<由后端提供的 X-API-Key>
```

请求方式：

```text
GET ${STEAMDB_API_URL}?app_id=<Steam AppID>
X-API-Key: ${STEAMDB_API_KEY}
```

不要把 `STEAMDB_API_KEY` 写入前端代码或提交到仓库。
