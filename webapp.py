"""
TeleLink — FastAPI Web Application

Routes:
  POST /api/auth/send-code     → Send OTP to phone
  POST /api/auth/verify-code   → Verify OTP, create session
  GET  /api/auth/me            → Get current user info
  POST /api/auth/logout        → Destroy session
  POST /api/fetch              → Fetch a t.me message link
  GET  /api/download/{token}   → Stream media file
  GET  /api/status             → Health check
  GET  /robots.txt, /sitemap.xml → SEO
  GET  /, /login, /tool        → HTML pages
"""

import asyncio
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyrogram import Client
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded

from config import Config
from session_store import (
    TEMP_DIR,
    cleanup_loop,
    download_tokens,
    pending_auth,
    user_sessions,
)

STATIC_DIR = Path(__file__).parent / "static"
LINK_PATTERN = r"https?://(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([\w\d_-]+)/(\d+)"

app = FastAPI(title="TeleLink", docs_url=None, redoc_url=None)


# ── Pydantic Models ─────────────────────────────────────────────────────────────

class PhoneReq(BaseModel):
    phone: str

class VerifyReq(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: Optional[str] = None

class FetchReq(BaseModel):
    link: str


# ── Helpers ─────────────────────────────────────────────────────────────────────

def require_session(token: Optional[str]) -> dict:
    if not token or token not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login.")
    session = user_sessions[token]
    session["last_used"] = time.time()
    return session


def format_size(size: Optional[int]) -> Optional[str]:
    if not size:
        return None
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ── Auth Routes ─────────────────────────────────────────────────────────────────

@app.post("/api/auth/send-code")
async def send_code(req: PhoneReq):
    phone = req.phone.strip()

    # Clean up any previous pending auth for this phone
    if phone in pending_auth:
        try:
            await pending_auth[phone]["client"].disconnect()
        except Exception:
            pass
        pending_auth.pop(phone, None)

    client = Client(
        name=f"auth_{abs(hash(phone)) % 10**9}",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        in_memory=True,
    )
    try:
        await client.connect()
        sent = await client.send_code(phone)
        pending_auth[phone] = {
            "client": client,
            "phone_code_hash": sent.phone_code_hash,
            "created_at": time.time(),
        }
        return {"ok": True, "phone_code_hash": sent.phone_code_hash}
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/verify-code")
async def verify_code(req: VerifyReq):
    phone = req.phone.strip()
    if phone not in pending_auth:
        raise HTTPException(
            status_code=400,
            detail="No pending auth. Please request a code first.",
        )

    auth = pending_auth[phone]
    client = auth["client"]

    try:
        await client.sign_in(phone, req.phone_code_hash, req.code)
    except SessionPasswordNeeded:
        if not req.password:
            raise HTTPException(status_code=403, detail="2FA_REQUIRED")
        try:
            await client.check_password(req.password)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"2FA failed: {e}")
    except PhoneCodeInvalid:
        raise HTTPException(status_code=400, detail="Invalid code. Please try again.")
    except PhoneCodeExpired:
        try:
            await client.disconnect()
        except Exception:
            pass
        pending_auth.pop(phone, None)
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        pending_auth.pop(phone, None)
        raise HTTPException(status_code=400, detail=str(e))

    # Export session string and create a persistent client
    session_string = await client.export_session_string()
    try:
        await client.disconnect()
    except Exception:
        pass
    pending_auth.pop(phone, None)

    persistent = Client(
        name=f"user_{abs(hash(phone + session_string[:8])) % 10**9}",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=session_string,
        in_memory=True,
    )
    await persistent.start()
    me = await persistent.get_me()

    token = str(uuid.uuid4())
    user_sessions[token] = {
        "client": persistent,
        "user_info": {
            "id": me.id,
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username or "",
            "phone": phone,
        },
        "last_used": time.time(),
    }

    return {
        "ok": True,
        "session_token": token,
        "user": user_sessions[token]["user_info"],
    }


@app.get("/api/auth/me")
async def get_me(x_session_token: Optional[str] = Header(None)):
    session = require_session(x_session_token)
    return {"ok": True, "user": session["user_info"]}


@app.post("/api/auth/logout")
async def logout(x_session_token: Optional[str] = Header(None)):
    if x_session_token and x_session_token in user_sessions:
        try:
            await user_sessions[x_session_token]["client"].stop()
        except Exception:
            pass
        user_sessions.pop(x_session_token, None)
    return {"ok": True}


