# utils/telegram_helpers.py
# -*- coding: utf-8 -*-
"""
Utility functions for common Telegram bot interactions,
including safe message deletion and streamed text responses
using custom Markdown-to-HTML conversion.
"""

import logging
import re
import asyncio
from html import escape
from typing import Optional, List, Dict, Any
from telegram import Message, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from telegram.error import TelegramError
from api.gemini_api import generate_text_with_gemini_stream
from .html_helpers import convert_basic_markdown_to_html
from config import CHAT_DATA_KEY_CONVERSATION_HISTORY, MAX_HISTORY_MESSAGES, GEMINI_TEXT_MODEL

logger = logging.getLogger(__name__)

# ================================== delete_message_safely(): Safely deletes a message ==================================
async def delete_message_safely(context: ContextTypes.DEFAULT_TYPE, chat_id: Optional[int], message_id: Optional[int]):
    if not message_id or not chat_id: logger.debug(f"delete_message_safely неверный chat_id ({chat_id}) или message_id ({message_id})."); return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Сообщение {message_id} удалено из чата {chat_id}.")
    except TelegramError as e:
        error_msg = str(e).lower()
        if ("message to delete not found" in error_msg or "message can't be deleted" in error_msg or
            "message_not_modified" in error_msg or "message_id_invalid" in error_msg):
            logger.warning(f"Не удалось удалить {message_id} в {chat_id}: {e}")
        else: logger.error(f"Ошибка TG при удалении {message_id} в {chat_id}: {e}")
    except Exception as e: logger.exception(f"Неож. ошибка при удалении {message_id} в {chat_id}: {e}")
# ================================== delete_message_safely() end ==================================


