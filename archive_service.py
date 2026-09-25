import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from database import (
    archive_add_file,
    archive_audit,
    archive_create_item,
    archive_create_job,
    archive_find_duplicate,
    archive_get_item,
    archive_update_item,
    archive_update_job,
)

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

try:
    import pymupdf
except Exception:
    pymupdf = None


CONTENT_TYPES = {"BOOK", "COMIC", "MANGA", "ANIME", "MOVIE", "VIDEO", "MUSIC"}
EXTENSIONS = {
    ".pdf": "BOOK",
    ".epub": "BOOK",
    ".mobi": "BOOK",
    ".azw": "BOOK",
    ".azw3": "BOOK",
    ".cbz": "COMIC",
    ".cbr": "COMIC",
    ".mp3": "MUSIC",
    ".flac": "MUSIC",
    ".m4a": "MUSIC",
    ".ogg": "MUSIC",
    ".wav": "MUSIC",
    ".mp4": "VIDEO",
    ".mkv": "VIDEO",
    ".webm": "VIDEO",
    ".mov": "VIDEO",
    ".avi": "VIDEO",
}
MAX_FILE_BYTES = int(os.getenv("ARCHIVE_MAX_FILE_MB", "4096")) * 1024 * 1024
STORAGE_DIR = Path(os.getenv("ARCHIVE_STORAGE_DIR", "archive_storage"))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    name = os.path.basename(name or "upload.bin")
    name = re.sub(r"[^A-Za-z0-9._() \-+[\]{}]", "_", name)
    return name[:180] or "upload.bin"


def detect_type(filename: str, mime: str = ""):
    ext = Path(filename).suffix.lower()
    detected = EXTENSIONS.get(ext)
    if detected:
        confidence = 96
    elif mime.startswith("audio/"):
        detected, confidence = "MUSIC", 82
    elif mime.startswith("video/"):
        detected, confidence = "VIDEO", 82
    elif mime == "application/pdf":
        detected, confidence = "BOOK", 95
    else:
        detected, confidence = "VIDEO" if "video" in mime else "BOOK", 35
    return detected, confidence


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _text(meta, key):
    value = meta.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def extract_pdf(path: Path):
    data = {}
    try:
        if PdfReader:
            reader = PdfReader(str(path))
            info = reader.metadata or {}
            data["pages"] = len(reader.pages)
            for source, target in (
                ("/Title", "title"),
                ("/Author", "authors"),
                ("/Subject", "description"),
                ("/Creator", "creator"),
            ):
                value = info.get(source)
                if value:
                    data[target] = str(value).strip()
        if pymupdf:
            doc = pymupdf.open(str(path))
            if len(doc):
                cover_dir = STORAGE_DIR / "covers"
                cover_dir.mkdir(parents=True, exist_ok=True)
                out = cover_dir / (path.stem + "-cover.png")
                pix = doc[0].get_pixmap(dpi=110, alpha=False)
                pix.save(str(out))
                data["cover_path"] = str(out)
            doc.close()
    except Exception as exc:
        data["analysis_error"] = str(exc)
    return data


def extract_epub(path: Path):
    data = {}
    try:
        with zipfile.ZipFile(path) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = next(
                x for x in container.iter()
                if x.tag.endswith("rootfile")
            )
            opf_path = rootfile.attrib["full-path"]
            opf = ET.fromstring(zf.read(opf_path))
            ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
            for tag, key in (
                ("title", "title"), ("creator", "authors"),
                ("publisher", "publisher"), ("language", "language"),
                ("description", "description"),
            ):
                node = opf.find(f".//dc:{tag}", ns)
                if node is not None and node.text:
                    data[key] = node.text.strip()
            for meta in opf.findall(".//opf:meta", ns):
                if meta.attrib.get("property") == "dcterms:modified" and meta.text:
                    data["modified"] = meta.text.strip()
            manifest = {
                item.attrib.get("id"): item.attrib
                for item in opf.findall(".//opf:item", ns)
            }
            cover_id = None
            for meta in opf.findall(".//opf:meta", ns):
                if meta.attrib.get("name") == "cover":
                    cover_id = meta.attrib.get("content")
            if cover_id and cover_id in manifest:
                href = manifest[cover_id].get("href", "")
                candidate = str((Path(opf_path).parent / href).as_posix())
                candidate = candidate.replace("./", "")
                if candidate in zf.namelist():
                    cover_dir = STORAGE_DIR / "covers"
                    cover_dir.mkdir(parents=True, exist_ok=True)
                    out = cover_dir / (path.stem + "-cover" + Path(candidate).suffix)
                    out.write_bytes(zf.read(candidate))
                    data["cover_path"] = str(out)
    except Exception as exc:
        data["analysis_error"] = str(exc)
    return data


