import os
from dotenv import load_dotenv

# Load .env from the project directory
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = {
    int(user_id.strip())
    for user_id in os.getenv("ADMIN_IDS", "").split(",")
    if user_id.strip().isdigit()
}


# ============================================================
# VALIDATION
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN to your .env file."
    )

if not ADMIN_IDS:
    raise RuntimeError(
        "ADMIN_IDS is missing. Add your Telegram user ID(s) "
        "to the .env file."
    )


# ============================================================
# WEB ADMIN / UNIFIED ARCHIVE
# ============================================================

ADMIN_WEB = os.getenv("ADMIN_WEB", "1").strip()
ADMIN_WEB_HOST = os.getenv("ADMIN_WEB_HOST", "127.0.0.1").strip()
ADMIN_WEB_PORT = int(os.getenv("ADMIN_WEB_PORT", "8080"))
ADMIN_WEB_TOKEN = os.getenv("ADMIN_WEB_TOKEN", "").strip()
ADMIN_WEB_PUBLIC_URL = os.getenv(
    "ADMIN_WEB_PUBLIC_URL",
    f"http://{ADMIN_WEB_HOST}:{ADMIN_WEB_PORT}/admin"
).strip()

ARCHIVE_STORAGE_DIR = os.getenv("ARCHIVE_STORAGE_DIR", "archive_storage").strip()
ARCHIVE_MAX_FILE_MB = int(os.getenv("ARCHIVE_MAX_FILE_MB", "4096"))
TELEGRAM_PUBLISH_CHAT_ID = os.getenv("TELEGRAM_PUBLISH_CHAT_ID", "").strip()
