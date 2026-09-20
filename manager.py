"""Loopback-only management console packaged as ElenaManager.exe."""
from __future__ import annotations

import asyncio
import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from manager_core import (
    ENVIRONMENT_KEYS, default_runtime_directory, find_repository,
    build_distribution, git_commit_and_push, git_pull_fast_forward, git_status, launch_bot,
    load_environment, save_environment,
    stop_managed_process,
)

PORT = 8090
COOKIE = "elena_manager_session"
ORIGIN = f"http://127.0.0.1:{PORT}"
DEFAULT_VALUES = {
    "TRICKCAL_MODE": "remote",
    "TRICKCAL_WEB_PUBLIC_URL": "http://127.0.0.1:8080/tr-board/",
    "TRICKCAL_WEB_SECURE_COOKIE": "false",
    "TRICKCAL_WEB_SESSION_DAYS": "30",
    "TRICKCAL_LOGIN_TICKET_MINUTES": "10",
}

PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>艾琳娜部署管理器</title><style>
:root{color-scheme:dark;--bg:#17131c;--card:#241e2c;--line:#4a3c55;--ink:#f7effb;--muted:#c2b5c9;--accent:#e78db5}*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#1e1627,var(--bg));color:var(--ink);font:15px system-ui,"Microsoft YaHei",sans-serif}main{max-width:960px;margin:auto;padding:22px}h1{margin:0}p{color:var(--muted)}section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:14px}.row{display:grid;grid-template-columns:160px 1fr auto;gap:8px;align-items:center;margin:7px 0}input{min-width:0;width:100%;background:#17131c;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}button{background:#3d2c46;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;cursor:pointer}button.primary{background:var(--accent);color:#3a1225;border:0}.actions{display:flex;flex-wrap:wrap;gap:8px}pre{white-space:pre-wrap;word-break:break-word;background:#151119;border-radius:8px;padding:12px;min-height:120px}@media(max-width:640px){main{padding:12px}.row{grid-template-columns:1fr}.row label{font-weight:bold}}
</style><main><h1>🤖 艾琳娜部署管理器</h1><p>本机控制台。密钥只在回环地址和本机 `.env` 中使用，绝不写入操作日志。</p><section><h2>位置</h2><div class="row"><label>机器人运行目录</label><input id="runtime"><button onclick="saveLocations()">应用目录</button></div><div class="row"><label>Git 工作区</label><input id="repository"><button onclick="saveLocations()">应用目录</button></div><p>服务器若只有 dist 目录，仍可管理机器人；Git 操作会安全拒绝。</p></section><section><h2>.env 配置</h2><div id="fields"></div><div class="actions"><button class="primary" onclick="saveEnv()">保存 .env</button><button onclick="loadState()">重新读取</button></div></section><section><h2>机器人与 Git</h2><div class="actions"><button class="primary" onclick="updateBot()">一键更新</button><button onclick="post('bot/start')">启动机器人</button><button onclick="post('bot/stop')">停止本管理器启动的机器人</button><button onclick="get('git/status')">Git 状态</button><button onclick="post('git/pull')">安全拉取</button><input id="message" placeholder="提交说明"><button onclick="commit()">提交并推送</button></div><p>一键更新会拒绝未提交修改；随后拉取、构建、替换管理器并重启机器人。</p></section><section><h2>操作结果</h2><pre id="output">正在读取…</pre></section></main><script>
let csrf='',state={};const sensitive=new Set(['QQ_APP_SECRET','TRICKCAL_BOT_API_KEY']);const labels={QQ_APP_ID:'QQ AppID',QQ_APP_SECRET:'QQ AppSecret',GIFT_API_BASE_URL:'礼包网站地址',TRICKCAL_MODE:'蜡笔板模式',TRICKCAL_API_BASE_URL:'蜡笔板网站地址',TRICKCAL_BOT_API_KEY:'蜡笔板 Bot API Key',TRICKCAL_WEB_PUBLIC_URL:'Legacy 蜡笔板公网地址',TRICKCAL_WEB_SECURE_COOKIE:'Legacy Secure Cookie',TRICKCAL_WEB_SESSION_DAYS:'Legacy 网页保存天数',TRICKCAL_LOGIN_TICKET_MINUTES:'Legacy 网页票据分钟数'};
const out=x=>document.querySelector('#output').textContent=typeof x==='string'?x:JSON.stringify(x,null,2);async function request(path,opt={}){let r=await fetch('/api/'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...(opt.headers||{})},...opt});let body=await r.json();if(!r.ok)throw new Error(body.detail||body.output||'操作失败');return body}function draw(){runtime.value=state.runtime;repository.value=state.repository||'';fields.innerHTML='';for(const key of state.keys){let row=document.createElement('div');row.className='row';let label=document.createElement('label');label.textContent=labels[key];let input=document.createElement('input');input.id='env-'+key;input.value=state.env[key]||'';if(sensitive.has(key))input.type='password';row.append(label,input);fields.append(row)}}async function loadState(){try{state=await request('state');csrf=state.csrf;draw();out('已读取本机配置。')}catch(e){out(e.message)}}async function post(path,data={}){try{out((await request(path,{method:'POST',body:JSON.stringify(data)})).output)}catch(e){out(e.message)}}async function get(path){try{out((await request(path)).output)}catch(e){out(e.message)}}function saveLocations(){post('locations',{runtime:runtime.value,repository:repository.value}).then(loadState)}function saveEnv(){let env={};for(const key of state.keys)env[key]=document.querySelector('#env-'+key).value;post('env',env)}function updateBot(){if(confirm('将安全拉取远程代码、重建 EXE，并重启机器人和管理器。未提交修改会被拒绝。继续吗？'))post('update')}function commit(){let message=document.querySelector('#message').value;if(!message){out('请输入提交说明。');return}if(confirm('将暂存未被 Git 忽略的改动、提交并推送到当前远程仓库。继续吗？'))post('git/commit-push',{message})}loadState();
</script>"""


class ManagerState:
    def __init__(self, runtime: Path | None = None) -> None:
        self.runtime = runtime or default_runtime_directory()
        self.repository = find_repository(self.runtime)
        self.process: subprocess.Popen[bytes] | None = None
        self.sessions: dict[str, str] = {}

    def data(self) -> dict[str, Any]:
        values = load_environment(self.runtime / ".env")
        return {
            "runtime": str(self.runtime), "repository": str(self.repository) if self.repository else "",
            "env": {key: values.get(key, DEFAULT_VALUES.get(key, "")) for key in ENVIRONMENT_KEYS},
            "keys": ENVIRONMENT_KEYS,
        }


def _schedule_exit() -> None:
    """Let the HTTP response reach the browser before releasing this EXE."""
    threading.Timer(1.5, lambda: os._exit(0)).start()


def _start_replacement_helper(*, staged: Path, target: Path, runtime: Path) -> None:
    """Run a copied helper so the current Manager EXE can be replaced on Windows."""
    helper_dir = Path(tempfile.mkdtemp(prefix="elena-manager-update-"))
    helper = helper_dir / "ElenaManagerUpdater.exe"
    shutil.copy2(sys.executable, helper)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            str(helper),
            "--apply-manager-update",
            "--staged",
            str(staged),
            "--target",
            str(target),
            "--runtime",
            str(runtime),
        ],
        cwd=runtime,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def _apply_manager_update(*, staged: Path, target: Path, runtime: Path) -> None:
    """Replace the old Manager binary after its server process releases the file."""
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            os.replace(staged, target)
            break
        except PermissionError:
            time.sleep(0.5)
        except OSError:
            return
    else:
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [str(target), "--launch-bot"],
        cwd=runtime,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def create_app(state: ManagerState | None = None) -> FastAPI:
    manager = state or ManagerState()
    app = FastAPI(docs_url=None, redoc_url=None)

    def secure(response: Response) -> Response:
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"})
        return response

    def require(request: Request, *, csrf: bool = False) -> None:
        token = request.cookies.get(COOKIE, "")
        if token not in manager.sessions:
            raise HTTPException(401, "本机管理会话无效，请刷新页面。")
        if csrf and (request.headers.get("origin") != ORIGIN or request.headers.get("x-csrf-token") != manager.sessions[token]):
            raise HTTPException(403, "本机请求校验失败。")

    def repository() -> Path:
        if manager.repository is None or not (manager.repository / ".git").exists():
            raise HTTPException(400, "未找到 Git 工作区。仅复制 dist 的部署目录不能执行拉取或推送。")
        return manager.repository

    @app.get("/")
    async def page(request: Request) -> Response:
        token = request.cookies.get(COOKIE)
        response = HTMLResponse(PAGE)
        if token not in manager.sessions:
            token = secrets.token_urlsafe(32)
            manager.sessions = {token: secrets.token_urlsafe(24)}
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
        return secure(response)

    @app.get("/api/state")
    async def state_endpoint(request: Request) -> Response:
        require(request)
        return secure(JSONResponse({**manager.data(), "csrf": manager.sessions[request.cookies[COOKIE]]}))

    @app.post("/api/locations")
    async def locations(request: Request) -> Response:
        require(request, csrf=True)
        body = await request.json()
        runtime = Path(str(body.get("runtime", ""))).expanduser().resolve()
        repo_text = str(body.get("repository", "")).strip()
        repo = Path(repo_text).expanduser().resolve() if repo_text else find_repository(runtime)
        if not runtime.is_dir():
            raise HTTPException(400, "机器人运行目录不存在。")
        manager.runtime, manager.repository = runtime, repo
        return secure(JSONResponse({"output": "目录已应用。"}))

    @app.post("/api/env")
    async def env(request: Request) -> Response:
        require(request, csrf=True)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "配置格式无效。")
        try:
            save_environment(manager.runtime / ".env", {key: str(body.get(key, "")) for key in ENVIRONMENT_KEYS})
        except OSError as exc:
            raise HTTPException(500, f".env 保存失败：{exc}") from None
        return secure(JSONResponse({"output": ".env 已保存；重启机器人后配置生效。"}))

    @app.post("/api/bot/start")
    async def start_bot(request: Request) -> Response:
        require(request, csrf=True)
        if manager.process is not None and manager.process.poll() is None:
            return secure(JSONResponse({"output": "机器人已由本管理器启动。"}))
        try:
            manager.process = launch_bot(manager.runtime)
        except (OSError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from None
        return secure(JSONResponse({"output": "已请求启动。请在 logs\\bot.log 中确认 ONLINE。"}))

    @app.post("/api/bot/stop")
    async def stop_bot(request: Request) -> Response:
        require(request, csrf=True)
        if manager.process is None or manager.process.poll() is not None:
            return secure(JSONResponse({"output": "没有可由本管理器安全停止的机器人进程。"}))
        manager.process.terminate()
        return secure(JSONResponse({"output": "已请求停止本管理器启动的机器人。"}))

    @app.post("/api/update")
    async def update(request: Request) -> Response:
        require(request, csrf=True)
        repo = repository()
        pulled, pull_output = await asyncio.to_thread(git_pull_fast_forward, repo)
        if not pulled:
            raise HTTPException(400, f"安全拉取失败：{pull_output}")
        if manager.process is not None and manager.process.poll() is None:
            stopped = await asyncio.to_thread(stop_managed_process, manager.process)
            if not stopped:
                raise HTTPException(500, "无法停止本管理器启动的机器人，已取消更新以避免覆盖运行文件。")
            manager.process = None
        frozen = bool(getattr(sys, "frozen", False))
        built, build_output = await asyncio.to_thread(
            build_distribution, repo, stage_manager=frozen
        )
        if not built:
            raise HTTPException(500, f"构建失败：{build_output}")
        if frozen:
            staged = manager.runtime / "ElenaManager.next.exe"
            target = Path(sys.executable).resolve()
            if not staged.is_file():
                raise HTTPException(500, "未生成管理器更新文件，已取消替换。")
            try:
                _start_replacement_helper(
                    staged=staged, target=target, runtime=manager.runtime
                )
            except OSError as exc:
                raise HTTPException(500, f"管理器重启准备失败：{exc}") from None
            _schedule_exit()
            output = "拉取与构建完成。管理器将自动替换并重启，机器人随后启动；请在日志中确认 ONLINE。"
        else:
            try:
                manager.process = launch_bot(manager.runtime)
            except (OSError, FileNotFoundError) as exc:
                raise HTTPException(500, f"构建完成，但机器人启动失败：{exc}") from None
            output = "拉取、构建与机器人重启完成。请在 logs\\bot.log 中确认 ONLINE。"
        return secure(JSONResponse({"output": f"{output}\n\n拉取结果：{pull_output}\n\n构建结果：{build_output}"}))

    @app.get("/api/git/status")
    async def status(request: Request) -> Response:
        require(request)
        ok, output = await asyncio.to_thread(git_status, repository())
        return secure(JSONResponse({"output": output}, status_code=200 if ok else 400))

    @app.post("/api/git/pull")
    async def pull(request: Request) -> Response:
        require(request, csrf=True)
        ok, output = await asyncio.to_thread(git_pull_fast_forward, repository())
        return secure(JSONResponse({"output": output}, status_code=200 if ok else 400))

    @app.post("/api/git/commit-push")
    async def commit_push(request: Request) -> Response:
        require(request, csrf=True)
        body = await request.json()
        ok, output = await asyncio.to_thread(git_commit_and_push, repository(), str(body.get("message", "")))
        return secure(JSONResponse({"output": output}, status_code=200 if ok else 400))

    return app


def main() -> None:
    # PyInstaller --windowed sets both streams to None.  Uvicorn configures
    # formatters through sys.stderr, so supply harmless handles before it
    # initializes logging; otherwise the EXE remains a running process but
    # never binds the loopback management port.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--apply-manager-update", action="store_true")
    parser.add_argument("--staged")
    parser.add_argument("--target")
    parser.add_argument("--runtime")
    parser.add_argument("--launch-bot", action="store_true")
    arguments, _unknown = parser.parse_known_args()
    if arguments.apply_manager_update:
        if not all((arguments.staged, arguments.target, arguments.runtime)):
            return
        _apply_manager_update(
            staged=Path(arguments.staged),
            target=Path(arguments.target),
            runtime=Path(arguments.runtime),
        )
        return
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    state = ManagerState()
    if arguments.launch_bot:
        try:
            state.process = launch_bot(state.runtime)
        except (OSError, FileNotFoundError):
            pass
    webbrowser.open(ORIGIN)
    uvicorn.run(create_app(state), host="127.0.0.1", port=PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
