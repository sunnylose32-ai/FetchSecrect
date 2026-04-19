import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    USER_SESSION = os.environ.get("USER_SESSION", "")  # Administrator User Account
    
    # Supabase (NEW)
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # Public Anon Key
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")   # Email associated with admin dashboard