def extract_video(path: Path):
    data = {}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return data
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30, check=True
        )
        payload = json.loads(proc.stdout or "{}")
        fmt = payload.get("format") or {}
        streams = payload.get("streams") or []
        data["duration"] = float(fmt["duration"]) if fmt.get("duration") else None
        data["bitrate"] = int(fmt["bit_rate"]) if fmt.get("bit_rate") else None
        for stream in streams:
            if stream.get("codec_type") == "video":
                data["codec"] = stream.get("codec_name")
                data["width"] = stream.get("width")
                data["height"] = stream.get("height")
                data["frame_rate"] = stream.get("r_frame_rate")
                break
        return {k: v for k, v in data.items() if v is not None}
    except Exception as exc:
        data["analysis_error"] = str(exc)
        return data


def extract_cbz(path: Path):
    data = {}
    try:
        with zipfile.ZipFile(path) as zf:
            images = [
                n for n in zf.namelist()
                if Path(n).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            ]
            images.sort(key=lambda x: (len(x), x.lower()))
            data["pages"] = len(images)
            if images:
                cover_dir = STORAGE_DIR / "covers"
                cover_dir.mkdir(parents=True, exist_ok=True)
                out = cover_dir / (path.stem + "-cover" + Path(images[0]).suffix.lower())
                out.write_bytes(zf.read(images[0]))
                data["cover_path"] = str(out)
    except Exception as exc:
        data["analysis_error"] = str(exc)
    return data


def extract_music(path: Path):
    data = {}
    if not MutagenFile:
        return data
    try:
        audio = MutagenFile(str(path), easy=True)
        raw = MutagenFile(str(path), easy=False)
        if not audio:
            return data
        mapping = {
            "title": "title", "artist": "artist", "album": "album",
            "albumartist": "album_artist", "genre": "genre",
            "date": "year", "tracknumber": "track_number",
            "discnumber": "disc_number", "composer": "composer",
        }
        for source, target in mapping.items():
            value = _text(audio, source)
            if value:
                data[target] = value
        if getattr(audio, "info", None):
            info = audio.info
            if getattr(info, "length", None):
                data["duration"] = round(float(info.length), 3)
            if getattr(info, "bitrate", None):
                data["bitrate"] = int(info.bitrate)
            if getattr(info, "sample_rate", None):
                data["sample_rate"] = int(info.sample_rate)
        if raw and getattr(raw, "tags", None):
            artwork = None
            for key, value in raw.tags.items():
                if str(key).upper().startswith("APIC") and getattr(value, "data", None):
                    artwork = value.data
                    break
                if key == "covr" and value:
                    artwork = bytes(value[0])
                    break
            if artwork:
                cover_dir = STORAGE_DIR / "covers"
                cover_dir.mkdir(parents=True, exist_ok=True)
                out = cover_dir / (path.stem + "-cover.jpg")
                out.write_bytes(artwork)
                data["cover_path"] = str(out)
    except Exception as exc:
        data["analysis_error"] = str(exc)
    return data


def extract_metadata(path: Path, detected_type: str):
    data = {"filename": path.name, "extension": path.suffix.lower()}
    if detected_type == "BOOK" and path.suffix.lower() == ".pdf":
        data.update(extract_pdf(path))
    elif detected_type == "BOOK" and path.suffix.lower() == ".epub":
        data.update(extract_epub(path))
    elif detected_type in {"COMIC", "MANGA"} and path.suffix.lower() == ".cbz":
        data.update(extract_cbz(path))
    elif detected_type == "MUSIC":
        data.update(extract_music(path))
    elif detected_type in {"ANIME", "MOVIE", "VIDEO"}:
        data.update(extract_video(path))
    return data


