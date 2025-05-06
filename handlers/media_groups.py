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
    # Pop the collected photo data list from bot_data
    photo_data_list = context.application.bot_data.pop(cache_key, []) # This pops the data

    # Check if we got exactly 2 photos (the expected count for combination)
    if not photo_data_list or len(photo_data_list) != 2:
        # If not 2, log a warning and potentially inform the user, then stop.
        log_msg = f"Медиагруппа {mgid} не содержит 2 фото ({len(photo_data_list)})."; logger.warning(log_msg)
        if photo_data_list: # Only send message if we got *some* photos, not if the list was empty from the start
            try: await context.bot.send_message(chat_id, "ℹ️ Для комбинации нужно 2 фото.", reply_to_message_id=fmid)
            except Exception: pass # Ignore sending error
        return # Exit the job if the photo count is wrong

    # If we have exactly 2 photos, extract their file IDs and message IDs
    try:
        # Sort by message ID to ensure consistent order (though Gemini might not care)
        photo_data_list.sort(key=lambda p: p["message_id"])
        file_id_1 = photo_data_list[0]["file_id"]
        file_id_2 = photo_data_list[1]["file_id"]
        # We also need the message IDs, especially the first one (fmid) for replying
        # mid_1 = photo_data_list[0]["message_id"]
        # mid_2 = photo_data_list[1]["message_id"]
        # fmid should already be the first message ID, but let's re-confirm
        fmid = photo_data_list[0]["message_id"]

    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Ошибка извлечения file_id из media_group_data для {mgid}: {e}");
        # Inform user about the error
        try: await context.bot.send_message(chat_id, "❌ Ошибка обработки фото.", reply_to_message_id=fmid)
        except Exception: pass
        return # Exit on data extraction error

    logger.info(f"Обработка группы {mgid} от {user_id}. Фото: {file_id_1}, {file_id_2}.")

    # Download the two images
    dl_status_msg = None
    img1_bytes = None
    img2_bytes = None
    dl_success = False # Flag to track successful download of both images

    try:
        dl_status_msg = await context.bot.send_message(chat_id, "⏳ Загрузка...", reply_to_message_id=fmid)

        # Download both images concurrently
        img1_bytes, img2_bytes = await asyncio.gather(
            get_cached_image_bytes_by_id(context, file_id_1, chat_id, uname),
            get_cached_image_bytes_by_id(context, file_id_2, chat_id, uname),
            return_exceptions=True # Allow gathering to complete even if one fails
        )

        # Check results from gathering
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if isinstance(img1_bytes, Exception) or img1_bytes is None:
            logger.error(f"Ошибка загрузки 1 ({file_id_1}): {img1_bytes}"); img1_bytes = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if isinstance(img2_bytes, Exception) or img2_bytes is None:
            logger.error(f"Ошибка загрузки 2 ({file_id_2}): {img2_bytes}"); img2_bytes = None

        # Check if both images were successfully downloaded (are bytes, not None)
        if img1_bytes is not None and img2_bytes is not None:
             dl_success = True
        else:
             logger.error(f"Сбой загрузки одного или обоих фото для {mgid}.")


    except Exception as e:
        # Catch any other unexpected errors during download or setup
        logger.exception(f"Ошибка загрузки фото для медиагруппы {mgid}: {e}");
        dl_success = False # Ensure success flag is False

    finally:
        # Always attempt to delete the status message
        if dl_status_msg: await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)

    # If download wasn't successful, inform the user and stop
    if not dl_success:
        await context.bot.send_message(chat_id, "❌ Ошибка загрузки фото.", reply_to_message_id=fmid)
        return

    # Get user mention for the processing message
    user_mention = f"User ({user_id})" # Default mention
    try:
        # Try to get the actual user mention HTML
        user_chat = await context.bot.get_chat(user_id)
        user_mention = user_chat.mention_html()
    except Exception as mention_err:
        logger.warning(f"Не удалось получить mention для пользователя {user_id}: {mention_err}")
        # Keep the default mention if getting the chat fails

    # Create a dummy source message object for _initiate_image_combination
    # We need a Message object primarily for the chat and message_id properties
    # that _determine_context inside _initiate_image_generation (called by combination) expects.
    # We can fetch the chat object and create a minimal Message instance.
    source_message_obj = None
    try:
        chat_obj = await context.bot.get_chat(chat_id)
        # Create a Message object mimicking the first message of the media group
        # We don't need the full message data, just enough structure for handlers
        source_message_obj = Message(
            message_id=fmid,
            date=update.message.date if update and update.message else None, # Use date from one of the received messages if available
            chat=chat_obj,
            from_user=user # Use the user who sent the media group
        )
    except Exception as chat_err:
        logger.error(f"Не удалось получить Chat object для {chat_id} или создать source_message_obj: {chat_err}.")
        # Fallback: Create a minimal Message object with just chat_id and type
        # This might cause issues later if more message properties are accessed.
        source_message_obj = Message(
             message_id=fmid,
             date=None, # Cannot get date without full message
             chat=Chat(id=chat_id, type=ChatType.GROUP), # Guess chat type
             from_user=user # Still need the user object
        )


    # Initiate the image combination process
    try:
        await _initiate_image_combination(
            context=context,
            base_image_bytes=img1_bytes, # Pass bytes of the first downloaded image
            user_image_bytes=img2_bytes, # Pass bytes of the second downloaded image
            user_prompt=DEFAULT_COMBINE_PROMPT_TEXT, # Use the default prompt for media group combinations
            chat_id=chat_id,
            user_id=user_id,
            user_mention=user_mention,
            reply_to_msg_id=fmid, # Reply to the first message in the media group
            source_message=source_message_obj, # Pass the constructed Message object
            original_file_id_1=file_id_1, # <<< PASS THE FIRST FILE ID HERE
            original_file_id_2=file_id_2  # <<< PASS THE SECOND FILE ID HERE
        )
    except Exception as e:
        # Catch any errors during the combination initiation itself
        logger.exception(f"Ошибка _initiate_image_combination для медиагруппы {mgid}: {e}")
        # Inform user about the error
        try: await context.bot.send_message(chat_id, "❌ Ошибка обработки группы.", reply_to_message_id=fmid)
        except Exception as final_err: logger.error(f"Не удалось отправить ошибку для {mgid}: {final_err}")

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