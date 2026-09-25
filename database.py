import sqlite3
from pathlib import Path


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE = Path("panelverse.db")


# ============================================================
# CONNECTION
# ============================================================

def connect():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ============================================================
# INITIALIZATION
# ============================================================

def init_db():
    connection = connect()

    try:
        # ----------------------------------------------------
        # COMICS
        # ----------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS comics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'manga',
                cover_file_id TEXT DEFAULT ''
            )
        """)

        # ----------------------------------------------------
        # CHAPTERS
        # ----------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comic_id INTEGER NOT NULL,
                number INTEGER NOT NULL,
                title TEXT DEFAULT '',
                file_id TEXT NOT NULL,

                FOREIGN KEY (comic_id)
                    REFERENCES comics(id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # MEDIA SERIES
        #
        # type:
        # anime
        # animation
        # movie
        # ----------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS media_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                media_type TEXT NOT NULL DEFAULT 'anime',
                cover_file_id TEXT DEFAULT ''
            )
        """)

        # ----------------------------------------------------
        # MEDIA EPISODES
        # ----------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS media_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                number INTEGER NOT NULL,
                title TEXT DEFAULT '',
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'video',

                FOREIGN KEY (series_id)
                    REFERENCES media_series(id)
                    ON DELETE CASCADE
            )
        """)

        ensure_archive_schema(connection)
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# COMICS
# ============================================================

def add_comic(
    title,
    description="",
    category="manga",
    cover_file_id=""
):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            INSERT INTO comics
            (
                title,
                description,
                category,
                cover_file_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                title,
                description,
                category,
                cover_file_id
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_comics(category=None):
    connection = connect()

    try:
        if category:
            rows = connection.execute(
                """
                SELECT *
                FROM comics
                WHERE category = ?
                ORDER BY title COLLATE NOCASE
                """,
                (category,)
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT *
                FROM comics
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_comic(comic_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT *
            FROM comics
            WHERE id = ?
            """,
            (comic_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def update_comic(
    comic_id,
    title=None,
    description=None,
    category=None,
    cover_file_id=None
):
    comic = get_comic(comic_id)

    if not comic:
        return False

    title = (
        comic["title"]
        if title is None
        else title
    )

    description = (
        comic["description"]
        if description is None
        else description
    )

    category = (
        comic["category"]
        if category is None
        else category
    )

    cover_file_id = (
        comic["cover_file_id"]
        if cover_file_id is None
        else cover_file_id
    )

    connection = connect()

    try:
        connection.execute(
            """
            UPDATE comics
            SET
                title = ?,
                description = ?,
                category = ?,
                cover_file_id = ?
            WHERE id = ?
            """,
            (
                title,
                description,
                category,
                cover_file_id,
                comic_id
            )
        )

        connection.commit()

        return True

    finally:
        connection.close()


def delete_comic(comic_id):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            DELETE FROM comics
            WHERE id = ?
            """,
            (comic_id,)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


# ============================================================
# CHAPTERS
# ============================================================

def add_chapter(
    comic_id,
    number,
    title,
    file_id
):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            INSERT INTO chapters
            (
                comic_id,
                number,
                title,
                file_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                comic_id,
                number,
                title,
                file_id
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_chapters(comic_id):
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM chapters
            WHERE comic_id = ?
            ORDER BY number
            """,
            (comic_id,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_chapter(chapter_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                chapters.*,
                comics.title AS comic_title
            FROM chapters
            JOIN comics
                ON comics.id = chapters.comic_id
            WHERE chapters.id = ?
            """,
            (chapter_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def delete_chapter(chapter_id):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            DELETE FROM chapters
            WHERE id = ?
            """,
            (chapter_id,)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


# ============================================================
# MEDIA SERIES
# ============================================================

def add_media_series(
    title,
    description="",
    media_type="anime",
    cover_file_id=""
):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            INSERT INTO media_series
            (
                title,
                description,
                media_type,
                cover_file_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                title,
                description,
                media_type,
                cover_file_id
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_media_series(media_type=None):
    connection = connect()

    try:
        if media_type:
            rows = connection.execute(
                """
                SELECT *
                FROM media_series
                WHERE media_type = ?
                ORDER BY title COLLATE NOCASE
                """,
                (media_type,)
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT *
                FROM media_series
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_media_series_by_id(series_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT *
            FROM media_series
            WHERE id = ?
            """,
            (series_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def update_media_series(
    series_id,
    title=None,
    description=None,
    media_type=None,
    cover_file_id=None
):
    series = get_media_series_by_id(series_id)

    if not series:
        return False

    title = (
        series["title"]
        if title is None
        else title
    )

    description = (
        series["description"]
        if description is None
        else description
    )

    media_type = (
        series["media_type"]
        if media_type is None
        else media_type
    )

    cover_file_id = (
        series["cover_file_id"]
        if cover_file_id is None
        else cover_file_id
    )

    connection = connect()

    try:
        connection.execute(
            """
            UPDATE media_series
            SET
                title = ?,
                description = ?,
                media_type = ?,
                cover_file_id = ?
            WHERE id = ?
            """,
            (
                title,
                description,
                media_type,
                cover_file_id,
                series_id
            )
        )

        connection.commit()

        return True

    finally:
        connection.close()


def delete_media_series(series_id):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            DELETE FROM media_series
            WHERE id = ?
            """,
            (series_id,)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


# ============================================================
# MEDIA EPISODES
# ============================================================

def add_media_episode(
    series_id,
    number,
    title,
    file_id,
    file_type="video"
):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            INSERT INTO media_episodes
            (
                series_id,
                number,
                title,
                file_id,
                file_type
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                series_id,
                number,
                title,
                file_id,
                file_type
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_media_episodes(series_id):
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM media_episodes
            WHERE series_id = ?
            ORDER BY number
            """,
            (series_id,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_media_episode(episode_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                media_episodes.*,
                media_series.title AS series_title
            FROM media_episodes
            JOIN media_series
                ON media_series.id = media_episodes.series_id
            WHERE media_episodes.id = ?
            """,
            (episode_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def delete_media_episode(episode_id):
    connection = connect()

    try:
        cursor = connection.execute(
            """
            DELETE FROM media_episodes
            WHERE id = ?
            """,
            (episode_id,)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


# ============================================================
# STATISTICS
# ============================================================

def count_comics():
    connection = connect()

    try:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM comics
            """
        ).fetchone()[0]

    finally:
        connection.close()


def count_chapters():
    connection = connect()

    try:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM chapters
            """
        ).fetchone()[0]

    finally:
        connection.close()


def count_media_series():
    connection = connect()

    try:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM media_series
            """
        ).fetchone()[0]

    finally:
        connection.close()


def count_media_episodes():
    connection = connect()

    try:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM media_episodes
            """
        ).fetchone()[0]

    finally:
        connection.close()

# ============================================================
# UNIFIED ARCHIVE INGESTION
# ============================================================

def ensure_archive_schema(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS archive_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            subtitle TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'DRAFT',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            detected_confidence INTEGER NOT NULL DEFAULT 0,
            completeness INTEGER NOT NULL DEFAULT 0,
            cover_path TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            legacy_kind TEXT NOT NULL DEFAULT '',
            legacy_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at TEXT
        );
        CREATE TABLE IF NOT EXISTS archive_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            extension TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            detected_type TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES archive_items(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS archive_ingestion_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            stage TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES archive_items(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS archive_publication_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            target TEXT NOT NULL DEFAULT 'telegram',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES archive_items(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS archive_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            item_id INTEGER,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES archive_items(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_archive_items_type_status ON archive_items(content_type, status);
        CREATE INDEX IF NOT EXISTS idx_archive_items_title ON archive_items(title COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_archive_files_item ON archive_files(item_id);
        CREATE INDEX IF NOT EXISTS idx_archive_files_hash ON archive_files(sha256);
        CREATE INDEX IF NOT EXISTS idx_archive_jobs_status ON archive_ingestion_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_archive_publication_status ON archive_publication_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_archive_audit_item ON archive_audit_log(item_id);
    """)


def archive_create_item(content_type, title="", metadata=None, created_by="", status="DRAFT", detected_confidence=0):
    import json
    connection = connect()
    try:
        cur = connection.execute(
            "INSERT INTO archive_items(content_type,title,status,metadata_json,created_by,detected_confidence) VALUES (?,?,?,?,?,?)",
            (content_type, title or "", status, json.dumps(metadata or {}, ensure_ascii=False), str(created_by), int(detected_confidence or 0))
        )
        connection.commit()
        return cur.lastrowid
    finally:
        connection.close()


def archive_update_item(item_id, **fields):
    import json
    allowed = {"content_type","title","subtitle","description","status","metadata_json","detected_confidence","completeness","cover_path","legacy_kind","legacy_id","published_at"}
    updates, values = [], []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "metadata_json" and not isinstance(value, str):
            value = json.dumps(value or {}, ensure_ascii=False)
        updates.append(key + " = ?")
        values.append(value)
    if not updates:
        return False
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(item_id)
    connection = connect()
    try:
        cur = connection.execute("UPDATE archive_items SET " + ", ".join(updates) + " WHERE id = ?", values)
        connection.commit()
        return cur.rowcount > 0
    finally:
        connection.close()


def archive_get_item(item_id):
    import json
    connection = connect()
    try:
        row = connection.execute("SELECT * FROM archive_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except Exception:
            item["metadata"] = {}
        item["files"] = [dict(x) for x in connection.execute("SELECT * FROM archive_files WHERE item_id = ? ORDER BY id", (item_id,)).fetchall()]
        return item
    finally:
        connection.close()


def archive_list_items(query="", content_type="", status="", limit=50, offset=0):
    import json
    connection = connect()
    try:
        where, params = [], []
        if query:
            where.append("(title LIKE ? OR description LIKE ? OR metadata_json LIKE ?)")
            q = "%" + query + "%"
            params.extend([q, q, q])
        if content_type:
            where.append("content_type = ?")
            params.append(content_type)
        if status:
            where.append("status = ?")
            params.append(status)
        clause = " WHERE " + " AND ".join(where) if where else ""
        rows = connection.execute(
            "SELECT * FROM archive_items" + clause + " ORDER BY datetime(updated_at) DESC, id DESC LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)]
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except Exception:
                item["metadata"] = {}
            result.append(item)
        return result
    finally:
        connection.close()


def archive_add_file(item_id, original_name, storage_path, mime_type, extension, size_bytes, sha256, detected_type, metadata=None):
    import json
    connection = connect()
    try:
        cur = connection.execute(
            "INSERT INTO archive_files(item_id,original_name,storage_path,mime_type,extension,size_bytes,sha256,detected_type,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (item_id, original_name, storage_path, mime_type, extension, int(size_bytes), sha256, detected_type, json.dumps(metadata or {}, ensure_ascii=False))
        )
        connection.commit()
        return cur.lastrowid
    finally:
        connection.close()


def archive_find_duplicate(sha256="", title="", isbn=""):
    connection = connect()
    try:
        if sha256:
            row = connection.execute(
                "SELECT i.* FROM archive_files f JOIN archive_items i ON i.id=f.item_id WHERE f.sha256=? LIMIT 1",
                (sha256,)
            ).fetchone()
            if row:
                return dict(row), "exact_hash", 100
        if isbn:
            row = connection.execute("SELECT * FROM archive_items WHERE metadata_json LIKE ? LIMIT 1", ("%" + isbn + "%",)).fetchone()
            if row:
                return dict(row), "isbn", 100
        if title:
            row = connection.execute("SELECT * FROM archive_items WHERE lower(trim(title)) = lower(trim(?)) LIMIT 1", (title,)).fetchone()
            if row:
                return dict(row), "title", 94
        return None
    finally:
        connection.close()


def archive_create_job(item_id):
    connection = connect()
    try:
        cur = connection.execute("INSERT INTO archive_ingestion_jobs(item_id) VALUES (?)", (item_id,))
        connection.commit()
        return cur.lastrowid
    finally:
        connection.close()


def archive_update_job(job_id, status=None, stage=None, progress=None, error=None):
    values, updates = [], []
    if status is not None:
        updates.append("status=?"); values.append(status)
    if stage is not None:
        updates.append("stage=?"); values.append(stage)
    if progress is not None:
        updates.append("progress=?"); values.append(max(0, min(100, int(progress))))
    if error is not None:
        updates.append("error=?"); values.append(error)
    if not updates:
        return
    updates.append("updated_at=CURRENT_TIMESTAMP"); values.append(job_id)
    connection = connect()
    try:
        connection.execute("UPDATE archive_ingestion_jobs SET " + ", ".join(updates) + " WHERE id=?", values)
        connection.commit()
    finally:
        connection.close()


def archive_get_job(job_id):
    connection = connect()
    try:
        row = connection.execute("SELECT * FROM archive_ingestion_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def archive_create_publication_job(item_id, target="telegram"):
    connection = connect()
    try:
        cur = connection.execute("INSERT INTO archive_publication_jobs(item_id,target) VALUES (?,?)", (item_id, target))
        connection.commit()
        return cur.lastrowid
    finally:
        connection.close()


def archive_audit(actor, action, item_id=None, details=None):
    import json
    connection = connect()
    try:
        connection.execute(
            "INSERT INTO archive_audit_log(actor,action,item_id,details_json) VALUES (?,?,?,?)",
            (str(actor), action, item_id, json.dumps(details or {}, ensure_ascii=False))
        )
        connection.commit()
    finally:
        connection.close()


def archive_stats():
    connection = connect()
    try:
        def count(sql):
            return connection.execute(sql).fetchone()[0]
        return {
            "items": count("SELECT COUNT(*) FROM archive_items"),
            "draft": count("SELECT COUNT(*) FROM archive_items WHERE status='DRAFT'"),
            "review": count("SELECT COUNT(*) FROM archive_items WHERE status='REVIEW'"),
            "published": count("SELECT COUNT(*) FROM archive_items WHERE status='PUBLISHED'"),
            "files": count("SELECT COUNT(*) FROM archive_files"),
            "jobs": count("SELECT COUNT(*) FROM archive_ingestion_jobs WHERE status NOT IN ('COMPLETED','FAILED')")
        }
    finally:
        connection.close()
