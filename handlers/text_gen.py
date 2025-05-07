# handlers/text_gen.py
# -*- coding: utf-8 -*-
"""
Handlers for text generation commands (/ask, ?) and conversation replies.
handle_text_reply routes to image editing (targeted or general) or text convo.
"""

import logging
import re
import asyncio
from html import escape
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from telegram.error import TelegramError
from utils.auth import is_authorized
from utils.telegram_helpers import stream_and_update_message, delete_message_safely
from utils.cache import get_cached_image_bytes
from handlers.image_gen import _initiate_image_generation, _initiate_image_editing, _resolve_settings, parse_img_args_prompt_first
from config import (
    CHAT_DATA_KEY_CONVERSATION_HISTORY, CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT,
    DEFAULT_TEXT_SYSTEM_PROMPT, MAX_HISTORY_MESSAGES,
    USER_DATA_KEY_PROMPT_EDIT_TARGET, IMAGE_STATE_CACHE_KEY_PREFIX
)
from ui.messages import update_caption_and_keyboard

logger = logging.getLogger(__name__)

# ================================== handle_ask_command(): Handles /ask command ==================================
async def handle_ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update, context): return
    if not update.message or not update.effective_user or not update.effective_chat: return
    user_prompt = " ".join(context.args).strip() if context.args else ""
    if not user_prompt: await update.message.reply_text("⚠️ Укажите вопрос после /ask."); return
    await process_text_generation_request(update, context, user_prompt)
# ================================== handle_ask_command() end ==================================


# ================================== handle_ask_shortcut(): Handles ? shortcut ==================================
async def handle_ask_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update, context): return
    if not update.message or not update.message.text or not update.effective_user or not update.effective_chat: return
    match = re.match(r"^\?\s*(.*)", update.message.text, re.DOTALL)
    if not match: logger.warning(f"Ask shortcut called for non-matching text: {update.message.text}"); return
    user_prompt = match.group(1).strip()
    if not user_prompt: await update.message.reply_text("⚠️ Укажите вопрос после ?."); return
    await process_text_generation_request(update, context, user_prompt)
# ================================== handle_ask_shortcut() end ==================================


# ================================== process_text_generation_request(): Common text generation processing ==================================
async def process_text_generation_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_prompt: str):
    if not update.message or not update.effective_user or not update.effective_chat: return
    user = update.effective_user; chat = update.effective_chat; message = update.message
    user_mention = user.mention_html(); sender_full_name = user.full_name or user.username or f"User_{user.id}"
    logger.info(f"Текст запрос от '{sender_full_name}' ({user.id}): '{user_prompt[:50]}...'")
    history_key = CHAT_DATA_KEY_CONVERSATION_HISTORY; sys_prompt_key = CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT
    raw_history = context.chat_data.get(history_key, [])
    current_text_system_prompt = context.chat_data.get(sys_prompt_key, DEFAULT_TEXT_SYSTEM_PROMPT)
    history_contents = [{"role": entry["role"], "parts": [{"text": entry["text"]}]} for entry in raw_history if entry.get("role") and entry.get("text")]
    logger.debug(f"История: {len(raw_history)}. Сист.инстр.: '{current_text_system_prompt[:100]}...'")
    try:
        placeholder_msg = await message.reply_html(text=f"⏳ {user_mention}, обрабатываю...")
        await stream_and_update_message(
            context=context, chat_id=chat.id, user_mention=user_mention, reply_msg_id=placeholder_msg.message_id,
            history_contents=history_contents, final_user_prompt=user_prompt,
            current_text_system_prompt=current_text_system_prompt, sender_full_name=sender_full_name
        )
    except TelegramError as e: logger.error(f"Ошибка ответа (текст): {e}")
    except Exception as e:
        logger.exception(f"Ошибка потока текста: {e}");
        try: await message.reply_text("❌ Ошибка обработки текста.")
        except Exception: pass
# ================================== process_text_generation_request() end ==================================


      
      
