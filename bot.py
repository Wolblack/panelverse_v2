import asyncio
import logging
import re
import tempfile
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from aiogram.utils.deep_linking import create_start_link
from pypdf import PdfReader

from config import BOT_TOKEN, ADMIN_IDS
from web_admin import start_web_admin, stop_web_admin

from database import (
    init_db,

    # Comics
    add_comic,
    get_comics,
    get_comic,
    update_comic,
    delete_comic,

    # Chapters
    add_chapter,
    get_chapters,
    get_chapter,
    delete_chapter,

    # Statistics
    count_comics,
    count_chapters,

    # Media
    add_media_series,
    get_media_series,
    get_media_series_by_id,
    delete_media_series,

    add_media_episode,
    get_media_episodes,
    get_media_episode,
    delete_media_episode,

    count_media_series,
    count_media_episodes,
)


# ============================================================
# SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Temporary state for admin workflows.
pending = {}


# ============================================================
# HELPERS
# ============================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def category_name(category):
    names = {
        "marvel": "🔴 MARVEL",
        "dc": "🔵 DC",
        "manga": "📕 MANGA",
    }

    return names.get(
        category,
        "📚 ARCHIVE"
    )


def media_type_name(media_type):
    names = {
        "anime": "🎞️ ANIME",
        "animation": "🎨 ANIMATION",
        "movie": "🎬 MOVIE",
    }

    return names.get(
        media_type,
        "🎬 MEDIA"
    )


# ============================================================
# MAIN USER KEYBOARD
# ============================================================

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔴 Marvel",
                    callback_data="category:marvel"
                ),
                InlineKeyboardButton(
                    text="🔵 DC",
                    callback_data="category:dc"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📕 Manga",
                    callback_data="category:manga"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📚 All Titles",
                    callback_data="all_comics"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Media",
                    callback_data="media_home"
                ),
                InlineKeyboardButton(
                    text="🤖 AI Assistant",
                    callback_data="ai_home"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ About",
                    callback_data="about"
                ),
            ],
        ]
    )


def home_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="home"
                )
            ]
        ]
    )


# ============================================================
# COMIC KEYBOARDS
# ============================================================

def comic_keyboard(comic_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Chapters",
                    callback_data=f"chapters:{comic_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Share",
                    callback_data=f"share_comic:{comic_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Back",
                    callback_data="back_categories"
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="home"
                ),
            ],
        ]
    )


def chapters_keyboard(comic_id, chapters):
    buttons = []

    for chapter_data in chapters:
        title = f"📖 Chapter {chapter_data['number']}"

        if chapter_data["title"]:
            title += f" — {chapter_data['title']}"

        buttons.append([
            InlineKeyboardButton(
                text=title,
                callback_data=f"chapter:{chapter_data['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Comic",
            callback_data=f"comic:{comic_id}"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# ============================================================
# ADMIN KEYBOARD
# ============================================================

def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Comic",
                    callback_data="admin_add"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Manage Comics",
                    callback_data="admin_comics"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📖 Manage Chapters",
                    callback_data="admin_chapters"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Manage Media",
                    callback_data="admin_media"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Statistics",
                    callback_data="admin_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 User Menu",
                    callback_data="home"
                )
            ],
        ]
    )


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject
):
    args = command.args

    if not args:
        await message.answer(
            "<b>📚 PANELVERSE</b>\n\n"
            "Your digital home for manga, comics and media.\n\n"
            "Choose an archive:",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
        return

    # --------------------------------------------------------
    # COMIC DEEP LINK
    # --------------------------------------------------------

    if args.startswith("comic_"):
        try:
            comic_id = int(
                args.replace("comic_", "", 1)
            )
        except ValueError:
            await message.answer(
                "❌ Invalid comic link."
            )
            return

        await show_comic_message(
            message,
            comic_id
        )
        return

    # --------------------------------------------------------
    # CHAPTER DEEP LINK
    # --------------------------------------------------------

    if args.startswith("chapter_"):
        try:
            chapter_id = int(
                args.replace("chapter_", "", 1)
            )
        except ValueError:
            await message.answer(
                "❌ Invalid chapter link."
            )
            return

        await send_chapter(
            message,
            chapter_id
        )
        return

    # --------------------------------------------------------
    # MEDIA EPISODE DEEP LINK
    # --------------------------------------------------------

    if args.startswith("media_episode_"):
        try:
            episode_id = int(
                args.replace("media_episode_", "", 1)
            )
        except ValueError:
            await message.answer(
                "❌ Invalid episode link."
            )
            return

        await send_media_episode(
            message,
            episode_id
        )
        return

    await message.answer(
        "❌ Unknown PanelVerse link.",
        reply_markup=main_keyboard()
    )


# ============================================================
# HOME
# ============================================================

@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>📚 PANELVERSE</b>\n\n"
        "Your digital home for manga, comics and media.\n\n"
        "Choose an archive:",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "back_categories")
