import asyncio
import re
import logging
import os
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Pattern: post link with message ID (e.g. t.me/c/12345/678 or t.me/username/78)
LINK_PATTERN = r"https?://(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([\w\d_-]+)/(\d+)"
# Pattern: channel link WITHOUT message ID (e.g. t.me/c/12345 or t.me/username)
CHANNEL_PATTERN = r"^https?://(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([\w\d_-]+)/?$"
# Join link pattern
JOIN_PATTERN = r"https?://(?:t\.me|telegram\.(?:me|dog))/(?:\+|joinchat/)([\w\d_-]+)"

bot = Client(
    "bot_session",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

user = None
if Config.USER_SESSION and "your_pyrogram_string_session_here" not in Config.USER_SESSION:
    user = Client(
        "user_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.USER_SESSION,
    )

user_is_active = False
# Track active bulk forward jobs: {user_id: True/False}
active_jobs = {}


# --------------- Helpers ---------------

async def send_media(chat_id, msg):
    """Try to copy a message; fall back to download+reupload if restricted."""
    try:
        if not msg.has_protected_content and not (msg.chat and msg.chat.has_protected_content):
            await msg.copy(chat_id)
            return True
    except Exception:
        pass

    # Download-reupload fallback
    if msg.media:
        downloader = user if (user and user_is_active) else bot
        file_path = None
        try:
            file_path = await downloader.download_media(msg)
            if file_path:
                caption = msg.caption or ""
                if msg.photo:      await bot.send_photo(chat_id, file_path, caption=caption)
                elif msg.video:    await bot.send_video(chat_id, file_path, caption=caption)
                elif msg.audio:    await bot.send_audio(chat_id, file_path, caption=caption)
                elif msg.voice:    await bot.send_voice(chat_id, file_path, caption=caption)
                elif msg.sticker:  await bot.send_sticker(chat_id, file_path)
                else:              await bot.send_document(chat_id, file_path, caption=caption)
                return True
        except Exception as e:
            logger.error(f"send_media error: {e}")
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    elif msg.text:
        await bot.send_message(chat_id, msg.text)
        return True
    return False


# --------------- Handlers ---------------

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await message.reply_text(
        "👋 Hello! Send me:\n\n"
        "📌 **Single post link** → `https://t.me/c/12345/678`\n"
        "📋 **Channel link** → `https://t.me/c/12345` (forward ALL posts)\n"
        "🔗 **Invite link** → `https://t.me/+abc` (join a private channel)"
    )

@bot.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message):
    await message.reply_text("🏓 Pong! I am alive.")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client, message):
    uid = message.from_user.id
    if active_jobs.get(uid):
        active_jobs[uid] = False
        await message.reply_text("🛑 Cancelling the forward job...")
    else:
        await message.reply_text("No active job to cancel.")

@bot.on_message(filters.regex(JOIN_PATTERN) & filters.private)
async def join_handler(client, message):
    if not (user and user_is_active):
        await message.reply_text("❌ USER_SESSION is not active.")
        return
    match = re.search(JOIN_PATTERN, message.text)
    invite_link = match.group(0)
    try:
        await user.join_chat(invite_link)
        await message.reply_text("✅ Joined channel!")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@bot.on_message(filters.text & filters.private)
