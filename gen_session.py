import asyncio
from pyrogram import Client
from config import Config

async def main():
    print("--- Telegram Session Generator ---")
    print("This script will help you generate a Pyrogram String Session.")
    print("You will need your API_ID and API_HASH from my.telegram.org.")
    
    api_id = input("Enter API_ID: ") or str(Config.API_ID)
    api_hash = input("Enter API_HASH: ") or Config.API_HASH
    
    async with Client("session_generator", api_id=int(api_id), api_hash=api_hash, in_memory=True) as app:
        session_string = await app.export_session_string()
        print("\n--- YOUR SESSION STRING ---")
        print(session_string)
        print("---------------------------\n")
        print("Copy this string and paste it into USER_SESSION in your .env file.")
        print("Keep this string SECRET! Anyone with it can access your account.")

if __name__ == "__main__":
    asyncio.run(main())