async def back_categories(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>📚 PANELVERSE</b>\n\n"
        "Choose an archive:",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

    await callback.answer()

@dp.callback_query(F.data == "media_menu")
async def media_menu(callback: CallbackQuery):

    await callback.message.edit_text(
        "<b>🎬 PANELVERSE MEDIA</b>\n\n"
        "Choose a media archive:",
        parse_mode="HTML",
        reply_markup=media_keyboard()
    )

    await callback.answer()

# ============================================================
# CATEGORY
# ============================================================

@dp.callback_query(F.data.startswith("category:"))
async def category(callback: CallbackQuery):
    category_value = callback.data.split(":", 1)[1]

    comics = get_comics(category_value)

    if not comics:
        await callback.message.edit_text(
            f"<b>{category_name(category_value)}</b>\n\n"
            "There are no titles here yet.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Back",
                            callback_data="home"
                        )
                    ]
                ]
            )
        )

        await callback.answer()
        return

    buttons = []

    for comic in comics:
        buttons.append([
            InlineKeyboardButton(
                text=f"📖 {comic['title']}",
                callback_data=f"comic:{comic['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Home",
            callback_data="home"
        )
    ])

    await callback.message.edit_text(
        f"<b>{category_name(category_value)}</b>\n\n"
        "Choose a title:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# ============================================================
# ALL COMICS
# ============================================================

@dp.callback_query(F.data == "all_comics")
async def all_comics(callback: CallbackQuery):
    comics = get_comics()

    if not comics:
        await callback.message.edit_text(
            "📚 <b>ARCHIVE</b>\n\n"
            "The archive is empty.",
            parse_mode="HTML",
            reply_markup=home_keyboard()
        )

        await callback.answer()
        return

    buttons = []

    for comic in comics:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{category_name(comic['category'])} "
                    f"• {comic['title']}"
                ),
                callback_data=f"comic:{comic['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Home",
            callback_data="home"
        )
    ])

    await callback.message.edit_text(
        "📚 <b>ALL TITLES</b>\n\n"
        "Choose a title:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# ============================================================
# COMIC DISPLAY
# ============================================================

async def show_comic_message(
    message,
    comic_id
):
    comic = get_comic(comic_id)

    if not comic:
        await message.answer(
            "❌ Comic not found.",
            reply_markup=main_keyboard()
        )
        return

    chapters = get_chapters(comic_id)

    description = (
        comic["description"]
        or "No description available."
    )

    text = (
        f"<b>{category_name(comic['category'])}</b>\n\n"
        f"<b>📖 {comic['title']}</b>\n\n"
        f"{description}\n\n"
        f"📚 <b>{len(chapters)}</b> chapters"
    )

    if comic["cover_file_id"]:
        await message.answer_photo(
            photo=comic["cover_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=comic_keyboard(comic_id)
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=comic_keyboard(comic_id)
        )


@dp.callback_query(F.data.startswith("comic:"))
async def comic(callback: CallbackQuery):
    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    chapters = get_chapters(comic_id)

    description = (
        comic_data["description"]
        or "No description available."
    )

    text = (
        f"<b>{category_name(comic_data['category'])}</b>\n\n"
        f"<b>📖 {comic_data['title']}</b>\n\n"
        f"{description}\n\n"
        f"📚 <b>{len(chapters)}</b> chapters"
    )

    if comic_data["cover_file_id"]:
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer_photo(
            photo=comic_data["cover_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=comic_keyboard(comic_id)
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=comic_keyboard(comic_id)
        )

    await callback.answer()


# ============================================================
# CHAPTER LIST
# ============================================================

@dp.callback_query(F.data.startswith("chapters:"))
async def chapters(callback: CallbackQuery):
    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    chapter_list = get_chapters(comic_id)

    if not chapter_list:
        await callback.answer(
            "No chapters yet.",
            show_alert=True
        )
        return

    text = (
        f"<b>📖 {comic_data['title']}</b>\n\n"
        "Choose a chapter:"
    )

    keyboard = chapters_keyboard(
        comic_id,
        chapter_list
    )

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    await callback.answer()


# ============================================================
# SEND CHAPTER
# ============================================================

async def send_chapter(
    message,
    chapter_id
):
    chapter_data = get_chapter(chapter_id)

    if not chapter_data:
        await message.answer(
            "❌ Chapter not found."
        )
        return

    caption = (
        f"📖 <b>{chapter_data['comic_title']}</b>\n"
        f"Chapter {chapter_data['number']}"
    )

    if chapter_data["title"]:
        caption += f" — {chapter_data['title']}"

    await message.answer_document(
        document=chapter_data["file_id"],
        caption=caption,
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("chapter:"))
async def chapter(callback: CallbackQuery):
    chapter_id = int(
        callback.data.split(":", 1)[1]
    )

    await send_chapter(
        callback.message,
        chapter_id
    )

    await callback.answer(
        "📄 Sending chapter..."
    )


# ============================================================
# SHARE COMIC
# ============================================================

@dp.callback_query(F.data.startswith("share_comic:"))
async def share_comic(callback: CallbackQuery):
    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    link = await create_start_link(
        bot,
        f"comic_{comic_id}"
    )

    await callback.message.answer(
        f"🔗 <b>{comic_data['title']}</b>\n\n"
        f"{link}",
        parse_mode="HTML"
    )

    await callback.answer()


# ============================================================
# ABOUT
# ============================================================

@dp.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>📚 PANELVERSE</b>\n\n"
        "A curated digital archive for manga, comics "
        "and animation.\n\n"
        "🔴 Marvel\n"
        "🔵 DC\n"
        "📕 Manga\n"
        "🎬 Anime & Animation\n\n"
        "Select a title to explore its content.",
        parse_mode="HTML",
        reply_markup=home_keyboard()
    )

    await callback.answer()


# ============================================================
# MEDIA
# ============================================================

def media_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎞️ Anime",
                    callback_data="media_category:anime"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Animation",
                    callback_data="media_category:animation"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Movies",
                    callback_data="media_category:movie"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📂 All Media",
                    callback_data="media_all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="home"
                )
            ],
        ]
    )


