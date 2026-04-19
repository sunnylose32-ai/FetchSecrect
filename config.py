import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    USER_SESSION = os.environ.get("USER_SESSION", "")  # Administrator User Account
    
    # Supabase
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")         # Anon Key (for users)
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") # Secret Key (for bypass)
    
    # Admin Credentials
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
