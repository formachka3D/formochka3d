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
from web.account_extras import router as extras_router, initialize as initialize_extras, verify_captcha, clean_name, AVATARS

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
    initialize_extras(conn)

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
    display_name: str = Field(min_length=2, max_length=60)
    email: str = Field(min_length=4, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    avatar_emoji: str = Field(default="🍪")
    captcha_id: str = Field(min_length=20, max_length=64)
    captcha_answer: str = Field(min_length=1, max_length=12)
    privacy_accepted: bool = False
    newsletter: bool = False
    website: str = ""


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
button.secondary{background:#f5dfd9;color:#6a4942}button:disabled{opacity:.55;cursor:wait}.linkbutton{background:none;color:#a64d62;padding:7px;text-decoration:underline}
input[type=email],input[type=password],input[type=search],select{width:100%;max-width:440px;
padding:13px;margin:8px 0 17px;border:1px solid #e8cdc1;border-radius:9px;font-size:15px}
label{display:block;margin-top:6px}small,.muted{color:#856c64}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}
.stat{background:#fff1e9;border-radius:14px;padding:18px}
.stat strong{display:block;font-size:28px;color:#d36b5d;margin-top:8px}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:700px}
th,td{text-align:left;padding:12px;border-bottom:1px solid #f2e6e0}
th{background:#fff7f3}.avatars{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.av{font-size:27px;border:2px solid #f1dcd5;background:#fff4f0;border-radius:15px;padding:7px 10px}.av.selected{border-color:#da7c6d;background:#fff0e3}.pass{display:flex;align-items:center;gap:4px}.pass input{flex:1;min-width:0}.pass button{margin:0 0 9px;white-space:nowrap}#message{padding:12px;color:#89503e;min-height:26px}
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
def account_home(request: Request, mode: str = "login"):
    user = store.get_session(request.cookies.get(COOKIE, ""))
    if user:
        with store.connect() as db:
            subscription = db.execute(
                "SELECT unsubscribed_at FROM newsletter_subscriptions WHERE user_id=?",
                (user["id"],)).fetchone()
            profile = db.execute("SELECT display_name,avatar_emoji,avatar_filename FROM user_profiles WHERE user_id=?",
                                 (user["id"],)).fetchone()
        checked = subscription is not None and subscription["unsubscribed_at"] is None
        display_name = html.escape(profile["display_name"]) if profile else html.escape(user["email"].split("@")[0])
        avatar = html.escape(profile["avatar_emoji"]) if profile else "🍪"
        admin_link = "<p><a class='action' href='/admin/'>Открыть админку</a></p>" if user["role"] == "admin" else ""
        avatar_grid = "".join(f'<button class="av" type="button" onclick="chooseAvatar(this)" data-avatar="{html.escape(a)}">{html.escape(a)}</button>'
                              for a in AVATARS)
        points = store.points_balance(user["id"])
        markup = (f"<section class='panel'><h1>Привет, {display_name}! {avatar}</h1>"
                  f"<p class='stat' aria-label='Баланс пряничков'>🍪 Мои прянички: <strong>{points}</strong></p>"
                  "<p><a href='/'>← Вернуться на главную</a></p>"
                  f"{admin_link}<h2>Мой профиль</h2>"
                  f"<label>Имя<input id='profile-name' value='{display_name}' maxlength='60'></label>"
                  f"<p>Выбери аватарку:</p><div class='avatars'>{avatar_grid}</div>"
                  "<p><button onclick='saveProfile()'>Сохранить профиль</button></p>"
                  "<label>Или загрузи свою фотографию (PNG/JPEG/WEBP до 2 МБ)"
                  "<input id='photo' type='file' accept='image/png,image/jpeg,image/webp'></label>"
                  "<p><button onclick='uploadPhoto()'>Загрузить фотографию</button></p>"
                  "<hr style='border:0;border-top:1px solid #f3ddd4;margin:26px 0'>"
                  "<h2>Рассылка</h2>"
                  "<label><input id='opt' type='checkbox' "
                  + ("checked" if checked else "") +
                  "> Хочу получать новости и предложения Formochka3D</label>"
                  "<p><button onclick='newsletter()'>Сохранить подписку</button></p>"
                  "<button class='secondary' onclick='logout()'>Выйти</button>"
                  "<div id='message' role='status'></div></section>")
        script = """<script>
let selectedAvatar='🍪';let currentAvatar=JSON.parse(document.getElementById('avatar-init').textContent);
selectedAvatar=currentAvatar;
function chooseAvatar(btn){selectedAvatar=btn.dataset.avatar;document.querySelectorAll('.av').forEach(x=>x.classList.toggle('selected',x===btn))}
document.querySelectorAll('.av').forEach(x=>x.classList.toggle('selected',x.dataset.avatar===currentAvatar));
async function send(url,body){let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'same-origin'});let d=await r.json();if(!r.ok)throw Error(d.detail||'Ошибка');return d}
let message=document.getElementById('message');
async function saveProfile(){try{await send('/account/api/profile',{display_name:document.getElementById('profile-name').value,avatar_emoji:selectedAvatar});location.reload()}catch(e){message.textContent=e.message}}
async function uploadPhoto(){let file=document.getElementById('photo').files[0];if(!file){message.textContent='Сначала выбери фотографию';return}let fd=new FormData();fd.append('photo',file);
let r=await fetch('/account/api/avatar',{method:'POST',body:fd});let d=await r.json();if(!r.ok){message.textContent=d.detail||'Ошибка загрузки'}else{message.textContent='Фотография сохранена';location.reload()}}
async function newsletter(){try{await send('/account/newsletter',{subscribed:document.getElementById('opt').checked});message.textContent='Настройки подписки сохранены'}catch(e){message.textContent=e.message}}
async function logout(){await send('/account/logout',{});location.href='/'}
</script>"""
        # JSON encode to avoid injecting untrusted data into executable script.
        import json
        script = "<script type='application/json' id='avatar-init'>" + json.dumps(avatar).replace("<", "\\u003c") + "</script>" + script
        return page("Личный кабинет", markup, script)
    avatars = "".join(f'<button class="av" type="button" onclick="chooseAvatar(this)" data-avatar="{html.escape(a)}">{html.escape(a)}</button>'
                      for a in AVATARS)
    if mode == "register":
        markup = ("""<section class='panel' style='max-width:580px;margin:auto'><h1>Создать аккаунт 🍓</h1>
<p>Уже зарегистрированы? <a href='/account/'>Войти</a></p>
<form id='signup-form' onsubmit='signup(event)'>
<label>Как тебя зовут?<input required id='signup-name' minlength='2' maxlength='60' autocomplete='given-name'></label>
<label>Электронная почта<input required id='signup-email' type='email' autocomplete='email'></label>
<label>Придумай пароль (от 12 символов)<span class='pass'><input required id='signup-password'
type='password' minlength='12' autocomplete='new-password'><button class='secondary' type='button'
onclick="togglePassword('signup-password',this)">Показать</button></span></label>
<p>Выбери милую аватарку или добавь свою фотографию позже:</p><div class='avatars'>"""
                  + avatars + """</div>
<label>Введи символы с картинки:</label><div id='captcha-image' aria-label='Код с картинки'></div>
<button type='button' class='secondary' onclick='reloadCaptcha()'>↻ Другой код</button>
<label>Код с картинки<input required id='captcha-answer' autocomplete='off' maxlength='12'></label>
<input id='website' tabindex='-1' autocomplete='off' aria-hidden='true' style='position:absolute;left:-9999px'>
<label><input id='privacy' type='checkbox' required> Я ознакомился(-ась) с
<a href='/privacy/' target='_blank' rel='noopener'>условиями обработки данных тестового сайта</a>
и соглашаюсь с обработкой данных для создания аккаунта.</label>
<label><input id='signup-newsletter' type='checkbox'> Хочу получать новости и предложения по почте (необязательно)</label>
<p><button id='submit' type='submit'>Зарегистрироваться</button></p>
</form><div id='message' role='status'></div></section>""")
    else:
        markup = """<section class='panel' style='max-width:480px;margin:auto'><h1>С возвращением! 🍪</h1>
<form id='login-form' onsubmit='login(event)'>
<label>Электронная почта<input required id='login-email' type='email' autocomplete='username'></label>
<label>Пароль<span class='pass'><input required id='login-password' type='password'
autocomplete='current-password'><button class='secondary' type='button'
onclick="togglePassword('login-password',this)">Показать</button></span></label>
<p><button id='submit' type='submit'>Войти</button></p></form>
<p><a href='/account/forgot'>Забыли пароль?</a></p>
<p>Впервые у нас? <a href='/account/?mode=register'>Зарегистрироваться</a></p>
<div id='message' role='status'></div></section>"""
    script = """<script>
let selectedAvatar='🍪',captchaId='';
const message=document.getElementById('message');
const submit=document.getElementById('submit');
function togglePassword(id,btn){const e=document.getElementById(id);e.type=e.type==='password'?'text':'password';btn.textContent=e.type==='password'?'Показать':'Скрыть'}
function chooseAvatar(btn){selectedAvatar=btn.dataset.avatar;document.querySelectorAll('.av').forEach(x=>x.classList.toggle('selected',x===btn))}
const initial=document.querySelector('.av[data-avatar="🍪"]');if(initial)initial.classList.add('selected');
async function reloadCaptcha(){let r=await fetch('/account/captcha',{cache:'no-store'});if(!r.ok){message.textContent='Не удалось загрузить проверку';return}let d=await r.json();captchaId=d.id;document.getElementById('captcha-image').innerHTML=d.svg;document.getElementById('captcha-answer').value=''}
async function send(url,body){let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'same-origin'});let d=await r.json();if(!r.ok)throw Error(d.detail||'Ошибка сервера');return d}
async function login(e){e.preventDefault();submit.disabled=true;submit.textContent='Входим…';try{
await send('/account/login',{email:document.getElementById('login-email').value,password:document.getElementById('login-password').value});
location.href='/';}catch(err){message.textContent=err.message;submit.disabled=false;submit.textContent='Войти'}}
async function signup(e){e.preventDefault();submit.disabled=true;submit.textContent='Регистрируем…';try{
let d=await send('/account/signup',{display_name:document.getElementById('signup-name').value,
email:document.getElementById('signup-email').value,password:document.getElementById('signup-password').value,
avatar_emoji:selectedAvatar,captcha_id:captchaId,captcha_answer:document.getElementById('captcha-answer').value,
privacy_accepted:document.getElementById('privacy').checked,newsletter:document.getElementById('signup-newsletter').checked,
website:document.getElementById('website').value});document.getElementById('signup-form').style.display='none';message.textContent=d.message;
}catch(err){message.textContent=err.message;submit.disabled=false;submit.textContent='Зарегистрироваться';await reloadCaptcha()}}
if(document.getElementById('captcha-image'))reloadCaptcha();
</script>"""
    return page("Регистрация" if mode=="register" else "Вход", markup, script)


@router.post("/account/signup")
async def signup(request: Request, data: Signup):
    require_json(request)
    try:
        email = normalize_email(data.email)
    except ValueError:
        raise HTTPException(400, "Проверьте адрес электронной почты")
    throttle(request, "signup", email, 4, 3600)
    if data.website:
        raise HTTPException(400, "Не удалось подтвердить запрос")
    if not data.privacy_accepted:
        raise HTTPException(400, "Подтвердите согласие на обработку данных")
    try:
        name = clean_name(data.display_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if data.avatar_emoji not in AVATARS:
        raise HTTPException(400, "Выберите предложенную аватарку")
    with store.connect() as db:
        if not verify_captcha(db, data.captcha_id, data.captcha_answer):
            raise HTTPException(400, "Неверный код с картинки. Попробуйте ещё раз")
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
    with store.connect() as db:
        db.execute("""INSERT INTO user_profiles(user_id,display_name,avatar_emoji,privacy_accepted_at)
            VALUES (?,?,?,?)""", (user_id, name, data.avatar_emoji, int(time.time())))
        if data.newsletter:
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


@router.get("/account/verify")
def verify(token: str = Query(..., min_length=24, max_length=256)):
    # The confirmation link is a bearer token. Consume once, then create a
    # short-lived secure browser session; no passwords travel by email.
    session = store.verify_and_start_session(token)
    if not session:
        return HTMLResponse(page("Ссылка недействительна",
            "<section class='panel'><h1>Ссылка истекла или уже использована</h1>"
            "<p>Если почта уже подтверждена, просто войдите в аккаунт.</p>"
            "<a class='action' href='/account/'>Войти</a></section>"), status_code=400)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(COOKIE, session, max_age=14*86400, httponly=True,
                        secure=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


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


@router.get("/account/api/points")
def own_points(request: Request):
    user = current_user(request)
    return JSONResponse({"balance": store.points_balance(user["id"]), "unit": "Прянички"},
                        headers={"Cache-Control": "no-store"})


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
<nav style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px"><a class="action" href="#users-section">Пользователи</a><a class="action" href="#subscribers-section">Подписчики и рассылки</a><a class="action" href="#stats-section">Статистика</a></nav>
<div class='grid' id='stats-section'>
<div class='stat'>Всего пользователей<strong id='total'>—</strong></div>
<div class='stat'>Подтвердили почту<strong id='verified'>—</strong></div>
<div class='stat'>Подписаны на рассылку<strong id='subscribed'>—</strong></div>
<div class='stat'>Зарегистрировались сегодня (UTC)<strong id='today'>—</strong></div></div>
<section class='panel' id='users-section' style='margin-top:20px'>
<h2>Пользователи</h2>
<input id='search' type='search' placeholder='Поиск по электронной почте'>
<label>Фильтр <select id='filter'><option value='all'>Все</option>
<option value='newsletter'>Подписчики</option>
<option value='unverified'>Не подтвердили почту</option></select></label>
<p><button onclick='load()'>Найти</button>
<a class='action' id='export' href='/admin/users.csv'>Выгрузить CSV для Excel</a></p>
<div class='table-wrap'><table><thead><tr><th>Имя</th><th>Адрес</th><th>Регистрация</th>
<th>Почта</th><th>Рассылка</th><th>Роль</th><th>Статус</th><th>Действия</th></tr></thead>
<tbody id='users'></tbody></table></div>
<p><button class='secondary' onclick='prev()'>Назад</button>
<span id='page'></span>
<button class='secondary' onclick='next()'>Дальше</button></p>
<div id='message' role='status'></div></section>
<section class='panel' id='subscribers-section'><h2>💌 Подписчики и рассылки</h2><p>Здесь учитываются подтверждённые аккаунты, включая администратора, если они дали отдельное согласие на рекламные письма. Отправка рекламных кампаний пока выключена.</p><p><button onclick='showSubscribers()'>Показать подписчиков</button> <a class='action' href='/admin/users.csv?filter=newsletter'>Скачать адреса подписчиков (CSV)</a></p></section>"""
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
tr.append(cell((u.avatar||'🍪')+' '+(u.name||'—')),cell(u.email),cell(u.registered),cell(u.verified?'Да':'Нет'),cell(u.newsletter?'Да':'Нет'),
cell(u.role==='admin'?'Администратор':'Пользователь'),cell(u.disabled?'Заблокирован':'Активен'));
let td=document.createElement('td'),b=document.createElement('button');b.className='secondary';
b.textContent=u.disabled?'Разблокировать':'Заблокировать';
b.disabled=u.role==='admin';if(u.role==='admin')b.textContent='Ваш аккаунт';
b.onclick=async()=>{if(u.role==='admin')return;if(!confirm('Изменить доступ пользователя?'))return;
let r=await fetch('/admin/api/users/'+u.id+'/disable',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({disabled:!u.disabled})});
if(r.ok)load();else document.getElementById('message').textContent='Не удалось изменить статус'};
td.append(b);tr.append(td);tbody.append(tr)}
document.getElementById('page').textContent=(offset+1)+'–'+Math.min(offset+limit,count)+' из '+count;
document.getElementById('export').href='/admin/users.csv?'+new URLSearchParams({search:q,filter:f});
}
function showSubscribers(){document.getElementById('filter').value='newsletter';offset=0;load();document.getElementById('users-section').scrollIntoView({behavior:'smooth'})}
function next(){if(offset+limit<count){offset+=limit;load()}}
function prev(){offset=Math.max(0,offset-limit);load()}
document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter'){offset=0;load()}});
document.getElementById('filter').addEventListener('change',()=>{offset=0;load()});load();
</script>"""
    return page("Администрирование", markup, script)


def admin_filter(filter_value: str):
    return {"all": "", "newsletter": " AND n.consent_at IS NOT NULL AND n.unsubscribed_at IS NULL AND u.verified_at IS NOT NULL AND u.disabled_at IS NULL",
            "unverified": " AND u.verified_at IS NULL"}[filter_value]


@router.get("/admin/api/users")
def admin_list(request: Request, search: str = Query("", max_length=120),
               filter: str = Query("all", pattern="^(all|newsletter|unverified)$"),
               offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    current_user(request, admin=True)
    like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "u.email LIKE ? ESCAPE '\\'" + admin_filter(filter)
    join = "LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id LEFT JOIN user_profiles p ON p.user_id=u.id"
    with store.connect() as db:
        stats = db.execute("""SELECT
            COUNT(*) total,
            COUNT(CASE WHEN u.verified_at IS NOT NULL THEN 1 END) verified,
            COUNT(CASE WHEN n.consent_at IS NOT NULL AND n.unsubscribed_at IS NULL AND u.verified_at IS NOT NULL AND u.disabled_at IS NULL THEN 1 END) subscribed,
            COUNT(CASE WHEN u.created_at >= ? THEN 1 END) today
            FROM users u LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id""",
            (int(time.time()) // 86400 * 86400,)).fetchone()
        matched = db.execute(f"SELECT COUNT(*) FROM users u {join} WHERE {where}", (like,)).fetchone()[0]
        rows = db.execute(f"""SELECT u.id,u.email,u.role,u.created_at,u.verified_at,u.disabled_at,
            n.consent_at,n.unsubscribed_at,p.display_name,p.avatar_emoji FROM users u {join}
            WHERE {where} ORDER BY u.created_at DESC,u.id DESC LIMIT ? OFFSET ?""",
            (like, limit, offset)).fetchall()
    users = [{"id": row["id"], "email": row["email"], "role": row["role"], "name": row["display_name"], "avatar": row["avatar_emoji"], "registered": safe_date(row["created_at"]),
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
    where = "u.email LIKE ? ESCAPE '\\'" + admin_filter(filter)
    with store.connect() as db:
        rows = db.execute(f"""SELECT u.email,u.role,u.created_at,u.verified_at,u.disabled_at,
            n.consent_at,n.unsubscribed_at,p.display_name FROM users u
            LEFT JOIN newsletter_subscriptions n ON n.user_id=u.id
            LEFT JOIN user_profiles p ON p.user_id=u.id WHERE {where}
            ORDER BY u.created_at DESC,u.id DESC""", (like,)).fetchall()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Имя", "Email", "Роль", "Регистрация (UTC)", "Почта подтверждена",
                     "Рассылка", "Согласие (UTC)", "Заблокирован"])
    for r in rows:
        subscribed = r["consent_at"] is not None and r["unsubscribed_at"] is None
        writer.writerow([spreadsheet_cell(r["display_name"] or ''), spreadsheet_cell(r["email"]), r["role"], safe_date(r["created_at"]),
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

router.include_router(extras_router)
