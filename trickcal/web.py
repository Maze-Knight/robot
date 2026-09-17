from __future__ import annotations

# LEGACY LOCAL IMPLEMENTATION: loaded only when TRICKCAL_MODE=local.

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

from .service import TrickcalBoardService


logger = logging.getLogger("elena.qq.trickcal.web")
COOKIE_NAME = "elena_trickcal_session"
MAX_IMPORT_BYTES = 512 * 1024


BOARD_CSS = """
:root{color-scheme:dark;--bg:#15121b;--panel:#231d2b;--ink:#f7eefc;--muted:#b8abc2;--accent:#e78db5;--line:#493b52}*{box-sizing:border-box}body{margin:0;background:linear-gradient(160deg,#1e1425,#15121b);color:var(--ink);font:16px system-ui,-apple-system,"Microsoft YaHei",sans-serif}main{max-width:1040px;margin:auto;padding:20px}header{display:flex;justify-content:space-between;gap:12px;align-items:center}h1{margin:0;font-size:1.55rem}p{color:var(--muted)}button,input{font:inherit}button{background:#3a2941;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:9px 12px;cursor:pointer}button.primary{background:var(--accent);color:#321426;border:0}button:disabled{opacity:.45}.summary,.toolbar,.unit{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:14px 0}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.summary b{display:block;font-size:1.2rem}.toolbar{display:flex;flex-wrap:wrap;gap:9px}.toolbar input{min-width:180px;flex:1;background:#18131d;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:9px}.unit h2{font-size:1.05rem;margin:0 0 10px}.meta{font-size:.86rem;color:var(--muted)}.nodes{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-top:10px}.node{padding:9px;border:1px solid var(--line);border-radius:10px;background:#1a1520;text-align:left}.node.selected{border-color:#e78db5;background:#412238}.node.planned{border-color:#e0b25d;background:#392e1b}.node small{display:block;color:var(--muted);margin-top:4px}.hidden{display:none}@media(max-width:600px){main{padding:14px}.summary{grid-template-columns:1fr 1fr}.toolbar{display:grid;grid-template-columns:1fr 1fr}.toolbar input{grid-column:1/-1}.nodes{grid-template-columns:1fr 1fr}}
"""

BOARD_JS = """
const api='/tr-board/api/';let state=null;let filter='all';
const $=s=>document.querySelector(s);const call=async(path,opt={})=>{const r=await fetch(api+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.method&&opt.method!=='GET'?{'X-CSRF-Token':state.csrf}:{}),...(opt.headers||{})},...opt});if(!r.ok)throw new Error(await r.text()||'请求失败');return r.headers.get('content-type')?.includes('json')?r.json():r.text()};
function resource(){const u=new Set(state.board.units), selected=new Set(state.board.selected), planned=new Set(state.board.planned), nodes=state.catalog.nodes;const owned=[...u];const known=owned.flatMap(id=>nodes.filter(n=>n.unit_id===id));const done=known.filter(n=>selected.has(n.id));const plan=known.filter(n=>planned.has(n.id));const rest=known.filter(n=>!selected.has(n.id));return {owned,known,done,plan,gold:rest.reduce((x,n)=>x+(n.gold||0),0),crayons:rest.reduce((x,n)=>x+(n.gold_crayons||0),0)}}
function render(){const r=resource();$('#summary').innerHTML=`<div><b>${r.owned.length} / ${state.catalog.units.length}</b>已登记角色</div><div><b>${r.done.length} / ${r.known.length}</b>已完成节点</div><div><b>${r.plan.length}</b>计划节点</div><div><b>${r.gold.toLocaleString()}</b>预计金币</div><div><b>${r.crayons.toLocaleString()}</b>预计金蜡笔</div>`;const q=$('#search').value.trim().toLocaleLowerCase();const units=state.catalog.units.filter(u=>(filter==='all'||(filter==='owned')===state.board.units.includes(u.id))&&`${u.name} ${u.alias||''}`.toLocaleLowerCase().includes(q));$('#units').innerHTML=units.map(u=>{const owned=state.board.units.includes(u.id);const nodes=state.catalog.nodes.filter(n=>n.unit_id===u.id);return `<article class="unit"><h2>${escapeHtml(u.name||u.alias||('角色 '+u.id))}</h2><div class="meta">${owned?'已拥有':'未拥有'} · 三层节点 ${nodes.length}</div><p><button class="${owned?'':'primary'}" data-unit="${u.id}" data-owned="${owned?'0':'1'}">${owned?'撤销拥有':'登记拥有'}</button></p><div class="nodes">${nodes.map(n=>nodeHtml(n)).join('')}</div></article>`}).join('')||'<p>没有符合条件的角色。</p>';}
function nodeHtml(n){const s=state.board.selected.includes(n.id)?'selected':state.board.planned.includes(n.id)?'planned':'';const label=s==='selected'?'已点亮':s==='planned'?'计划':'未处理';return `<button class="node ${s}" data-node="${n.id}" data-state="${s}">第${n.layer}层 · ${label}<small>金币 ${n.gold||0} · 金蜡笔 ${n.gold_crayons||0}</small></button>`}
function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
async function load(){state=await call('state');state.csrf=(await call('session')).csrf;render()}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.unit){await call('units/'+b.dataset.unit,{method:'PUT',body:JSON.stringify({owned:b.dataset.owned==='1'})})}else if(b.dataset.node){const current=b.dataset.state;const next=current==='selected'?'planned':current==='planned'?null:'selected';await call('nodes/'+b.dataset.node,{method:'PUT',body:JSON.stringify({state:next})})}else if(b.id==='all'){await call('units/owned-all',{method:'POST',body:'{}'})}else if(b.id==='export'){const doc=await call('export');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));a.download='soshage-trickcal.json';a.click();URL.revokeObjectURL(a.href)}else if(b.id==='logout'){await call('logout',{method:'POST',body:'{}'});location.reload()}else return;await load()}catch(err){alert(err.message)}});document.addEventListener('input',e=>{if(e.target.id==='search')render()});document.addEventListener('change',e=>{if(e.target.name==='filter'){filter=e.target.value;render()}});$('#import').addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;try{await call('import',{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:await f.text()});await load()}catch(err){alert(err.message)}finally{e.target.value=''}});load().catch(e=>{$('#units').textContent='读取蜡笔板失败：'+e.message});
"""