def media_series_keyboard(series_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📺 Episodes",
                    callback_data=f"media_episodes:{series_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Media",
                    callback_data="media_home"
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="home"
                ),
            ],
        ]
    )


def media_episode_keyboard(
    series_id,
    episodes
):
    buttons = []

    for episode_data in episodes:
        title = (
            f"▶️ Episode "
            f"{episode_data['number']}"
        )

        if episode_data["title"]:
            title += (
                f" — {episode_data['title']}"
            )

        buttons.append([
            InlineKeyboardButton(
                text=title,
                callback_data=(
                    f"media_episode:"
                    f"{episode_data['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Series",
            callback_data=f"media_series:{series_id}"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


@dp.callback_query(F.data == "media_home")
async def media_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>🎬 PANELVERSE MEDIA</b>\n\n"
        "Choose a media archive:",
        parse_mode="HTML",
        reply_markup=media_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("media_category:"))
async def media_category(callback: CallbackQuery):
    media_type = callback.data.split(":", 1)[1]

    series_list = get_media_series(
        media_type
    )

    if not series_list:
        await callback.message.edit_text(
            f"<b>{media_type_name(media_type)}</b>\n\n"
            "There are no titles here yet.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Media",
                            callback_data="media_home"
                        )
                    ]
                ]
            )
        )

        await callback.answer()
        return

    buttons = []

    for series in series_list:
        buttons.append([
            InlineKeyboardButton(
                text=f"🎬 {series['title']}",
                callback_data=(
                    f"media_series:{series['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Media",
            callback_data="media_home"
        )
    ])

    await callback.message.edit_text(
        f"<b>{media_type_name(media_type)}</b>\n\n"
        "Choose a title:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


@dp.callback_query(F.data == "media_all")
async def media_all(callback: CallbackQuery):
    series_list = get_media_series()

    if not series_list:
        await callback.message.edit_text(
            "<b>🎬 ALL MEDIA</b>\n\n"
            "The media archive is empty.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Media",
                            callback_data="media_home"
                        )
                    ]
                ]
            )
        )

        await callback.answer()
        return

    buttons = []

    for series in series_list:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{media_type_name(series['media_type'])} "
                    f"• {series['title']}"
                ),
                callback_data=(
                    f"media_series:{series['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Media",
            callback_data="media_home"
        )
    ])

    await callback.message.edit_text(
        "<b>🎬 ALL MEDIA</b>\n\n"
        "Choose a title:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("media_series:"))
async def media_series(callback: CallbackQuery):
    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Media title not found.",
            show_alert=True
        )
        return

    episodes = get_media_episodes(
        series_id
    )

    text = (
        f"<b>{media_type_name(series['media_type'])}</b>\n\n"
        f"<b>🎬 {series['title']}</b>\n\n"
        f"{series['description'] or 'No description available.'}\n\n"
        f"📺 Episodes: <b>{len(episodes)}</b>"
    )

    if series["cover_file_id"]:
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer_photo(
            photo=series["cover_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=media_series_keyboard(
                series_id
            )
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=media_series_keyboard(
                series_id
            )
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("media_episodes:"))
async def media_episodes(callback: CallbackQuery):
    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Media title not found.",
            show_alert=True
        )
        return

    episodes = get_media_episodes(
        series_id
    )

    if not episodes:
        await callback.answer(
            "No episodes have been added yet.",
            show_alert=True
        )
        return

    text = (
        f"<b>🎬 {series['title']}</b>\n\n"
        "Choose an episode:"
    )

    keyboard = media_episode_keyboard(
        series_id,
        episodes
    )

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    await callback.answer()


async def send_media_episode(
    message,
    episode_id
):
    episode = get_media_episode(
        episode_id
    )

    if not episode:
        await message.answer(
            "❌ Episode not found."
        )
        return

    caption = (
        f"🎬 <b>{episode['series_title']}</b>\n"
        f"📺 Episode {episode['number']}"
    )

    if episode["title"]:
        caption += f" — {episode['title']}"

    if episode["file_kind"] == "video":
        await message.answer_video(
            video=episode["file_id"],
            caption=caption,
            parse_mode="HTML"
        )
    else:
        await message.answer_document(
            document=episode["file_id"],
            caption=caption,
            parse_mode="HTML"
        )


