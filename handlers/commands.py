# handlers/commands.py
# -*- coding: utf-8 -*-
"""
Handlers for basic informational and configuration commands.
Includes /edit command to modify last generated image using targeted editing.
Handles /prompt set/reset/clear for image suffix (renamed from prefix).
"""

import logging
from html import escape
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.auth import is_authorized
from config import (
    CHAT_DATA_KEY_CONVERSATION_HISTORY, CHAT_DATA_KEY_IMAGE_SUFFIX, # Renamed key
    CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT, DEFAULT_TEXT_SYSTEM_PROMPT,
    MAX_HISTORY_MESSAGES, CHAT_DATA_KEY_DISPLAY_LLM_TEXT,
    CHAT_DATA_KEY_LAST_GENERATION, IMAGE_STATE_CACHE_KEY_PREFIX,
    DEFAULT_IMAGE_PROMPT_SUFFIX # Renamed constant
)
from handlers.image_gen import parse_img_args_prompt_first, _initiate_image_generation, _initiate_image_editing
from utils.cache import get_cached_image_bytes
from utils.telegram_helpers import delete_message_safely
import config # Import config to access constants easily

logger = logging.getLogger(__name__)

      
      
# ================================== start(): Handles /start command ==================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_user:
        return
    logger.info(f"/start from {update.effective_user.id}")
    welcome_text = (
        "👋 Привет\\! Я бот для работы с изображениями \\(и текстом\\) через Google Gemini\\. \n\n"
        "**Основные Команды:**\n"
        "`/img <запрос>` — Сгенерировать изображение\n"
        "`/ask <вопрос>` — Задать текстовый вопрос \\(с учетом истории\\)\n"
        "`/clear` — Очистить контекст *текстового* диалога\n"
        "`/history` — Показать контекст *текстового* диалога\n"
        "`/prompt <текст|reset|clear>` — Управление *суффиксом* для *изображений*\n"
        "`/reset <текст?>` — Установить/сбросить *системную инструкцию* для *текста*\n"
        "`/toggle_llm` — Вкл/Выкл показ *текста* от Gemini в подписи \\(по умолч\\.: ВЫКЛ\\)\n"
        "`/types` — Показать список доступных типов\\.\n"
        "`/styles` — Показать список доступных стилей и групп\\.\n"
        "`/artists` — Показать список доступных художников\\.\n"
        "`/ts` — Показать список типов с применимыми к ним стилями\\.\n"
        "`/show_all` — Показать все списки \\(типы, стили, художники, типы\\+стили\\)\\.\n"
        "`/man` — Подробное объяснение параметров и взаимодействия\\.\n" # Added /man
        "`/help` — Показать это сообщение\n\n"
        # ... (остальной текст без изменений) ...
    )
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await update.message.reply_markdown_v2(welcome_text, disable_web_page_preview=True)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Ошибка /start: {e}", exc_info=True)
# ================================== start() end ==================================

    
    


# ================================== help_command(): Handles /help command ==================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.effective_user:
        return
    logger.info(f"/help from {update.effective_user.id}")
    await start(update, context)
# ================================== help_command() end ==================================


# ================================== clear_command(): Clears text conversation history ==================================
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    history_cleared = False
    history_key = CHAT_DATA_KEY_CONVERSATION_HISTORY
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if history_key in context.chat_data:
        hist_len = len(context.chat_data[history_key])
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if hist_len > 0:
            del context.chat_data[history_key]
            await update.message.reply_html(f"✅ Контекст ({hist_len}) очищен.")
            logger.info(f"История {chat_id} очищена {user_id}")
            history_cleared = True
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not history_cleared:
        await update.message.reply_text("ℹ️ Контекст пуст.")
# ================================== clear_command() end ==================================


