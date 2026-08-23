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