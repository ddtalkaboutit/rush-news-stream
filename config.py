import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

# API key used by your local ingestion engine when calling /sync
API_KEY = os.getenv("SYNC_API_KEY", "TAi-newsroom")