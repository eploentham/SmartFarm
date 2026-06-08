"""Send a yes/no question, wait up to 60s for the reply, report what came back.
   This is exactly what spray_monitor will do for chemical confirmation."""
import requests
import time

BOT_TOKEN = "8620409986:AAFPOBeTnqwRYqRhae9_nkVUE6ZY9Jh6-gw"
CHAT_ID   = "8394445325"   # your TG_CHAT_ID from tg_test1_getid.py
TIMEOUT_S = 60

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 1. Send the question
print("Sending question...")
r = requests.post(f"{BASE}/sendMessage", json={
    "chat_id": CHAT_ID,
    "text": "🧪 TEST: Are you about to spray chemicals?\nReply *yes* or *no*."
}, timeout=10).json()

if not r.get("ok"):
    print("Send failed:", r)
    exit(1)

prompt_ts = time.time()
print(f"Question sent at {time.strftime('%H:%M:%S')}. Waiting up to {TIMEOUT_S}s for reply...")

# 2. Long-poll for the reply
offset = None
deadline = time.time() + TIMEOUT_S
result = None

while time.time() < deadline:
    params = {"timeout": 25}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=30).json()
    except Exception as e:
        print("poll error:", e)
        time.sleep(2)
        continue

    for upd in r.get("result", []):
        offset = upd["update_id"] + 1
        msg = upd.get("message") or {}
        if msg.get("date", 0) < prompt_ts:
            continue              # ignore messages from before our question
        text = (msg.get("text") or "").strip().lower()
        print(f"  ← got: {text!r}")
        if text in ("yes", "y", "ใช่", "/yes"):
            result = "YES"
            break
        if text in ("no", "n", "ไม่", "/no", "cancel"):
            result = "NO"
            break
    if result:
        break

# 3. Report
print(f"\nResult after {time.time()-prompt_ts:.1f}s: {result or 'TIMEOUT'}")

# 4. Echo back to Telegram
echo = {
    "YES":     "✅ Great — would now show camera 2 on TV.",
    "NO":      "🛑 OK, cancelling the log.",
    None:      "⏰ Timeout — no reply received."
}[result]
requests.post(f"{BASE}/sendMessage",
              json={"chat_id": CHAT_ID, "text": echo}, timeout=10)