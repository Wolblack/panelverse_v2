import asyncio
import html
import json
import mimetypes
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

try:
    from aiogram.types import FSInputFile
except Exception:
    FSInputFile = None

from archive_service import CONTENT_TYPES, MAX_FILE_BYTES, STORAGE_DIR, create_ingestion, process_ingestion
from database import (
    archive_audit,
    archive_create_publication_job,
    archive_claim_publication_job,
    archive_finish_publication_job,
    archive_get_item,
    archive_get_job,
    archive_list_items,
    archive_stats,
    archive_update_item,
)

ADMIN_WEB_ENABLED = os.getenv("ADMIN_WEB", "1").strip().lower() not in {"0", "false", "no"}
ADMIN_WEB_HOST = os.getenv("ADMIN_WEB_HOST", "127.0.0.1")
ADMIN_WEB_PORT = int(os.getenv("ADMIN_WEB_PORT", "8080"))
ADMIN_WEB_TOKEN = os.getenv("ADMIN_WEB_TOKEN", "").strip()
TELEGRAM_PUBLISH_CHAT_ID = os.getenv("TELEGRAM_PUBLISH_CHAT_ID", "").strip()
MAX_UPLOAD = MAX_FILE_BYTES
_tasks = set()
_runner = None
_publication_task = None


def _authorized(request):
    token = request.headers.get("X-Admin-Token") or request.cookies.get("panelverse_admin")
    return bool(ADMIN_WEB_TOKEN and secrets.compare_digest(token or "", ADMIN_WEB_TOKEN))


def _require(request):
    if not _authorized(request):
        raise web.HTTPUnauthorized(text="Authentication required.")


def _json(data, status=200):
    return web.json_response(data, status=status)


