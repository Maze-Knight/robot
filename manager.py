"""Loopback-only management console packaged as ElenaManager.exe."""
from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from manager_core import (
    ENVIRONMENT_KEYS, default_runtime_directory, find_repository,
    git_commit_and_push, git_pull_fast_forward, git_status, launch_bot,
    load_environment, save_environment,
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
</style><main><h1>🤖 艾琳娜部署管理器</h1><p>本机控制台。密钥只在回环地址和本机 `.env` 中使用，绝不写入操作日志。</p><section><h2>位置</h2><div class="row"><label>机器人运行目录</label><input id="runtime"><button onclick="saveLocations()">应用目录</button></div><div class="row"><label>Git 工作区</label><input id="repository"><button onclick="saveLocations()">应用目录</button></div><p>服务器若只有 dist 目录，仍可管理机器人；Git 操作会安全拒绝。</p></section><section><h2>.env 配置</h2><div id="fields"></div><div class="actions"><button class="primary" onclick="saveEnv()">保存 .env</button><button onclick="loadState()">重新读取</button></div></section><section><h2>机器人与 Git</h2><div class="actions"><button class="primary" onclick="post('bot/start')">启动机器人</button><button onclick="post('bot/stop')">停止本管理器启动的机器人</button><button onclick="get('git/status')">Git 状态</button><button onclick="post('git/pull')">安全拉取</button><input id="message" placeholder="提交说明"><button onclick="commit()">提交并推送</button></div></section><section><h2>操作结果</h2><pre id="output">正在读取…</pre></section></main><script>
let csrf='',state={};const sensitive=new Set(['QQ_APP_SECRET','TRICKCAL_BOT_API_KEY']);const labels={QQ_APP_ID:'QQ AppID',QQ_APP_SECRET:'QQ AppSecret',GIFT_API_BASE_URL:'礼包网站地址',TRICKCAL_MODE:'蜡笔板模式',TRICKCAL_API_BASE_URL:'蜡笔板网站地址',TRICKCAL_BOT_API_KEY:'蜡笔板 Bot API Key',TRICKCAL_WEB_PUBLIC_URL:'Legacy 蜡笔板公网地址',TRICKCAL_WEB_SECURE_COOKIE:'Legacy Secure Cookie',TRICKCAL_WEB_SESSION_DAYS:'Legacy 网页保存天数',TRICKCAL_LOGIN_TICKET_MINUTES:'Legacy 网页票据分钟数'};
const out=x=>document.querySelector('#output').textContent=typeof x==='string'?x:JSON.stringify(x,null,2);async function request(path,opt={}){let r=await fetch('/api/'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...(opt.headers||{})},...opt});let body=await r.json();if(!r.ok)throw new Error(body.detail||body.output||'操作失败');return body}function draw(){runtime.value=state.runtime;repository.value=state.repository||'';fields.innerHTML='';for(const key of state.keys){let row=document.createElement('div');row.className='row';let label=document.createElement('label');label.textContent=labels[key];let input=document.createElement('input');input.id='env-'+key;input.value=state.env[key]||'';if(sensitive.has(key))input.type='password';row.append(label,input);fields.append(row)}}async function loadState(){try{state=await request('state');csrf=state.csrf;draw();out('已读取本机配置。')}catch(e){out(e.message)}}async function post(path,data={}){try{out((await request(path,{method:'POST',body:JSON.stringify(data)})).output)}catch(e){out(e.message)}}async function get(path){try{out((await request(path)).output)}catch(e){out(e.message)}}function saveLocations(){post('locations',{runtime:runtime.value,repository:repository.value}).then(loadState)}function saveEnv(){let env={};for(const key of state.keys)env[key]=document.querySelector('#env-'+key).value;post('env',env)}function commit(){let message=document.querySelector('#message').value;if(!message){out('请输入提交说明。');return}if(confirm('将暂存未被 Git 忽略的改动、提交并推送到当前远程仓库。继续吗？'))post('git/commit-push',{message})}loadState();
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
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    webbrowser.open(ORIGIN)
    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
