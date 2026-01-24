#config
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "https://dev.rushnewstream.com/api")
API_SYNC_STORIES_URL = f"{API_BASE_URL}/sync_stories"
API_SYNC_TRENDS_URL = f"{API_BASE_URL}/sync_trends"
API_PURGE_TRENDS_URL = f"{API_BASE_URL}/purge_trends"

API_KEY = os.getenv("SYNC_API_KEY", "TAi-newsroom")

X_COOKIE_FILE = os.getenv("X_COOKIE_FILE", r"C:\RUSH\x_cookie.json")

# Scheduling (minutes)
X_INTERVAL_MINUTES = 15
NEWS_INTERVAL_MINUTES = 60
CHROME_NEWS_INTERVAL_MINUTES = 60
GOOGLE_TRENDS_INTERVAL_MINUTES = 60