# ================================== show_text_history_command(): Displays text conversation history ==================================
async def show_text_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    history_key = CHAT_DATA_KEY_CONVERSATION_HISTORY
    logger.info(f"/history от {user_id} чат {chat_id}")
    raw_history = context.chat_data.get(history_key, [])
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not raw_history:
        await update.message.reply_text("ℹ️ Контекст пуст.")
        return
    display_limit = MAX_HISTORY_MESSAGES * 2
    history_to_display = raw_history[-display_limit:]
    num_displayed = len(history_to_display)
    total_in_memory = len(raw_history)
    formatted_lines = [f"📖 <b>Контекст</b> ({num_displayed}/{total_in_memory}):\n---"]
    for entry in history_to_display:
        role = entry.get("role", "?")
        text = entry.get("text", "").strip()
        sender = entry.get("sender")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not text:
            continue
        escaped_text = escape(text);
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if role == "user":
            entry_header = f"👤 <b>{escape(sender) if sender else 'User'}:</b>"
        elif role == "model":
            entry_header = "🤖 <b>Gemini:</b>"
        else:
            entry_header = f"❓ <b>{escape(role.capitalize())}:</b>"
        truncated_text = (escaped_text[:500] + '...') if len(escaped_text) > 500 else escaped_text
        formatted_lines.append(f"{entry_header}\n{truncated_text}")
    full_text = "\n\n".join(formatted_lines)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if len(full_text) > 4096:
        full_text = full_text[:4080] + "\n...(сокращено)"
        logger.warning(f"Контекст {chat_id} сокращен.")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await update.message.reply_html(full_text)
        logger.info(f"Отображен контекст для {user_id} чата {chat_id}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Ошибка отправки {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка отправки контекста.")
# ================================== show_text_history_command() end ==================================


# ================================== set_image_prompt_suffix_command(): Handles /prompt <text|reset|clear> (Suffix) ==================================
async def set_image_prompt_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE): # Renamed function
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    current_chat_data = context.chat_data
    prompt_key = config.CHAT_DATA_KEY_IMAGE_SUFFIX # Use new key
    default_suffix = config.DEFAULT_IMAGE_PROMPT_SUFFIX # Use new constant
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not context.args:
        current_suffix = current_chat_data.get(prompt_key, default_suffix)
        # Check explicitly for empty string to differentiate from default if default is also empty
        is_explicitly_cleared = prompt_key in current_chat_data and current_chat_data[prompt_key] == ""
        is_default = not is_explicitly_cleared and current_suffix == default_suffix
        usage_set = f"<code>/prompt {escape('<текст>')}</code>"
        usage_reset = f"<code>/prompt reset</code>"
        usage_clear = f"<code>/prompt clear</code>"
        reply_text = "ℹ️ Текущий <b>суффикс</b> для <b>изображений</b>:\n" # Updated text
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if is_explicitly_cleared:
            reply_text += "<i>(Пусто - очищено)</i>"
        elif current_suffix:
             reply_text += f"<code>{escape(current_suffix)}</code>"
        else:
            reply_text += "<i>(Пусто - по умолчанию)</i>" # Default is empty
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if is_default:
             reply_text += " (По умолчанию)"
        reply_text += f"\n\nУстановить: {usage_set}\nСбросить к умолч.: {usage_reset}\nОчистить: {usage_clear}"
        await update.message.reply_html(reply_text)
        return
    sub_command = " ".join(context.args).strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if sub_command.lower() == "reset":
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if prompt_key in current_chat_data:
            del current_chat_data[prompt_key]
        await update.message.reply_html(f"✅ <b>Суффикс</b> изображений сброшен к стандартному:\n<code>{escape(default_suffix) if default_suffix else '(Пусто)'}</code>") # Updated text
        logger.info(f"Суффикс img {chat_id} сброшен к умолч. {user_id}")
    # --- Handle "clear" explicitly ---
    elif sub_command.lower() == "clear":
        current_chat_data[prompt_key] = "" # Set to empty string
        await update.message.reply_html(f"✅ <b>Суффикс</b> для изображений очищен.") # Updated text
        logger.info(f"Суффикс img {chat_id} очищен {user_id}")
    # --- Handle setting new text ---
    elif sub_command:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if len(sub_command) > 1000:
            await update.message.reply_text("⚠️ Суффикс > 1000.")
            return
        current_chat_data[prompt_key] = sub_command
        await update.message.reply_html(f"✅ <b>Суффикс</b> изображений установлен:\n<code>{escape(sub_command)}</code>") # Updated text
        logger.info(f"Суффикс img {chat_id} установлен {user_id}: '{sub_command[:50]}...'")
    else:
        # This case should ideally not be reached if context.args is checked first, but keep as fallback
        await update.message.reply_text("⚠️ Укажите текст, 'reset' или 'clear'.")