# ================================== handle_text_reply(): Handles text replies to the bot (Text convo or Image edit) ==================================
async def handle_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.message.text: return
    user = update.effective_user; chat = update.effective_chat; message = update.message
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user or not chat: return
    user_id = user.id; reply_text = message.text.strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not reply_text: return

    # --- Handle Pending Keyboard Prompt Change ---
    pending_edit_target = context.user_data.get(USER_DATA_KEY_PROMPT_EDIT_TARGET)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if pending_edit_target and isinstance(pending_edit_target, dict) and pending_edit_target.get('chat_id') == chat.id:
        target_msg_id = pending_edit_target.get('message_id')
        logger.info(f"Получен текст от {user_id} для изменения промпта {target_msg_id}")
        state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{chat.id}:{target_msg_id}"
        target_state = context.application.bot_data.get(state_key)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if target_state:
            target_state["effective_prompt"] = reply_text; target_state["awaiting_prompt_change"] = False
            context.application.bot_data[state_key] = target_state; del context.user_data[USER_DATA_KEY_PROMPT_EDIT_TARGET]
            logger.info(f"Промпт {target_msg_id} обновлен: '{reply_text[:50]}...'")
            await update_caption_and_keyboard(context, chat.id, target_msg_id)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try: await message.reply_text("✅ Промпт обновлен.") # Removed quote=True
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception: pass
        else:
            logger.warning(f"Ожидалось изм. промпта для {state_key}, но состояние не найдено."); del context.user_data[USER_DATA_KEY_PROMPT_EDIT_TARGET];
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try: await message.reply_text("⚠️ Не удалось обновить: исх. сообщение истекло.") # Removed quote=True
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception: pass
        return # Stop further processing
    elif pending_edit_target:
        logger.warning(f"User {user_id} sent text while awaiting reply for chat {pending_edit_target.get('chat_id')}. Clearing flag."); del context.user_data[USER_DATA_KEY_PROMPT_EDIT_TARGET]

    # --- Handle Replies to Bot Messages ---
    replied_msg = message.reply_to_message
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not replied_msg: logger.debug("Текст не является ответом."); return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if message.photo or reply_text.startswith('/') or re.match(r'^(?:!|!!|\?)\s*', reply_text): return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not (replied_msg.from_user and replied_msg.from_user.is_bot and replied_msg.from_user.id == context.bot.id): logger.debug(f"Ответ не на сообщение бота."); return

    # --- Reply to Bot TEXT -> Continue Conversation ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if replied_msg.text and not replied_msg.photo:
        logger.info(f"Текст ответ на ТЕКСТ бота от {user.id} -> Продолжение диалога")
        await process_text_generation_request(update, context, reply_text)

    # --- Reply to Bot IMAGE -> Edit Image ---
    elif replied_msg.photo:
        logger.info(f"Текст ответ на ИЗОБРАЖЕНИЕ бота от {user.id}. Текст: '{reply_text[:100]}...'")
        new_prompt_part, parsed_reply_args = parse_img_args_prompt_first(reply_text)
        has_new_args = any(v is not None or parsed_reply_args[f"randomize_{k}"] for k, v in parsed_reply_args.items() if k != "ar")
        has_new_prompt = bool(new_prompt_part)

        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not has_new_prompt and not has_new_args:
             logger.info("Ответ на изображение не содержит ни промпта, ни аргументов. Игнорируется.")
             return

        logger.info(f"Редактирование изображения. Новый Промпт: {has_new_prompt}. Новые Аргументы: {has_new_args}.")
        target_msg_id = replied_msg.message_id
        state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{chat.id}:{target_msg_id}"
        last_msg_state = context.application.bot_data.get(state_key)

        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not last_msg_state:
            await message.reply_text("😕 Настройки исх. изображения утеряны (истекли?). Не могу редактировать.") # Removed quote=True
            return
        original_settings = last_msg_state.get("api_call_settings", {})
        original_user_prompt = last_msg_state.get("original_user_prompt", "")
        original_api_prompt = last_msg_state.get("api_call_prompt", original_user_prompt)
        file_id_to_edit = last_msg_state.get("generated_file_id")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not file_id_to_edit:
            await message.reply_text("😕 Ошибка: нет файла исх. изображения в сохраненном состоянии.") # Removed quote=True
            return

        current_effective_prompt = new_prompt_part if has_new_prompt else original_user_prompt
        current_settings_base = {
            "type_data": last_msg_state.get("selected_type_data"), "style_data": last_msg_state.get("selected_style_data"),
            "artist_data": last_msg_state.get("selected_artist_data"), "ar": last_msg_state.get("selected_ar")
        }
        current_settings_for_resolve = {
            "type": parsed_reply_args["type"] if parsed_reply_args.get("type") else current_settings_base["type_data"],
            "style": parsed_reply_args["style"] if parsed_reply_args.get("style") else current_settings_base["style_data"],
            "artist": parsed_reply_args["artist"] if parsed_reply_args.get("artist") else current_settings_base["artist_data"],
            "ar": parsed_reply_args["ar"] if parsed_reply_args.get("ar") else current_settings_base["ar"],
            
            "randomize_type": parsed_reply_args.get("randomize_type", False),
            "randomize_style": parsed_reply_args.get("randomize_style", False),
            "randomize_artist": parsed_reply_args.get("randomize_artist", False),
            
            "style_marker": parsed_reply_args.get("style_marker"),

            "type_choice_list": parsed_reply_args.get("type_choice_list"),
            "style_choice_list": parsed_reply_args.get("style_choice_list"),
            "artist_choice_list": parsed_reply_args.get("artist_choice_list"),
        }

        logger.debug(f"Settings BEFORE resolve for reply edit: {current_settings_for_resolve}")
        resolved_settings_for_edit, _, _, _ = _resolve_settings(current_settings_for_resolve)
        logger.debug(f"Settings AFTER resolve for reply edit: {resolved_settings_for_edit}")

        # FIX: Removed quote=True from this call
        dl_status_msg = await message.reply_text("⏳ Загрузка исх. изображения...")
        image_bytes = await get_cached_image_bytes(context, file_id_to_edit, chat)
        await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not image_bytes:
            await message.reply_text(f"❌ Ошибка загрузки исх. изображения ({file_id_to_edit}).") # Removed quote=True
            return

        await _initiate_image_editing(
            context=context, base_image_bytes=image_bytes, current_settings=resolved_settings_for_edit,
            original_settings=original_settings, current_effective_prompt=current_effective_prompt,
            original_user_prompt=original_user_prompt, original_api_prompt=original_api_prompt,
            chat_id=chat.id, user_id=user_id, user_mention=user.mention_html(),
            reply_to_msg_id=message.message_id, source_message=message
        )
    else:
        logger.debug(f"Текст ответ на сообщение неизвестного типа.")
