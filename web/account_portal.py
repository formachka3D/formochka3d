"""Staging account, newsletter-consent and administrator views for Formochka3D.

Add to web/app.py:
    from web.account_portal import router as account_router
    app.include_router(account_router)

Environment:
    FORMOCHKA_ACCOUNT_DB=/app/data/staging-users.sqlite3
    FORMOCHKA_PUBLIC_URL=https://test.formochka3d.ru
    FORMOCHKA_SMTP_HOST, FORMOCHKA_SMTP_USER, FORMOCHKA_SMTP_PASSWORD
Never reuse the staging database in production.
"""
from __future__ import annotations

import asyncio
import csv
import html
import io
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from web.account_store import AccountStore, normalize_email
from web.account_mailer import send_account_email, smtp_settings

router = APIRouter()
COOKIE = "__Host-f3d-session"
DB_PATH = os.environ.get("FORMOCHKA_ACCOUNT_DB", "/app/data/staging-users.sqlite3")
BASE_URL = os.environ.get("FORMOCHKA_PUBLIC_URL", "https://test.formochka3d.ru").rstrip("/")
store = AccountStore(DB_PATH)

with store.connect() as conn:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            consent_at INTEGER NOT NULL,
            unsubscribed_at INTEGER,
            source TEXT NOT NULL DEFAULT 'registration'
        );
        CREATE INDEX IF NOT EXISTS ix_newsletter_active
            ON newsletter_subscriptions(unsubscribed_at);
    """)

_rate_lock = threading.Lock()
_attempts = defaultdict(deque)


def throttle(request: Request, action: str, key: str, maximum: int, seconds: int):
    """Per-process abuse control; production should add edge-level IP rate limiting."""
    origin = request.client.host if request.client else "unknown"
    tag = (action, origin, key.casefold()[:180])
    now = time.monotonic()
    with _rate_lock:
        hits = _attempts[tag]
        while hits and now - hits[0] > seconds:
            hits.popleft()
        if len(hits) >= maximum:
            raise HTTPException(429, "Слишком много попыток. Попробуйте позже.")
        hits.append(now)


def require_json(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Используйте JSON")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != BASE_URL:
        raise HTTPException(403, "Недопустимый источник запроса")


def current_user(request: Request, admin: bool = False):
    token = request.cookies.get(COOKIE)
    result = store.get_session(token) if token else None
    if result is None:
        raise HTTPException(401, "Требуется войти в аккаунт")
    if admin and result["role"] != "admin":
        raise HTTPException(403, "Недостаточно прав")
    return result


def send_later(recipient: str, kind: str, token: str):
    return asyncio.to_thread(send_account_email, recipient, kind, token, base_url=BASE_URL)


def safe_date(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if ts else "—"


class Signup(BaseModel):
    email: str = Field(min_length=4, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    newsletter: bool = False


class Login(BaseModel):
    email: str
    password: str


class EmailOnly(BaseModel):
    email: str


class ResetFinish(BaseModel):
    token: str = Field(min_length=24, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class Newsletter(BaseModel):
    subscribed: bool


class DisableUser(BaseModel):
    disabled: bool


PAGE_STYLE = """<style>
*{box-sizing:border-box}body{margin:0;background:#fff8f5;color:#46332f;
font:16px Arial,sans-serif}header{padding:22px 28px;background:#fff;
border-bottom:1px solid #f3ddd4;display:flex;justify-content:space-between;align-items:center}
a{color:#a64d62}h1,h2{color:#754d50}main{max-width:1080px;margin:36px auto;padding:0 18px}
.panel{background:#fff;border-radius:22px;border:1px solid #f3e2dc;
padding:28px;box-shadow:0 12px 36px #6f42350b;margin-bottom:18px}
.brand{font-size:25px;font-weight:800;color:#e18257;text-decoration:none}
button,.action{background:#e7845e;color:white;border:0;border-radius:11px;
padding:12px 17px;cursor:pointer;font-weight:bold;text-decoration:none}
button.secondary{background:#f5dfd9;color:#6a4942}
input[type=email],input[type=password],input[type=search],select{width:100%;max-width:440px;
padding:13px;margin:8px 0 17px;border:1px solid #e8cdc1;border-radius:9px;font-size:15px}
label{display:block;margin-top:6px}small,.muted{color:#856c64}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}
.stat{background:#fff1e9;border-radius:14px;padding:18px}
.stat strong{display:block;font-size:28px;color:#d36b5d;margin-top:8px}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:700px}
th,td{text-align:left;padding:12px;border-bottom:1px solid #f2e6e0}
th{background:#fff7f3}#message{padding:12px;color:#89503e;min-height:26px}
@media(max-width:600px){header{padding:15px;gap:8px}main{margin:16px auto}.panel{padding:17px}}
</style>"""


def page(title: str, body: str, script: str = ""):
    return ("<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)} — Formochka3D</title>{PAGE_STYLE}</head><body>"
            "<header><a class='brand' href='/'>🍓 Formochka3D</a>"
            "<a href='/account/'>Личный кабинет</a></header>"
            f"<main>{body}</main>{script}</body></html>")


@router.get("/account/", response_class=HTMLResponse)
def account_home(request: Request):
    user = store.get_session(request.cookies.get(COOKIE, ""))
    if user:
        with store.connect() as db:
            subscription = db.execute(
                "SELECT unsubscribed_at FROM newsletter_subscriptions WHERE user_id=?",
                (user["id"],)).fetchone()
        checked = subscription is not None and subscription["unsubscribed_at"] is None
        admin_link = "<a class='action' href='/admin/'>Открыть админку</a>" if user["role"] == "admin" else ""
        markup = (f"<section class='panel'><h1>Здравствуйте, {html.escape(user['email'])}!</h1>"
                  f"<p>Ваш личный кабинет.</p>{admin_link}"
                  "<label><input id='opt' type='checkbox' "
                  + ("checked" if checked else "") + "> Хочу получать новости и предложения по электронной почте</label>"
                  "<p><button onclick='newsletter()'>Сохранить подписку</button> "
                  "<button class='secondary' onclick='logout()'>Выйти</button></p>"
                  "<div id='message' role='status'></div></section>")
    else:
        markup = """<div class='grid'>
<section class='panel'><h1>Войти</h1>
<label>Электронная почта<input id='login-email' type='email' autocomplete='username'></label>
<label>Пароль<input id='login-password' type='password' autocomplete='current-password'></label>
<button onclick='login()'>Войти</button>
<p><a href='/account/forgot'>Забыли пароль?</a></p></section>
<section class='panel'><h1>Регистрация</h1>
<label>Электронная почта<input id='signup-email' type='email' autocomplete='email'></label>
<label>Пароль (минимум 12 символов)<input id='signup-password' type='password'
autocomplete='new-password' minlength='12'></label>
<label><input id='signup-newsletter' type='checkbox'>
Хочу получать новости и рекламные предложения Formochka3D (необязательно)</label>
<p><small>Регистрация не означает согласие на рекламную рассылку.</small></p>
<button onclick='signup()'>Зарегистрироваться</button></section></div>
<div id='message' role='status'></div>"""
    script = """<script>
async function send(url,body){let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(body),credentials:'same-origin'});let data=await r.json();
if(!r.ok)throw Error(data.detail||'Ошибка запроса');return data;}
let el=document.getElementById('message');
function show(s){el.textContent=s;}
async function login(){try{await send('/account/login',{email:document.getElementById('login-email').value,
password:document.getElementById('login-password').value});location.reload()}catch(e){show(e.message)}}
async function signup(){try{let r=await send('/account/signup',{
email:document.getElementById('signup-email').value,
password:document.getElementById('signup-password').value,
newsletter:document.getElementById('signup-newsletter').checked});
show(r.message)}catch(e){show(e.message)}}
async function logout(){try{await send('/account/logout',{});location.href='/account/'}catch(e){show(e.message)}}
async function newsletter(){try{await send('/account/newsletter',{subscribed:document.getElementById('opt').checked});
show('Настройки подписки сохранены')}catch(e){show(e.message)}}
</script>"""
    return page("Личный кабинет", markup, script)


@router.post("/account/signup")
async def signup(request: Request, data: Signup):
    require_json(request)
    try:
        email = normalize_email(data.email)
    except ValueError:
        raise HTTPException(400, "Проверьте адрес электронной почты")
    throttle(request, "signup", email, 4, 3600)
    # Fail closed: users must be able to verify their email before signup is enabled.
    try:
        smtp_settings()
    except RuntimeError:
        raise HTTPException(503, "Регистрация пока настраивается. Попробуйте позже.")
    try:
        user_id = store.register(email, data.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Этот адрес уже зарегистрирован")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if data.newsletter:
        with store.connect() as db:
            db.execute("INSERT INTO newsletter_subscriptions(user_id,consent_at,source) VALUES(?,?,?)",
                       (user_id, int(time.time()), "registration"))
    token = store.issue_one_time(user_id, "verify", 86400)
    try:
        await send_later(email, "verify", token)
    except Exception:
        # Keep pending account; allow retry via /account/resend-verification.
        raise HTTPException(502, "Аккаунт создан, но письмо пока не отправлено. Попробуйте запросить его повторно.")
    return {"message": "Письмо для подтверждения отправлено. Проверьте почту."}


@router.post("/account/resend-verification")
async def resend(request: Request, data: EmailOnly):
    require_json(request)
    try:
        email = normalize_email(data.email)
    except ValueError:
        raise HTTPException(400, "Проверьте адрес электронной почты")
    throttle(request, "resend", email, 3, 3600)
    user = store.find_user(email)
    if user and not user["verified_at"] and not user["disabled_at"]:
        try:
            smtp_settings()
            token = store.issue_one_time(user["id"], "verify", 86400)
            await send_later(email, "verify", token)
        except Exception:
            pass  # Do not disclose whether email exists.
    return {"message": "Если адрес зарегистрирован, письмо будет отправлено."}


@router.get("/account/verify", response_class=HTMLResponse)
def verify(token: str = Query(..., min_length=24, max_length=256)):
    success = store.consume_one_time(token, "verify")
    message = ("Адрес подтверждён! Теперь можно войти." if success
               else "Ссылка недействительна или срок действия истёк.")
    return page("Подтверждение почты", f"<section class='panel'><h1>{message}</h1>"
                "<p><a class='action' href='/account/'>Перейти к входу</a></p></section>")


@router.post("/account/login")
def login(request: Request, response: Response, data: Login):
    require_json(request)
    throttle(request, "login", data.email, 12, 900)
    try:
        user = store.authenticate(data.email, data.password)
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(401, "Неверные данные или почта ещё не подтверждена")
    token = store.create_session(user["id"])
    response.set_cookie(COOKIE, token, max_age=14*86400, httponly=True, secure=True,
                        samesite="lax", path="/")
    return {"ok": True, "role": user["role"]}


@router.post("/account/logout")
def logout(request: Request, response: Response):
    require_json(request)
    token = request.cookies.get(COOKIE)
    if token:
        store.logout(token)
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return {"ok": True}


@router.get("/account/forgot", response_class=HTMLResponse)
def forgot():
    markup = """<section class='panel'><h1>Восстановить пароль</h1>
<p>Отправим ссылку для восстановления на вашу почту.</p>
<input id='email' type='email' placeholder='Электронная почта'>
<button onclick='go()'>Отправить ссылку</button><div id='message' role='status'></div></section>"""
    script = """<script>async function go(){let r=await fetch('/account/forgot',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value})});
let data=await r.json();document.getElementById('message').textContent=data.message||data.detail}</script>"""
    return page("Восстановление пароля", markup, script)


@router.post("/account/forgot")
async def forgot_send(request: Request, data: EmailOnly):
    require_json(request)
    try:
        email = normalize_email(data.email)
    except ValueError:
        raise HTTPException(400, "Проверьте адрес электронной почты")
    throttle(request, "forgot", email, 4, 3600)
    user = store.find_user(email)
    if user and user["verified_at"] and not user["disabled_at"]:
        try:
            smtp_settings()
            token = store.issue_one_time(user["id"], "reset", 3600)
            await send_later(email, "reset", token)
        except Exception:
            pass
    return {"message": "Если адрес зарегистрирован, ссылка для восстановления отправлена."}


@router.get("/account/reset", response_class=HTMLResponse)
def reset_page(token: str = Query(..., min_length=24, max_length=256)):
    # Token inserted into JS through JSON-like escaping of quotes and markup.
    import json
    markup = """<section class='panel'><h1>Новый пароль</h1>
<input id='password' type='password' autocomplete='new-password' minlength='12'
placeholder='Не менее 12 символов'><button onclick='go()'>Сохранить новый пароль</button>
<div id='message' role='status'></div></section>"""
    script = """<script>async function go(){let r=await fetch('/account/reset',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({token:TOKEN,
password:document.getElementById('password').value})});let d=await r.json();
document.getElementById('message').textContent=d.message||d.detail}</script>"""
    script = script.replace("TOKEN", json.dumps(token).replace("<", "\\u003c"))
    return page("Новый пароль", markup, script)


@router.post("/account/reset")
def reset_finish(request: Request, data: ResetFinish):
    require_json(request)
    throttle(request, "reset", "token", 15, 3600)
    try:
        success = store.consume_one_time(data.token, "reset", data.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not success:
        raise HTTPException(400, "Ссылка недействительна или срок действия истёк")
    return {"message": "Пароль изменён. Теперь можно войти."}


@router.post("/account/newsletter")
def newsletter(request: Request, data: Newsletter):
    require_json(request)
    user = current_user(request)
    if data.subscribed:
        with store.connect() as db:
            db.execute("""INSERT INTO newsletter_subscriptions(user_id,consent_at,unsubscribed_at,source)
                VALUES(?,?,NULL,'account')
                ON CONFLICT(user_id) DO UPDATE SET consent_at=excluded.consent_at,
                    unsubscribed_at=NULL,source='account'""", (user["id"], int(time.time())))
    else:
        with store.connect() as db:
            db.execute("UPDATE newsletter_subscriptions SET unsubscribed_at=? WHERE user_id=?",
                       (int(time.time()), user["id"]))
    return {"ok": True, "subscribed": data.subscribed}


def fetch_users(search: str, offset: int, limit: int):
    like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "u.role='user' AND u.email LIKE ? ESCAPE '\\'"
    with store.connect() as db:
        rows = db.execute(f"""SELECT u.id,u.email,u.created_at,u.verified_at,u.disabled_at,
            n.consent_at,n.unsubscribed_at FROM users u
            LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id
            WHERE {where} ORDER BY u.created_at DESC,u.id DESC LIMIT ? OFFSET ?""",
            (like, limit, offset)).fetchall()
    return [{"id": r["id"], "email": r["email"],
             "registered": safe_date(r["created_at"]),
             "verified": r["verified_at"] is not None,
             "disabled": r["disabled_at"] is not None,
             "newsletter": r["consent_at"] is not None and r["unsubscribed_at"] is None,
             "consent_at": safe_date(r["consent_at"])} for r in rows]


@router.get("/admin/", response_class=HTMLResponse)
def admin_home(request: Request):
    current_user(request, admin=True)
    markup = """<h1>🍓 Админка Formochka3D</h1>
<div class='grid'>
<div class='stat'>Всего пользователей<strong id='total'>—</strong></div>
<div class='stat'>Подтвердили почту<strong id='verified'>—</strong></div>
<div class='stat'>Подписаны на рассылку<strong id='subscribed'>—</strong></div>
<div class='stat'>Зарегистрировались сегодня (UTC)<strong id='today'>—</strong></div></div>
<section class='panel' style='margin-top:20px'>
<h2>Пользователи</h2>
<input id='search' type='search' placeholder='Поиск по электронной почте'>
<label>Фильтр <select id='filter'><option value='all'>Все</option>
<option value='newsletter'>Подписчики</option>
<option value='unverified'>Не подтвердили почту</option></select></label>
<p><button onclick='load()'>Найти</button>
<a class='action' id='export' href='/admin/users.csv'>Выгрузить CSV для Excel</a></p>
<div class='table-wrap'><table><thead><tr><th>Адрес</th><th>Регистрация</th>
<th>Почта</th><th>Рассылка</th><th>Статус</th><th>Действия</th></tr></thead>
<tbody id='users'></tbody></table></div>
<p><button class='secondary' onclick='prev()'>Назад</button>
<span id='page'></span>
<button class='secondary' onclick='next()'>Дальше</button></p>
<div id='message' role='status'></div></section>"""
    script = """<script>
let offset=0,limit=25,count=0;
function cell(text){let td=document.createElement('td');td.textContent=text;return td}
async function load(){let q=document.getElementById('search').value;
let f=document.getElementById('filter').value;
let params=new URLSearchParams({search:q,filter:f,offset:String(offset),limit:String(limit)});
let r=await fetch('/admin/api/users?'+params);if(!r.ok){location.href='/account/';return}
let d=await r.json();count=d.matched;
for(let k of ['total','verified','subscribed','today'])document.getElementById(k).textContent=d.stats[k];
let tbody=document.getElementById('users');tbody.replaceChildren();
for(let u of d.users){let tr=document.createElement('tr');
tr.append(cell(u.email),cell(u.registered),cell(u.verified?'Да':'Нет'),cell(u.newsletter?'Да':'Нет'),
cell(u.disabled?'Заблокирован':'Активен'));
let td=document.createElement('td'),b=document.createElement('button');b.className='secondary';
b.textContent=u.disabled?'Разблокировать':'Заблокировать';
b.onclick=async()=>{if(!confirm('Изменить доступ пользователя?'))return;
let r=await fetch('/admin/api/users/'+u.id+'/disable',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({disabled:!u.disabled})});
if(r.ok)load();else document.getElementById('message').textContent='Не удалось изменить статус'};
td.append(b);tr.append(td);tbody.append(tr)}
document.getElementById('page').textContent=(offset+1)+'–'+Math.min(offset+limit,count)+' из '+count;
document.getElementById('export').href='/admin/users.csv?'+new URLSearchParams({search:q,filter:f});
}
function next(){if(offset+limit<count){offset+=limit;load()}}
function prev(){offset=Math.max(0,offset-limit);load()}
document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter'){offset=0;load()}});
document.getElementById('filter').addEventListener('change',()=>{offset=0;load()});load();
</script>"""
    return page("Администрирование", markup, script)


def admin_filter(filter_value: str):
    return {"all": "", "newsletter": " AND n.consent_at IS NOT NULL AND n.unsubscribed_at IS NULL",
            "unverified": " AND u.verified_at IS NULL"}[filter_value]


@router.get("/admin/api/users")
def admin_list(request: Request, search: str = Query("", max_length=120),
               filter: str = Query("all", pattern="^(all|newsletter|unverified)$"),
               offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    current_user(request, admin=True)
    like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "u.role='user' AND u.email LIKE ? ESCAPE '\\'" + admin_filter(filter)
    join = "LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id"
    with store.connect() as db:
        stats = db.execute("""SELECT
            COUNT(*) total,
            COUNT(CASE WHEN u.verified_at IS NOT NULL THEN 1 END) verified,
            COUNT(CASE WHEN n.consent_at IS NOT NULL AND n.unsubscribed_at IS NULL THEN 1 END) subscribed,
            COUNT(CASE WHEN u.created_at >= ? THEN 1 END) today
            FROM users u LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id WHERE u.role='user'""",
            (int(time.time()) // 86400 * 86400,)).fetchone()
        matched = db.execute(f"SELECT COUNT(*) FROM users u {join} WHERE {where}", (like,)).fetchone()[0]
        rows = db.execute(f"""SELECT u.id,u.email,u.created_at,u.verified_at,u.disabled_at,
            n.consent_at,n.unsubscribed_at FROM users u {join}
            WHERE {where} ORDER BY u.created_at DESC,u.id DESC LIMIT ? OFFSET ?""",
            (like, limit, offset)).fetchall()
    users = [{"id": row["id"], "email": row["email"], "registered": safe_date(row["created_at"]),
              "verified": row["verified_at"] is not None, "disabled": row["disabled_at"] is not None,
              "newsletter": row["consent_at"] is not None and row["unsubscribed_at"] is None}
             for row in rows]
    return JSONResponse({"users": users, "matched": matched, "stats": dict(stats)},
                        headers={"Cache-Control": "no-store"})


def spreadsheet_cell(text: str):
    """Prevent CSV formula injection when opened in Excel."""
    value = str(text)
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@router.get("/admin/users.csv")
def admin_csv(request: Request, search: str = Query("", max_length=120),
              filter: str = Query("all", pattern="^(all|newsletter|unverified)$")):
    current_user(request, admin=True)
    like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "u.role='user' AND u.email LIKE ? ESCAPE '\\'" + admin_filter(filter)
    with store.connect() as db:
        rows = db.execute(f"""SELECT u.email,u.created_at,u.verified_at,u.disabled_at,
            n.consent_at,n.unsubscribed_at FROM users u
            LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id WHERE {where}
            ORDER BY u.created_at DESC,u.id DESC""", (like,)).fetchall()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Email", "Регистрация (UTC)", "Почта подтверждена",
                     "Рассылка", "Согласие (UTC)", "Заблокирован"])
    for r in rows:
        subscribed = r["consent_at"] is not None and r["unsubscribed_at"] is None
        writer.writerow([spreadsheet_cell(r["email"]), safe_date(r["created_at"]),
                         "Да" if r["verified_at"] else "Нет",
                         "Да" if subscribed else "Нет",
                         safe_date(r["consent_at"]), "Да" if r["disabled_at"] else "Нет"])
    output = "\ufeff" + out.getvalue()
    return Response(output, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=formochka3d-users.csv",
                             "Cache-Control": "no-store"})


@router.post("/admin/api/users/{user_id}/disable")
def admin_disable(request: Request, user_id: int, data: DisableUser):
    require_json(request)
    current_user(request, admin=True)
    with store.connect() as db:
        row = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or row["role"] != "user":
        raise HTTPException(404, "Пользователь не найден")
    store.set_disabled(user_id, data.disabled)
    return {"ok": True}


@router.get("/admin/health")
def admin_health(request: Request):
    current_user(request, admin=True)
    return {"ok": True, "storage": "sqlite"}
