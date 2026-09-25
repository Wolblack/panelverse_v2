# PanelVerse AI v2

PanelVerse is a Telegram archive bot with a unified Web Admin ingestion and archive-control system.

## Unified Archive Ingestion

The Web Admin is integrated into the existing bot/database architecture. It is not a second archive or second database.

Workflow: Upload -> detect content type -> extract metadata -> SHA-256 -> duplicate check -> QC -> Draft/Review/Approve/Publish -> optional Telegram publication -> audit log.

Supported types: BOOK, COMIC, MANGA, ANIME, MOVIE, VIDEO, MUSIC.

PDF metadata uses pypdf. EPUB and CBZ covers are extracted when present. Music metadata uses Mutagen. Large uploads are streamed through aiohttp multipart handling.

## Setup

Use Python 3.11-3.13 for the smoothest compatibility.

    cd ~/Downloads/panelverse_v2
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Set BOT_TOKEN and ADMIN_IDS, then configure ADMIN_WEB, ADMIN_WEB_HOST, ADMIN_WEB_PORT, ADMIN_WEB_TOKEN, ADMIN_WEB_PUBLIC_URL, ARCHIVE_STORAGE_DIR and ARCHIVE_MAX_FILE_MB.

Generate a token with: python -c "import secrets; print(secrets.token_urlsafe(32))"

Run: python bot.py

Open: http://127.0.0.1:8080/admin

## Database

Existing comics, chapters, media_series and media_episodes tables are preserved.

The additive ingestion layer adds archive_items, archive_files, archive_ingestion_jobs, archive_publication_jobs and archive_audit_log.

## Telegram publication

Set TELEGRAM_PUBLISH_CHAT_ID to an authorized channel/chat. Web publication is queued rather than blocking the browser.

## Security

Do not commit .env, bot tokens or admin web tokens. Uploaded filenames are reduced to safe basenames. File access is constrained to ARCHIVE_STORAGE_DIR.

Only handle material you own, are licensed to archive/distribute, is public-domain, or otherwise have authorization to handle.

## Verification

Run: python -m compileall -q .
Run: python -c "import database; database.init_db(); print(database.archive_stats())"
Then start python bot.py and verify /admin -> + Add to Archive -> upload -> analysis -> QC -> review -> publish.