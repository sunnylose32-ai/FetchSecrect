"""
TeleLink — SaaS Manual Request Portal
Powered by Supabase for Auth & Database
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Response, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import create_client, Client as SupabaseClient

from config import Config

# Supabase Setup
supabase: SupabaseClient = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TeleLink SaaS", docs_url=None, redoc_url=None)

# ── Pydantic Models ─────────────────────────────────────────────────────────────

class RequestSubmit(BaseModel):
    channel_link: str
    content_link: str

class CompleteRequest(BaseModel):
    request_id: int
    status: str
    result_content: str

# ── Auth Middleware Helper ──────────────────────────────────────────────────────

async def get_user_from_token(token: str):
    try:
        user = supabase.auth.get_user(token)
        return user.user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session. Please login again.")

# ── API Routes ──────────────────────────────────────────────────────────────────

@app.post("/api/orders/submit")
async def submit_order(req: RequestSubmit, x_supabase_token: str = Header(None)):
    user = await get_user_from_token(x_supabase_token)
    
    try:
        # 1. Fetch profile
        profile_res = supabase.table("profiles").select("*").eq("id", user.id).execute()
        
        if not profile_res.data:
            # SELF-HEALING: Create missing profile automatically
            print(f"🔄 Creating missing profile for {user.email}")
            insert_res = supabase.table("profiles").insert({
                "id": user.id,
                "user_email": user.email,
                "free_trials_left": 1
            }).execute()
            profile = insert_res.data[0]
        else:
            profile = profile_res.data[0]
        
        # 2. Check limits
        if profile.get("free_trials_left", 0) <= 0:
            return JSONResponse(
                status_code=402, 
                content={"ok": False, "detail": "LIMIT_REACHED", "msg": "Free trial used up."}
            )

        # Insert request
        data = {
            "user_id": user.id,
            "user_email": user.email,
            "channel_link": req.channel_link.strip(),
            "content_link": req.content_link.strip(),
            "status": "Pending"
        }
        supabase.table("requests").insert(data).execute()

        # Decrement trial
        supabase.table("profiles").update({
            "free_trials_left": profile["free_trials_left"] - 1
        }).eq("id", user.id).execute()

        return {"ok": True, "message": "Request submitted! Admin will process it soon."}
    except Exception as e:
        print(f"❌ Submission Error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/orders/history")
async def get_history(x_supabase_token: str = Header(None)):
    try:
        user = await get_user_from_token(x_supabase_token)
        res = supabase.table("requests").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
        return {"ok": True, "orders": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/profile/me")
async def get_profile(x_supabase_token: str = Header(None)):
    try:
        user = await get_user_from_token(x_supabase_token)
        profile_res = supabase.table("profiles").select("*").eq("id", user.id).execute()
        
        if not profile_res.data:
            # SELF-HEALING: Create it on the fly
            insert_res = supabase.table("profiles").insert({
                "id": user.id,
                "user_email": user.email,
                "free_trials_left": 1
            }).execute()
            profile = insert_res.data[0]
        else:
            profile = profile_res.data[0]
            
        return {"ok": True, "profile": profile}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

# ── Admin Routes ────────────────────────────────────────────────────────────────

@app.post("/api/admin/login")
async def admin_login(req: dict):
    password = req.get("password")
    if not Config.ADMIN_PASSWORD or password != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    return {"ok": True, "message": "Admin authenticated."}

@app.get("/api/admin/requests")
async def admin_get_requests(x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized. Admin password required.")
    
    try:
        res = supabase.table("requests").select("*").order("created_at", desc=True).execute()
        return {"ok": True, "orders": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/admin/complete")
async def admin_complete_order(req: CompleteRequest, x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")

    try:
        supabase.table("requests").update({
            "status": req.status,
            "result_content": req.result_content
        }).eq("id", req.request_id).execute()
        return {"ok": True, "message": "Order updated successfully."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

# ── Pages ───────────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/index.html")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/login")
@app.get("/login.html")
async def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))

@app.get("/signup")
@app.get("/signup.html")
async def signup_page():
    return FileResponse(str(STATIC_DIR / "signup.html"))

@app.get("/verify")
@app.get("/verify.html")
async def verify_page():
    return FileResponse(str(STATIC_DIR / "verify.html"))

@app.get("/tool")
@app.get("/tool.html")
async def tool_page():
    return FileResponse(str(STATIC_DIR / "tool.html"))

@app.get("/admin")
@app.get("/admin.html")
async def admin_page():
    return FileResponse(str(STATIC_DIR / "admin.html"))

# ── Dynamic Config for Frontend ──────────────────────────────────────────────────

@app.get("/static/config.js")
async def get_frontend_config():
    """Serves Supabase keys to the frontend dynamically from .env"""
    content = f"""
    window.SUPABASE_URL = "{Config.SUPABASE_URL}";
    window.SUPABASE_KEY = "{Config.SUPABASE_KEY}";
    """
    return Response(content=content, media_type="application/javascript")

# ── Static files ─────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Robots & Sitemap ─────────────────────────────────────────────────────────────

@app.get("/robots.txt")
async def robots():
    return Response(content="User-agent: *\nAllow: /", media_type="text/plain")
