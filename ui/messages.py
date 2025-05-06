# ui/messages.py
# -*- coding: utf-8 -*-
"""
Functions for formatting and sending bot messages to the user, including
initial image response with keyboard and updates via callbacks.
Refactored caption generation for clarity and specific formatting.
Adheres strictly to multi-line formatting rules. Includes Artist selection.
LLM text response shown by default. Handles prompt change request state.
Displays /edit prefix if settings/prompt changed from original generation.
Tracks last successful image generation.
"""

import logging
import io
from html import escape
from typing import Optional, Dict, Any, List, Tuple

from telegram import Update, InputFile, InlineKeyboardMarkup, PhotoSize
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest

# Import helpers and config
from utils.html_helpers import convert_basic_markdown_to_html
from utils.telegram_helpers import delete_message_safely
from config import (
    IMAGE_STATE_CACHE_KEY_PREFIX,
    CHAT_DATA_KEY_DISPLAY_LLM_TEXT,
    CHAT_DATA_KEY_LAST_GENERATION # Import key for last generation tracking
)
# Import keyboard generator
from .keyboards import (
    generate_main_keyboard,
    generate_ar_selection_keyboard,
    generate_type_selection_keyboard,
    generate_style_selection_keyboard,
    generate_artist_selection_keyboard,
    generate_prompt_action_keyboard
)
import config

logger = logging.getLogger(__name__)

# ================================== _compare_settings(): Compares two setting dicts ==================================
def _compare_settings(current_state: Dict[str, Any], original_settings: Dict[str, Any]) -> bool:
    """
    Compares relevant current settings from state with original API call settings.
    Returns True if any setting differs, False otherwise.
    Also checks if effective_prompt differs from original_user_prompt.
    """
    if not original_settings: return True # Assume changed if no original settings found

    # Compare AR
    if current_state.get("selected_ar") != original_settings.get("ar"): return True

    # Compare Type (by ID if available)
    current_type_id = current_state.get("selected_type_data", {}).get('id') if current_state.get("selected_type_data") else None
    original_type_id = original_settings.get("type_data", {}).get('id') if original_settings.get("type_data") else None
    if current_type_id != original_type_id: return True

    # Compare Style (by name if available)
    current_style_name = current_state.get("selected_style_data", {}).get('name') if current_state.get("selected_style_data") else None
    original_style_name = original_settings.get("style_data", {}).get('name') if original_settings.get("style_data") else None
    if current_style_name != original_style_name: return True

    # Compare Artist (by name if available)
    current_artist_name = current_state.get("selected_artist_data", {}).get('name') if current_state.get("selected_artist_data") else None
    original_artist_name = original_settings.get("artist_data", {}).get('name') if original_settings.get("artist_data") else None
    if current_artist_name != original_artist_name: return True

    # Compare Effective Prompt vs Original User Prompt
    current_effective = current_state.get("effective_prompt", "")
    original_user = current_state.get("original_user_prompt", "")
    if current_effective != original_user: return True

    # If none differ, return False
    return False