# ── Fetch Route ─────────────────────────────────────────────────────────────────

@app.post("/api/fetch")
async def fetch_link(
    req: FetchReq, x_session_token: Optional[str] = Header(None)
):
    session = require_session(x_session_token)
    client = session["client"]

    match = re.search(LINK_PATTERN, req.link.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid link. Use format: https://t.me/c/123456789/123",
        )

    chat_val, msg_id_str = match.groups()
    msg_id = int(msg_id_str)
    chat_id = int(f"-100{chat_val}") if chat_val.isdigit() else chat_val

    try:
        # Resolve peer (may fail if not a member — that's fine)
        try:
            await client.get_chat(chat_id)
        except Exception:
            pass

        msg = await client.get_messages(chat_id, msg_id)

        if not msg or msg.empty:
            raise HTTPException(
                status_code=404,
                detail="Message not found. Are you a member of this channel?",
            )

        result = {
            "ok": True,
            "message_id": msg.id,
            "date": msg.date.isoformat() if msg.date else None,
            "type": "text",
            "content": "",
            "caption": msg.caption or "",
            "media_type": None,
            "download_url": None,
            "file_name": None,
            "file_size": None,
            "file_size_human": None,
            "from_user": None,
        }

        if msg.from_user:
            fn = msg.from_user.first_name or ""
            ln = msg.from_user.last_name or ""
            result["from_user"] = f"{fn} {ln}".strip() or None

        if msg.text:
            result["type"] = "text"
            result["content"] = msg.text

        elif msg.media:
            result["type"] = "media"

            if msg.photo:
                mt = "photo"
            elif msg.video:
                mt = "video"
            elif msg.audio:
                mt = "audio"
            elif msg.voice:
                mt = "voice"
            elif msg.document:
                mt = "document"
            elif msg.sticker:
                mt = "sticker"
            elif msg.animation:
                mt = "animation"
            else:
                mt = "file"

            result["media_type"] = mt
            media_obj = (
                msg.photo
                or msg.video
                or msg.audio
                or msg.voice
                or msg.document
                or msg.sticker
                or msg.animation
            )
            if media_obj:
                result["file_name"] = getattr(media_obj, "file_name", None)
                sz = getattr(media_obj, "file_size", None)
                result["file_size"] = sz
                result["file_size_human"] = format_size(sz)

            dl_token = str(uuid.uuid4())
            download_tokens[dl_token] = {
                "chat_id": chat_id,
                "msg_id": msg_id,
                "session_token": x_session_token,
                "media_type": mt,
                "file_name": result["file_name"],
                "expires_at": time.time() + 3600,
            }
            result["download_url"] = f"/api/download/{dl_token}"

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Download Route ──────────────────────────────────────────────────────────────

@app.get("/api/download/{token}")
async def download_file(token: str):
    if token not in download_tokens:
        raise HTTPException(
            status_code=404, detail="Download link expired or not found."
        )

    dl = download_tokens[token]
    if dl["session_token"] not in user_sessions:
        raise HTTPException(status_code=401, detail="Session expired. Please re-login.")

    client = user_sessions[dl["session_token"]]["client"]
    try:
        msg = await client.get_messages(dl["chat_id"], dl["msg_id"])
        file_path = await client.download_media(
            msg, file_name=str(TEMP_DIR / token)
        )

        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to download media.")

        download_tokens.pop(token, None)
        filename = dl.get("file_name") or os.path.basename(str(file_path))

        def gen():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    yield chunk
            try:
                os.remove(file_path)
            except Exception:
                pass

        return StreamingResponse(
            gen(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SEO ─────────────────────────────────────────────────────────────────────────

@app.get("/robots.txt")
async def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /tool\n"
        "Disallow: /api/\n"
        "Sitemap: https://yourdomain.com/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap_xml():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://yourdomain.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://yourdomain.com/login</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
</urlset>"""
    return Response(content=content, media_type="application/xml")


@app.get("/api/status")
async def status():
    return {
        "ok": True,
        "service": "TeleLink",
        "active_sessions": len(user_sessions),
        "pending_auths": len(pending_auth),
    }


# ── Pages ───────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/login")
async def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.get("/tool")
async def tool_page():
    return FileResponse(str(STATIC_DIR / "tool.html"))


# ── Static files ─────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Startup ──────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(cleanup_loop())