@dp.callback_query(F.data.startswith("media_episode:"))
async def media_episode(callback: CallbackQuery):
    episode_id = int(
        callback.data.split(":", 1)[1]
    )

    await send_media_episode(
        callback.message,
        episode_id
    )

    await callback.answer(
        "▶️ Sending episode..."
    )
def media_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎞️ Anime",
                    callback_data="media_category:anime"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Animation",
                    callback_data="media_category:animation"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📺 All Media",
                    callback_data="media_category:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="home"
                )
            ]
        ]
    )

# ============================================================
# AI BUTTON
# ============================================================

@dp.callback_query(F.data == "ai_home")
async def ai_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>🤖 PANELVERSE AI</b>\n\n"
        "AI Assistant is coming next.\n\n"
        "This section will let you talk with "
        "PanelVerse AI about comics, manga, "
        "characters and stories.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Home",
                        callback_data="home"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.message(Command("admin"))
async def admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(
            "⛔ You are not authorized."
        )
        return

    await message.answer(
        "<b>⚙️ PANELVERSE ADMIN</b>\n\n"
        "Content management and system controls.",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "<b>⚙️ PANELVERSE ADMIN</b>\n\n"
        "Content management and system controls.",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN STATISTICS
# ============================================================

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "<b>📊 PANELVERSE STATISTICS</b>\n\n"
        f"📚 Comics: <b>{count_comics()}</b>\n"
        f"📖 Chapters: <b>{count_chapters()}</b>\n"
        f"🎬 Media Series: <b>{count_media_series()}</b>\n"
        f"📺 Media Episodes: <b>{count_media_episodes()}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Admin",
                        callback_data="admin_home"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# ADMIN COMICS
# ============================================================

@dp.callback_query(F.data == "admin_comics")
async def admin_comics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    comics = get_comics()

    buttons = []

    for comic_data in comics:
        buttons.append([
            InlineKeyboardButton(
                text=f"📖 {comic_data['title']}",
                callback_data=(
                    f"admin_view:{comic_data['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="➕ Add Comic",
            callback_data="admin_add"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Admin",
            callback_data="admin_home"
        )
    ])

    await callback.message.edit_text(
        "<b>📚 MANAGE COMICS</b>\n\n"
        "Select a title:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# ============================================================
# ADMIN VIEW COMIC
# ============================================================

@dp.callback_query(F.data.startswith("admin_view:"))
async def admin_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    chapters_list = get_chapters(
        comic_id
    )

    text = (
        "<b>📖 COMIC MANAGEMENT</b>\n\n"
        f"Title: <b>{comic_data['title']}</b>\n"
        f"Category: {category_name(comic_data['category'])}\n"
        f"Chapters: <b>{len(chapters_list)}</b>\n\n"
        f"{comic_data['description'] or 'No description'}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Chapters",
                    callback_data=(
                        f"admin_chapters:{comic_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=(
                        f"admin_delete:{comic_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Comics",
                    callback_data="admin_comics"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


# ============================================================
# ADMIN ADD COMIC
# ============================================================

@dp.callback_query(F.data == "admin_add")
async def admin_add(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    pending[callback.from_user.id] = {
        "action": "add_comic"
    }

    await callback.message.edit_text(
        "<b>➕ ADD COMIC</b>\n\n"
        "Send the comic information in this format:\n\n"
        "<code>Title | Category | Description</code>\n\n"
        "Category must be:\n"
        "🔴 marvel\n"
        "🔵 dc\n"
        "📕 manga\n\n"
        "Example:\n"
        "<code>Batman | dc | The Dark Knight...</code>\n\n"
        "After that, send the cover image.",
        parse_mode="HTML"
    )

    await callback.answer()


# ============================================================
# ADMIN CHAPTERS
# ============================================================

@dp.callback_query(F.data == "admin_chapters")
async def admin_chapters(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    comics = get_comics()

    buttons = []

    for comic_data in comics:
        buttons.append([
            InlineKeyboardButton(
                text=f"📖 {comic_data['title']}",
                callback_data=(
                    f"admin_chapters:{comic_data['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Admin",
            callback_data="admin_home"
        )
    ])

    await callback.message.edit_text(
        "<b>📖 MANAGE CHAPTERS</b>\n\n"
        "Choose a comic:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("admin_chapters:"))
async def admin_chapter_list(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    chapters_list = get_chapters(
        comic_id
    )

    buttons = []

    for chapter_data in chapters_list:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"📖 Chapter "
                    f"{chapter_data['number']}"
                ),
                callback_data=(
                    f"admin_chapter:"
                    f"{chapter_data['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="➕ Add Chapter",
            callback_data="admin_add_chapter"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Comics",
            callback_data="admin_comics"
        )
    ])

    await callback.message.edit_text(
        f"<b>📖 {comic_data['title']}</b>\n\n"
        f"Chapters: {len(chapters_list)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_add_chapter")
async def admin_add_chapter(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    pending[callback.from_user.id] = {
        "action": "add_chapter"
    }

    await callback.message.edit_text(
        "<b>📖 ADD CHAPTER</b>\n\n"
        "Send:\n\n"
        "<code>Comic ID | Chapter Number | Title</code>\n\n"
        "Then send the PDF.",
        parse_mode="HTML"
    )

    await callback.answer()


# ============================================================
# ADMIN MEDIA
# ============================================================

def admin_media_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Series",
                    callback_data="admin_media_add"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Manage Series",
                    callback_data="admin_media_series"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Admin",
                    callback_data="admin_home"
                )
            ],
        ]
    )


@dp.callback_query(F.data == "admin_media")
async def admin_media(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "<b>🎬 MEDIA MANAGEMENT</b>\n\n"
        "Manage anime, animation and movies.",
        parse_mode="HTML",
        reply_markup=admin_media_keyboard()
    )

    await callback.answer()


# ------------------------------------------------------------
# ADD MEDIA TYPE
# ------------------------------------------------------------

def admin_media_type_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎞️ Anime",
                    callback_data="admin_media_type:anime"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Animation",
                    callback_data="admin_media_type:animation"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Movie",
                    callback_data="admin_media_type:movie"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="admin_media"
                )
            ],
        ]
    )