# ================================== _compare_settings() end ==================================


      
# ================================== _build_caption_parts(): Builds caption lines (with index and short alias) ==================================
def _build_caption_parts(
    state: Dict[str, Any],
    api_text_result: Optional[str],
    context: ContextTypes.DEFAULT_TYPE
) -> List[str]:
    """
    Builds caption components. Always uses '!' command prefix.
    Handles awaiting_prompt_change state. Displays indices in <pre> block.
    Uses <pre> block for Type/Style/Artist alignment. Adds newline before command.
    Shows full Russian artist alias in <pre> block, short alias in command line.
    Removes 'Команда:' label. Uses configurable default for showing LLM text.
    """
    caption_parts = []
    is_awaiting_prompt = state.get("awaiting_prompt_change", False)
    prompt_to_display = state.get("effective_prompt", state.get("original_user_prompt", ""))
    selected_type_data = state.get("selected_type_data")
    selected_style_data = state.get("selected_style_data")
    selected_artist_data = state.get("selected_artist_data")
    selected_ar = state.get("selected_ar")
    selected_type_index = state.get("selected_type_index")
    selected_style_abs_index = state.get("selected_style_abs_index")
    selected_artist_abs_index = state.get("selected_artist_abs_index")
    p_type_alias = selected_type_data.get('alias') if selected_type_data else None
    p_style_alias = selected_style_data.get('alias') if selected_style_data else None
    p_artist_alias_full = selected_artist_data.get('alias') if selected_artist_data else None
    p_artist_alias_short = selected_artist_data.get('alias_short') if selected_artist_data else None # Get short alias

    # 1. LLM Text (only if not awaiting prompt)
    show_llm_text = context.chat_data.get(CHAT_DATA_KEY_DISPLAY_LLM_TEXT, config.DEFAULT_DISPLAY_LLM_TEXT_BOOL)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not is_awaiting_prompt and show_llm_text and api_text_result:
        processed_llm_text = ""
        raw_text_input = api_text_result.strip()
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if raw_text_input:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try: processed_llm_text = convert_basic_markdown_to_html(raw_text_input)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as e: logger.warning(f"Ошибка форматирования LLM: {e}"); processed_llm_text = escape(raw_text_input)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if processed_llm_text: caption_parts.append(processed_llm_text); caption_parts.append("\n\n")

    # 2. Parameters Section within <pre> block
    label_type_raw = "Тип:"; label_style_raw = "Стиль:"; label_artist_raw = "Художник:"
    label_type = label_type_raw; label_style = label_style_raw; label_artist = label_artist_raw
    type_value_html = ""; style_value_html = ""; artist_value_html = ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if p_type_alias and selected_type_index is not None: type_value_html = f"[{selected_type_index}] <b>{escape(str(p_type_alias))}</b>"
    elif p_type_alias: type_value_html = f"<b>{escape(str(p_type_alias))}</b>"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if p_style_alias and selected_style_abs_index is not None: style_value_html = f"[{selected_style_abs_index}] <b>{escape(str(p_style_alias))}</b>"
    elif p_style_alias: style_value_html = f"<b>{escape(str(p_style_alias))}</b>"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if p_artist_alias_full and selected_artist_abs_index is not None: artist_value_html = f"[{selected_artist_abs_index}] <b>{escape(str(p_artist_alias_full))}</b>" # Show full alias here
    elif p_artist_alias_full: artist_value_html = f"<b>{escape(str(p_artist_alias_full))}</b>"
    type_line_safe = f"{escape(label_type)} {type_value_html}" if type_value_html else ""
    style_line_safe = f"{escape(label_style)} {style_value_html}" if style_value_html else ""
    artist_line_safe = f"{escape(label_artist)} {artist_value_html}" if artist_value_html else ""
    params_lines = "\n".join(filter(None, [type_line_safe, style_line_safe, artist_line_safe]))
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if params_lines: params_block = f"<pre>{params_lines}</pre>"; caption_parts.append(params_block)

    # 3. Command Line
    prompt_value_html = ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if is_awaiting_prompt:
        prompt_value_html = "<pre>Пожалуйста, отправьте желаемые изменения ответом на это сообщение.</pre>"
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if params_lines: caption_parts.append("\n") # Add newline if params exist
        caption_parts.append(f"\n{prompt_value_html}")
    else:
        command_prefix = "!"
        prompt_text_part = str(prompt_to_display or "").strip()
        arg_parts_display = []
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_type_data and selected_type_index is not None: arg_parts_display.append(f"-t{selected_type_index}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_style_data and selected_style_abs_index is not None: arg_parts_display.append(f"-s{selected_style_abs_index}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_artist_data and selected_artist_abs_index is not None:
            # Use SHORT alias for command line if available, else index
            artist_cmd_val = p_artist_alias_short if p_artist_alias_short else selected_artist_abs_index
            arg_parts_display.append(f"-a {artist_cmd_val}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_ar: arg_parts_display.append(f"--ar {selected_ar}")
        current_args_string = " ".join(arg_parts_display)
        display_prompt_line = prompt_text_part
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if arg_parts_display:
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if prompt_text_part: display_prompt_line += " "
             display_prompt_line += current_args_string
        escaped_display_prompt = escape(display_prompt_line) if display_prompt_line else ""
        command_separator = " " if escaped_display_prompt else ""
        prompt_value_html = f"<code>{command_prefix}{command_separator}{escaped_display_prompt}</code>"
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if params_lines: caption_parts.append("\n")
        caption_parts.append(f"\n{prompt_value_html}")
    return caption_parts
# ================================== _build_caption_parts() end ==================================

    


# ================= Sends image generation result, including inline keyboard and storing original args =====================
async def send_image_generation_response(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    reply_to_message_id: Optional[int],
    processing_msg_id: Optional[int],
    api_text_result: Optional[str],
    api_image_bytes: Optional[bytes],
    api_error_message: Optional[str],
    original_user_prompt: str,
    resolved_settings_tuple: Tuple[Dict[str, Any], int | None, int | None, int | None],
    prompt_used_for_api: Optional[str] = None,
    original_parsed_settings_data: Optional[Dict[str, Any]] = None,
    base_image_file_id_for_regen: Optional[str] = None, # For single user-uploaded base
    source_image_file_id_1_for_regen: Optional[str] = None, # For combined image source 1
    source_image_file_id_2_for_regen: Optional[str] = None  # For combined image source 2
):
    sent_message = None
    final_caption_or_text = ""
    message_to_delete_id = processing_msg_id
    keyboard = None
    generated_file_id = None # To store the file_id of the sent photo

    # Unpack resolved settings
    resolved_settings, type_idx, style_idx, artist_idx = resolved_settings_tuple

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if message_to_delete_id:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_to_delete_id, text="Отправка результата...")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as edit_err: logger.warning(f"Не удалось отредактировать сообщение о обработке: {edit_err}")

    # Build the initial state for the NEW message
    initial_state = {
        "original_user_prompt": original_user_prompt, # The user's initial typed prompt
        "effective_prompt": original_user_prompt, # Starts same as original
        # Store RESOLVED settings for display and potential "Apply" baseline
        "selected_type_data": resolved_settings.get("type_data"),
        "selected_style_data": resolved_settings.get("style_data"),
        "selected_artist_data": resolved_settings.get("artist_data"),
        "selected_ar": resolved_settings.get("ar"),
        "selected_type_index": type_idx,
        "selected_style_abs_index": style_idx,
        "selected_artist_abs_index": artist_idx,
        # UI state
        "settings_visible": False, "ar_select_visible": False, "type_select_visible": False,
        "style_select_visible": False, "artist_select_visible": False, "prompt_action_visible": False,
        "awaiting_prompt_change": False,
        "type_page": 0, "style_page": 0, "artist_page": 0,
        # API call details for this message
        "last_api_text_result": api_text_result,
        "api_call_prompt": prompt_used_for_api,
        "api_call_settings": resolved_settings.copy(), # Store the RESOLVED settings used for THIS call
        # Store ORIGINAL PARSED settings for Re-Gen
        "original_parsed_settings": original_parsed_settings_data,
        # Placeholder for file_id
        "generated_file_id": None,
        "base_image_file_id_for_regen": base_image_file_id_for_regen, # For single base image
        "source_image_file_id_1_for_regen": source_image_file_id_1_for_regen, # <<< ADD THIS
        "source_image_file_id_2_for_regen": source_image_file_id_2_for_regen, # <<< ADD THIS
        "is_combination_result": bool(source_image_file_id_1_for_regen and source_image_file_id_2_for_regen)
    }
    logger.debug(f"Initial state built in sender (before file_id): {initial_state}")

    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if api_error_message:
            logger.warning(f"API вернул ошибку для чата {chat_id}: {api_error_message}")
            error_prefix = "⚠️ Ошибка API:"; escaped_api_error = escape(api_error_message)
            # Build caption based on the state WE BUILT, even on error, showing intended settings
            caption_parts = _build_caption_parts(initial_state, None, context)
            error_body = f"{error_prefix}\n<pre>{escaped_api_error}</pre>"
            final_caption_or_text = f"{error_body}\n\n{''.join(caption_parts)}"; parse_mode = ParseMode.HTML
            sent_message = await context.bot.send_message(
                chat_id=chat_id, text=final_caption_or_text[:4096], parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id, disable_web_page_preview=True
            )
            logger.info(f"Отправлено сообщение об ошибке API для чата {chat_id}.")
            # Clear last generation on error
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION]

        elif api_image_bytes:
            # Build caption based on the state WE BUILT
            caption_parts = _build_caption_parts(initial_state, api_text_result, context)
            final_caption_or_text = "".join(caption_parts); parse_mode = ParseMode.HTML
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if len(final_caption_or_text) > 1024: final_caption_or_text = final_caption_or_text[:1020] + "..."
            keyboard = generate_main_keyboard(initial_state, msg_id=0) # Temp ID
            sent_message = await context.bot.send_photo(
                chat_id=chat_id, photo=InputFile(io.BytesIO(api_image_bytes), "gemini_image.png"),
                caption=final_caption_or_text, parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id, reply_markup=keyboard
            )
            logger.info(f"Отправлено изображение {sent_message.message_id} с клавиатурой.")

            # Reminder: Use new line, not semicolon, for the following block/statement.
            if sent_message and sent_message.photo:
                best_photo: PhotoSize = max(sent_message.photo, key=lambda p: p.width * p.height)
                generated_file_id = best_photo.file_id
                initial_state["generated_file_id"] = generated_file_id # Add file_id to state
                logger.debug(f"Stored generated_file_id in state: {generated_file_id}")

                context.chat_data[CHAT_DATA_KEY_LAST_GENERATION] = {'chat_id': chat_id, 'message_id': sent_message.message_id}
                logger.info(f"Updated last generation tracker for chat {chat_id} to msg {sent_message.message_id}")

                keyboard_with_id = generate_main_keyboard(initial_state, sent_message.message_id)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=sent_message.message_id, reply_markup=keyboard_with_id)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except Exception as e_kbd: logger.error(f"Не удалось обновить клавиатуру {sent_message.message_id}: {e_kbd}")

                state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{chat_id}:{sent_message.message_id}"
                context.application.bot_data[state_key] = initial_state
                logger.debug(f"Сохранено состояние для {state_key} (включая orig_parsed_settings)")
            else:
                logger.error("Не удалось получить sent_message или photo details!")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION]

        elif api_text_result: # Text only response
            logger.info(f"API изображений вернул только текст для чата {chat_id}.")
            caption_parts = _build_caption_parts(initial_state, api_text_result, context) # Build caption anyway
            info_prefix = "\n\nℹ️ Ответ API (только текст):"; final_caption_or_text = "".join(caption_parts)
            show_llm_text = context.chat_data.get(CHAT_DATA_KEY_DISPLAY_LLM_TEXT, config.DEFAULT_DISPLAY_LLM_TEXT_BOOL)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not show_llm_text: # If LLM text hidden by default, add the raw text here
                final_caption_or_text = f"{info_prefix}\n{escape(api_text_result.strip())}\n\n{final_caption_or_text}"
            else: # If LLM text shown by default (already included), just add prefix before params
                final_caption_or_text = f"{info_prefix}\n\n{final_caption_or_text}"

            parse_mode = ParseMode.HTML
            sent_message = await context.bot.send_message(
                chat_id=chat_id, text=final_caption_or_text[:4096], parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id, disable_web_page_preview=True
            )
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION]

        else: # Empty response
            logger.error(f"send_image_generation_response: От API не получено ни ошибки, ни контента (чат {chat_id}).")
            caption_parts = _build_caption_parts(initial_state, None, context) # Build caption anyway
            error_msg_text = f"Извините, не удалось сгенерировать ответ (пустой ответ от API)."
            final_caption_or_text = f"{error_msg_text}\n\n{''.join(caption_parts)}"
            await context.bot.send_message(chat_id=chat_id, text=final_caption_or_text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_message_id, disable_web_page_preview=True)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION]

    # Error handling remains the same...
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except TelegramError as e:
        logger.error(f"Ошибка Telegram при отправке ответа генерации (чат {chat_id}): {e}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION] # Clear tracker on error
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "parse error" in str(e).lower() or "Can't parse entities" in str(e):
             logger.error(f"ОШИБКА ПАРСИНГА! Контент: {final_caption_or_text[:500]}...")
             # Reminder: Use new line, not semicolon, for the following block/statement.
             try:
                  fallback_text = "Произошла ошибка отображения ответа."
                  # Reminder: Use new line, not semicolon, for the following block/statement.
                  if api_image_bytes and not api_error_message:
                      # Reminder: Use new line, not semicolon, for the following block/statement.
                      try: await context.bot.send_photo(chat_id=chat_id, photo=InputFile(io.BytesIO(api_image_bytes),"gemini_fallback.png"), reply_to_message_id=reply_to_message_id)
                      # Reminder: Use new line, not semicolon, for the following block/statement.
                      except Exception as photo_err: logger.error(f"Не удалось отправить фото fallback: {photo_err}")
                  await context.bot.send_message(chat_id=chat_id, text=fallback_text, reply_to_message_id=reply_to_message_id)
             # Reminder: Use new line, not semicolon, for the following block/statement.
             except Exception as fallback_err: logger.error(f"Не удалось отправить fallback сообщение: {fallback_err}")
        elif "message is too long" not in str(e).lower():
             # Reminder: Use new line, not semicolon, for the following block/statement.
             try: await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при отправке ответа.", reply_to_message_id=reply_to_message_id)
             # Reminder: Use new line, not semicolon, for the following block/statement.
             except Exception: pass
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
         logger.exception(f"Неожиданная ошибка в send_image_generation_response (чат {chat_id}): {e}")
         # Reminder: Use new line, not semicolon, for the following block/statement.
         if CHAT_DATA_KEY_LAST_GENERATION in context.chat_data: del context.chat_data[CHAT_DATA_KEY_LAST_GENERATION] # Clear tracker on error
         # Reminder: Use new line, not semicolon, for the following block/statement.
         try: await context.bot.send_message(chat_id=chat_id, text="❌ Внутренняя ошибка.", reply_to_message_id=reply_to_message_id)
         # Reminder: Use new line, not semicolon, for the following block/statement.
         except Exception: pass
    finally:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if message_to_delete_id: await delete_message_safely(context, chat_id, message_to_delete_id)
# ================= send_image_generation_response() end =====================


# ================= Fetches the current state, rebuilds caption and keyboard, and edits the message =====================
async def update_caption_and_keyboard(context: ContextTypes.DEFAULT_TYPE, chat_id: int, msg_id: int):
    state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{chat_id}:{msg_id}"
    state = context.application.bot_data.get(state_key)
    if not state:
        logger.warning(f"Состояние для {state_key} не найдено. Невозможно обновить.")
        try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
        except Exception: pass
        return

    keyboard = None; ar_select_visible = state.get("ar_select_visible", False); type_select_visible = state.get("type_select_visible", False)
    style_select_visible = state.get("style_select_visible", False); artist_select_visible = state.get("artist_select_visible", False)
    prompt_action_visible = state.get("prompt_action_visible", False)

    if ar_select_visible: keyboard = generate_ar_selection_keyboard(state, msg_id)
    elif type_select_visible: keyboard = generate_type_selection_keyboard(state, msg_id)
    elif style_select_visible: keyboard = generate_style_selection_keyboard(state, msg_id)
    elif artist_select_visible: keyboard = generate_artist_selection_keyboard(state, msg_id)
    elif prompt_action_visible: keyboard = generate_prompt_action_keyboard(state, msg_id)
    else: keyboard = generate_main_keyboard(state, msg_id)

    api_text_result = state.get("last_api_text_result")
    caption_parts = _build_caption_parts(state, api_text_result, context)
    new_caption = "".join(caption_parts); parse_mode = ParseMode.HTML
    if len(new_caption) > 1024: new_caption = new_caption[:1020] + "..."; logger.warning(f"Обновленная подпись усечена (msg {msg_id}).")

    try:
        await context.bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=new_caption, parse_mode=parse_mode, reply_markup=keyboard)
        logger.debug(f"Сообщение {msg_id} обновлено.")
    except BadRequest as e:
        if "Message is not modified" in str(e): logger.debug(f"Сообщение {msg_id} не изменено.")
        elif "message can't be edited" in str(e).lower(): logger.warning(f"Сообщение {msg_id} больше не может быть отредактировано.")
        else: logger.error(f"Ошибка BadRequest при обновлении {msg_id}: {e}"); logger.error(f"ОШИБКА ПАРСИНГА! Контент: {new_caption[:500]}...")
    except TelegramError as e: logger.error(f"Ошибка Telegram при обновлении {msg_id}: {e}")
    except Exception as e: logger.exception(f"Неожиданная ошибка при обновлении {msg_id}: {e}")
# ================= update_caption_and_keyboard() end =====================


# ui/messages.py end