import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    USER_SESSION = os.environ.get("USER_SESSION", "")  # Optional: For fetching from private channels the bot isn't in
    TARGET_CHANNEL = os.environ.get("TARGET_CHANNEL", "")  # Where to send all posts (username or ID)
