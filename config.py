# config.py
import os
import platform
from dotenv import load_dotenv

load_dotenv()

# Directory settings - use /tmp on Render (Linux) for better performance
if platform.system() == "Linux":
    DOWNLOAD_DIR = "/tmp/downloads"
else:
    DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Template defaults
DEFAULT_COLOR1 = "#001534"
DEFAULT_COLOR2 = "#6409a4"
DEFAULT_PLATFORM = "instagram"

# Template dimensions (9:16 vertical)
TEMPLATE_WIDTH = 1080
TEMPLATE_HEIGHT = 1920