def completeness_for(content_type, metadata, file_path, cover_path=""):
    required = {
        "BOOK": ["title", "authors", "language"],
        "COMIC": ["title"],
        "MANGA": ["title"],
        "ANIME": ["title"],
        "MOVIE": ["title", "year"],
        "VIDEO": ["title"],
        "MUSIC": ["title", "artist"],
    }.get(content_type, ["title"])
    present = sum(1 for field in required if str(metadata.get(field, "")).strip())
    score = int((present / max(1, len(required))) * 100)
    if file_path and file_path.exists():
        score = min(100, score + 10)
    if cover_path:
        score = min(100, score + 5)
    return score


def qc_result(item, file_record):
    errors = []
    warnings = []
    if not file_record or not Path(file_record["storage_path"]).exists():
        errors.append("File is missing or unreadable.")
    if not file_record.get("sha256"):
        errors.append("File hash was not generated.")
    if not item.get("title"):
        errors.append("Title is required.")
    if item.get("content_type") == "BOOK" and not item.get("metadata", {}).get("authors"):
        warnings.append("Author is missing.")
    if not item.get("cover_path") and item.get("content_type") in {"BOOK", "COMIC", "MANGA", "ANIME", "MOVIE"}:
        warnings.append("Cover/poster is missing.")
    return {"errors": errors, "warnings": warnings, "can_publish": not errors}


async def process_ingestion(job_id, item_id, storage_path, filename, mime_type, actor):
    path = Path(storage_path)
    try:
        archive_update_job(job_id, status="RUNNING", stage="hashing", progress=10)
        digest = await asyncio.to_thread(sha256_file, path)
        detected, confidence = detect_type(filename, mime_type)
        archive_update_job(job_id, stage="metadata", progress=30)

        metadata = await asyncio.to_thread(extract_metadata, path, detected)
        title = metadata.get("title") or Path(filename).stem
        override = metadata.get("_override_type")
        if override in CONTENT_TYPES:
            detected = override

        duplicate = await asyncio.to_thread(
            archive_find_duplicate,
            digest,
            title,
            metadata.get("isbn13") or metadata.get("isbn10") or metadata.get("isbn")
        )

        item = archive_get_item(item_id)
        metadata.pop("_override_type", None)
        completeness = completeness_for(
            detected, metadata, path, metadata.get("cover_path", "")
        )
        archive_update_item(
            item_id,
            content_type=detected,
            title=title,
            description=metadata.get("description", ""),
            metadata_json=metadata,
            detected_confidence=confidence,
            completeness=completeness,
            cover_path=metadata.get("cover_path", ""),
        )

        file_meta = {
            "analysis": metadata,
            "duplicate": (
                {"item_id": duplicate[0]["id"], "reason": duplicate[1], "similarity": duplicate[2]}
                if duplicate else None
            ),
        }
        archive_add_file(
            item_id=item_id,
            original_name=filename,
            storage_path=str(path),
            mime_type=mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            extension=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            sha256=digest,
            detected_type=detected,
            metadata=file_meta,
        )

        archive_update_job(job_id, stage="qc", progress=75)
        item = archive_get_item(item_id)
        file_record = item["files"][-1] if item and item["files"] else None
        qc = qc_result(item or {}, file_record or {})
        metadata["_qc"] = qc
        metadata["_duplicate"] = file_meta["duplicate"]
        archive_update_item(
            item_id,
            metadata_json=metadata,
            status="REVIEW" if qc["can_publish"] else "DRAFT",
            completeness=completeness,
        )

        archive_audit(
            actor, "SYSTEM_INGEST_ANALYZED", item_id,
            {"detected_type": detected, "confidence": confidence, "qc": qc, "duplicate": file_meta["duplicate"]}
        )
        archive_update_job(job_id, status="COMPLETED", stage="review", progress=100)
    except Exception as exc:
        archive_update_job(job_id, status="FAILED", stage="failed", progress=100, error=str(exc))
        archive_audit(actor, "SYSTEM_INGEST_FAILED", item_id, {"error": str(exc)})


def create_ingestion(filename, storage_path, mime_type, actor, content_type=""):
    detected, confidence = detect_type(filename, mime_type)
    if content_type in CONTENT_TYPES:
        detected, confidence = content_type, 100
    item_id = archive_create_item(
        detected,
        Path(filename).stem,
        {"_requested_type": content_type, "_filename": filename},
        created_by=actor,
        status="DRAFT",
        detected_confidence=confidence,
    )
    job_id = archive_create_job(item_id)
    return item_id, job_id, detected, confidence