# ================================== set_image_prompt_suffix_command() end ==================================


# ================================== clear_image_prompt_suffix_command(): Handles /prompt clear (Suffix) ==================================
async def clear_image_prompt_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE): # Renamed function
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    current_chat_data = context.chat_data
    prompt_key = config.CHAT_DATA_KEY_IMAGE_SUFFIX # Use new key
    current_chat_data[prompt_key] = "" # Set to empty string
    await update.message.reply_html(f"✅ <b>Суффикс</b> для изображений очищен (до перезапуска).") # Updated text
    logger.info(f"Суффикс img {chat_id} очищен {user_id}")
# ================================== clear_image_prompt_suffix_command() end ==================================


# ================================== toggle_llm_text_command(): Toggles LLM text display ==================================
async def toggle_llm_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    key = CHAT_DATA_KEY_DISPLAY_LLM_TEXT
    # Use the new default value from config
    current_value = context.chat_data.get(key, config.DEFAULT_DISPLAY_LLM_TEXT_BOOL)
    new_value = not current_value
    context.chat_data[key] = new_value
    state_text = "ВКЛ" if new_value else "ВЫКЛ"
    await update.message.reply_html(f"✅ Отображение текста LLM в подписях: <b>{state_text}</b>.")
    logger.info(f"Текст LLM {chat_id} изменен на {new_value} {user_id}")
# ================================== toggle_llm_text_command() end ==================================


# ================================== reset_text_system_prompt_command(): Resets/sets text system prompt ==================================
async def reset_text_system_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    current_chat_data = context.chat_data
    prompt_key = CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT
    logger.debug(f"/reset check: before = {current_chat_data}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not context.args:
        prompt_was_set = prompt_key in current_chat_data
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if prompt_was_set:
            del current_chat_data[prompt_key]
            logger.info(f"Removed '{prompt_key}' from {chat_id}")
        optional_feedback = "\n(Стандартная.)" if not prompt_was_set else ""
        reply_text = (f"✅ Инструкция <b>текста</b> сброшена:\n<code>{escape(DEFAULT_TEXT_SYSTEM_PROMPT)}</code>{optional_feedback}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await update.message.reply_html(reply_text)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e:
            logger.error(f"Error /reset confirm: {e}")
            await update.message.reply_text("Ошибка сброса.")
        logger.info(f"Текст инструкция {chat_id} сброшена {user_id}")
    else:
        new_prompt = " ".join(context.args).strip()
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not new_prompt:
            await update.message.reply_text("⚠️ Укажите текст или /reset.")
            return
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if len(new_prompt) > 2000:
            await update.message.reply_text("⚠️ Инструкция > 2000.")
            return
        current_chat_data[prompt_key] = new_prompt
        await update.message.reply_html(f"✅ Инструкция <b>текста</b>:\n<code>{escape(new_prompt)}</code>")
        logger.info(f"Текст инструкция {chat_id} установлена {user_id}: '{new_prompt[:50]}...'")
        logger.debug(f"/reset set: after = {current_chat_data}")
    logger.debug(f"/reset check: final = {context.chat_data}")
# ================================== reset_text_system_prompt_command() end ==================================


# handlers/commands.py end