async def login(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    token = str(payload.get("token", ""))
    if not ADMIN_WEB_TOKEN or not secrets.compare_digest(token, ADMIN_WEB_TOKEN):
        return _json({"ok": False, "error": "Invalid admin token."}, 401)
    response = _json({"ok": True})
    response.set_cookie("panelverse_admin", ADMIN_WEB_TOKEN, httponly=True, samesite="Strict", max_age=86400)
    return response


async def logout(request):
    response = _json({"ok": True})
    response.del_cookie("panelverse_admin")
    return response


async def dashboard(request):
    _require(request)
    return _json({"ok": True, "stats": archive_stats()})


async def list_items(request):
    _require(request)
    q = request.query.get("q", "")
    content_type = request.query.get("type", "").upper()
    status = request.query.get("status", "").upper()
    limit = min(100, max(1, int(request.query.get("limit", "50"))))
    offset = max(0, int(request.query.get("offset", "0")))
    return _json({"items": archive_list_items(q, content_type, status, limit, offset)})


async def get_item(request):
    _require(request)
    item = archive_get_item(int(request.match_info["item_id"]))
    if not item:
        return _json({"error": "Archive item not found."}, 404)
    return _json(item)


async def update_item(request):
    _require(request)
    item_id = int(request.match_info["item_id"])
    item = archive_get_item(item_id)
    if not item:
        return _json({"error": "Archive item not found."}, 404)
    payload = await request.json()
    allowed = {"content_type", "title", "subtitle", "description", "status", "metadata_json", "detected_confidence", "completeness", "cover_path"}
    changes = {k: payload[k] for k in allowed if k in payload}
    if "content_type" in changes and changes["content_type"] not in CONTENT_TYPES:
        return _json({"error": "Unsupported content type."}, 400)
    archive_update_item(item_id, **changes)
    archive_audit("web-admin", "ADMIN_ITEM_UPDATED", item_id, {"fields": list(changes)})
    return _json(archive_get_item(item_id))


async def transition_item(request):
    _require(request)
    item_id = int(request.match_info["item_id"])
    action = request.match_info["action"].lower()
    item = archive_get_item(item_id)
    if not item:
        return _json({"error": "Archive item not found."}, 404)
    target = {"draft": "DRAFT", "review": "REVIEW", "approve": "APPROVED", "publish": "PUBLISHED", "archive": "ARCHIVED", "reject": "REJECTED"}.get(action)
    if not target:
        return _json({"error": "Unknown workflow action."}, 400)
    qc = (item.get("metadata") or {}).get("_qc") or {}
    if target in {"APPROVED", "PUBLISHED"} and qc.get("errors"):
        return _json({"error": "Critical QC errors must be resolved before publication.", "qc": qc}, 409)
    archive_update_item(item_id, status=target, published_at=(datetime.now(timezone.utc).isoformat() if target == "PUBLISHED" else item.get("published_at")))
    archive_audit("web-admin", "ADMIN_STATUS_CHANGED", item_id, {"status": target})
    return _json(archive_get_item(item_id))


async def ingest(request):
    _require(request)
    reader = await request.multipart()
    requested_type = ""
    actor = "web-admin"
    files = []
    while True:
        field = await reader.next()
        if field is None:
            break
        if field.name == "content_type":
            requested_type = (await field.text()).strip().upper()
            continue
        if field.name != "files" or not field.filename:
            continue
        safe_name = Path(field.filename).name
        if not safe_name or safe_name in {".", ".."}:
            return _json({"error": "Invalid filename."}, 400)
        temp_dir = STORAGE_DIR / "incoming"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target = temp_dir / (secrets.token_hex(16) + "-" + safe_name)
        total = 0
        try:
            with target.open("wb") as handle:
                while True:
                    chunk = await field.read_chunk(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        target.unlink(missing_ok=True)
                        return _json({"error": safe_name + " exceeds the configured upload limit."}, 413)
                    handle.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        mime = field.headers.get("Content-Type") or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        item_id, job_id, detected, confidence = create_ingestion(safe_name, str(target), mime, actor, requested_type)
        archive_audit(actor, "ADMIN_UPLOAD_RECEIVED", item_id, {"filename": safe_name, "size": total, "mime": mime, "requested_type": requested_type, "detected_type": detected})
        task = asyncio.create_task(process_ingestion(job_id, item_id, str(target), safe_name, mime, actor))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        files.append({"item_id": item_id, "job_id": job_id, "filename": safe_name, "detected_type": detected, "confidence": confidence})
    if not files:
        return _json({"error": "No files were uploaded."}, 400)
    return _json({"ok": True, "files": files}, 202)


async def job(request):
    _require(request)
    result = archive_get_job(int(request.match_info["job_id"]))
    if not result:
        return _json({"error": "Job not found."}, 404)
    return _json(result)


async def publish_telegram(request):
    _require(request)
    item_id = int(request.match_info["item_id"])
    item = archive_get_item(item_id)
    if not item:
        return _json({"error": "Archive item not found."}, 404)
    if item["status"] not in {"APPROVED", "PUBLISHED"}:
        return _json({"error": "Approve the archive item before Telegram publication."}, 409)
    if not TELEGRAM_PUBLISH_CHAT_ID:
        return _json({"error": "TELEGRAM_PUBLISH_CHAT_ID is not configured."}, 503)
    job_id = archive_create_publication_job(item_id, "telegram")
    archive_audit("web-admin", "TELEGRAM_PUBLICATION_QUEUED", item_id, {"job_id": job_id})
    return _json({"ok": True, "job_id": job_id, "status": "QUEUED"}, 202)


async def audit(request):
    _require(request)
    from database import connect
    connection = connect()
    try:
        rows = connection.execute("SELECT * FROM archive_audit_log ORDER BY id DESC LIMIT 100").fetchall()
        return _json({"events": [dict(x) for x in rows]})
    finally:
        connection.close()


async def serve_file(request):
    _require(request)
    item = archive_get_item(int(request.match_info["item_id"]))
    if not item or not item.get("files"):
        raise web.HTTPNotFound()
    file_id = int(request.match_info["file_id"])
    file_record = next((x for x in item["files"] if int(x["id"]) == file_id), None)
    if not file_record:
        raise web.HTTPNotFound()
    path = Path(file_record["storage_path"]).resolve()
    root = STORAGE_DIR.resolve()
    if root not in path.parents:
        raise web.HTTPForbidden()
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def index(request):
    return web.Response(text=HTML, content_type="text/html")


def create_app(bot=None):
    app = web.Application(client_max_size=MAX_UPLOAD + 16 * 1024 * 1024)
    app["telegram_bot"] = bot
    app.add_routes([
        web.get("/admin", index), web.get("/", index),
        web.post("/api/admin/login", login), web.post("/api/admin/logout", logout),
        web.get("/api/archive/stats", dashboard), web.get("/api/archive/items", list_items),
        web.get("/api/archive/items/{item_id}", get_item),
        web.patch("/api/archive/items/{item_id}", update_item),
        web.post("/api/archive/items/{item_id}/{action}", transition_item),
        web.post("/api/archive/ingest", ingest),
        web.get("/api/archive/jobs/{job_id}", job),
        web.post("/api/archive/items/{item_id}/telegram", publish_telegram),
        web.get("/api/archive/audit", audit),
        web.get("/api/archive/items/{item_id}/files/{file_id}", serve_file),
    ])
    return app



async def _telegram_publication_worker(bot):
    while True:
        job = None
        try:
            if bot and TELEGRAM_PUBLISH_CHAT_ID and FSInputFile:
                job = archive_claim_publication_job()
                if job:
                    item = archive_get_item(job["item_id"])
                    if not item or not item.get("files"):
                        archive_finish_publication_job(job["id"], "FAILED", "Archive item has no file.")
                        continue
                    record = item["files"][0]
                    path = Path(record["storage_path"])
                    if not path.is_file():
                        archive_finish_publication_job(job["id"], "FAILED", "Stored file is missing.")
                        continue
                    caption = item["title"] or "PanelVerse Archive"
                    content_type = item["content_type"]
                    source = FSInputFile(str(path), filename=record["original_name"])
                    if content_type == "MUSIC" and record["mime_type"].startswith("audio/"):
                        await bot.send_audio(TELEGRAM_PUBLISH_CHAT_ID, source, caption=caption)
                    elif content_type in {"VIDEO", "MOVIE", "ANIME"} and record["mime_type"].startswith("video/"):
                        await bot.send_video(TELEGRAM_PUBLISH_CHAT_ID, source, caption=caption)
                    else:
                        await bot.send_document(TELEGRAM_PUBLISH_CHAT_ID, source, caption=caption)
                    archive_finish_publication_job(job["id"], "PUBLISHED")
                    archive_update_item(job["item_id"], status="PUBLISHED", published_at=datetime.now(timezone.utc).isoformat())
                    archive_audit("system", "TELEGRAM_PUBLICATION_COMPLETED", job["item_id"], {"job_id": job["id"]})
                else:
                    await asyncio.sleep(2)
            else:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                if 'job' in locals() and job:
                    archive_finish_publication_job(job["id"], "FAILED", str(exc))
                    archive_audit("system", "TELEGRAM_PUBLICATION_FAILED", job["item_id"], {"job_id": job["id"], "error": str(exc)})
            finally:
                await asyncio.sleep(3)


async def start_web_admin(bot=None):
    global _runner, _publication_task
    if not ADMIN_WEB_ENABLED:
        return None
    if not ADMIN_WEB_TOKEN:
        raise RuntimeError("ADMIN_WEB_TOKEN is required when ADMIN_WEB=1")
    _runner = web.AppRunner(create_app(bot), access_log=None)
    await _runner.setup()
    await web.TCPSite(_runner, ADMIN_WEB_HOST, ADMIN_WEB_PORT).start()
    _publication_task = asyncio.create_task(_telegram_publication_worker(bot))
    return _runner


async def stop_web_admin():
    global _runner, _publication_task
    if _publication_task:
        _publication_task.cancel()
        try:
            await _publication_task
        except asyncio.CancelledError:
            pass
        _publication_task = None
    if _runner:
        await _runner.cleanup()
        _runner = None


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PanelVerse Archive Control</title>
<style>
:root{--bg:#07080c;--panel:#10131a;--line:#252a36;--text:#f5f7fb;--muted:#8e97a8;--gold:#d8b46a;--ok:#55d39a;--bad:#ff6b7a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -20%,#263044 0,#0b0d13 34%,var(--bg) 70%);color:var(--text);font:14px/1.5 Inter,system-ui,sans-serif}.hidden{display:none!important}
.shell{display:grid;grid-template-columns:245px 1fr;min-height:100vh}.side{border-right:1px solid var(--line);background:#080a0fdd;backdrop-filter:blur(18px);padding:22px 16px;position:sticky;top:0;height:100vh}.brand{font-size:19px;font-weight:800;letter-spacing:.12em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.2em;margin-top:4px}.nav{margin-top:28px;display:grid;gap:5px}.nav button{border:0;background:transparent;color:#aeb6c6;text-align:left;padding:11px 12px;border-radius:10px}.nav button:hover{background:#171b25;color:#fff}.nav .primary{background:linear-gradient(135deg,#e0c17a,#9b7940);color:#0b0b0d;font-weight:800;margin-bottom:12px}.main{padding:28px;max-width:1600px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:24px}.eyebrow{color:var(--gold);font-size:11px;letter-spacing:.18em;text-transform:uppercase}.title{font-size:31px;font-weight:800;margin:5px 0}.sub,.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:linear-gradient(180deg,#161a24f0,#0c0f15f0);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 24px 70px #0006}.metric b{font-size:28px;display:block}.metric span{color:var(--muted);font-size:12px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.input,.select,.textarea{background:#0c0f15;border:1px solid var(--line);color:#fff;border-radius:10px;padding:10px 12px;outline:none}.input:focus,.select:focus,.textarea:focus{border-color:#70798b}.btn{border:1px solid var(--line);background:#171b24;color:#fff;border-radius:10px;padding:10px 14px}.btn:hover{border-color:#4d5566}.btn.gold{background:var(--gold);color:#0a0b0e;border-color:var(--gold);font-weight:800}.drop{border:1px dashed #3b4352;border-radius:18px;padding:42px;text-align:center;background:#d8b46a0d}.drop.drag{border-color:var(--gold);background:#d8b46a1f}.drop strong{font-size:18px;display:block}.types{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin:14px 0}.type{padding:13px 8px;border:1px solid var(--line);background:#0d1016;border-radius:11px;color:#b9c0ce}.type.active{border-color:var(--gold);color:#fff;background:#191710}.list{margin-top:18px;overflow:auto}.row{display:grid;grid-template-columns:1.6fr .7fr .7fr .8fr auto;gap:12px;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)}.badge{display:inline-flex;padding:4px 8px;border-radius:999px;background:#1b202b;color:#c8ced9;font-size:11px}.login{min-height:100vh;display:grid;place-items:center;padding:20px}.loginbox{width:min(430px,100%)}.modal{position:fixed;inset:0;background:#000b;display:none;align-items:center;justify-content:center;padding:22px;z-index:20}.modal.open{display:flex}.modalbox{width:min(920px,100%);max-height:90vh;overflow:auto;background:#0d1016;border:1px solid var(--line);border-radius:18px;padding:24px}.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.full{grid-column:1/-1}.field label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.textarea{min-height:110px;width:100%;resize:vertical}.toast{position:fixed;right:20px;bottom:20px;background:#161b25;border:1px solid var(--line);padding:12px 15px;border-radius:11px;z-index:50}@media(max-width:1050px){.grid{grid-template-columns:repeat(2,1fr)}.types{grid-template-columns:repeat(4,1fr)}.shell{grid-template-columns:1fr}.side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap}.nav .primary{margin:0}}@media(max-width:650px){.main{padding:18px}.grid,.formgrid{grid-template-columns:1fr}.types{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr 1fr}.row>*:nth-child(n+3){display:none}}
</style>
</head>
<body>
<div id="login" class="login"><div class="loginbox card"><div class="eyebrow">PANELVERSE</div><div class="title">Archive Control</div><p class="sub">Unified ingestion, QC, review and publication.</p><input id="token" class="input" style="width:100%;margin:14px 0" type="password" placeholder="Admin web token"><button class="btn gold" style="width:100%" onclick="login()">Enter Control Center</button><p id="loginerr" class="muted"></p></div></div>
<div id="app" class="shell hidden"><aside class="side"><div class="brand">PANELVERSE<small>ARCHIVE CONTROL</small></div><div class="nav">
<button class="primary" onclick="openIngest()">＋ Add to Archive</button><button onclick="loadDashboard()">Overview</button><button onclick="loadItems()">Archive</button><button onclick="loadItems('BOOK')">Books</button><button onclick="loadItems('COMIC')">Comics</button><button onclick="loadItems('MANGA')">Manga</button><button onclick="loadItems('ANIME')">Anime</button><button onclick="loadItems('MOVIE')">Movies</button><button onclick="loadItems('VIDEO')">Video</button><button onclick="loadItems('MUSIC')">Music</button><button onclick="loadAudit()">Activity</button><button onclick="logout()">Sign out</button>
</div></aside><main class="main"><div class="top"><div><div class="eyebrow">UNIFIED ARCHIVE</div><div id="heading" class="title">Command Center</div><div id="subtitle" class="sub">One ingestion pipeline for every PanelVerse category.</div></div><button class="btn gold" onclick="openIngest()">＋ Add to Archive</button></div><section id="content"></section></main></div>
<div id="modal" class="modal"><div id="modalbox" class="modalbox"></div></div><div id="toast" class="toast hidden"></div>
<script>
var type='BOOK', selectedFiles=[];
function $(id){return document.getElementById(id)}
async function api(path,opt){opt=opt||{};var r=await fetch(path,Object.assign({credentials:'same-origin'},opt));if(r.status===401){showLogin();throw Error('Unauthorized')}var d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
function showLogin(){$('app').classList.add('hidden');$('login').classList.remove('hidden')}
async function login(){try{await api('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('token').value})});$('login').classList.add('hidden');$('app').classList.remove('hidden');loadDashboard()}catch(e){$('loginerr').textContent=e.message}}
async function logout(){await api('/api/admin/logout',{method:'POST'});showLogin()}
function toast(t){$('toast').textContent=t;$('toast').classList.remove('hidden');setTimeout(function(){$('toast').classList.add('hidden')},2800)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]})}
function metric(a,b){return '<div class="card metric"><span>'+a+'</span><b>'+b+'</b></div>'}
function quick(t,f,d){return '<button class="card" style="text-align:left;color:#fff" onclick="openIngest(\\''+t+'\\')"><b>'+t+'</b><div class="muted">'+f+' · '+d+'</div></button>'}
function loadDashboard(){$('heading').textContent='Command Center';$('subtitle').textContent='Archive health, ingestion and publishing at a glance.';api('/api/archive/stats').then(function(d){$('content').innerHTML='<div class="grid">'+metric('Archive Items',d.stats.items)+metric('Drafts',d.stats.draft)+metric('Review',d.stats.review)+metric('Published',d.stats.published)+'</div><div class="card" style="margin-top:16px"><div class="eyebrow">WORKFLOW</div><h2>Ingestion pipeline</h2><p class="muted">Upload → detection → metadata → duplicate check → QC → review → publish → optional Telegram distribution.</p><div class="toolbar"><button class="btn gold" onclick="openIngest()">Start ingestion</button><button class="btn" onclick="loadItems(\\'\\',\\'REVIEW\\')">Review queue</button><button class="btn" onclick="loadItems(\\'\\',\\'DRAFT\\')">Drafts</button></div></div><div class="card" style="margin-top:16px"><div class="eyebrow">QUICK START</div><div class="grid" style="grid-template-columns:repeat(3,1fr)">'+quick('BOOK','PDF / EPUB','Books and reference material')+quick('MANGA','CBZ / CBR','Comics and manga archives')+quick('MUSIC','MP3 / FLAC','Albums and audio')+'</div></div>'}).catch(function(e){toast(e.message)})}
function openIngest(t){type=t||'BOOK';$('modalbox').innerHTML='<div class="top"><div><div class="eyebrow">ADD TO ARCHIVE</div><h2>New ingestion</h2><div class="muted">Drop files, let PanelVerse analyze them, then review before publication.</div></div><button class="btn" onclick="closeModal()">Close</button></div><div class="types">'+['BOOK','COMIC','MANGA','ANIME','MOVIE','VIDEO','MUSIC'].map(function(x){return '<button class="type '+(x===type?'active':'')+'" onclick="setType(\\''+x+'\\')">'+x+'</button>'}).join('')+'</div><div id="drop" class="drop" onclick="$(\\'fileinput\\').click()"><strong>Drop files here</strong><p>or click to browse · multiple files supported · server validates MIME and extension</p><input id="fileinput" class="hidden" type="file" multiple onchange="pickFiles(this.files)"></div><div id="files" class="card" style="margin-top:14px;display:none"></div><div class="toolbar" style="justify-content:flex-end"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn gold" onclick="uploadFiles()">Analyze & Upload</button></div>';$('modal').classList.add('open');selectedFiles=[];bindDrop()}
function setType(x){type=x;openIngest(x)}
function bindDrop(){var d=$('drop');d.addEventListener('dragover',function(e){e.preventDefault();d.classList.add('drag')});d.addEventListener('dragleave',function(){d.classList.remove('drag')});d.addEventListener('drop',function(e){e.preventDefault();d.classList.remove('drag');pickFiles(e.dataTransfer.files)})}
function pickFiles(files){selectedFiles=Array.from(files);$('files').style.display='block';$('files').innerHTML=selectedFiles.map(function(f){return '<div style="padding:7px 0;border-bottom:1px solid var(--line)"><b>'+esc(f.name)+'</b><span class="muted"> · '+(f.size/1024/1024).toFixed(2)+' MB</span></div>'}).join('')}
async function uploadFiles(){if(!selectedFiles.length)return toast('Select at least one file.');var fd=new FormData();fd.append('content_type',type);selectedFiles.forEach(function(f){fd.append('files',f,f.name)});try{var d=await api('/api/archive/ingest',{method:'POST',body:fd});closeModal();toast(d.files.length+' file(s) queued for analysis');loadItems('','REVIEW')}catch(e){toast(e.message)}}
async function loadItems(t,s){t=t||'';s=s||($('status')?$('status').value:'');var q=$('search')?$('search').value:'';$('heading').textContent=t?t+' Archive':'Archive';$('subtitle').textContent='Search, filter, review and manage unified archive records.';var d=await api('/api/archive/items?type='+encodeURIComponent(t)+'&status='+encodeURIComponent(s)+'&q='+encodeURIComponent(q));$('content').innerHTML='<div class="toolbar"><input id="search" class="input" placeholder="Search archive…" onkeydown="if(event.key===\\'Enter\\')loadItems()"><select id="status" class="select" onchange="loadItems(\\'\\',this.value)"><option value="">All statuses</option><option>DRAFT</option><option>REVIEW</option><option>APPROVED</option><option>PUBLISHED</option><option>ARCHIVED</option><option>REJECTED</option></select><button class="btn gold" onclick="openIngest()">＋ Add to Archive</button></div><div class="card list">'+(d.items.length?d.items.map(itemRow).join(''):'<div class="muted">No archive items match this view.</div>')+'</div>'}
function itemRow(x){return '<div class="row"><div><b>'+esc(x.title||'Untitled')+'</b><div class="muted">'+esc(x.content_type)+' · '+esc(x.created_at)+'</div></div><span class="badge">'+esc(x.status)+'</span><span class="badge">'+esc(x.completeness)+'% complete</span><span class="badge">'+esc(x.detected_confidence)+'% detection</span><button class="btn" onclick="viewItem('+x.id+')">Open</button></div>'}
async function viewItem(id){var x=await api('/api/archive/items/'+id),m=x.metadata||{};$('modalbox').innerHTML='<div class="top"><div><div class="eyebrow">'+esc(x.content_type)+'</div><h2>'+esc(x.title)+'</h2><div class="muted">'+esc(x.status)+' · '+x.completeness+'% complete · '+x.detected_confidence+'% detection</div></div><button class="btn" onclick="closeModal()">Close</button></div><div class="formgrid"><div class="field"><label>Title</label><input id="etitle" class="input" style="width:100%" value="'+esc(x.title)+'"></div><div class="field"><label>Content type</label><select id="etype" class="select" style="width:100%">'+['BOOK','COMIC','MANGA','ANIME','MOVIE','VIDEO','MUSIC'].map(function(t){return '<option '+(t===x.content_type?'selected':'')+'>'+t+'</option>'}).join('')+'</select></div><div class="field full"><label>Description</label><textarea id="edesc" class="textarea">'+esc(x.description)+'</textarea></div><div class="field full"><label>Metadata JSON</label><textarea id="emeta" class="textarea">'+esc(JSON.stringify(m,null,2))+'</textarea></div></div><div class="card" style="margin-top:14px"><b>QC / detection</b><pre style="white-space:pre-wrap;color:#aeb6c6">'+esc(JSON.stringify(m._qc||{},null,2))+'</pre></div><div class="toolbar"><button class="btn" onclick="saveItem('+id+')">Save</button><button class="btn" onclick="transition('+id+',\\'draft\\')">Draft</button><button class="btn" onclick="transition('+id+',\\'review\\')">Send to review</button><button class="btn gold" onclick="transition('+id+',\\'approve\\')">Approve</button><button class="btn gold" onclick="transition('+id+',\\'publish\\')">Publish</button><button class="btn" onclick="telegram('+id+')">Publish to Telegram</button></div><div class="card" style="margin-top:12px"><b>Files</b>'+(x.files||[]).map(function(f){return '<div style="padding:8px 0;border-bottom:1px solid var(--line)"><a style="color:var(--gold)" href="/api/archive/items/'+id+'/files/'+f.id+'">'+esc(f.original_name)+'</a><span class="muted"> · '+(f.size_bytes/1024/1024).toFixed(2)+' MB · '+esc(f.mime_type)+'</span></div>'}).join('')+'</div>';$('modal').classList.add('open')}
async function saveItem(id){var meta={};try{meta=JSON.parse($('emeta').value)}catch(e){return toast('Metadata JSON is invalid.')}await api('/api/archive/items/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('etitle').value,content_type:$('etype').value,description:$('edesc').value,metadata_json:meta})});toast('Saved');viewItem(id)}
async function transition(id,a){try{await api('/api/archive/items/'+id+'/'+a,{method:'POST'});toast('Status updated');viewItem(id)}catch(e){toast(e.message)}}
async function telegram(id){try{var d=await api('/api/archive/items/'+id+'/telegram',{method:'POST'});toast('Telegram publication queued #'+d.job_id)}catch(e){toast(e.message)}}
async function loadAudit(){var d=await api('/api/archive/audit');$('heading').textContent='Activity';$('subtitle').textContent='Archive ingestion and administration audit trail.';$('content').innerHTML='<div class="card list">'+d.events.map(function(e){return '<div class="row" style="grid-template-columns:1fr 1fr 1fr"><div><b>'+esc(e.action)+'</b></div><div>'+esc(e.actor)+'</div><div class="muted">'+esc(e.created_at)+'</div></div>'}).join('')+'</div>'}
function closeModal(){$('modal').classList.remove('open')}
(async function(){try{await api('/api/archive/stats');$('login').classList.add('hidden');$('app').classList.remove('hidden');loadDashboard()}catch(e){showLogin()}})();
</script>
</body></html>"""