BOARD_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>🖍️ 蜡笔板</title><link rel="stylesheet" href="/tr-board/assets/board.css"><main><header><div><h1>🖍️ 蜡笔板</h1><p>莫纳提姆市政终端 · 个人节点管理</p></div><button id="logout">退出网页登录</button></header><section id="summary" class="summary"></section><section class="toolbar"><input id="search" placeholder="搜索角色"><label><input type="radio" name="filter" value="all" checked> 全部</label><label><input type="radio" name="filter" value="owned"> 已拥有</label><label><input type="radio" name="filter" value="unowned"> 未拥有</label><button id="all">全部登记</button><button id="export">导出 JSON</button><label><button type="button" onclick="document.querySelector('#import').click()">导入 JSON</button><input id="import" type="file" accept="application/json,.json" class="hidden"></label></section><section id="units"></section></main><script src="/tr-board/assets/board.js"></script></html>"""


class BoardWeb:
    def __init__(self, service: TrickcalBoardService, *, secure_cookie: bool) -> None:
        self.service = service
        self.secure_cookie = secure_cookie
        self._rate: dict[str, deque[float]] = defaultdict(deque)
        self.app = FastAPI(docs_url=None, redoc_url=None)
        self._install_routes()

    def _security(self, response: Response, *, asset: bool = False) -> Response:
        response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'","Cache-Control":"public, max-age=3600" if asset else "no-store"})
        return response

    def _origin(self) -> str:
        parsed = urlsplit(self.service.public_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _limited(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic(); queue = self._rate[client]
        while queue and queue[0] <= now - 60: queue.popleft()
        if len(queue) >= 60: raise HTTPException(429, "请求过于频繁。")
        queue.append(now)

    async def _session(self, request: Request, *, csrf: bool = False) -> dict[str, Any]:
        self._limited(request)
        token = request.cookies.get(COOKIE_NAME, "")
        session = await self.service.repository.get_session(token)
        if session is None: raise HTTPException(401, "请通过 QQ 机器人重新打开蜡笔板。")
        if csrf:
            if request.headers.get("origin") != self._origin() or request.headers.get("x-csrf-token") != session["csrf_token"]:
                raise HTTPException(403, "请求校验失败。")
        return session

    def _install_routes(self) -> None:
        @self.app.get("/tr-board")
        async def root_redirect() -> Response:
            return RedirectResponse("/tr-board/", status_code=307)

        @self.app.get("/tr-board/entry")
        async def entry(t: str = "") -> Response:
            if not 32 <= len(t) <= 128:
                raise HTTPException(400, "登录票据无效或已失效。")
            redeemed = await self.service.redeem_entry(t)
            if redeemed is None:
                raise HTTPException(400, "登录票据无效、已使用或已过期。请回 QQ 重新打开。")
            session, _csrf = redeemed
            response = RedirectResponse("/tr-board/", status_code=302)
            response.set_cookie(COOKIE_NAME, session, max_age=self.service.session_days * 86400, httponly=True, secure=self.secure_cookie, samesite="lax", path="/tr-board")
            return self._security(response)

        @self.app.get("/tr-board/")
        async def page() -> Response:
            return self._security(HTMLResponse(BOARD_HTML))

        @self.app.get("/tr-board/assets/board.css")
        async def css() -> Response:
            return self._security(Response(BOARD_CSS, media_type="text/css"), asset=True)

        @self.app.get("/tr-board/assets/board.js")
        async def js() -> Response:
            return self._security(Response(BOARD_JS, media_type="application/javascript"), asset=True)

        @self.app.get("/tr-board/api/session")
        async def session(request: Request) -> Response:
            value = await self._session(request)
            return self._security(JSONResponse({"csrf": value["csrf_token"]}))

        @self.app.get("/tr-board/api/state")
        async def state(request: Request) -> Response:
            value = await self._session(request)
            return self._security(JSONResponse(await self.service.state(int(value["profile_id"]))))

        @self.app.put("/tr-board/api/units/{unit_id}")
        async def unit(unit_id: int, request: Request) -> Response:
            value = await self._session(request, csrf=True); body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("owned"), bool): raise HTTPException(400, "请求格式不正确。")
            await self.service.set_owned(int(value["profile_id"]), unit_id, body["owned"])
            return self._security(JSONResponse({"ok": True}))

        @self.app.post("/tr-board/api/units/owned-all")
        async def all_units(request: Request) -> Response:
            value = await self._session(request, csrf=True); await self.service.own_all(int(value["profile_id"])); return self._security(JSONResponse({"ok": True}))

        @self.app.put("/tr-board/api/nodes/{node_id}")
        async def node(node_id: int, request: Request) -> Response:
            value = await self._session(request, csrf=True); body = await request.json(); state = body.get("state") if isinstance(body, dict) else object()
            if state not in {None, "selected", "planned"}: raise HTTPException(400, "节点状态不正确。")
            await self.service.set_node(int(value["profile_id"]), node_id, state)
            return self._security(JSONResponse({"ok": True}))

        @self.app.post("/tr-board/api/import")
        async def import_board(request: Request) -> Response:
            value = await self._session(request, csrf=True); raw = await request.body()
            if len(raw) > MAX_IMPORT_BYTES: raise HTTPException(413, "导入文件不能超过 512 KiB。")
            try: text = raw.decode("utf-8-sig"); await self.service.import_export(int(value["profile_id"]), text)
            except (UnicodeDecodeError, ValueError) as exc: raise HTTPException(400, str(exc)) from None
            return self._security(JSONResponse({"ok": True}))

        @self.app.get("/tr-board/api/export")
        async def export_board(request: Request) -> Response:
            value = await self._session(request)
            return self._security(JSONResponse(await self.service.export(int(value["profile_id"]))))

        @self.app.post("/tr-board/api/logout")
        async def logout(request: Request) -> Response:
            await self._session(request, csrf=True); token = request.cookies.get(COOKIE_NAME, ""); await self.service.repository.logout(token)
            response = JSONResponse({"ok": True}); response.delete_cookie(COOKIE_NAME, path="/tr-board")
            return self._security(response)

        @self.app.get("/api/v1/tr-board/catalog")
        async def public_catalog(request: Request) -> Response:
            self._limited(request)
            return self._security(JSONResponse((await self.service.catalog.get()).public()))

        @self.app.get("/tr-board/api-docs")
        async def docs() -> Response:
            return self._security(PlainTextResponse("蜡笔板 API：网页 API 仅限已登录会话；公开目录为 /api/v1/tr-board/catalog。"))


class BoardWebServer:
    """A same-process loopback ASGI server; Nginx owns public HTTPS."""

    def __init__(self, web: BoardWeb) -> None:
        self.web = web
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        config = uvicorn.Config(self.web.app, host="127.0.0.1", port=8080, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        for _ in range(100):
            if self._server.started: return
            if self._task.done(): raise RuntimeError("蜡笔板网页服务未能启动。")
            await asyncio.sleep(0.05)
        raise RuntimeError("蜡笔板网页服务启动超时。")

    async def stop(self) -> None:
        if self._server is not None: self._server.should_exit = True
        if self._task is not None:
            await self._task
        self._task = None; self._server = None