@dp.callback_query(F.data == "admin_media_add")
async def admin_media_add(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "<b>➕ ADD MEDIA SERIES</b>\n\n"
        "Choose the type:",
        parse_mode="HTML",
        reply_markup=admin_media_type_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("admin_media_type:"))
async def admin_media_type(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    media_type = callback.data.split(":", 1)[1]

    pending[callback.from_user.id] = {
        "action": "add_media_info",
        "media_type": media_type
    }

    await callback.message.edit_text(
        f"<b>➕ ADD {media_type_name(media_type)}</b>\n\n"
        "Send:\n\n"
        "<code>Title | Description</code>\n\n"
        "Example:\n"
        "<code>Attack on Titan | Humanity fights for survival...</code>\n\n"
        "Then I'll ask for the cover.",
        parse_mode="HTML"
    )

    await callback.answer()


# ------------------------------------------------------------
# MANAGE MEDIA SERIES
# ------------------------------------------------------------

@dp.callback_query(F.data == "admin_media_series")
async def admin_media_series(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_list = get_media_series()

    buttons = []

    for series in series_list:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{media_type_name(series['media_type'])} "
                    f"• {series['title']}"
                ),
                callback_data=(
                    f"admin_media_view:{series['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="➕ Add Series",
            callback_data="admin_media_add"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Media",
            callback_data="admin_media"
        )
    ])

    if not series_list:
        text = (
            "<b>📚 MANAGE MEDIA</b>\n\n"
            "No media series yet."
        )
    else:
        text = (
            "<b>📚 MANAGE MEDIA</b>\n\n"
            "Choose a series:"
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# ------------------------------------------------------------
# VIEW MEDIA SERIES
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_view:"))
async def admin_media_view(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Series not found.",
            show_alert=True
        )
        return

    episodes = get_media_episodes(
        series_id
    )

    text = (
        "<b>🎬 MEDIA MANAGEMENT</b>\n\n"
        f"Title: <b>{series['title']}</b>\n"
        f"Type: {media_type_name(series['media_type'])}\n"
        f"Episodes: <b>{len(episodes)}</b>\n\n"
        f"{series['description'] or 'No description'}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Episode",
                    callback_data=(
                        f"admin_media_add_episode:"
                        f"{series_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="📺 Manage Episodes",
                    callback_data=(
                        f"admin_media_episodes:"
                        f"{series_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Delete Series",
                    callback_data=(
                        f"admin_media_delete:"
                        f"{series_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Media",
                    callback_data="admin_media_series"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


# ------------------------------------------------------------
# ADD EPISODE
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_add_episode:"))
async def admin_media_add_episode(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Series not found.",
            show_alert=True
        )
        return

    pending[callback.from_user.id] = {
        "action": "add_media_episode",
        "series_id": series_id
    }

    await callback.message.edit_text(
        f"<b>➕ ADD EPISODE</b>\n\n"
        f"Series: <b>{series['title']}</b>\n\n"
        "Send:\n\n"
        "<code>Episode Number | Episode Title</code>\n\n"
        "Example:\n"
        "<code>1 | To You, in 2000 Years</code>\n\n"
        "Then send the video.",
        parse_mode="HTML"
    )

    await callback.answer()


# ------------------------------------------------------------
# MANAGE EPISODES
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_episodes:"))
async def admin_media_episodes(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Series not found.",
            show_alert=True
        )
        return

    episodes = get_media_episodes(
        series_id
    )

    buttons = []

    for episode_data in episodes:
        title = (
            f"📺 Episode "
            f"{episode_data['number']}"
        )

        if episode_data["title"]:
            title += (
                f" — {episode_data['title']}"
            )

        buttons.append([
            InlineKeyboardButton(
                text=title,
                callback_data=(
                    f"admin_media_episode:"
                    f"{episode_data['id']}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="➕ Add Episode",
            callback_data=(
                f"admin_media_add_episode:"
                f"{series_id}"
            )
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Series",
            callback_data=(
                f"admin_media_view:{series_id}"
            )
        )
    ])

    await callback.message.edit_text(
        f"<b>📺 {series['title']}</b>\n\n"
        f"Episodes: <b>{len(episodes)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# ------------------------------------------------------------
# VIEW EPISODE
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_episode:"))
async def admin_media_episode(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    episode_id = int(
        callback.data.split(":", 1)[1]
    )

    episode = get_media_episode(
        episode_id
    )

    if not episode:
        await callback.answer(
            "Episode not found.",
            show_alert=True
        )
        return

    text = (
        "<b>📺 EPISODE MANAGEMENT</b>\n\n"
        f"Series: <b>{episode['series_title']}</b>\n"
        f"Episode: <b>{episode['number']}</b>\n"
        f"Title: <b>{episode['title'] or 'Untitled'}</b>\n"
        f"Format: {episode['file_kind']}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Send Episode",
                    callback_data=(
                        f"admin_media_send:"
                        f"{episode_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Delete Episode",
                    callback_data=(
                        f"admin_media_delete_episode:"
                        f"{episode_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Episodes",
                    callback_data=(
                        f"admin_media_episodes:"
                        f"{episode['series_id']}"
                    )
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("admin_media_send:"))
async def admin_media_send(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    episode_id = int(
        callback.data.split(":", 1)[1]
    )

    await send_media_episode(
        callback.message,
        episode_id
    )

    await callback.answer(
        "▶️ Sending..."
    )


# ------------------------------------------------------------
# DELETE EPISODE
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_delete_episode:"))
async def admin_media_delete_episode(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    episode_id = int(
        callback.data.split(":", 1)[1]
    )

    episode = get_media_episode(
        episode_id
    )

    if not episode:
        await callback.answer(
            "Episode not found.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ YES, DELETE",
                    callback_data=(
                        f"admin_media_delete_episode_confirm:"
                        f"{episode_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=(
                        f"admin_media_episode:"
                        f"{episode_id}"
                    )
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "<b>⚠️ DELETE EPISODE</b>\n\n"
        f"Are you sure you want to delete "
        f"<b>Episode {episode['number']}</b>?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith(
        "admin_media_delete_episode_confirm:"
    )
)
async def admin_media_delete_episode_confirm(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    episode_id = int(
        callback.data.split(":", 1)[1]
    )

    episode = get_media_episode(
        episode_id
    )

    if not episode:
        await callback.answer(
            "Episode not found.",
            show_alert=True
        )
        return

    series_id = episode["series_id"]

    if delete_media_episode(episode_id):
        await callback.message.edit_text(
            "✅ Episode deleted.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Episodes",
                            callback_data=(
                                f"admin_media_episodes:"
                                f"{series_id}"
                            )
                        )
                    ]
                ]
            )
        )
    else:
        await callback.message.edit_text(
            "❌ Could not delete episode."
        )

    await callback.answer()


# ------------------------------------------------------------
# DELETE SERIES
# ------------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_media_delete:"))
async def admin_media_delete(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_id = int(
        callback.data.split(":", 1)[1]
    )

    series = get_media_series_by_id(
        series_id
    )

    if not series:
        await callback.answer(
            "Series not found.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ YES, DELETE",
                    callback_data=(
                        f"admin_media_delete_confirm:"
                        f"{series_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=(
                        f"admin_media_view:"
                        f"{series_id}"
                    )
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "<b>⚠️ DELETE MEDIA SERIES</b>\n\n"
        f"Are you sure you want to delete "
        f"<b>{series['title']}</b>?\n\n"
        "All episodes belonging to this series "
        "will also be deleted.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith(
        "admin_media_delete_confirm:"
    )
)
async def admin_media_delete_confirm(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    series_id = int(
        callback.data.split(":", 1)[1]
    )

    if delete_media_series(series_id):
        await callback.message.edit_text(
            "✅ Media series and all its episodes "
            "were deleted.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Media",
                            callback_data="admin_media_series"
                        )
                    ]
                ]
            )
        )
    else:
        await callback.message.edit_text(
            "❌ Series not found."
        )

    await callback.answer()


# ============================================================
# DELETE COMIC
# ============================================================

@dp.callback_query(F.data.startswith("admin_delete:"))
async def admin_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    comic_data = get_comic(comic_id)

    if not comic_data:
        await callback.answer(
            "Comic not found.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ YES, DELETE",
                    callback_data=(
                        f"delete_confirm:{comic_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=(
                        f"admin_view:{comic_id}"
                    )
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "<b>⚠️ DELETE COMIC</b>\n\n"
        f"Are you sure you want to delete "
        f"<b>{comic_data['title']}</b>?\n\n"
        "This will also delete all its chapters.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("delete_confirm:"))
async def delete_confirm(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        return

    comic_id = int(
        callback.data.split(":", 1)[1]
    )

    if delete_comic(comic_id):
        await callback.message.edit_text(
            "✅ Comic and its chapters were deleted.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Admin",
                            callback_data="admin_home"
                        )
                    ]
                ]
            )
        )
    else:
        await callback.message.edit_text(
            "❌ Comic not found."
        )

    await callback.answer()


# ============================================================
# ADMIN MESSAGE / UPLOAD ROUTER
# ============================================================

@dp.message()
async def admin_messages(message: Message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        return

    state = pending.get(user_id)

    if not state:
        return

    action = state.get("action")

    # ========================================================
    # ADD COMIC
    # ========================================================

    if action == "add_comic":

        if not message.text or "|" not in message.text:
            await message.answer(
                "❌ Use:\n"
                "Title | Category | Description"
            )
            return

        parts = [
            value.strip()
            for value in message.text.split("|", 2)
        ]

        if len(parts) != 3:
            await message.answer(
                "❌ Invalid format."
            )
            return

        title, category_value, description = parts

        category_value = category_value.lower()

        if category_value not in {
            "marvel",
            "dc",
            "manga"
        }:
            await message.answer(
                "❌ Category must be:\n"
                "marvel\n"
                "dc\n"
                "manga"
            )
            return

        pending[user_id] = {
            "action": "add_comic_cover",
            "title": title,
            "category": category_value,
            "description": description
        }

        await message.answer(
            "🖼️ Now send the cover image."
        )

        return

    # ========================================================
    # COMIC COVER
    # ========================================================

    if action == "add_comic_cover":

        if not message.photo:
            await message.answer(
                "❌ Please send an image."
            )
            return

        cover_id = message.photo[-1].file_id

        comic_id = add_comic(
            state["title"],
            state["description"],
            state["category"],
            cover_id
        )

        title = state["title"]
        category_value = state["category"]

        pending.pop(
            user_id,
            None
        )

        await message.answer(
            "✅ <b>COMIC CREATED</b>\n\n"
            f"📖 {title}\n"
            f"{category_name(category_value)}\n"
            f"🆔 ID: {comic_id}\n\n"
            "You can now add chapters from "
            "the Admin Panel.",
            parse_mode="HTML",
            reply_markup=admin_keyboard()
        )

        return

    # ========================================================
    # ADD CHAPTER INFORMATION
    # ========================================================

    if action == "add_chapter":

        if not message.text or "|" not in message.text:
            await message.answer(
                "❌ Use:\n"
                "Comic ID | Chapter Number | Chapter Title"
            )
            return

        parts = [
            value.strip()
            for value in message.text.split("|", 2)
        ]

        if len(parts) != 3:
            await message.answer(
                "❌ Invalid format."
            )
            return

        if (
            not parts[0].isdigit()
            or not parts[1].isdigit()
        ):
            await message.answer(
                "❌ Comic ID and chapter number "
                "must be numbers."
            )
            return

        comic_id = int(parts[0])
        number = int(parts[1])
        title = parts[2]

        if not get_comic(comic_id):
            await message.answer(
                "❌ Comic not found."
            )
            return

        pending[user_id] = {
            "action": "add_chapter_pdf",
            "comic_id": comic_id,
            "number": number,
            "title": title
        }

        await message.answer(
            "📄 Now send the chapter PDF."
        )

        return

    # ========================================================
    # CHAPTER PDF
    # ========================================================

    if action == "add_chapter_pdf":

        if not message.document:
            await message.answer(
                "❌ Please send a PDF file."
            )
            return

        filename = (
            message.document.file_name
            or ""
        )

        if not filename.lower().endswith(".pdf"):
            await message.answer(
                "❌ Please send a PDF file."
            )
            return

        status = await message.answer(
            "🔎 Processing PDF..."
        )

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf",
                delete=False
            ) as temp:
                temp_path = temp.name

            telegram_file = await bot.get_file(
                message.document.file_id
            )

            await bot.download_file(
                telegram_file.file_path,
                temp_path
            )

            reader = PdfReader(temp_path)
            pages = len(reader.pages)

            chapter_id = add_chapter(
                state["comic_id"],
                state["number"],
                state["title"],
                message.document.file_id
            )

            comic_data = get_comic(
                state["comic_id"]
            )

            pending.pop(
                user_id,
                None
            )

            link = await create_start_link(
                bot,
                f"chapter_{chapter_id}"
            )

            await status.edit_text(
                "✅ <b>CHAPTER ADDED</b>\n\n"
                f"📖 Comic: {comic_data['title']}\n"
                f"🔢 Chapter: {state['number']}\n"
                f"📝 Title: {state['title']}\n"
                f"📑 Pages: {pages}\n\n"
                f"🔗 <b>Direct link:</b>\n{link}",
                parse_mode="HTML"
            )

        except Exception:
            logging.exception(
                "PDF upload failed"
            )

            await status.edit_text(
                "❌ Something went wrong while "
                "processing the PDF."
            )

        finally:
            if temp_path:
                Path(temp_path).unlink(
                    missing_ok=True
                )

        return

    # ========================================================
    # ADD MEDIA INFORMATION
    # ========================================================

    if action == "add_media_info":

        if not message.text or "|" not in message.text:
            await message.answer(
                "❌ Use:\n"
                "Title | Description"
            )
            return

        parts = [
            value.strip()
            for value in message.text.split("|", 1)
        ]

        if len(parts) != 2:
            await message.answer(
                "❌ Invalid format."
            )
            return

        title, description = parts

        pending[user_id] = {
            "action": "add_media_cover",
            "title": title,
            "description": description,
            "media_type": state["media_type"]
        }

        await message.answer(
            "🖼️ Now send the cover image."
        )

        return

    # ========================================================
    # MEDIA COVER
    # ========================================================

    if action == "add_media_cover":

        if not message.photo:
            await message.answer(
                "❌ Please send an image."
            )
            return

        cover_file_id = message.photo[-1].file_id

        series_id = add_media_series(
            title=state["title"],
            description=state["description"],
            media_type=state["media_type"],
            cover_file_id=cover_file_id
        )

        title = state["title"]
        media_type = state["media_type"]

        pending.pop(
            user_id,
            None
        )

        await message.answer(
            "✅ <b>MEDIA SERIES CREATED</b>\n\n"
            f"🎬 {title}\n"
            f"{media_type_name(media_type)}\n"
            f"🆔 ID: {series_id}\n\n"
            "Now you can add episodes from "
            "the Media Management menu.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Add Episode",
                            callback_data=(
                                f"admin_media_add_episode:"
                                f"{series_id}"
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📚 Manage Series",
                            callback_data=(
                                "admin_media_series"
                            )
                        )
                    ]
                ]
            )
        )

        return

    # ========================================================
    # ADD MEDIA EPISODE INFORMATION
    # ========================================================

    if action == "add_media_episode":

        if not message.text or "|" not in message.text:
            await message.answer(
                "❌ Use:\n"
                "Episode Number | Episode Title"
            )
            return

        parts = [
            value.strip()
            for value in message.text.split("|", 1)
        ]

        if len(parts) != 2:
            await message.answer(
                "❌ Invalid format."
            )
            return

        if not parts[0].isdigit():
            await message.answer(
                "❌ Episode number must be a number."
            )
            return

        number = int(parts[0])
        title = parts[1]

        series = get_media_series_by_id(
            state["series_id"]
        )

        if not series:
            pending.pop(
                user_id,
                None
            )

            await message.answer(
                "❌ Media series not found."
            )
            return

        existing_episodes = get_media_episodes(
            state["series_id"]
        )

        if any(
            episode["number"] == number
            for episode in existing_episodes
        ):
            await message.answer(
                f"❌ Episode {number} already exists."
            )
            return

        pending[user_id] = {
            "action": "add_media_episode_file",
            "series_id": state["series_id"],
            "number": number,
            "title": title
        }

        await message.answer(
            "🎬 Now send the episode video.\n\n"
            "MP4 and other Telegram-supported "
            "video formats are accepted."
        )

        return

    # ========================================================
    # MEDIA VIDEO
    # ========================================================

    if action == "add_media_episode_file":

        file_id = None
        file_kind = None

        # Native Telegram video
        if message.video:
            file_id = message.video.file_id
            file_kind = "video"

        # Video uploaded as a document
        elif message.document:
            filename = (
                message.document.file_name
                or ""
            )

            allowed_extensions = (
                ".mp4",
                ".mkv",
                ".webm",
                ".mov"
            )

            if not filename.lower().endswith(
                allowed_extensions
            ):
                await message.answer(
                    "❌ Please send a supported video file:\n"
                    ".mp4\n"
                    ".mkv\n"
                    ".webm\n"
                    ".mov"
                )
                return

            file_id = message.document.file_id
            file_kind = "document"

        else:
            await message.answer(
                "❌ Please send the episode video."
            )
            return

        try:
            episode_id = add_media_episode(
                series_id=state["series_id"],
                number=state["number"],
                title=state["title"],
                file_id=file_id,
                file_kind=file_kind
            )

        except sqlite3.IntegrityError:
            await message.answer(
                "❌ That episode number already "
                "exists for this series."
            )
            return

        series = get_media_series_by_id(
            state["series_id"]
        )

        pending.pop(
            user_id,
            None
        )

        link = await create_start_link(
            bot,
            f"media_episode_{episode_id}"
        )

        await message.answer(
            "✅ <b>EPISODE ADDED</b>\n\n"
            f"🎬 Series: {series['title']}\n"
            f"📺 Episode: {state['number']}\n"
            f"📝 Title: {state['title']}\n\n"
            f"🔗 <b>Direct link:</b>\n{link}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Add Another Episode",
                            callback_data=(
                                f"admin_media_add_episode:"
                                f"{state['series_id']}"
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📺 Manage Episodes",
                            callback_data=(
                                f"admin_media_episodes:"
                                f"{state['series_id']}"
                            )
                        )
                    ]
                ]
            )
        )

        return


# ============================================================
# RUN
# ============================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    if not ADMIN_IDS:
        raise RuntimeError(
            "ADMIN_IDS is missing."
        )

    init_db()
    web_runner = await start_web_admin(bot)

    logging.info(
        "PanelVerse is running."
    )

    try:
        await dp.start_polling(bot)
    finally:
        await stop_web_admin()


if __name__ == "__main__":
    asyncio.run(main())