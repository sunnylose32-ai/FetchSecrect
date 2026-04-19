"""
TeleLink — Combined entry point.

Runs the Telegram bot (from bot.py) AND the FastAPI web server
in the same asyncio event loop. Use this instead of `python bot.py`.

Usage:
    python main.py
"""

import asyncio
import uvicorn
import bot  # Registers all Telegram handlers as a side effect
from webapp import app


async def main():
    # ── Start Pyrogram clients ──────────────────────────────────────────────────
    await bot.bot.start()
    print("✅ Telegram bot started")

    if bot.user:
        try:
            await bot.user.start()
            bot.user_is_active = True
            print("✅ Userbot started")
            await bot.preload_dialogs()
        except Exception as e:
            bot.user_is_active = False
            print(f"⚠️  Userbot failed: {e}")

    print()
    print("══════════════════════════════════════════════════")
    print("  🔗  TeleLink is running!")
    print("  🌐  Web UI  →  http://localhost:8000")
    print("  🤖  Telegram Bot is active in parallel")
    print("══════════════════════════════════════════════════")
    print()

    # ── Start web server (blocks until interrupted) ─────────────────────────────
    import os
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        loop="none",          # reuse existing asyncio loop
    )
    server = uvicorn.Server(config)
    await server.serve()

    # ── Graceful shutdown ───────────────────────────────────────────────────────
    print("\nShutting down TeleLink…")
    try:
        await bot.bot.stop()
    except Exception:
        pass
    if bot.user:
        try:
            await bot.user.stop()
        except Exception:
            pass
    print("Goodbye! 👋")


if __name__ == "__main__":
    asyncio.run(main())
