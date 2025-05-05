# handlers/media_groups.py
# -*- coding: utf-8 -*-
"""
Handlers for collecting and processing media groups. Uses _initiate_image_combination.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from telegram import Update, Message, Chat
from telegram.ext import ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError
from utils.auth import is_authorized
from utils.cache import get_cached_image_bytes_by_id
from utils.telegram_helpers import delete_message_safely
from handlers.image_gen import _initiate_image_combination
from config import (
    MEDIA_GROUP_CACHE_KEY_PREFIX, MEDIA_GROUP_PROCESS_DELAY_SECONDS,
    DEFAULT_COMBINE_PROMPT_TEXT
)

logger = logging.getLogger(__name__)
media_group_data_lock = asyncio.Lock()

# ================================== process_media_group(): Processes collected media group photos ==================================
async def process_media_group(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data if context.job else {}
    if not isinstance(job_data, dict): logger.error(f"Invalid job_data: {job_data}"); return
    chat_id = job_data.get("chat_id"); mgid = job_data.get("media_group_id")
    user_id = job_data.get("user_id"); uname = job_data.get("chat_username")
    fmid = job_data.get("first_message_id")
    if not all([chat_id, mgid, user_id, fmid]): logger.error(f"Invalid/missing job data: {job_data}"); return
    cache_key = f"{MEDIA_GROUP_CACHE_KEY_PREFIX}{mgid}"
    photo_data_list = context.application.bot_data.pop(cache_key, [])
    if not photo_data_list or len(photo_data_list) != 2:
        log_msg = f"Медиагруппа {mgid} не содержит 2 фото ({len(photo_data_list)})."; logger.warning(log_msg)
        if photo_data_list:
            try: await context.bot.send_message(chat_id, "ℹ️ Для комбинации нужно 2 фото.", reply_to_message_id=fmid)
            except Exception: pass
        return
    try: photo_data_list.sort(key=lambda p: p["message_id"]); file_id_1 = photo_data_list[0]["file_id"]; file_id_2 = photo_data_list[1]["file_id"]
    except (KeyError, IndexError, TypeError) as e: logger.error(f"Ошибка извлечения file_id {mgid}: {e}"); return
    logger.info(f"Обработка группы {mgid} от {user_id}. Фото: {file_id_1}, {file_id_2}.")
    dl_status_msg = None; img1_bytes = None; img2_bytes = None; dl_success = False
    try:
        dl_status_msg = await context.bot.send_message(chat_id, "⏳ Загрузка...", reply_to_message_id=fmid)
        img1_bytes, img2_bytes = await asyncio.gather(get_cached_image_bytes_by_id(context, file_id_1, chat_id, uname), get_cached_image_bytes_by_id(context, file_id_2, chat_id, uname), return_exceptions=True)
        dl_success = True
        if isinstance(img1_bytes, Exception) or img1_bytes is None: logger.error(f"Ошибка загр. 1 ({file_id_1}): {img1_bytes}"); img1_bytes = None; dl_success = False
        if isinstance(img2_bytes, Exception) or img2_bytes is None: logger.error(f"Ошибка загр. 2 ({file_id_2}): {img2_bytes}"); img2_bytes = None; dl_success = False
    except Exception as e: logger.exception(f"Ошибка загрузки {mgid}: {e}"); dl_success = False
    finally:
        if dl_status_msg: await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)
    if not dl_success: logger.error(f"Сбой загрузки {mgid}"); await context.bot.send_message(chat_id, "❌ Ошибка загрузки.", reply_to_message_id=fmid); return
    user_mention = f"User ({user_id})"
    try: user_chat = await context.bot.get_chat(user_id); user_mention = user_chat.mention_html()
    except Exception as mention_err: logger.warning(f"Не удалось mention {user_id}: {mention_err}")
    source_message = None
    try:
        chat_obj = await context.bot.get_chat(chat_id)
        source_message = await context.bot.forward_message(chat_id=chat_id, from_chat_id=chat_id, message_id=fmid)
        if source_message: await delete_message_safely(context, chat_id, source_message.message_id)
        else: raise ValueError("Forwarding failed")
        source_message = Message(message_id=fmid, date=source_message.date, chat=chat_obj, from_user=source_message.from_user)
    except Exception as fwd_err:
        logger.error(f"Не удалось получить source_message {fmid}: {fwd_err}.")
        source_message = Message(message_id=fmid, date=None, chat=Chat(id=chat_id, type=filters.ChatType.GROUP))
    try:
        await _initiate_image_combination(
            context=context, base_image_bytes=img1_bytes, user_image_bytes=img2_bytes,
            user_prompt=DEFAULT_COMBINE_PROMPT_TEXT, chat_id=chat_id, user_id=user_id, user_mention=user_mention,
            reply_to_msg_id=fmid, source_message=source_message
        )
    except Exception as e:
        logger.exception(f"Ошибка _initiate_image_combination для {mgid}: {e}")
        try: await context.bot.send_message(chat_id, "❌ Ошибка обработки группы.", reply_to_message_id=fmid)
        except Exception as final_err: logger.error(f"Не удалось отправить ошибку {mgid}: {final_err}")
# ================================== process_media_group() end ==================================


# ================================== handle_media_group_photo(): Collects photos from a media group ==================================
async def handle_media_group_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update, context): return
    if not (update.message and update.message.photo and update.message.media_group_id and not update.message.caption and not update.message.reply_to_message): return
    chat = update.effective_chat; user = update.effective_user; msg = update.message
    if not chat or not user: return
    mgid = msg.media_group_id; photo = msg.photo[-1]; fid = photo.file_id; mid = msg.message_id
    cache_key = f"{MEDIA_GROUP_CACHE_KEY_PREFIX}{mgid}"
    async with media_group_data_lock:
        mg_photos = context.application.bot_data.setdefault(cache_key, [])
        if not any(p["message_id"] == mid for p in mg_photos):
            mg_photos.append({"file_id": fid, "message_id": mid})
            mg_photos.sort(key=lambda p: p["message_id"]); fmid = mg_photos[0]["message_id"]
            logger.debug(f"Добавлено фото {mid} в группу {mgid}. Всего: {len(mg_photos)}.")
            job_data = {"chat_id": chat.id, "media_group_id": mgid, "user_id": user.id, "chat_username": chat.username, "first_message_id": fmid,}
            context.job_queue.run_once(process_media_group, MEDIA_GROUP_PROCESS_DELAY_SECONDS, data=job_data, name=cache_key, job_kwargs={'replace_existing': True})
            logger.debug(f"Запланирована/сброшена задача '{cache_key}' для группы {mgid}.")
        else: logger.warning(f"Дубликат фото {mid} для группы {mgid}.")
# ================================== handle_media_group_photo() end ==================================


# handlers/media_groups.py end