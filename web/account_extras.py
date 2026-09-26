"""Staging-only registration CAPTCHA, profile, optional photo and privacy notice.

The CAPTCHA is an abuse deterrent, not a guarantee against automated OCR.
Do not enable public production signup before finalizing the privacy notice.
"""
from __future__ import annotations

import html
import io
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

router = APIRouter()
CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
AVATARS = ("🍓", "🍪", "💗", "🧁", "🌸", "🐻", "🍒", "🌈", "🐰", "✨", "🥨", "🍬")
DATA_DIR = Path(os.environ.get("FORMOCHKA_ACCOUNT_DB", "/app/data/staging-users.sqlite3")).parent
AVATAR_DIR = DATA_DIR / "avatars"
AVATAR_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def initialize(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS user_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        display_name TEXT NOT NULL,
        avatar_emoji TEXT NOT NULL DEFAULT '🍪',
        avatar_filename TEXT,
        privacy_accepted_at INTEGER NOT NULL,
        privacy_version TEXT NOT NULL DEFAULT 'staging-20260926'
      );
      CREATE TABLE IF NOT EXISTS captcha_challenges (
        id TEXT PRIMARY KEY,
        answer TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS ix_captcha_created ON captcha_challenges(created_at);
    """)


def verify_captcha(db, challenge_id: str, answer: str) -> bool:
    """Consume challenge on success; expire quickly and lock after 5 guesses."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", challenge_id or ""):
        return False
    with db:
        db.execute("DELETE FROM captcha_challenges WHERE created_at<?", (int(time.time()) - 600,))
        row = db.execute("SELECT answer,attempts FROM captcha_challenges WHERE id=?",
                         (challenge_id,)).fetchone()
        if row is None or row["attempts"] >= 5:
            return False
        db.execute("UPDATE captcha_challenges SET attempts=attempts+1 WHERE id=?",
                   (challenge_id,))
        correct = secrets.compare_digest(row["answer"], (answer or "").strip().upper())
        if correct:
            db.execute("DELETE FROM captcha_challenges WHERE id=?", (challenge_id,))
        return correct


@router.get("/account/captcha")
def new_captcha(request: Request):
    """Server-side sessionless SVG challenge. HTML never receives the answer."""
    from web.account_portal import store, throttle
    throttle(request, "captcha", "new", 20, 600)
    challenge_id = secrets.token_urlsafe(24)
    answer = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(6))
    with store.connect() as db:
        db.execute("DELETE FROM captcha_challenges WHERE created_at<?", (int(time.time()) - 600,))
        db.execute("INSERT INTO captcha_challenges(id,answer,created_at) VALUES(?,?,?)",
                   (challenge_id, answer, int(time.time())))
    marks = []
    for i, ch in enumerate(answer):
        x = 25 + 35 * i
        y = 45 + secrets.randbelow(14)
        angle = secrets.randbelow(29) - 14
        marks.append(f'<text x="{x}" y="{y}" transform="rotate({angle} {x} {y})"'
                     f' font-family="Verdana,Arial" font-size="32" font-weight="800"'
                     f' fill="#744654">{ch}</text>')
    noise = "".join(f'<path d="M{secrets.randbelow(235)} {secrets.randbelow(70)} '
                    f'l{secrets.randbelow(50)} {secrets.randbelow(26)-13}"'
                    f' stroke="#d5a4a5" stroke-width="1" fill="none"/>'
                    for _ in range(13))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 245 70"'
           f' role="img" aria-label="Код подтверждения из шести символов">'
           f'<rect width="245" height="70" rx="12" fill="#fff2e9"/>{noise}'
           + "".join(marks) + '</svg>')
    return JSONResponse({"id": challenge_id, "svg": svg}, headers={"Cache-Control": "no-store"})


@router.get("/privacy/", response_class=HTMLResponse)
def privacy():
    from web.account_portal import page
    body = """<section class='panel'><h1>Обработка персональных данных — тестовая версия</h1>
<p>Для регистрации на тестовом сайте мы сохраняем имя, адрес электронной почты,
хеш пароля, выбранную аватарку и время подтверждения согласия. При отдельном согласии
сохраняем статус подписки на письма. Для защиты аккаунта используются технические
данные сессии и проверки CAPTCHA. Пользователь может отказаться от рассылки в кабинете.</p>
<p>Данные тестовой версии хранятся на защищённом VPS. Доступ к списку пользователей
ограничен учётной записью администратора.</p>
<p><strong>Это ознакомительное описание тестового сервиса, не окончательная
политика конфиденциальности.</strong> Перед открытием регистрации на основном
сайте необходимо указать юридического оператора, контакты, сроки хранения и
процедуру запросов на удаление данных и проверить соответствие применимому праву.</p>
<p><a href='/account/'>Вернуться к регистрации</a></p></section>"""
    return page("Обработка данных (тест)", body)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    avatar_emoji: str = Field(max_length=4, default="🍪")


