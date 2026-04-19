"""
TeleLink — SaaS Manual Request Portal
Powered by Supabase for Auth & Database
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Response, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import create_client, Client as SupabaseClient

from config import Config

# Supabase Setup (Normal User Client)
supabase: SupabaseClient = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

# Supabase Setup (Admin Client - Bypasses RLS)
admin_supabase: SupabaseClient = None
if Config.SUPABASE_SERVICE_KEY:
    admin_supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)
else:
    admin_supabase = supabase # Fallback if key missing

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TeleLink SaaS", docs_url=None, redoc_url=None)

# ── Pydantic Models ─────────────────────────────────────────────────────────────

class RequestSubmit(BaseModel):
    channel_link: str
    content_link: str = ""
    request_type: str = "single"
    bulk_end_link: str = None

class CompleteRequest(BaseModel):
    request_id: int
    status: str
    result_content: str

class SettingsUpdate(BaseModel):
    default_trials: int
    price_per_credit: float
    bdt_rate: float
    pay_binance: str
    pay_webmoney: str
    pay_usdt: str
    pay_nagad: str
    contact_link: str

class UserUpdate(BaseModel):
    user_id: str
    free_trials_left: int

class PaymentSubmit(BaseModel):
    method: str
    trx_id: str
    requested_credits: int

class PaymentUpdate(BaseModel):
    payment_id: int
    status: str
    add_credits: int

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
            settings_res = admin_supabase.table("site_settings").select("default_trials").eq("id", 1).execute()
            default_t = settings_res.data[0].get("default_trials", 1) if settings_res.data else 1
            
            # SELF-HEALING: Use UPSERT (Update if exists, otherwise create)
            print(f"🔄 Syncing missing profile for {user.email}")
            insert_res = admin_supabase.table("profiles").upsert({
                "id": user.id,
                "email": user.email,
                "user_email": user.email,
                "free_trials_left": default_t
            }, on_conflict="id").execute()
            profile = insert_res.data[0]
        else:
            profile = profile_res.data[0]
        
        # 2. Check limits
        if profile.get("free_trials_left", 0) <= 0:
            return JSONResponse(
                status_code=402, 
                content={"ok": False, "detail": "LIMIT_REACHED", "msg": "Free trial used up."}
            )

        if req.request_type != 'single' and not profile.get("is_premium", False):
            return JSONResponse(
                status_code=403, 
                content={"ok": False, "detail": "PREMIUM_REQUIRED", "msg": "Buy credits to unlock Bulk requests."}
            )

        # Insert request (Using ADMIN client to bypass RLS blocks)
        data = {
            "user_id": user.id,
            "user_email": user.email,
            "channel_link": req.channel_link.strip(),
            "content_link": req.content_link.strip(),
            "request_type": req.request_type,
            "bulk_end_link": req.bulk_end_link.strip() if req.bulk_end_link else None,
            "status": "Pending"
        }
        admin_supabase.table("requests").insert(data).execute()

        # Decrement trial
        admin_supabase.table("profiles").update({
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
        # Using admin client here ensures users always see their history without RLS lag
        res = admin_supabase.table("requests").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
        return {"ok": True, "orders": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/profile/me")
async def get_profile(x_supabase_token: str = Header(None)):
    try:
        user = await get_user_from_token(x_supabase_token)
        profile_res = supabase.table("profiles").select("*").eq("id", user.id).execute()
        
        if not profile_res.data:
            settings_res = admin_supabase.table("site_settings").select("default_trials").eq("id", 1).execute()
            default_t = settings_res.data[0].get("default_trials", 1) if settings_res.data else 1
            
            # SELF-HEALING: Use UPSERT
            insert_res = admin_supabase.table("profiles").upsert({
                "id": user.id,
                "email": user.email,
                "user_email": user.email,
                "free_trials_left": default_t
            }, on_conflict="id").execute()
            profile = insert_res.data[0]
        else:
            profile = profile_res.data[0]
            
        return {"ok": True, "profile": profile}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/public/settings")
async def get_public_settings():
    try:
        res = admin_supabase.table("site_settings").select("*").eq("id", 1).execute()
        return {"ok": True, "settings": res.data[0] if res.data else {}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/payments/submit")
async def submit_payment(req: PaymentSubmit, x_supabase_token: str = Header(None)):
    user = await get_user_from_token(x_supabase_token)
    try:
        data = {
            "user_id": user.id,
            "user_email": user.email,
            "method": req.method,
            "trx_id": req.trx_id.strip(),
            "status": "Pending",
            "requested_credits": req.requested_credits
        }
        admin_supabase.table("transactions").insert(data).execute()
        return {"ok": True, "message": "Transaction submitted for verification."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/payments/history")
async def get_payment_history(x_supabase_token: str = Header(None)):
    try:
        user = await get_user_from_token(x_supabase_token)
        res = admin_supabase.table("transactions").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
        return {"ok": True, "payments": res.data}
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

@app.get("/api/admin/users")
async def admin_get_users(x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    try:
        res = admin_supabase.table("profiles").select("*").order("created_at", desc=True).execute()
        return {"ok": True, "users": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/admin/users/update")
async def admin_update_user(req: UserUpdate, x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    try:
        admin_supabase.table("profiles").update({
            "free_trials_left": req.free_trials_left
        }).eq("id", req.user_id).execute()
        return {"ok": True, "message": "User updated."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/admin/settings")
async def admin_update_settings(req: SettingsUpdate, x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    try:
        admin_supabase.table("site_settings").upsert({
            "id": 1,
            "default_trials": req.default_trials,
            "price_per_credit": req.price_per_credit,
            "bdt_rate": req.bdt_rate,
            "pay_binance": req.pay_binance,
            "pay_webmoney": req.pay_webmoney,
            "pay_usdt": req.pay_usdt,
            "pay_nagad": req.pay_nagad,
            "contact_link": req.contact_link
        }).execute()
        return {"ok": True, "message": "Settings updated."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/admin/upload")
async def admin_upload_file(file: UploadFile = File(...), x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    
    try:
        file_bytes = await file.read()
        file_ext = file.filename.split(".")[-1]
        import uuid
        file_name = f"{uuid.uuid4()}.{file_ext}"
        
        # Upload using the admin client
        admin_supabase.storage.from_("deliveries").upload(
            path=file_name,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        
        # Get the public URL
        public_url = admin_supabase.storage.from_("deliveries").get_public_url(file_name)
        return {"ok": True, "url": public_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.get("/api/admin/payments")
async def admin_get_payments(x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    try:
        res = admin_supabase.table("transactions").select("*").order("created_at", desc=True).execute()
        return {"ok": True, "payments": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

@app.post("/api/admin/payments/update")
async def admin_update_payment(req: PaymentUpdate, x_admin_secret: str = Header(None)):
    if not Config.ADMIN_PASSWORD or x_admin_secret != Config.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    try:
        # Update transaction status
        admin_supabase.table("transactions").update({
            "status": req.status
        }).eq("id", req.payment_id).execute()
        
        # If approved and credits added, give credits to user
        if req.status == "Completed" and req.add_credits > 0:
            tx_res = admin_supabase.table("transactions").select("user_id").eq("id", req.payment_id).execute()
            if tx_res.data:
                uid = tx_res.data[0]["user_id"]
                # get current
                prof_res = admin_supabase.table("profiles").select("free_trials_left").eq("id", uid).execute()
                if prof_res.data:
                    current = prof_res.data[0].get("free_trials_left", 0)
                    admin_supabase.table("profiles").update({
                        "free_trials_left": current + req.add_credits,
                        "is_premium": True
                    }).eq("id", uid).execute()

        return {"ok": True, "message": "Transaction updated successfully."}
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
