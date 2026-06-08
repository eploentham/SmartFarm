"""Print all recent messages received by your bot.
   The 'chat':{'id': ...} in the output is your TG_CHAT_ID."""
import requests

BOT_TOKEN = "8620409986:AAFPOBeTnqwRYqRhae9_nkVUE6ZY9Jh6-gw"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
r = requests.get(url, timeout=10).json()

if not r.get("ok"):
    print("ERROR:", r)
elif not r.get("result"):
    print("No messages yet. Open Telegram, send '/start' to your bot, then re-run.")
else:
    for update in r["result"]:
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        print(f"From: {sender.get('first_name')} (user_id={sender.get('id')})")
        print(f"  chat_id = {chat.get('id')}   ← THIS is your TG_CHAT_ID")
        print(f"  text    = {msg.get('text')}")
        print(f"  date    = {msg.get('date')}")
        print("-" * 40)