# ================================== handle_text_reply() end ==================================

# ================================== handle_private_text() ==================================
async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    # Only allow plain text generation in PRIVATE CHATS
    if message.chat.type != ChatType.PRIVATE:
        return

    user_prompt = message.text.strip()
    if not user_prompt:
        return

    # Skip if replying to a bot message — already handled by handle_text_reply()
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        return

    text = message.text.strip()

    # Check for /ask
    if text.startswith("/ask"):
        args = text[len("/ask"):].strip()
        await handle_ask_command_with_args(update, context, args)
        return

    # Check for ? shortcut
    ask_match = re.match(r"^\?\s*(.+)", text, re.DOTALL)
    if ask_match:
        user_prompt = ask_match.group(1).strip()
        await process_text_generation_request(update, context, user_prompt)
        return

    # Block messages starting with commands like !, !!, /img, /man, etc.
    if re.match(
        r"^(!|!!|/img|/help|/start|/clear|/history|/prompt|/toggle_llm|/types|/artists|/styles|/man)",
        text
    ):
        return

    # If none of the above, treat as normal text input (private chat only)
    await process_text_generation_request(update, context, user_prompt)
# ================================== handle_private_text() end ==================================

async def handle_ask_command_with_args(update: Update, context: ContextTypes.DEFAULT_TYPE, user_prompt: str):
    if not await is_authorized(update, context):
        return
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    if not user_prompt:
        await update.message.reply_text("⚠️ Укажите вопрос.")
        return
    await process_text_generation_request(update, context, user_prompt)
    

# handlers/text_gen.py end
