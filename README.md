# 艾琳娜：QQ 官方机器人最小测试项目

本项目只验证 QQ 官方机器人的最小链路：

`QQ 群/C2C 消息 -> 统一 MessageContext -> handle_message(context) -> 被动回复`

收到 `测试` 或 `ping` 后回复：

```text
艾琳娜收到啦！
```

## 艾琳娜市政终端 v1.0

发送 `菜单`、`/菜单`、`/menu` 或 `/help` 打开“🍹 莫纳提姆市政终端”。群聊需要先 @艾琳娜，C2C 可直接发送。

### QQ 原生指令面板

程序启动后会通过 QQ OpenAPI 同步两个由本项目管理的“指令面板”（群聊与 C2C 各一个），让 QQ 客户端可以从原生指令入口发现高频功能。该能力由 QQ 官方称为“指令面板”，并非机器人发送的 Markdown 菜单。

```text
菜单       打开莫纳提姆市政终端
蜡笔板     进入个人蜡笔板
蜡笔进度   查看当前节点进度
礼包查询   查询礼包性价比
帮助       查看终端使用说明
```

QQ 的指令面板 API 会自动去掉名称中的 `/`，而呈现和填入方式由 QQ 客户端决定；机器人同时兼容带 `/` 与不带 `/` 的入口。它们只复用现有处理逻辑：菜单走主菜单，蜡笔板与蜡笔进度走蜡笔板模块，礼包查询走礼包查询，帮助走使用说明。同步会查询再创建或更新，不会每次启动重复添加；非本项目或重复的面板一律保留并记录警告，不会自动删除。

普通用户主菜单固定为两行四个真实 InlineKeyboard 按钮：

```text
[📟 市政服务] [🧪 实验项目]
[📢 公告记录] [📖 使用说明]
```

菜单最大深度为主菜单到二级菜单。Steam 监测站、礼包性价比查询、每日单抽和使徒图鉴已经接入；实验功能仍是占位回复。角色文案集中在各模块的 `copywriting.py`；菜单页面、键盘和 Interaction 路由分别位于 `ui/menus.py`、`ui/keyboards.py`、`ui/interactions.py`。

当前不包含 NoneBot2、AI 或其他未迁移业务插件。

### 每日单抽

发送 `/每日单抽` 会立即执行当天单抽，不经过确认页面；`/抽取记录` 可重新查看当天结果：

```text
/每日单抽
/抽取记录
```

当前规则固定为：每个 QQ 官方身份每天一次单抽；所有使徒属于同一个抽取级别，从完整名单中等概率独立选择，不设稀有度和保底。日期按北京时间计算，结果保存在 `data/daily_draw.sqlite3`，并通过数据库唯一约束避免并发重复抽取。