def clean_name(value: str) -> str:
    result = " ".join(value.split()).strip()
    if not (2 <= len(result) <= 60) or any(ord(ch) < 32 for ch in result) or "<" in result:
        raise ValueError("Введите имя длиной от 2 до 60 символов")
    return result


@router.get("/account/api/me")
def me(request: Request):
    from web.account_portal import store
    token = request.cookies.get("__Host-f3d-session", "")
    user = store.get_session(token)
    if not user:
        return JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
    with store.connect() as db:
        p = db.execute("SELECT display_name,avatar_emoji,avatar_filename FROM user_profiles WHERE user_id=?",
                       (user["id"],)).fetchone()
    return JSONResponse({"authenticated": True,
                         "name": p["display_name"] if p else user["email"].split("@")[0],
                         "avatar": p["avatar_emoji"] if p else "🍪",
                         "has_photo": bool(p and p["avatar_filename"]),
                         "avatar_url": "/account/avatar" if p and p["avatar_filename"] else None},
                        headers={"Cache-Control": "no-store"})


@router.post("/account/api/profile")
def update_profile(request: Request, data: ProfileUpdate):
    from web.account_portal import store, current_user, require_json
    require_json(request)
    user = current_user(request)
    try:
        name = clean_name(data.display_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if data.avatar_emoji not in AVATARS:
        raise HTTPException(400, "Выберите аватарку из предложенных")
    with store.connect() as db:
        db.execute("""INSERT INTO user_profiles(user_id,display_name,avatar_emoji,privacy_accepted_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE
            SET display_name=excluded.display_name,avatar_emoji=excluded.avatar_emoji,
                avatar_filename=NULL""", (user["id"], name, data.avatar_emoji, int(time.time())))
    return {"ok": True}


@router.post("/account/api/avatar")
async def upload_avatar(request: Request, photo: UploadFile = File(...)):
    from web.account_portal import store, current_user, throttle
    user = current_user(request)
    throttle(request, "avatar", str(user["id"]), 10, 3600)
    if photo.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(415, "Поддерживаются PNG, JPEG и WEBP")
    data = await photo.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "Фотография должна быть меньше 2 МБ")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        if image.width * image.height > 20_000_000:
            raise ValueError
        image = ImageOps.fit(image.convert("RGB"), (256, 256))
        out = io.BytesIO()
        image.save(out, format="WEBP", quality=84, method=4)
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "Не удалось обработать изображение")
    filename = f"{user['id']}-{secrets.token_hex(12)}.webp"
    dest = AVATAR_DIR / filename
    dest.write_bytes(out.getvalue())
    dest.chmod(0o600)
    previous = None
    with store.connect() as db:
        p = db.execute("SELECT avatar_filename FROM user_profiles WHERE user_id=?",
                       (user["id"],)).fetchone()
        previous = p["avatar_filename"] if p else None
        db.execute("""INSERT INTO user_profiles(user_id,display_name,avatar_emoji,avatar_filename,privacy_accepted_at)
             VALUES(?,?,?, ?,?) ON CONFLICT(user_id) DO UPDATE SET avatar_filename=excluded.avatar_filename""",
             (user["id"], user["email"].split("@")[0], "🍪", filename, int(time.time())))
    if previous and previous != filename:
        (AVATAR_DIR / Path(previous).name).unlink(missing_ok=True)
    return {"ok": True, "avatar_url": "/account/avatar"}


@router.get("/account/avatar")
def own_avatar(request: Request):
    from web.account_portal import store, current_user
    user = current_user(request)
    with store.connect() as db:
        p = db.execute("SELECT avatar_filename FROM user_profiles WHERE user_id=?",
                       (user["id"],)).fetchone()
    if not p or not p["avatar_filename"]:
        raise HTTPException(404, "Аватарка не найдена")
    path = AVATAR_DIR / Path(p["avatar_filename"]).name
    if not path.is_file():
        raise HTTPException(404, "Аватарка не найдена")
    return Response(path.read_bytes(), media_type="image/webp",
                    headers={"Cache-Control": "private, max-age=120"})