# ================================== stream_and_update_message(): Streams text response, updates message ==================================
async def stream_and_update_message(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_mention: str, reply_msg_id: int, history_contents: list,
    final_user_prompt: str, current_text_system_prompt: str, sender_full_name: str
):
    full_response = ""
    edit_buffer = ""
    last_edit_time = asyncio.get_event_loop().time()
    edit_interval = 1.7
    stream_successful = True
    final_model_response = ""
    error_occurred_during_stream = False
    initial_message_sent = False
    reply_msg = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        reply_msg = await context.bot.edit_message_text(chat_id=chat_id, message_id=reply_msg_id, text=f"⏳ {user_mention}, думаю...", parse_mode=ParseMode.HTML)
        initial_message_sent = True
        stream_generator = generate_text_with_gemini_stream(history_contents=history_contents, current_prompt=final_user_prompt, system_prompt_text=current_text_system_prompt, model_name=GEMINI_TEXT_MODEL)
        async for chunk, error_message in stream_generator:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if error_message:
                stream_successful = False
                error_occurred_during_stream = True
                logger.warning(f"Ошибка стриминга: {error_message}")
                edit_buffer += f"\n\n[ {error_message} ]"
                break
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if chunk:
                full_response += chunk
                edit_buffer += chunk
            current_time = asyncio.get_event_loop().time()
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if edit_buffer and (current_time - last_edit_time > edit_interval or len(edit_buffer) > 150):
                text_to_edit = f"{user_mention},\n{escape(full_response)} ✍️"
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if len(text_to_edit) > 4096:
                    text_to_edit = text_to_edit[:4090] + "..."
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=reply_msg_id, text=text_to_edit, parse_mode=None)
                    edit_buffer = ""
                    last_edit_time = current_time
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except TelegramError as e:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if "message is not modified" in str(e).lower():
                        logger.debug(f"Промежуточное редактирование пропущено {chat_id}.")
                        edit_buffer = ""
                    elif "FLOOD_WAIT" in str(e).upper():
                        logger.warning(f"Flood wait {chat_id}.")
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        try:
                            wait_match = re.search(r"FLOOD_WAIT_(\d+)", str(e), re.IGNORECASE)
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            if wait_match:
                                wait_time = int(wait_match.group(1)) + 1
                            else:
                                wait_time = 5
                            logger.warning(f"Ожидание {wait_time} сек...")
                            await asyncio.sleep(wait_time)
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        except Exception:
                            await asyncio.sleep(5)
                    else:
                        logger.warning(f"Ошибка промежуточного ред. {chat_id}: {e}")
                    last_edit_time = current_time
            await asyncio.sleep(0.05)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if stream_successful:
            final_model_response = full_response
        response_to_format = final_model_response if stream_successful and final_model_response else full_response
        final_text = ""
        parse_mode = ParseMode.HTML
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not response_to_format and not error_occurred_during_stream:
            logger.warning(f"Стрим завершен без контента {chat_id}. Успех: {stream_successful}")
            final_text = f"{user_mention},\n[Ответ пуст]"
            final_text = f"⚠️ {final_text}" if not stream_successful else final_text
        elif response_to_format:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if edit_buffer and error_occurred_during_stream:
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if not full_response.endswith(edit_buffer):
                     response_to_format += edit_buffer
            formatted_content = ""
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                raw_text_input = str(response_to_format).strip()
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not raw_text_input:
                    raise ValueError("Input text is empty")
                formatted_content = convert_basic_markdown_to_html(raw_text_input)
                prefix = f"{'⚠️ ' if not stream_successful or error_occurred_during_stream else ''}{user_mention},\n"
                final_text = f"{prefix}{formatted_content}"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as format_err:
                logger.error(f"Ошибка Markdown->HTML {chat_id}: {format_err}. Escape.", exc_info=True)
                escaped_final_response = escape(str(response_to_format).strip())
                prefix = f"{'⚠️ ' if not stream_successful or error_occurred_during_stream else ''}{user_mention},\n"
                final_text = f"{prefix}{escaped_final_response}"
                parse_mode = None
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if len(final_text) > 4096:
                final_text = final_text[:4090] + "..."
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if initial_message_sent:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=reply_msg_id, text=final_text, parse_mode=parse_mode)
                logger.debug(f"Финальное ред. {reply_msg_id} успешно {chat_id}.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except TelegramError as e:
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if "parse error" in str(e).lower() or "Can't parse entities" in str(e):
                     logger.error(f"Ошибка парсинга ПОСЛЕ КОНВЕРТЕРА {chat_id}: {e}. Простой текст.")
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     try:
                          escaped_fallback_text = escape(str(response_to_format).strip())
                          prefix = f"{'⚠️ ' if not stream_successful or error_occurred_during_stream else ''}{user_mention},\n"
                          final_fallback_text = f"{prefix}{escaped_fallback_text}"
                          # Reminder: Use new line, not semicolon, for the following block/statement.
                          if len(final_fallback_text) > 4096:
                              final_fallback_text = final_fallback_text[:4090] + "..."
                          await context.bot.edit_message_text(chat_id=chat_id, message_id=reply_msg_id, text=final_fallback_text, parse_mode=None)
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     except Exception as fallback_err:
                          logger.error(f"Не удалось fallback {chat_id}: {fallback_err}")
                 elif "message is not modified" not in str(e).lower():
                     logger.error(f"Ошибка финального ред. {chat_id}: {e}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Критическая ошибка потока {chat_id}: {e}")
        stream_successful = False
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if initial_message_sent:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=reply_msg_id, text=f"⚠️ {user_mention}, крит. ошибка:\n<pre>{escape(str(e))}</pre>", parse_mode=ParseMode.HTML)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception:
                pass
    history_key = CHAT_DATA_KEY_CONVERSATION_HISTORY
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if stream_successful and final_model_response:
        model_response_to_store = final_model_response.strip()
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if model_response_to_store:
            current_history = context.chat_data.setdefault(history_key, [])
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not current_history or not (current_history[-1]['role'] == 'user' and current_history[-1]['text'] == final_user_prompt):
                current_history.append({'role': 'user', 'sender': sender_full_name, 'text': final_user_prompt})
            else:
                logger.debug(f"Дубль user prompt {chat_id}")
            current_history.append({'role': 'model', 'text': model_response_to_store})
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if len(current_history) > MAX_HISTORY_MESSAGES * 2:
                context.chat_data[history_key] = current_history[-(MAX_HISTORY_MESSAGES * 2) :]
                logger.debug(f"История {chat_id} обрезана до {len(context.chat_data[history_key])}.")
        else:
            logger.warning(f"Финальный ответ модели пуст {chat_id}.")
    else:
        logger.info(f"Поток неуспешен, не в историю {chat_id}.")
    logger.info(f"Завершение потока {chat_id}. Успех: {stream_successful}")
# ================================== stream_and_update_message() end ==================================

# utils/telegram_helpers.py end