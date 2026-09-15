# Windows 服务器部署

## 直接运行 EXE

1. 将构建得到的整个 `dist` 目录复制到 Windows 服务器。
2. 把 `.env.example` 复制或重命名为 `.env`。
3. 在 `.env` 中填写 `QQ_APP_ID`、`QQ_APP_SECRET`、`STEAM_API_KEY` 和礼包网站地址。
4. 双击 `ElenaBot.exe`，或在 PowerShell 中运行：

```powershell
cd C:\Bots\ElenaBot
.\ElenaBot.exe
```

出现 `ONLINE（Gateway 已 READY/RESUMED）` 才表示连接成功。日志写入 EXE 同目录的 `logs\bot.log`，Steam 身份数据写入 `data\steam.sqlite3`。

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

## 服务器长期运行

双击适合联调。正式长期运行建议使用 Windows 任务计划程序：

- 触发器：计算机启动时；
- 操作：启动 `C:\Bots\ElenaBot\ElenaBot.exe`；
- 起始于：`C:\Bots\ElenaBot`；
- 启用“如果任务失败，重新启动”。

不要把 `.env`、`data` 和 `logs` 提交到 Git。
