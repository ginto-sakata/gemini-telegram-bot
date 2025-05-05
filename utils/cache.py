# utils/cache.py
# -*- coding: utf-8 -*-
"""
Handles downloading and caching Telegram photos locally.
Refactored to avoid code duplication.
"""

import io
import logging
import re
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from telegram import Chat
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from config import IMAGE_CACHE_DIR

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_SIZE_BYTES = 20 * 1024 * 1024

# ================================== _get_safe_chat_subdir_name(): Generates safe subdirectory name ==================================
def _get_safe_chat_subdir_name(chat_id: int, chat_username: Optional[str]) -> str:
    if chat_username:
        safe_username = re.sub(r'[\\/*?:"<>|\s]', "_", chat_username)
        return f"{chat_id}@{safe_username}"
    else:
        return str(chat_id)
# ================================== _get_safe_chat_subdir_name() end ==================================


# ================================== _guess_mime_type(): Guesses MIME type from magic bytes ==================================
def _guess_mime_type(image_bytes: bytes) -> Tuple[str, str]:
    if image_bytes.startswith(b"\xff\xd8\xff"): return "image/jpeg", ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png", ".png"
    if image_bytes.startswith(b"GIF8"): return "image/gif", ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP": return "image/webp", ".webp"
    logger.warning("Не удалось определить тип, используется image/png")
    return "image/png", ".png"
# ================================== _guess_mime_type() end ==================================


# ================================== _save_to_cache(): Saves downloaded image bytes ==================================
async def _save_to_cache(image_bytes: bytes, file_id: str, chat_cache_path: Path) -> bool:
    try:
        mime, ext = _guess_mime_type(image_bytes); safe_file_id = re.sub(r'[\\/*?:"<>|\s]', "_", file_id)
        fname = f"{safe_file_id}{ext}"; save_path = chat_cache_path / fname
        chat_cache_path.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(image_bytes)
        logger.info(f"Кэшировано {len(image_bytes)} байт: {save_path}")
        return True
    except OSError as e: logger.error(f"Ошибка записи кэша {save_path}: {e}"); return False
    except Exception as e: logger.exception(f"Ошибка сохранения кэша {save_path}: {e}"); return False
# ================================== _save_to_cache() end ==================================


# ================================== _get_or_download_image(): Gets image from cache or downloads ==================================
async def _get_or_download_image(context: ContextTypes.DEFAULT_TYPE, file_id: str, chat_cache_path: Path) -> Optional[bytes]:
    safe_file_id = re.sub(r'[\\/*?:"<>|\s]', "_", file_id)
    try:
        potential_files = list(chat_cache_path.glob(f"{safe_file_id}.*"))
        cached_file_path = potential_files[0] if potential_files else None
        if cached_file_path and cached_file_path.is_file():
            logger.debug(f"Кэш HIT: {file_id} в {cached_file_path}")
            try: return cached_file_path.read_bytes()
            except Exception as e:
                logger.error(f"Ошибка чтения кэша {cached_file_path}: {e}")
                try: cached_file_path.unlink(missing_ok=True)
                except Exception as ue: logger.error(f"Ошибка удаления кэша {cached_file_path}: {ue}")
    except Exception as e: logger.exception(f"Ошибка проверки кэша {file_id}: {e}")
    logger.debug(f"Кэш MISS: {file_id}. Загрузка...")
    try:
        bot_file = await context.bot.get_file(file_id); buf = io.BytesIO()
        await bot_file.download_to_memory(out=buf); img_bytes = buf.getvalue()
        if len(img_bytes) > MAX_DOWNLOAD_SIZE_BYTES:
            size_mb = len(img_bytes)/(1024*1024); limit_mb = MAX_DOWNLOAD_SIZE_BYTES/(1024*1024)
            logger.warning(f"Размер ({size_mb:.1f}MB) > лимита ({limit_mb:.1f}MB) {file_id}."); return None
        logger.debug(f"Загружено {len(img_bytes)} байт для {file_id}.")
        asyncio.create_task(_save_to_cache(img_bytes, file_id, chat_cache_path))
        return img_bytes
    except TelegramError as e:
        error_msg = str(e).lower()
        if "file is too big" in error_msg: logger.warning(f"TG Error: File too big {file_id}. {e}")
        elif "file not found" in error_msg or "invalid file_id" in error_msg: logger.warning(f"TG Error: File not found {file_id}. {e}")
        else: logger.error(f"TG Error при загрузке {file_id}: {e}")
        return None
    except Exception as e: logger.exception(f"Неож. ошибка при загрузке {file_id}: {e}"); return None
# ================================== _get_or_download_image() end ==================================


# ================================== get_cached_image_bytes(): Public: gets image, uses Chat object for path ==================================
async def get_cached_image_bytes(context: ContextTypes.DEFAULT_TYPE, file_id: str, chat: Chat) -> Optional[bytes]:
    if not file_id: logger.warning("get_cached_image_bytes вызван без file_id."); return None
    if not chat: logger.warning("get_cached_image_bytes вызван без Chat."); return None
    subdir_name = _get_safe_chat_subdir_name(chat.id, chat.username)
    chat_cache_path = IMAGE_CACHE_DIR / subdir_name
    return await _get_or_download_image(context, file_id, chat_cache_path)
# ================================== get_cached_image_bytes() end ==================================


# ================================== get_cached_image_bytes_by_id(): Public: gets image, uses IDs for path ==================================
async def get_cached_image_bytes_by_id(context: ContextTypes.DEFAULT_TYPE, file_id: str, chat_id: int, chat_username: Optional[str]) -> Optional[bytes]:
    if not file_id: logger.warning("get_cached_image_bytes_by_id вызван без file_id."); return None
    subdir_name = _get_safe_chat_subdir_name(chat_id, chat_username)
    chat_cache_path = IMAGE_CACHE_DIR / subdir_name
    return await _get_or_download_image(context, file_id, chat_cache_path)
# ================================== get_cached_image_bytes_by_id() end ==================================

# utils/cache.py end