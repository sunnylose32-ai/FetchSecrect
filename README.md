# Telegram Private Channel Message Forwarder Bot

A simple Telegram bot written in Python using Pyrogram that allows users to send a private channel message link (e.g. `https://t.me/c/123456789/123`) and forwards that exact message in the bot chat.

## Features

- **Forward Post**: Send a link, and the bot forwards it back.
- **Restricted Content**: Automatically bypasses "Restrict Saving Content" by downloading/uploading.
- **Userbot Support**: Access private channels the bot isn't in!
- **Auto-Join**: Send a Join Link (`t.me/+xyz`), and the bot's user account will join automatically.

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Rename `.env.sample` to `.env` and fill in your credentials.
   ```env
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   # USER_SESSION is optional for advanced users who want to fetch from channels where the bot is not present.
   ```

3. **Important**: Add your bot to the private channel you want to forward messages from! (The bot must be an admin or a member in the private channel to read its messages).

## Run

Run the bot script:

```bash
python bot.py
```

## How to use

1. Go to your private channel and copy a Post Link (it will look like `https://t.me/c/<chat_id>/<msg_id>`).
2. Send this link to your bot.
3. The bot will automatically retrieve the message from the channel and forward/copy it back to you in your chat.
