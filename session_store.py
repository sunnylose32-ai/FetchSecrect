"""
TeleLink — In-memory session store.

Tracks:
  - pending_auth  : phone → {client, phone_code_hash, created_at}
  - user_sessions : session_token → {client, user_info, last_used}
  - download_tokens: dl_token → {chat_id, msg_id, session_token, ...}
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

# ── Stores ─────────────────────────────────────────────────────────────────────
pending_auth: dict = {}
user_sessions: dict = {}
download_tokens: dict = {}

# ── Config ─────────────────────────────────────────────────────────────────────
SESSION_TTL      = 43200   # 12 hours
PENDING_TTL      = 300     # 5 minutes
DOWNLOAD_TTL     = 3600    # 1 hour

TEMP_DIR = Path(tempfile.gettempdir()) / "telelink_downloads"
TEMP_DIR.mkdir(exist_ok=True)


# ── Background Cleanup ─────────────────────────────────────────────────────────
async def cleanup_loop():
    """Runs every 30 min, purges expired sessions/tokens/files."""
    while True:
        await asyncio.sleep(1800)
        now = time.time()

        # ── Expired user sessions
        expired = [
            t for t, s in list(user_sessions.items())
            if now - s["last_used"] > SESSION_TTL
        ]
        for token in expired:
            try:
                await user_sessions[token]["client"].stop()
            except Exception:
                pass
            user_sessions.pop(token, None)

        # ── Stale pending auths
        stale = [
            p for p, d in list(pending_auth.items())
            if now - d["created_at"] > PENDING_TTL
        ]
        for phone in stale:
            try:
                await pending_auth[phone]["client"].disconnect()
            except Exception:
                pass
            pending_auth.pop(phone, None)

        # ── Expired download tokens + temp files
        expired_dl = [
            t for t, d in list(download_tokens.items())
            if now > d["expires_at"]
        ]
        for token in expired_dl:
            fp = download_tokens[token].get("file_path")
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            download_tokens.pop(token, None)