抽取名单取自 [Crayon Note 自订角色清单](https://crayon-note.vercel.app/checklist.html)。当前同步到 78 名使徒；头像由该页面实际使用的五张人物雪碧图按其 CSS 坐标裁切。单抽结果会生成只显示该名使徒头像和名称的图片卡片。

清单保存在 `daily_draw_pool.json`，头像位于 `daily_draw_assets/`。需要重新同步源站后可运行 `python scripts/sync_crayon_note_daily_draw.py`，构建 EXE 时头像会打包进程序，部署目录中的奖池 JSON 仍用于控制启用名单。

此次切换使用新的 `pool_id`。程序首次加载单抽奖池时会在一个事务内清空旧十连产生的每日次数、抽取记录和图鉴进度；不会保留或转换旧用户数据。

### 使徒图鉴

发送 `/图鉴` 可打开“@用户 的圣团”。图鉴包含当前清单中的全部 78 名使徒：未抽到的项目显示为锁定，已抽到的项目显示头像、名称和当前升星等级，同时显示收集数量与收集率。

每名使徒第一次获得时以 1★ 解锁；此后每重复获得一次，培养等级增加一星。这里的星数只表示累计抽到次数，不代表稀有度。抽取记录、图鉴数量和升星在同一个 SQLite 事务中提交。

### 🖍️ 嘟嘟脸蜡笔板

入口为“莫纳提姆市政终端 → 市政服务 → 🖍️ 蜡笔板”。默认 `TRICKCAL_MODE=remote`：机器人只将 QQ 官方身份原样交给礼包网站的 HTTPS Bot API，取得网页登录入口或个人摘要；网页、鉴权、票据、资料与数据库均由网站负责。

```dotenv
TRICKCAL_MODE=remote
TRICKCAL_API_BASE_URL=https://gift.example.com
TRICKCAL_BOT_API_KEY=请填写强随机服务密钥
```

群聊传 `member_openid + group`，C2C 传 `openid + c2c`，机器人不会猜测它们是否是同一身份。API 返回的入口必须为 HTTPS 且域名与配置域名一致，避免异常响应跳转到不可信网站。缺少远程配置时 QQ Gateway 仍会启动，蜡笔板仅提示尚未接入。

旧的本地 Web/SQLite 实现保留为 `TRICKCAL_MODE=local` 的开发与回滚路径，默认不启动 `127.0.0.1:8080`。其旧配置为 **LEGACY ONLY**，来源审计与许可证边界记录见 [NOTICE_TRICKCAL.md](NOTICE_TRICKCAL.md)。

## 技术选择（调研日期：2026-09-11）

采用：

- 腾讯官方 `tencent-connect/qqbot-agent-sdk`，固定版本 `1.2.2`
- WebSocket Gateway 接收事件
- OpenAPI v2 发送回复
- AppID + AppSecret 换取 Access Token
- Python 3.11（SDK 要求 Python >= 3.10）

选择原因：

1. 腾讯当前官方文档同时描述 Webhook 与 WebSocket；WebSocket 无需公网 HTTPS 回调地址，最适合先完成本地最小收发闭环。
2. 腾讯官方新 Python 仓库 `qqbot-agent-sdk` 明确实现 WebSocket Gateway + OpenAPI v2，并包含 Token 自动管理、心跳、断线自动重连、会话 Resume、C2C/群/频道发送和统一事件解析。
3. 老 `qq-botpy` 仍被官方“启动接入”页列为 Python SDK Demo，并非完全不可用；但新 SDK 更贴近本项目后续做协议适配层、再接 NoneBot2 的目标。
4. 不选 Webhook 作为第一阶段接入方式，是因为 Webhook 需要平台可访问的公网 HTTPS 地址、签名校验和后台回调验证，会增加最小本地联调成本。生产部署可在后续根据后台能力切换。

注意：官方“启动接入”页仍链接 `botpy`，而腾讯官方组织在 2026-05 发布了更晚的 `qqbot-agent-sdk`。因此这里表述为“本项目选择的新官方 SDK”，不声称腾讯文档已宣布全面淘汰 `botpy`。

官方依据：

- [QQ 机器人官方文档：启动接入](https://bot.q.qq.com/wiki/develop/api-v2/)
- [QQ 机器人官方文档：获取访问凭证](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)
- [QQ 机器人官方文档：事件订阅与通知](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html)
- [腾讯官方 GitHub：qqbot-agent-sdk](https://github.com/tencent-connect/qqbot-agent-sdk)
- [腾讯官方 GitHub：botpy（用于比较）](https://github.com/tencent-connect/botpy)

官方文档在 2026-07 已将 Token 标为弃用，并要求使用 AppID/AppSecret 获取 Access Token；OpenAPI 鉴权头格式为 `QQBot ACCESS_TOKEN`。本项目由 SDK 自动管理 Access Token，不要求也不读取旧 Token。

SDK 1.2.2 的默认域名仍是旧的 `api.sgroup.qq.com` / `bots.qq.com`，而当前官方文档使用统一域名 `api.bot.qq.com`。本项目在导入 SDK 前显式设置当前官方域名；如腾讯后台给你的应用展示了不同环境域名，以后台为准，通过 `.env` 覆盖。

## 目录结构

```text
qq-official-bot/
├─ main.py                  # Gateway、事件转换、ping 回复和日志
├─ config.py                # .env 读取、校验及官方 API 域名配置
├─ .env.example             # 无真实密钥的配置模板
├─ .gitignore               # 排除密钥、虚拟环境、缓存和运行日志
├─ requirements.txt         # 固定官方 SDK 版本及直接依赖
├─ README.md                # 本文档
├─ gifts/                   # 礼包网站只读 API、期次查询与展示
├─ daily_draw/              # 每日单抽、次数控制、图鉴与结果记录
├─ daily_draw_pool.json     # Crayon Note 使徒名单与头像映射
├─ steam/                   # Steam 主动查询与身份绑定
├─ ui/                      # Markdown 菜单和中文指令按钮
├─ logs/
│  └─ .gitkeep              # 保留空日志目录
└─ tests/
   └─ test_main.py          # 无真实凭证的处理器/配置单元测试
```

## Windows PowerShell 启动

### 1. 安装 Python

安装 64 位 Python 3.11，并确认：

```powershell
py -3.11 --version
```

### 2. 创建并启用虚拟环境

```powershell
cd D:\project-coze\qq-official-bot
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 3. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 4. 配置凭证

```powershell
Copy-Item .env.example .env
notepad .env
```

填写：

```dotenv
QQ_APP_ID=你的AppID
QQ_APP_SECRET=你的AppSecret
```

礼包查询还需要填写已经部署的网站根地址（没有地址时机器人仍可启动，只有礼包模块会提示未配置）：

```dotenv
GIFT_API_BASE_URL=https://你的礼包网站域名
```

不要填写旧式 Token，也不要提交 `.env`。如果密钥曾进入聊天、日志或 Git 历史，请立即在 QQ 开放平台重置 AppSecret。

### 5. 启动机器人

```powershell
python main.py
```

按 `Ctrl+C` 停止。

### 一键启动 EXE

项目提供 Windows 单文件 EXE 构建脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

结果位于 `dist\ElenaBot.exe`。部署时复制整个 `dist` 目录，将其中的
`.env.example` 改名为 `.env` 并填写真实配置，然后双击 `ElenaBot.exe`。
EXE 不包含任何真实凭证，且带有单实例锁，重复启动不会造成重复回复。
完整步骤见 [DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md)。

构建也会生成 `dist\ElenaManager.exe`。它是 Windows 本机管理终端：可以编辑部署目录的 `.env`、启动或停止由它启动的机器人、执行 Git 状态/安全拉取，并在确认后提交推送。Git 操作只对含 `.git` 的完整仓库可用；单独复制到服务器的 `dist` 不会被误认为仓库。

也可不创建 `.env`，仅对当前 PowerShell 会话设置环境变量：

```powershell
$env:QQ_APP_ID = "你的AppID"
$env:QQ_APP_SECRET = "你的AppSecret"
python main.py
```

## 怎样判断连接成功

启动过程应依次看到类似日志（不会打印密钥或 Access Token）：

```text
启动时间：... | bot=艾琳娜 | Python=3.11.x
当前连接状态：AUTHENTICATING
AppID / AppSecret 鉴权成功（敏感凭证未输出）
当前连接状态：CONNECTING
当前连接状态：ONLINE（Gateway 已 READY/RESUMED，机器人可用）
机器人身份就绪 | name=...
```

只有出现 `ONLINE（Gateway 已 READY/RESUMED）`，才代表已经完成 Gateway 登录、机器人处于可用状态。仅出现“鉴权成功”不等于已连接。

日志同时写入 `logs/bot.log`，单文件最多 2 MiB，保留 3 个轮转文件。

## QQ 中的测试方式

### QQ 群（优先）

群消息事件是 `GROUP_AT_MESSAGE_CREATE`。当前官方能力要求用户在群内 **@机器人**：

```text
@艾琳娜 ping
```

或：

```text
@艾琳娜 测试
```

SDK 会去掉消息开头的 @ 提及，再交给 `handle_message(context)`。

### C2C 单聊

打开机器人的消息列表单聊，直接发送：

```text
ping
```

对应事件为 `C2C_MESSAGE_CREATE`。

正常收到消息时，控制台会记录接收时间、官方事件类型、消息类型、`group/c2c/guild` 场景、群 openid、用户 openid/member_openid、消息 ID、内容以及回复成功/失败。项目不会假定这些标识是传统 QQ 号。

## QQ 开放平台后台需要配置什么

后台入口：[QQ 开放平台](https://q.qq.com/)

后台 UI、可申请场景和权限会随开发者主体类型、机器人审核/上线状态变化。下面凡标注“需要用户在 QQ 开放平台确认此项”的内容，必须以你的机器人后台实际页面为准。

### AppID / AppSecret

进入目标机器人的开发设置/开发管理页面，找到机器人 `AppID` 与 `AppSecret`。复制到本机 `.env`；不要把旧 `Token` 当作 AppSecret。官方文档明确旧 Token 鉴权已弃用。

### 场景能力与权限

1. 开启/申请“QQ群”场景能力，作为本阶段首要测试场景。
2. 开启/申请“消息列表单聊（C2C）”场景能力，作为第二测试场景。
3. Gateway 代码只申请 `GROUP_AND_C2C_EVENT (1 << 25)`；它包含 `GROUP_AT_MESSAGE_CREATE` 和 `C2C_MESSAGE_CREATE`。
4. SDK 1.2.2 没有公开的逐客户端 intents 参数，且其内置默认值还会申请频道/Interaction 权限。本项目固定 SDK 版本，并在启动时把 SDK 模块的 Identify intent 收窄为官方定义的 `1 << 25`，避免无关权限导致连接被关闭；同时会校验该枚举值，SDK 升级后若协议值变化将明确报错。

以上场景是否对当前主体开放、是否需要申请/审核：**需要用户在 QQ 开放平台确认此项**。

### 事件订阅与 Webhook

- 本项目使用 WebSocket，在 Identify 时通过 intents 订阅消息事件。
- 当前阶段不需要配置 Webhook URL，也不启动 HTTP 服务。
- 如果后台强制选择“消息接收方式”，选择 WebSocket；后台是否提供此选择：**需要用户在 QQ 开放平台确认此项**。
- 不要同时把同一批事件接入另一个正在运行的 Webhook/旧进程，以免测试结果混淆。

### IP 白名单

如果后台存在并启用了 IP 白名单，请填写运行本程序机器/服务器的固定公网出口 IPv4。家庭宽带公网 IP 可能变化，公司网络/VPN/代理出口也可能改变。

新旧机器人、沙箱和正式环境的白名单策略可能不同，因此是否必须填写以及当前生效范围：**需要用户在 QQ 开放平台确认此项**。鉴权成功但 Gateway/OpenAPI 被拒绝时，优先核对实际出口 IP 与白名单。

可在准备启动的同一网络中查看公网出口 IP，例如：

```powershell
(Invoke-RestMethod -Uri "https://api.ipify.org?format=json").ip
```

### 沙箱/测试环境与添加测试机器人

1. 在后台找到“沙箱配置”“测试环境”或当前等价入口。
2. 配置一个由测试账号可管理的测试群；人数、管理员身份和主体限制以后台提示为准。
3. 从机器人资料卡、后台二维码，或群设置中的“群机器人”入口，把测试机器人加入该测试群。
4. 为 C2C 配置测试账号/白名单（若后台要求），再从机器人资料卡进入消息列表单聊。
5. 后台是否要求单独的沙箱 API 域名：**需要用户在 QQ 开放平台确认此项**。本项目默认使用当前官方文档的正式统一域名；若后台明确给出其他域名，在 `.env` 设置 `QQ_API_BASE` 与 `QQ_TOKEN_URL`，不要自行猜测。

测试机器人能否加入群、C2C 是否对当前开发者主体开放、具体人数限制：**需要用户在 QQ 开放平台确认此项**。

### “离线（服务不可用）”

当程序完成鉴权并收到 Gateway `READY` 后，代码会记录 `ONLINE`。平台状态通常会随有效连接恢复，但后台展示可能有刷新/同步延迟。不能只凭程序进程存在判断在线，也不能保证后台立即刷新；请以 `ONLINE` 日志、后台状态及实际消息收发三者共同确认。若仍显示离线：**需要用户在 QQ 开放平台确认此项**，并检查权限、环境、IP 白名单与是否连接到了该 AppID 对应的机器人。

## 统一消息上下文

所有官方事件先转换为：

```python
MessageContext(
    platform="qq_official",
    scene_type="group",       # group / c2c / guild
    group_id="群 openid",     # 非群消息为 None
    user_id="member_openid",  # C2C 为 user_openid
    message_id="官方消息 ID",
    content="ping",
    event_type="GROUP_AT_MESSAGE_CREATE",
    message_type=0,
    reply=...,
)
```

随后只调用：

```python
await handle_message(context)
```

后续 NoneBot2 或插件适配应接在这个边界之后，不应让插件直接依赖 QQ 原始事件对象。

## 🎁 礼包性价比查询

入口：`市政终端 → 市政服务 → 礼包性价比`。机器人只读调用礼包网站已有 API，不保存 Supabase 管理密钥，也不复制网站数据库。网站后台新增或修改礼包后，机器人下次查询会直接读取最新数据。

支持的中文指令：

```text
/礼包查询                 直接显示最新一期的完整排行
/礼包排行                 查看最新一期排行
/礼包期次                 选择最近期次
/礼包期次 第12期          查询指定期次
礼包 每周特惠             按名称模糊搜索
```

“期次”来自网站的 `gift_folders`。优先读取 `periodic`、`event_collection` 类型，也兼容名称中包含“第 N 期/N 期”的旧文件夹。最新一期优先按期号判断，没有期号时再按创建时间判断。

统一展示售价、折算水晶叶总价值、每元价值和推荐等级。付费礼包按每元价值降序；价格为零且有价值的免费礼包单独置顶，不把网站内部的 `999999` 哨兵值展示给用户。阶梯礼包保留阶梯编号。

需要网站保持以下公开只读接口可访问：

```text
GET /api/gift-folders
GET /api/gifts
GET /api/ratings/enabled
```

压缩包不包含线上数据库或部署域名，因此只有填写真实 `GIFT_API_BASE_URL` 后，才能进行真实每期数据联调。

## 🎮 Steam 监测站（第一阶段）

Steam 已归入“市政终端 → 市政服务 → Steam 监测站”。监测站首页只有四个按钮：

- `👤 我的档案` → `steam:profile`
- `📡 当前状态` → `steam:status`
- `🔗 身份登记` → `steam:bind`
- `🔙 返回市政服务` → `steam:back`

第一阶段只启用主动查询。自动监测、上线/下线、开始/停止/切换游戏和主动群通知尚未调度，`STEAM_MONITOR_ENABLED` 必须保持 `false`。

### Steam 配置

登录 [Steam Web API Key 页面](https://steamcommunity.com/dev/apikey) 创建 Key，然后只在本机 `.env` 中填写：

```dotenv
STEAM_API_KEY=你的真实Key
STEAM_MONITOR_ENABLED=false
```

可选参数：

```dotenv
STEAM_API_BASE=https://api.steampowered.com
STEAM_REQUEST_TIMEOUT=15
STEAM_RETRY_TIMES=2
```

程序使用 Valve 当前文档中的 `ISteamUser/GetPlayerSummaries/v2` 与 `ISteamUser/ResolveVanityURL/v1`。Key 只作为请求参数传给 Steam，不写入数据库，也会被日志过滤器脱敏。参考：[Valve ISteamUser Web API 文档](https://partner.steamgames.com/doc/webapi/ISteamUser)。

### 身份与数据库

绑定数据写入 `data/steam.sqlite3` 的 `steam_platform_bindings` 表。表使用：

```text
platform + user_id + group_id → steam_id
```

QQ群使用 `member_openid + group_openid`，C2C 使用该会话的用户 `openid`，不读取或假定传统 QQ 号。GROUP 与 C2C 的官方 openid 可能不同，因此需要分别登记。建表只使用 `CREATE TABLE IF NOT EXISTS`；旧插件、旧 JSON 和旧数据库不会被改写或删除。

### 文本命令

群聊需要先 `@艾琳娜`，C2C 直接发送：

```text
steam
steam状态
我的steam
绑定steam 7656119xxxxxxxxxx
steam绑定 7656119xxxxxxxxxx
解绑steam
```

身份登记支持 SteamID64、好友码、`steamcommunity.com/profiles/...` 和 `steamcommunity.com/id/...`。Vanity URL 需要有效 `STEAM_API_KEY` 才能解析。

`GetPlayerSummaries` 能返回当前游戏，但不提供游戏开始时间。“本终端已持续观测”从首次查询到同一游戏时开始计时，不伪造成 Steam 的完整游戏时长；第二阶段自动轮询启用后才会形成连续监测数据。

### Steam 错误排查

- 提示接口参数未登记：检查 `.env` 中的 `STEAM_API_KEY`，重启程序。
- HTTP 401/403：Key 无效、不可用或被 Steam 拒绝。
- HTTP 429：触发 Steam 限流，等待后重试。
- 超时/网络失败：检查本机到 `api.steampowered.com` 的网络；当前阶段未自动继承旧机器人的代理配置。
- 玩家不存在：确认 SteamID/好友码正确；部分字段是否展示还受 Steam 个人资料隐私设置影响。

## 自检

无需真实凭证的检查：

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
python -c "from qqbot_agent_sdk import EventParser, QQApiClient, QQWebSocket, WSCallbacks; print('SDK imports OK')"
```

检查缺失配置的提示：

```powershell
Remove-Item Env:QQ_APP_ID -ErrorAction SilentlyContinue
Remove-Item Env:QQ_APP_SECRET -ErrorAction SilentlyContinue
python main.py
```

预期退出码为 `2`，并明确提示缺少 `QQ_APP_ID` / `QQ_APP_SECRET`。

需要真实凭证才能完成的联调：

- AppID/AppSecret 实际换取 Access Token
- 获取 Gateway URL 并收到 `READY`
- 后台从“离线”恢复
- 测试群投递 `GROUP_AT_MESSAGE_CREATE`
- C2C 投递 `C2C_MESSAGE_CREATE`
- OpenAPI 被动回复成功

没有真实凭证时，不能宣称上述项目已验证成功。

## 常见错误排查

### `invalid appid or secret` / 100016

确认 `.env` 中没有引号、全角空格或复制错机器人；确认填写的是 AppSecret，不是已弃用 Token。必要时在后台重置 AppSecret并同步更新 `.env`。

### 鉴权成功，但拿不到 Gateway 或连接后立即断开

依次检查：

1. 机器人状态是否正常，是否被下架/封禁。
2. 群/C2C 场景及所需事件权限是否已开通。
3. 运行机器的公网出口 IP 是否在后台白名单。
4. 当前机器人应连接正式还是沙箱环境。
5. 代理、防火墙是否允许 HTTPS 和 WSS 访问 `api.bot.qq.com`。
6. 是否有另一进程占用同一机器人连接或消耗 Gateway 会话配额。

### 已 ONLINE，但收不到群消息

确认机器人已实际加入该群，并使用 `@艾琳娜 ping`，不是只发 `ping`。再确认该群属于后台允许的测试范围，事件能力包含 `GROUP_AT_MESSAGE_CREATE`。

### C2C 收不到消息

确认“消息列表单聊”场景已对当前主体开放，测试 QQ 已加入沙箱/白名单或机器人已上线，并从正确机器人的资料卡进入会话。

### 收到消息但回复失败

查看 `status`、错误消息和 `trace_id` 日志；核对 OpenAPI 权限、被动回复窗口、原始 `message_id`、IP 白名单和机器人状态。日志不会输出 Authorization、AppSecret 或 Access Token。

### SDK 域名变化

当前默认值是：

```dotenv
QQ_API_BASE=https://api.bot.qq.com
QQ_TOKEN_URL=https://api.bot.qq.com/app/getAppAccessToken
```

仅当 QQ 官方文档或你的后台明确提供新值时覆盖它们。
