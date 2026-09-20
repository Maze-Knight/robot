# 雀魂本地数据服务（第一阶段）

这是供艾琳娜未来使用的本地数据边界，不是抓取器，也不会访问雀魂、牌谱屋或任何第三方网站。

## 启动

在完整仓库中运行：

```powershell
.\scripts\start_majsoul_data_service.ps1
```

默认只监听 `127.0.0.1:8787`，不会随 `ElenaBot.exe` 或 `ElenaManager.exe` 自动启动。

## 本地 API

```text
GET http://127.0.0.1:8787/health
GET http://127.0.0.1:8787/v1/players/{amae_player_id}
GET http://127.0.0.1:8787/v1/players/{amae_player_id}/profile?mode=four
GET http://127.0.0.1:8787/v1/players/{amae_player_id}/profile?mode=three
```

初始 Provider 是 `EmptyProvider`：它不产生任何网络请求，也不写入玩家数据。未同步玩家统一返回 HTTP 404 和 `not_synced`，绝不伪造段位、统计或牌谱。

SQLite 文件默认为 `data/majsoul_data_service.sqlite3`，已被 Git 忽略。表包括 `players`、`player_profiles`、`game_records` 与 `sync_jobs`；每条资料或牌谱记录预留来源、同步时间、模式和原始记录标识。

## 机器人设置

`.env.example` 提供：

```dotenv
MAJSOUL_DATA_MODE=public
MAJSOUL_DATA_API_BASE_URL=http://127.0.0.1:8787
```

第一阶段机器人仍保持 `public`，不会读取此服务。改为 `self_hosted` 或接入任何同步 Provider 前，必须先明确确认数据来源的授权范围、访问频率、数据保留期限和用户告知方式。
