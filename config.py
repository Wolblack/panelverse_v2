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
