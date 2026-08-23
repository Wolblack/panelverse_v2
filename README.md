# PanelVerse AI v2

A cleaner Telegram bot MVP for PanelVerse with an inline-button menu, image recognition, library/search, recommendations, favorites, popular/latest views, and an authorized-download infrastructure.

## Setup

Use Python 3.11–3.13 for the smoothest compatibility.

```bash
cd ~/Downloads/panelverse_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables before running:

```bash
export TELEGRAM_BOT_TOKEN='YOUR_TOKEN'
export OPENAI_API_KEY='YOUR_KEY'
export OPENAI_MODEL='gpt-5.5'
export ADMIN_ID='YOUR_TELEGRAM_USER_ID'
python3 bot.py
```

Do not paste secrets into chat or commit them to GitHub.

## Download feature

The bot can send a Telegram `file_id` stored in the catalog. Only add files you own, licensed, public-domain, or otherwise authorized to distribute.

## Next production upgrades

- Proper admin dashboard and metadata editor
- PostgreSQL instead of SQLite
- Vector embeddings for better visual/title similarity
- OCR for issue numbers and speech bubbles
- Cover/image deduplication
- User rate limits and abuse controls
- Cloud deployment for 24/7 operation
