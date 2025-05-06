# handlers/media_groups.py
# -*- coding: utf-8 -*-
"""
Handlers for collecting and processing media groups. Uses _initiate_image_combination.
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from telegram import Update, Message, Chat, User # Import User
from telegram.ext import ContextTypes, filters
from telegram.constants import ParseMode, ChatType # Import ChatType
from telegram.error import TelegramError

from utils.auth import is_authorized
from utils.cache import get_cached_image_bytes_by_id # Ensure this is imported

# Ensure _initiate_image_combination is imported correctly
# Assuming it's in handlers.image_gen and modified as per previous steps
from handlers.image_gen import _initiate_image_combination 

from utils.telegram_helpers import delete_message_safely
from config import (
    MEDIA_GROUP_CACHE_KEY_PREFIX, MEDIA_GROUP_PROCESS_DELAY_SECONDS,
    DEFAULT_COMBINE_PROMPT_TEXT
)

logger = logging.getLogger(__name__)

# No need for this lock if we handle data retrieval/clearing carefully
# media_group_data_lock = asyncio.Lock()

# ================================== process_media_group(): Processes collected media group photos ==================================
async def process_media_group(context: ContextTypes.DEFAULT_TYPE):
    """
    Job function to process a collected media group.
    Retrieves photos from cache, checks count, initiates combination, and clears cache.
    """
    job_data = context.job.data if context.job else {}
    if not isinstance(job_data, dict):
        logger.error(f"Invalid job_data type: {type(job_data)}. Data: {job_data}");
        return # Stop if job data is invalid

    chat_id = job_data.get("chat_id")
    mgid = job_data.get("media_group_id")
    user_id = job_data.get("user_id")
    # uname = job_data.get("chat_username") # Not directly used here, but kept in job_data for cache helper
    fmid = job_data.get("first_message_id") # First message ID of the group

    # Basic validation of required job data
    if not all([chat_id, mgid, user_id, fmid]):
        logger.error(f"Invalid/missing job data fields: chat_id={chat_id}, mgid={mgid}, user_id={user_id}, fmid={fmid}. Data: {job_data}");
        return # Stop if essential data is missing

    cache_key = f"{MEDIA_GROUP_CACHE_KEY_PREFIX}{mgid}"

    # --- REVISED: Retrieve photos from bot_data using .get(), DO NOT pop yet ---
    # Use .get() to retrieve the list. If the key doesn't exist (e.g., job ran twice
    # and the first instance already processed and deleted it), it returns []
    photo_data_list = context.application.bot_data.get(cache_key, []) 
    # --- END REVISED ---

    # Check if we retrieved exactly 2 photos (the expected count for combination)
    if not isinstance(photo_data_list, list) or len(photo_data_list) != 2:
        # If photo_data_list is not a list or doesn't have 2 photos,
        # log a warning and clean up the cache entry if it exists.
        # This handles cases where:
        # 1. The job ran twice and the first instance already processed and deleted the key (list is [])
        # 2. Telegram sent > 2 photos in the group (list has > 2 items)
        # 3. Some unexpected error occurred in handle_media_group_photo
        log_msg = f"Медиагруппа {mgid} не содержит ровно 2 фото ({len(photo_data_list) if isinstance(photo_data_list, list) else 'Invalid Type'}).";
        logger.warning(log_msg)

        # --- REVISED: Clean up the cache entry if it exists ---
        if cache_key in context.application.bot_data:
            logger.debug(f"Cleaning up cache key {cache_key} after finding {len(photo_data_list) if isinstance(photo_data_list, list) else 'Invalid Type'} photos.")
            del context.application.bot_data[cache_key]
        # --- END REVISED ---

        # Inform user if we received some photos but not exactly 2
        if isinstance(photo_data_list, list) and len(photo_data_list) > 0:
             try: await context.bot.send_message(chat_id, "ℹ️ Для комбинации нужно ровно 2 фото.", reply_to_message_id=fmid)
             except Exception: pass # Ignore sending error

        return # Exit the job if the photo count is wrong

    # --- REVISED: If we have exactly 2 photos, NOW extract file IDs and clean up the cache ---
    try:
        # Sort by message ID to ensure consistent order (img1 vs img2 in API call)
        photo_data_list.sort(key=lambda p: p["message_id"])
        file_id_1 = photo_data_list[0]["file_id"]
        file_id_2 = photo_data_list[1]["file_id"]
        # Ensure fmid is indeed the message ID of the first photo
        fmid = photo_data_list[0]["message_id"]

        # --- REVISED: Clean up the cache entry AFTER successfully extracting file IDs ---
        if cache_key in context.application.bot_data:
            logger.debug(f"Successfully extracted 2 file IDs for {mgid}. Cleaning up cache key {cache_key}.")
            del context.application.bot_data[cache_key]
        # --- END REVISED ---

    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Ошибка извлечения file_id/message_id from photo_data_list for {mgid}: {e}");
        # Clean up cache on error during extraction too
        if cache_key in context.application.bot_data:
            logger.debug(f"Error extracting file IDs for {mgid}. Cleaning up cache key {cache_key}.")
            del context.application.bot_data[cache_key]
        # Inform user about the error
        try: await context.bot.send_message(chat_id, "❌ Ошибка обработки фото.", reply_to_message_id=fmid)
        except Exception: pass
        return # Exit on data extraction error
    # --- END REVISED ---


    logger.info(f"Обработка группы {mgid} от {user_id}. Фото: {file_id_1}, {file_id_2}.")

    # Download the two images
    dl_status_msg = None
    img1_bytes = None
    img2_bytes = None
    dl_success = False # Flag to track successful download of both images

    try:
        # Send a status message replying to the first message of the group
        dl_status_msg = await context.bot.send_message(chat_id, "⏳ Загрузка...", reply_to_message_id=fmid)

        # Download both images concurrently using their file IDs
        # Use chat_id and uname from job_data for the cache helper
        img1_bytes, img2_bytes = await asyncio.gather(
            get_cached_image_bytes_by_id(context, file_id_1, job_data.get("chat_id"), job_data.get("chat_username")),
            get_cached_image_bytes_by_id(context, file_id_2, job_data.get("chat_id"), job_data.get("chat_username")),
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
             logger.error(f"Сбой загрузки одного или обоих фото для {mgid}.");


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
    # user_id is available from job_data
    user_mention = f"User ({user_id})" # Default mention
    try:
        # Try to get the actual user mention HTML using the user_id
        user_chat_obj = await context.bot.get_chat(user_id)
        user_mention = user_chat_obj.mention_html()
    except Exception as mention_err:
        logger.warning(f"Не удалось получить mention для пользователя {user_id}: {mention_err}")
        # Keep the default mention if getting the chat fails

    # Create a dummy source message object for _initiate_image_combination
    # This object is primarily needed by _initiate_image_combination's call
    # to _determine_context within _initiate_image_generation.
    # It needs chat, from_user, and message_id.
    source_message_obj = None
    try:
        # Fetch the chat object using chat_id from job_data
        chat_obj = await context.bot.get_chat(chat_id)
        # Fetch the user object using user_id from job_data
        user_obj = await context.bot.get_chat(user_id) # Fetch user as a Chat object (often works like User)

        # Create a Message object mimicking the first message of the media group
        # We don't have the original message's date directly, so omit it.
        # We don't need the full message data, just enough structure for handlers.
        source_message_obj = Message(
            message_id=fmid, # Use the first message ID from job_data
            date=None, # Cannot reliably get the exact date here
            chat=chat_obj, # Use the fetched chat object
            from_user=user_obj # Use the fetched user object (as a Chat type)
        )
    except Exception as chat_err:
        logger.error(f"Не удалось получить Chat/User object или создать source_message_obj для {chat_id}/{user_id}: {chat_err}.")
        # Fallback: Create a minimal Message object with just chat_id, type, and a dummy user
        # This might cause issues later if more message properties are accessed or if from_user is expected as a User type.
        from telegram import User # Ensure User is imported for dummy object

        # Create a dummy User object
        dummy_user = User(id=user_id, first_name=user_mention, is_bot=False) # Use user_mention as first_name fallback

        source_message_obj = Message(
             message_id=fmid, # Use the first message ID from job_data
             date=None, # Cannot reliably get the date
             chat=Chat(id=chat_id, type=ChatType.GROUP), # Create a minimal Chat object (guess group type)
             from_user=dummy_user # Use the dummy User object
        )


    # Initiate the image combination process
    try:
        # Call _initiate_image_combination, passing the downloaded bytes,
        # the default prompt, and importantly, the original file IDs
        await _initiate_image_combination(
            context=context,
            base_image_bytes=img1_bytes, # Pass bytes of the first downloaded image
            user_image_bytes=img2_bytes, # Pass bytes of the second downloaded image
            user_prompt=DEFAULT_COMBINE_PROMPT_TEXT, # Use the default prompt for media group combinations
            chat_id=chat_id, # Pass chat_id from job_data
            user_id=user_id, # Pass user_id from job_data
            user_mention=user_mention, # Pass the generated user mention
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


# ================================== handle_media_group_photo(): Collects photos from a media group ==================================
async def handle_media_group_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Collects photo information from media group messages and schedules a processing job.
    Uses the media group ID as a key in bot_data.
    """
    # Check if authorized and if it's a photo in a media group without a caption or reply
    # We allow photos *with* captions or replies to be handled by image_gen handlers.
    if not await is_authorized(update, context): return
    if not (update.message and update.message.photo and update.message.media_group_id and not update.message.caption and not update.message.reply_to_message):
         logger.debug(f"Ignoring message (not media group photo, or has caption/reply): {update.message.message_id}, mgid={update.message.media_group_id}")
         return # Ignore if not a media group photo without caption/reply

    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    # Basic validation
    if not chat or not user:
        logger.warning(f"Ignoring message {msg.message_id}: Missing chat or user info.")
        return

    mgid = msg.media_group_id # Media group ID
    photo = msg.photo[-1]      # Get the largest photo size
    fid = photo.file_id        # File ID of the photo
    mid = msg.message_id       # Message ID of the photo

    cache_key = f"{MEDIA_GROUP_CACHE_KEY_PREFIX}{mgid}"

    # Use a lock to ensure only one handler instance modifies the list at a time
    # This helps prevent race conditions when multiple photos arrive very fast
    # for the same media group.
    media_group_data_lock = asyncio.Lock() # Define lock within the function scope or outside if shared

    async with media_group_data_lock:
        # Retrieve the current list for this media group ID. If it doesn't exist, create an empty one.
        # Use setdefault to get the list and add it if missing in one atomic step
        mg_photos = context.application.bot_data.setdefault(cache_key, [])

        # Check if this specific message ID is already in the list (shouldn't happen with unique messages, but safe check)
        if not any(p["message_id"] == mid for p in mg_photos):
            # Append the new photo's data to the list
            mg_photos.append({"file_id": fid, "message_id": mid})
            logger.debug(f"Added photo {mid} (file {fid}) to group {mgid}. Total collected: {len(mg_photos)}.")

            # Store the first message ID of the group (useful for replying later)
            # We can assume the first message to arrive is the one with the lowest ID,
            # but sorting ensures this. Let's make sure the list is sorted before getting fmid.
            mg_photos.sort(key=lambda p: p["message_id"])
            fmid = mg_photos[0]["message_id"]

            # Define job data to pass to the processing function
            job_data = {
                "chat_id": chat.id,
                "media_group_id": mgid,
                "user_id": user.id,
                "chat_username": chat.username, # Pass username for cache helper
                "first_message_id": fmid,
                # We do NOT pass the file IDs here. The job will retrieve the list from bot_data.
            }

            # Schedule the processing job.
            # Use replace_existing=True so if another photo for the same group arrives,
            # the timer is reset, giving more time to collect all photos.
            # The job name is based on the media group ID.
            context.job_queue.run_once(
                process_media_group, # The job function to run
                MEDIA_GROUP_PROCESS_DELAY_SECONDS, # The delay (inactivity timeout)
                data=job_data, # Data to pass to the job function
                name=cache_key, # Unique name for this media group job
                job_kwargs={'replace_existing': True} # Replace any existing job with the same name
            )
            logger.debug(f"Scheduled/reset processing job '{cache_key}' for media group {mgid} to run in {MEDIA_GROUP_PROCESS_DELAY_SECONDS} seconds.")
        else:
            logger.warning(f"Duplicate photo message ID {mid} received for media group {mgid}. Ignoring.")

# ================================== handle_media_group_photo() end ==================================
# handlers/media_groups.py end