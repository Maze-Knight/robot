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
GET http://127.0.0.1:8787/v1/players/search?nickname=玩家名
GET http://127.0.0.1:8787/v1/players/{amae_player_id}/records?mode=four
```

初始 Provider 是 `EmptyProvider`：它不产生任何网络请求，也不写入玩家数据。未同步玩家统一返回 HTTP 404 和 `not_synced`，绝不伪造段位、统计或牌谱。

SQLite 文件默认为 `data/majsoul_data_service.sqlite3`，已被 Git 忽略。表包括 `players`、`player_profiles`、`game_records` 与 `sync_jobs`；每条资料或牌谱记录预留来源、同步时间、模式和原始记录标识。

## 导入合法数据

服务不会爬取或同步任何第三方。只有在你已确认数据来源和用户授权后，才能导入明确提供的 JSON 文件：

```powershell
.\scripts\import_majsoul_data.ps1 -Path .\合法来源的数据.json
```

导入根对象需要 `players` 数组；每名玩家包含 `amae_player_id`、`nickname`、`profiles`（`mode` 为 `four` 或 `three`）以及可选的 `game_records`。重复导入同一 `source + source_record_id` 会更新已有记录，不会伪造或重复战绩。用以下命令停止独立服务：

```powershell
.\scripts\stop_majsoul_data_service.ps1
```

## 机器人设置

`.env.example` 提供：

```dotenv
MAJSOUL_DATA_MODE=public
MAJSOUL_DATA_API_BASE_URL=http://127.0.0.1:8787
```

默认机器人仍保持 `public`。设为 `self_hosted` 时只会访问本机 API，健康检查失败也绝不回退访问牌谱屋。切换前必须确认：本地 `/health` 正常、至少一个合法来源玩家的档案可查询，以及数据来源的授权范围、数据保留期限和用户告知方式。