async def handle_message(client, message):
    if message.text.startswith("/"): return
    
    text = message.text.strip()

    # ── 1. CHANNEL LINK (bulk forward all posts) ──
    channel_match = re.match(CHANNEL_PATTERN, text)
    if channel_match:
        if not (user and user_is_active):
            await message.reply_text("❌ USER_SESSION not active. Cannot read private channels.")
            return
        
        # Determine target
        target = Config.TARGET_CHANNEL
        if not target:
            target = message.chat.id  # send to user if no TARGET_CHANNEL set

        chat_val = channel_match.group(1)
        channel_id = int(f"-100{chat_val}") if chat_val.isdigit() else chat_val

        uid = message.from_user.id
        active_jobs[uid] = True

        status_msg = await message.reply_text("⏳ Starting bulk forward... Send /cancel to stop.")
        count = 0
        failed = 0

        try:
            # Force peer resolution
            try: await user.get_chat(channel_id)
            except Exception: pass

            async for msg in user.get_chat_history(channel_id):
                if not active_jobs.get(uid):
                    break
                if msg.empty or msg.service:
                    continue

                # Rate limit handling
                try:
                    success = await send_media(target, msg)
                    if success:
                        count += 1
                    else:
                        failed += 1
                except FloodWait as fw:
                    logger.warning(f"FloodWait: sleeping {fw.value}s")
                    await asyncio.sleep(fw.value)
                except Exception as e:
                    logger.error(f"Error forwarding msg {msg.id}: {e}")
                    failed += 1

                # Progress update every 20 messages
                if (count + failed) % 20 == 0 and (count + failed) > 0:
                    try:
                        await status_msg.edit_text(
                            f"⏳ Progress: ✅ {count} sent | ❌ {failed} failed\n"
                            f"Send /cancel to stop."
                        )
                    except Exception: pass

                await asyncio.sleep(0.5)  # Be gentle with rate limits

        except Exception as e:
            await message.reply_text(f"❌ Error during bulk forward: {e}")
        finally:
            active_jobs[uid] = False

        await status_msg.edit_text(
            f"{'✅ Done!' if active_jobs.get(uid) is not None else '🛑 Cancelled!'}\n"
            f"**{count}** messages forwarded | **{failed}** failed."
        )
        return

    # ── 2. RANGE LINK (forward messages from start_id to end_id) ──
    all_links = re.findall(LINK_PATTERN, text)
    if len(all_links) == 2:
        if not (user and user_is_active):
            await message.reply_text("❌ USER_SESSION not active. Cannot read private channels.")
            return

        chat_val_1, msg_id_1 = all_links[0]
        chat_val_2, msg_id_2 = all_links[1]

        if chat_val_1 != chat_val_2:
            await message.reply_text("❌ Both links must be from the same channel.")
            return

        start_id = int(msg_id_1)
        end_id = int(msg_id_2)

        if start_id > end_id:
            start_id, end_id = end_id, start_id  # flip if needed

        source_chat_id = int(f"-100{chat_val_1}") if chat_val_1.isdigit() else chat_val_1
        target = Config.TARGET_CHANNEL or message.chat.id
        uid = message.from_user.id
        active_jobs[uid] = True

        status_msg = await message.reply_text(f"⏳ Forwarding range {start_id} to {end_id}... Send /cancel to stop.")
        count = 0
        failed = 0

        try:
            # Force peer resolution
            try: await user.get_chat(source_chat_id)
            except Exception: pass

            for m_id in range(start_id, end_id + 1):
                if not active_jobs.get(uid):
                    break

                try:
                    target_msg = await user.get_messages(source_chat_id, m_id)
                    if not target_msg or target_msg.empty:
                        failed += 1
                        continue

                    # Rate limit handling
                    success = await send_media(target, target_msg)
                    if success:
                        count += 1
                    else:
                        failed += 1
                except FloodWait as fw:
                    logger.warning(f"FloodWait: sleeping {fw.value}s")
                    await asyncio.sleep(fw.value)
                except Exception as e:
                    logger.error(f"Error range forwarding msg {m_id}: {e}")
                    failed += 1

                # Progress update every 10 messages (slightly more frequent for range)
                total_processed = count + failed
                if total_processed % 10 == 0:
                    try:
                        await status_msg.edit_text(
                            f"⏳ Progress: {total_processed}/{(end_id - start_id + 1)}\n"
                            f"✅ {count} sent | ❌ {failed} failed\n"
                            f"Send /cancel to stop."
                        )
                    except Exception: pass

                await asyncio.sleep(0.5)

        except Exception as e:
            await message.reply_text(f"❌ Error during range forward: {e}")
        finally:
            status_text = f"{'✅ Done!' if active_jobs.get(uid) is not False else '🛑 Cancelled!'}\n"
            status_text += f"**{count}** messages forwarded | **{failed}** failed."
            await status_msg.edit_text(status_text)
            active_jobs[uid] = False
        return

    # ── 3. SINGLE POST LINK ──
    post_match = re.search(LINK_PATTERN, text)
    if not post_match:
        return

    chat_val, msg_id = post_match.groups()
    msg_id = int(msg_id)
    formatted_chat_id = int(f"-100{chat_val}") if chat_val.isdigit() else chat_val

    await message.reply_chat_action(ChatAction.TYPING)
    try:
        target_msg = None
        if user and user_is_active:
            try:
                try: await user.get_chat(formatted_chat_id)
                except Exception: pass
                target_msg = await user.get_messages(formatted_chat_id, msg_id)
                if not target_msg or target_msg.empty:
                    logger.warning(f"Userbot got empty message for {formatted_chat_id}/{msg_id}")
            except Exception as e:
                logger.error(f"Userbot failed get_messages: {e}")

        if not target_msg or target_msg.empty:
            try:
                target_msg = await bot.get_messages(formatted_chat_id, msg_id)
            except Exception as e:
                logger.error(f"Bot failed get_messages: {e}")

        if not target_msg or target_msg.empty:
            await message.reply_text(
                "❌ Message not found.\n\n"
                "• Is your Userbot in this channel?\n"
                "• Try sending the invite link first (`t.me/+...`)"
            )
            return

        success = await send_media(message.chat.id, target_msg)
        if not success:
            await message.reply_text("❌ Could not forward this message.")

    except Exception as e:
        logger.error(f"Error in single post handler: {e}")
        await message.reply_text(f"❌ Failed: {e}")


# --------------- Startup ---------------

async def preload_dialogs():
    logger.info("Preloading dialogs to resolve peer cache...")
    try:
        async for _ in user.get_dialogs():
            pass
        logger.info("Dialog preload complete!")
    except Exception as e:
        logger.error(f"Dialog preload failed: {e}")

async def run_bot():
    global user_is_active
    await bot.start()
    if user:
        try:
            await user.start()
            user_is_active = True
            logger.info("Userbot started successfully!")
            await preload_dialogs()
        except Exception as e:
            user_is_active = False
            logger.error(f"❌ Userbot failed to start: {e}")

    logger.info("Bot is running!")
    await bot.stop()
    if user:
        try: await user.stop()
        except: pass

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run_bot())
