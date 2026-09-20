# Windows 服务器部署

## 直接运行 EXE

1. 将构建得到的整个 `dist` 目录复制到 Windows 服务器。
2. 把 `.env.example` 复制或重命名为 `.env`。
3. 在 `.env` 中填写 `QQ_APP_ID`、`QQ_APP_SECRET`、礼包网站地址和蜡笔板所需变量。
4. 双击 `ElenaBot.exe`，或在 PowerShell 中运行：

```powershell
cd C:\Bots\ElenaBot
.\ElenaBot.exe
```

出现 `ONLINE（Gateway 已 READY/RESUMED）` 才表示连接成功。日志写入 EXE 同目录的 `logs\bot.log`，每日抽取记录写入 `data\daily_draw.sqlite3`。

同目录的 `ElenaManager.exe` 是本机管理终端，可安全编辑该部署目录的 `.env`、启动/停止它自己启动的机器人、查看 Git 状态、安全拉取，以及在输入提交说明并确认后提交和推送。

- 只复制 `dist` 到服务器时，管理器仍可管理 `.env` 和机器人；Git 功能会提示没有 `.git`，这是正常的保护行为。
- 如需在另一台电脑维护代码，请先克隆完整仓库，再从该仓库的 `dist\ElenaManager.exe` 启动管理器。它会自动向上找到 `.git`。
- “安全拉取”会在存在未提交文件时拒绝执行，避免覆盖本地工作；“.env`、`data`、`logs` 仍由 `.gitignore` 排除。
- 完整仓库中可点击“一键更新”：它会拒绝未提交修改，安全拉取远程代码、重建机器人 EXE，并自动替换和重启管理器及机器人。完成后仍须在 `logs\bot.log` 中确认 `ONLINE`。
- 管理器不会读取或写入任何 Access Token，也不会将 `.env` 的值写进终端日志。

`daily_draw_pool.json` 必须和 `ElenaBot.exe` 放在同一目录。Crayon Note 使徒头像已经打包进 EXE；奖池 JSON 负责名称和图片映射。新奖池首次加载时会自动清空旧每日抽取记录与旧图鉴进度。

程序带有单实例锁。重复启动时，新进程会显示“机器人已经在运行”并退出，不会让同一条 QQ 消息被回复两次。

## 从源码重新构建

```powershell
git clone https://github.com/Maze-Knight/robot.git
cd robot
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

构建结果为 `dist\ElenaBot.exe`。PyInstaller 不是跨平台编译器，因此 Windows EXE 必须在 Windows 上构建。

同一构建命令还会生成 `dist\ElenaManager.exe`。

## 服务器长期运行

双击适合联调。正式长期运行建议使用 Windows 任务计划程序：

- 触发器：计算机启动时；
- 操作：启动 `C:\Bots\ElenaBot\ElenaBot.exe`；
- 起始于：`C:\Bots\ElenaBot`；
- 启用“如果任务失败，重新启动”。

不要把 `.env`、`data` 和 `logs` 提交到 Git。

## 🖍️ 嘟嘟脸蜡笔板（远程网站 API）

生产默认模式不再启动本地网页或 SQLite。将网站端 HTTPS 地址与独立 Bot API Key 写入 `.env`：

```dotenv
TRICKCAL_MODE=remote
TRICKCAL_API_BASE_URL=https://gift.example.com
TRICKCAL_BOT_API_KEY=请填写强随机服务密钥
```

不要把 Key 写入 Git、URL、反向代理日志或截图。远程配置未填写不会阻止 QQ Gateway 启动，只会使蜡笔板入口提示“施工还没结束”。机器人会拒绝 API 返回的非 HTTPS 或非同域入口 URL。

旧本地实现仅供开发或回滚：`TRICKCAL_MODE=local` 时才监听 `127.0.0.1:8080` 并读取以下 **LEGACY ONLY** 配置。网站版真实联调完成前请保留它们，但不要在 remote 模式配置 Nginx 转发。

```dotenv
TRICKCAL_WEB_PUBLIC_URL=https://你的域名/tr-board/
TRICKCAL_WEB_SECURE_COOKIE=true
TRICKCAL_WEB_SESSION_DAYS=30
TRICKCAL_LOGIN_TICKET_MINUTES=10
```
