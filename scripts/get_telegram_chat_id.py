import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is empty. Put it into .env first.")

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
data = requests.get(url, timeout=15).json()
print(data)
