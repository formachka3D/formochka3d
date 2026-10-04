"""Transactional email for account verification and password reset.

SMTP credentials live in server environment variables, never in GitHub.
This module is inert until explicitly called by the registration routes.
"""
from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import quote


def smtp_settings() -> dict:
    """Read SMTP config from env or a root-only file. Never put keys in Git."""
    if all(os.environ.get(k) for k in ("FORMOCHKA_SMTP_HOST", "FORMOCHKA_SMTP_USER", "FORMOCHKA_SMTP_PASSWORD")):
        return {
            "host": os.environ["FORMOCHKA_SMTP_HOST"],
            "port": int(os.environ.get("FORMOCHKA_SMTP_PORT", "465")),
            "user": os.environ["FORMOCHKA_SMTP_USER"],
            "password": os.environ["FORMOCHKA_SMTP_PASSWORD"],
            "sender": os.environ.get("FORMOCHKA_MAIL_FROM", "noreply@formochka3d.ru"),
        }
    config_file = Path(os.environ.get("FORMOCHKA_SMTP_CONFIG_FILE", "/app/data/mailer.json"))
    try:
        if config_file.stat().st_mode & 0o077:
            raise RuntimeError("SMTP config file must be owner-only")
        config = json.loads(config_file.read_text(encoding="utf-8"))
        if not all(config.get(k) for k in ("host", "user", "password")):
            raise RuntimeError("Incomplete SMTP config")
        return {
            "host": config["host"],
            "port": int(config.get("port", 465)),
            "user": config["user"],
            "password": config["password"],
            "sender": config.get("sender", "noreply@formochka3d.ru"),
        }
    except FileNotFoundError:
        raise RuntimeError("SMTP credentials are not configured") from None


def send_account_email(recipient: str, kind: str, token: str, *, base_url: str = "https://formochka3d.ru"):
    if kind not in {"verify", "reset"}:
        raise ValueError("Unknown transactional email kind")
    if not base_url.startswith("https://") or "\r" in recipient or "\n" in recipient:
        raise ValueError("Invalid email settings")
    action = "Подтвердить почту" if kind == "verify" else "Восстановить доступ"
    purpose = "Подтвердите адрес электронной почты" if kind == "verify" else "Сброс пароля"
    route = "/account/verify" if kind == "verify" else "/account/reset"
    url = base_url.rstrip("/") + route + "?token=" + quote(token, safe="")
    safe_url = html.escape(url, quote=True)
    body = (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:#fff8f3;font-family:Arial,sans-serif;color:#39302c'>"
        "<div style='max-width:520px;margin:40px auto;background:white;padding:40px;border-radius:22px'>"
        "<h1 style='color:#e78148;text-align:center'>Formochka3D</h1>"
        f"<h2 style='text-align:center'>{purpose}</h2>"
        "<p>Здравствуйте! Вы получили это письмо для управления учётной записью Formochka3D.</p>"
        f"<p style='text-align:center;margin:32px 0'><a href='{safe_url}' "
        f"style='padding:16px 25px;border-radius:12px;background:#e78148;color:white;text-decoration:none;font-weight:bold'>{action}</a></p>"
        "<p style='font-size:13px;color:#7b6c64'>Если вы не запрашивали это письмо, просто проигнорируйте его.</p>"
        "</div></body></html>"
    )
    cfg = smtp_settings()
    msg = EmailMessage()
    msg["Subject"] = "Formochka3D — " + action
    msg["From"] = f"Formochka3D <{cfg['sender']}>"
    msg["To"] = recipient
    msg.set_content(f"{purpose}: {url}\n\nЕсли вы не запрашивали это письмо, проигнорируйте его.")
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ssl.create_default_context(), timeout=15) as smtp:
        smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg)
