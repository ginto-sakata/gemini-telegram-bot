# handlers/callbacks.py
# -*- coding: utf-8 -*-
"""
Handles callback queries from inline keyboards on image messages.
Introduces Prompt action row. Updates button logic and layout.
Preserves style when type is changed. Handles prompt change requests.
Calls appropriate generation/editing function based on action.
"""

import logging
import random
import asyncio
from typing import Optional, Dict, Any
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from utils.auth import is_authorized
from utils.telegram_helpers import delete_message_safely
from utils.cache import get_cached_image_bytes
from config import (
    IMAGE_STATE_CACHE_KEY_PREFIX, USER_DATA_KEY_PROMPT_EDIT_TARGET,
    TYPE_INDEX_TO_DATA, STYLE_ABSOLUTE_INDEX_TO_DATA, ARTIST_ABSOLUTE_INDEX_TO_DATA,
    MAIN_TYPES_DATA, ALL_STYLES_DATA, ALL_ARTISTS_DATA, STYLE_NAME_TO_DATA,
    ARTIST_NAME_TO_DATA, STYLE_NAME_TO_ABSOLUTE_INDEX, ARTIST_NAME_TO_ABSOLUTE_INDEX
)
import config
from api.gemini_api import enhance_prompt_with_gemini
from ui.messages import update_caption_and_keyboard
from handlers.image_gen import _initiate_image_generation, _initiate_image_editing
from utils.prompt_helpers import get_style_detail
from ui.keyboards import ITEMS_PER_PAGE_TYPE, ITEMS_PER_PAGE_STYLE, ITEMS_PER_PAGE_ARTIST

logger = logging.getLogger(__name__)

# ================================== parse_callback_data(): Parses callback data string ==================================
def parse_callback_data(data: str) -> Optional[Dict[str, Any]]:
    parts = str(data).split('|', 2)
    action = parts[0]
    value = parts[1] if len(parts) > 1 else None
    if not parts:
        return None
    return {"action": action, "value": value}
# ================================== parse_callback_data() end ==================================


# ================================== _hide_all_selectors(): Helper to hide all selectors ==================================
def _hide_all_selectors(state: dict):
    state["ar_select_visible"] = False
    state["type_select_visible"] = False
    state["style_select_visible"] = False
    state["artist_select_visible"] = False
    state["prompt_action_visible"] = False
    state["awaiting_prompt_change"] = False
    state["type_page"] = 0
    state["style_page"] = 0
    state["artist_page"] = 0
# ================================== _hide_all_selectors() end ==================================


# ================================== _handle_toggle_settings(): Toggles settings visibility ==================================
def _handle_toggle_settings(state: dict):
    state["settings_visible"] = not state.get("settings_visible", False)
    _hide_all_selectors(state)
    logger.debug(f"Toggled settings visibility: {state['settings_visible']}")
# ================================== _handle_toggle_settings() end ==================================


# ================================== _handle_show_ar(): Shows AR selection ==================================
def _handle_show_ar(state: dict):
    _hide_all_selectors(state)
    state["ar_select_visible"] = True
    if not state.get("settings_visible"): state["settings_visible"] = True
    logger.debug(f"Showing AR selection")
# ================================== _handle_show_ar() end ==================================


# ================================== _handle_hide_ar(): Hides AR selection ==================================
def _handle_hide_ar(state: dict):
    state["ar_select_visible"] = False
    logger.debug("Hiding AR selection.")
# ================================== _handle_hide_ar() end ==================================


# ================================== _handle_set_ar(): Sets or clears aspect ratio ==================================
def _handle_set_ar(state: dict, value: Optional[str]):
    if value == "reset":
        state["selected_ar"] = None
        logger.info("AR cleared.")
    elif value and value in ["1:1", "4:3", "16:9", "3:4", "9:16"]:
        state["selected_ar"] = value
        logger.info(f"AR set: {value}")
    else:
        logger.warning(f"Invalid AR value: {value}")
    _handle_hide_ar(state)
# ================================== _handle_set_ar() end ==================================


# ================================== _handle_show_type(): Shows Type selection ==================================
def _handle_show_type(state: dict):
    _hide_all_selectors(state)
    state["type_select_visible"] = True
    state["type_page"] = 0
    if not state.get("settings_visible"): state["settings_visible"] = True
    logger.debug("Showing Type selection.")
# ================================== _handle_show_type() end ==================================


# ================================== _handle_hide_type(): Hides Type selection ==================================
def _handle_hide_type(state: dict):
    state["type_select_visible"] = False
    state["type_page"] = 0
    logger.debug("Hiding Type selection.")
# ================================== _handle_hide_type() end ==================================


# ================================== _handle_clear_type(): Clears type and style ==================================
def _handle_clear_type(state: dict):
    state["selected_type_data"] = None
    state["selected_type_index"] = None
    state["selected_style_data"] = None
    state["selected_style_abs_index"] = None
    _handle_hide_type(state)
    logger.info("Type and Style cleared.")
# ================================== _handle_clear_type() end ==================================


# ================================== _set_new_type(): Helper to set type, random style if none ==================================
def _set_new_type(state: dict, type_data: Optional[Dict]):
    state["selected_type_data"] = type_data
    state["selected_type_index"] = None
    style_already_selected = state.get("selected_style_data") is not None
    if type_data:
        type_id = type_data.get('id')
        found_index = next((idx for idx, data in TYPE_INDEX_TO_DATA.items() if data['id'] == type_id), None)
        state["selected_type_index"] = found_index
        logger.info(f"Type set: '{type_data.get('alias')}' #{found_index}.")
        if not style_already_selected:
            type_name = type_data.get('name')
            if type_name:
                type_config = config.TYPE_NAME_TO_DATA.get(type_name.lower())
                if type_config and type_config.get('style_keys'):
                    random_style_name = get_style_detail(type_name)
                    random_style_data = STYLE_NAME_TO_DATA.get(random_style_name.lower())
                    if random_style_data:
                        state["selected_style_data"] = random_style_data
                        state["selected_style_abs_index"] = STYLE_NAME_TO_ABSOLUTE_INDEX.get(random_style_data.get('name','').lower())
                        logger.info(f"Setting random style: '{random_style_data.get('alias')}' #{state['selected_style_abs_index']}")
                    else:
                        logger.warning(f"Cannot find random style data '{random_style_name}'.")
                else:
                    logger.info(f"Type '{type_name}' has no styles.")
            else:
                logger.warning("Type has no name.")
        else:
            logger.info("Preserving existing style.")
    else:
        state["selected_style_data"] = None
        state["selected_style_abs_index"] = None
        logger.info("Type cleared.")
# ================================== _set_new_type() end ==================================


# ================================== _handle_set_type(): Sets type from index ==================================
def _handle_set_type(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for set_type")
        return
    try:
        type_index = int(value_str)
        type_data = TYPE_INDEX_TO_DATA.get(type_index)
    except (ValueError, TypeError):
        logger.error(f"Invalid value for set_type: {value_str}")
        return
    if type_data:
        _set_new_type(state, type_data)
    else:
        logger.warning(f"Invalid type index: {type_index}")
    _handle_hide_type(state)
# ================================== _handle_set_type() end ==================================


# ================================== _handle_rnd_type(): Selects random type ==================================
def _handle_rnd_type(state: dict):
    if MAIN_TYPES_DATA:
        random_type_data = random.choice(MAIN_TYPES_DATA)
        _set_new_type(state, random_type_data)
        logger.info("Random Type selected.")
    else:
        logger.error("Cannot select random type: MAIN_TYPES_DATA empty.")
    state["type_page"] = 0
# ================================== _handle_rnd_type() end ==================================


# ================================== _handle_type_page(): Handles type pagination ==================================
def _handle_type_page(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for type_page")
        return
    try:
        page_num = int(value_str)
        total_pages = (len(MAIN_TYPES_DATA) + ITEMS_PER_PAGE_TYPE - 1) // ITEMS_PER_PAGE_TYPE
    except (ValueError, TypeError):
        logger.error(f"Invalid value for type_page: {value_str}")
        return
    if 0 <= page_num < total_pages:
        state["type_page"] = page_num
        logger.debug(f"Set type page: {page_num}")
    else:
        logger.warning(f"Invalid type page: {page_num}")
# ================================== _handle_type_page() end ==================================


# ================================== _handle_show_style(): Shows Style selection ==================================
def _handle_show_style(state: dict):
    _hide_all_selectors(state)
    state["style_select_visible"] = True
    state["style_page"] = 0
    if not state.get("settings_visible"): state["settings_visible"] = True
    logger.debug("Showing Style selection.")
# ================================== _handle_show_style() end ==================================


# ================================== _handle_hide_style(): Hides Style selection ==================================
def _handle_hide_style(state: dict):
    state["style_select_visible"] = False
    state["style_page"] = 0
    logger.debug("Hiding Style selection.")
# ================================== _handle_hide_style() end ==================================


# ================================== _handle_clear_style(): Clears style ==================================
def _handle_clear_style(state: dict):
    state["selected_style_data"] = None
    state["selected_style_abs_index"] = None
    _handle_hide_style(state)
    logger.info("Style cleared.")
# ================================== _handle_clear_style() end ==================================


# ================================== _handle_set_style(): Sets style from absolute index ==================================
def _handle_set_style(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for set_style")
        return
    try:
        style_abs_index = int(value_str)
        style_data = STYLE_ABSOLUTE_INDEX_TO_DATA.get(style_abs_index)
    except (ValueError, TypeError):
        logger.error(f"Invalid value for set_style: {value_str}")
        return
    if style_data:
        state["selected_style_data"] = style_data
        state["selected_style_abs_index"] = style_abs_index
        logger.info(f"Style set: '{style_data.get('alias')}' #{style_abs_index}")
    else:
        logger.warning(f"Invalid style index: {style_abs_index}")
    _handle_hide_style(state)
# ================================== _handle_set_style() end ==================================


# ================================== _handle_rnd_style(): Selects random style ==================================
def _handle_rnd_style(state: dict):
    chosen_style_data = None
    current_type_data = state.get("selected_type_data")
    if current_type_data:
        type_name = current_type_data.get("name")
        type_config = config.TYPE_NAME_TO_DATA.get(type_name.lower()) if type_name else None
        if type_config and type_config.get('style_keys'):
            random_style_name = get_style_detail(type_name)
            chosen_style_data = STYLE_NAME_TO_DATA.get(random_style_name.lower())
            if chosen_style_data:
                logger.info(f"Random style for type '{current_type_data.get('alias')}': '{chosen_style_data.get('alias')}'")
            else:
                logger.warning(f"Cannot find random style data '{random_style_name}'. Falling back.")
                chosen_style_data = None
        else:
            logger.info(f"Type '{type_name}' has no styles. Falling back.")
    else:
        logger.info("No type selected. Choosing global random style.")
    if not chosen_style_data and ALL_STYLES_DATA:
        chosen_style_data = random.choice(ALL_STYLES_DATA)
        logger.info(f"Random style (global): '{chosen_style_data.get('alias')}'")
    if chosen_style_data:
        state["selected_style_data"] = chosen_style_data
        state["selected_style_abs_index"] = STYLE_NAME_TO_ABSOLUTE_INDEX.get(chosen_style_data.get('name','').lower())
    else:
        logger.error("Cannot select random style: No data.")
    state["style_page"] = 0
    logger.info("Random Style selected.")
# ================================== _handle_rnd_style() end ==================================


# ================================== _handle_style_page(): Handles style pagination ==================================
def _handle_style_page(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for style_page")
        return
    try:
        page_num = int(value_str)
        styles_to_paginate = []
        current_type_data = state.get("selected_type_data")
    except (ValueError, TypeError):
        logger.error(f"Invalid value for style_page: {value_str}")
        return
    if current_type_data:
        relevant_keys = current_type_data.get('style_keys', [])
        seen_names = set()
        for key in relevant_keys:
            if key == 'artists': continue
            style_list = config.STYLE_LISTS.get(key, [])
            if isinstance(style_list, list):
                for style_data in style_list:
                    if isinstance(style_data, dict) and 'name' in style_data and 'alias' in style_data:
                        name_lower = style_data['name'].lower()
                        if name_lower not in seen_names:
                            styles_to_paginate.append(style_data)
                            seen_names.add(name_lower)
    else:
        styles_to_paginate = ALL_STYLES_DATA
    total_pages = (len(styles_to_paginate) + ITEMS_PER_PAGE_STYLE - 1) // ITEMS_PER_PAGE_STYLE
    if 0 <= page_num < total_pages:
        state["style_page"] = page_num
        logger.debug(f"Set style page: {page_num}")
    else:
        logger.warning(f"Invalid style page: {page_num}")
# ================================== _handle_style_page() end ==================================


# ================================== _handle_show_artist(): Shows Artist selection ==================================
def _handle_show_artist(state: dict):
    _hide_all_selectors(state)
    state["artist_select_visible"] = True
    state["artist_page"] = 0
    if not state.get("settings_visible"): state["settings_visible"] = True
    logger.debug("Showing Artist selection.")
# ================================== _handle_show_artist() end ==================================


# ================================== _handle_hide_artist(): Hides Artist selection ==================================
def _handle_hide_artist(state: dict):
    state["artist_select_visible"] = False
    state["artist_page"] = 0
    logger.debug("Hiding Artist selection.")
# ================================== _handle_hide_artist() end ==================================


# ================================== _handle_clear_artist(): Clears artist ==================================
def _handle_clear_artist(state: dict):
    state["selected_artist_data"] = None
    state["selected_artist_abs_index"] = None
    _handle_hide_artist(state)
    logger.info("Artist cleared.")
# ================================== _handle_clear_artist() end ==================================


# ================================== _handle_set_artist(): Sets artist from absolute index ==================================
def _handle_set_artist(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for set_artist")
        return
    try:
        artist_abs_index = int(value_str)
        artist_data = ARTIST_ABSOLUTE_INDEX_TO_DATA.get(artist_abs_index)
    except (ValueError, TypeError):
        logger.error(f"Invalid value for set_artist: {value_str}")
        return
    if artist_data:
        state["selected_artist_data"] = artist_data
        state["selected_artist_abs_index"] = artist_abs_index
        logger.info(f"Artist set: '{artist_data.get('alias')}' #{artist_abs_index}")
    else:
        logger.warning(f"Invalid artist index: {artist_abs_index}")
    _handle_hide_artist(state)
# ================================== _handle_set_artist() end ==================================


# ================================== _handle_rnd_artist(): Selects random artist ==================================
def _handle_rnd_artist(state: dict):
    if ALL_ARTISTS_DATA:
        chosen_artist_data = random.choice(ALL_ARTISTS_DATA)
        logger.info(f"Random artist: '{chosen_artist_data.get('alias')}'")
        state["selected_artist_data"] = chosen_artist_data
        state["selected_artist_abs_index"] = ARTIST_NAME_TO_ABSOLUTE_INDEX.get(chosen_artist_data.get('name','').lower())
    else:
        logger.error("Cannot select random artist: No data.")
    state["artist_page"] = 0
    logger.info("Random Artist selected.")
# ================================== _handle_rnd_artist() end ==================================


# ================================== _handle_artist_page(): Handles artist pagination ==================================
def _handle_artist_page(state: dict, value_str: Optional[str]):
    if value_str is None:
        logger.error("None value for artist_page")
        return
    try:
        page_num = int(value_str)
        artists_to_paginate = ALL_ARTISTS_DATA
        total_pages = (len(artists_to_paginate) + ITEMS_PER_PAGE_ARTIST - 1) // ITEMS_PER_PAGE_ARTIST
    except (ValueError, TypeError):
        logger.error(f"Invalid value for artist_page: {value_str}")
        return
    if 0 <= page_num < total_pages:
        state["artist_page"] = page_num
        logger.debug(f"Set artist page: {page_num}")
    else:
        logger.warning(f"Invalid artist page: {page_num}")
# ================================== _handle_artist_page() end ==================================


# ================================== _handle_show_prompt(): Shows prompt action row ==================================
def _handle_show_prompt(state: dict):
    _hide_all_selectors(state)
    state["prompt_action_visible"] = True
    if not state.get("settings_visible"): state["settings_visible"] = True
    logger.debug("Showing Prompt actions.")
# ================================== _handle_show_prompt() end ==================================


# ================================== _handle_hide_prompt(): Hides prompt action row ==================================
def _handle_hide_prompt(state: dict):
    state["prompt_action_visible"] = False
    state["awaiting_prompt_change"] = False
    logger.debug("Hiding Prompt actions.")
# ================================== _handle_hide_prompt() end ==================================


# ================================== _handle_reset_prompt(): Resets effective prompt to original ==================================
def _handle_reset_prompt(state: dict):
    original_prompt = state.get("original_user_prompt", "")
    state["effective_prompt"] = original_prompt
    _handle_hide_prompt(state)
    logger.info("Effective prompt reset.")
# ================================== _handle_reset_prompt() end ==================================


# ================================== _handle_change_prompt_request(): Sets flag to await prompt reply ==================================
async def _handle_change_prompt_request(state: dict, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    state["awaiting_prompt_change"] = True
    context.user_data[USER_DATA_KEY_PROMPT_EDIT_TARGET] = {'chat_id': chat_id, 'message_id': msg_id}
    logger.info(f"User {user_id} req prompt change for {msg_id}. Awaiting reply.")
    try:
        await query.answer("Пожалуйста, отправьте новый текст промпта.")
        return True
    except Exception as e_ans:
        logger.warning(f"Error answering change_prompt_req: {e_ans}")
        return False
# ================================== _handle_change_prompt_request() end ==================================


# ================================== _handle_enhance(): Enhances prompt via LLM ==================================
async def _handle_enhance(state: dict, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery):
    await query.answer("✨ Улучшаю запрос...")
    original_prompt = state.get("original_user_prompt", "")
    current_type = state.get("selected_type_data")
    current_style = state.get("selected_style_data")
    enhanced_prompt, error_msg = await enhance_prompt_with_gemini(original_prompt, current_type, current_style)
    if error_msg:
        logger.error(f"Enhance error: {error_msg}");
        try:
            await query.answer(f"⚠️ Ошибка: {error_msg[:150]}", show_alert=True)
        except Exception:
            pass
        return False
    if enhanced_prompt:
        state["effective_prompt"] = enhanced_prompt
        logger.info("Prompt enhanced.");
        try:
            await query.answer("✅ Промпт улучшен!")
        except Exception:
            pass
        return True
    else:
        logger.warning("Enhance returned no result.");
        try:
            await query.answer("ℹ️ LLM не вернул результат.", show_alert=True)
        except Exception:
            pass
        return False
# ================================== _handle_enhance() end ==================================


# ================================== _handle_regen(): Handles Regenerate button (uses original parsed args) ==================================
async def _handle_regen(state: dict, update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery) -> bool:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await query.answer("🔄 Генерирую заново...")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e_ans:
        logger.warning(f"Error answering regen query: {e_ans}")

    # --- Use ORIGINAL parsed settings for Re-Gen ---
    original_parsed_settings = state.get("original_parsed_settings")
    original_prompt_for_regen = state.get("original_user_prompt", "")
    original_prompt_for_display = state.get("original_user_prompt", "") # Keep original for display

    # Default to None for image bytes
    base_image_bytes_for_api = None
    user_image_bytes_for_api = None # For the second image in a combination

    # For passing original file_ids back to state if this regen results in a new message
    # (especially if it's a single user-uploaded image being re-processed)
    single_base_file_id_to_pass = state.get("base_image_file_id_for_regen")
    source_1_file_id_to_pass = state.get("source_image_file_id_1_for_regen")
    source_2_file_id_to_pass = state.get("source_image_file_id_2_for_regen")

    is_re_combination = state.get("is_combination_result", False) and \
                        state.get("source_image_file_id_1_for_regen") and \
                        state.get("source_image_file_id_2_for_regen")

    if is_re_combination:
        logger.info("Re-Gen: Detected re-combination request.")
        file_id_1 = state["source_image_file_id_1_for_regen"]
        file_id_2 = state["source_image_file_id_2_for_regen"]
        prompt_for_re_combination = state.get("api_call_prompt", DEFAULT_COMBINE_PROMPT_TEXT) # Use original combine prompt
        original_prompt_for_regen = prompt_for_re_combination # Use this as the prompt for API
        original_prompt_for_display = state.get("original_user_prompt", "") # Display original user prompt if any

        dl_status_msg_combo_regen = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            dl_status_msg_combo_regen = await context.bot.send_message(query.message.chat.id, "⏳ Загрузка исходных фото для повторной комбинации...")
            img1_bytes, img2_bytes = await asyncio.gather(
                get_cached_image_bytes(context, file_id_1, query.message.chat),
                get_cached_image_bytes(context, file_id_2, query.message.chat),
                return_exceptions=True
            )
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if dl_status_msg_combo_regen: await delete_message_safely(context, dl_status_msg_combo_regen.chat_id, dl_status_msg_combo_regen.message_id)

            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(img1_bytes, Exception) or not img1_bytes:
                logger.error(f"Re-Gen Combo: Failed to download image 1 ({file_id_1}): {img1_bytes}")
                await query.answer("⚠️ Ошибка: не удалось загрузить первое фото для комбинации.", show_alert=True)
                return False # Stop processing
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(img2_bytes, Exception) or not img2_bytes:
                logger.error(f"Re-Gen Combo: Failed to download image 2 ({file_id_2}): {img2_bytes}")
                await query.answer("⚠️ Ошибка: не удалось загрузить второе фото для комбинации.", show_alert=True)
                return False # Stop processing
            
            base_image_bytes_for_api = img1_bytes
            user_image_bytes_for_api = img2_bytes
            parsed_settings_for_initiate = {"type": None, "style": None, "artist": None, "ar": None} # No specific settings for combine
            single_base_file_id_to_pass = None # Clear this as it's a combo
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e_dl_combo_regen:
            logger.error(f"Re-Gen Combo: Error downloading original images: {e_dl_combo_regen}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if dl_status_msg_combo_regen: await delete_message_safely(context, dl_status_msg_combo_regen.chat_id, dl_status_msg_combo_regen.message_id)
            await query.answer("⚠️ Ошибка при загрузке фото для повторной комбинации.", show_alert=True)
            return False
    elif state.get("base_image_file_id_for_regen"): # Single user-uploaded base image
        file_id_single_base = state["base_image_file_id_for_regen"]
        logger.info(f"Re-Gen: Found original single user-uploaded image file_id to re-use: {file_id_single_base}")
        dl_status_msg_single_regen = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            dl_status_msg_single_regen = await context.bot.send_message(query.message.chat.id, "⏳ Загрузка исходного пользовательского фото для 'Заново'...")
            base_image_bytes_for_api = await get_cached_image_bytes(context, file_id_single_base, query.message.chat)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if dl_status_msg_single_regen: await delete_message_safely(context, dl_status_msg_single_regen.chat_id, dl_status_msg_single_regen.message_id)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not base_image_bytes_for_api:
                logger.error(f"Re-Gen: Failed to download original user-uploaded image {file_id_single_base}")
                await query.answer("⚠️ Ошибка: не удалось загрузить исходное фото для 'Заново'.", show_alert=True)
                return False # Stop processing
            source_1_file_id_to_pass = None # Clear these as it's a single base
            source_2_file_id_to_pass = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e_dl_single_regen:
            logger.error(f"Re-Gen: Error downloading original single user image {file_id_single_base}: {e_dl_single_regen}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if dl_status_msg_single_regen: await delete_message_safely(context, dl_status_msg_single_regen.chat_id, dl_status_msg_single_regen.message_id)
            await query.answer("⚠️ Ошибка при загрузке исходного фото для 'Заново'.", show_alert=True)
            return False
        # Use original parsed settings if available for single image re-gen
        parsed_settings_for_initiate = original_parsed_settings if original_parsed_settings is not None else \
                                   {"type": None, "style": None, "artist": None, "ar": None, "randomize_type": True, "randomize_style": True, "randomize_artist": True, "style_marker": "RANDOM_GLOBAL"}

    else: # No user-uploaded base image, just re-gen from prompt
        logger.info("Re-Gen: No specific base image to re-use. Generating from prompt and original args.")
        parsed_settings_for_initiate = original_parsed_settings if original_parsed_settings is not None else \
                                   {"type": None, "style": None, "artist": None, "ar": None, "randomize_type": True, "randomize_style": True, "randomize_artist": True, "style_marker": "RANDOM_GLOBAL"}
        single_base_file_id_to_pass = None
        source_1_file_id_to_pass = None
        source_2_file_id_to_pass = None


    # Fallback for parsed_settings if somehow still None (should be covered by above)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if parsed_settings_for_initiate is None:
        logger.error(f"Original parsed settings not found in state for msg {query.message.message_id}. Falling back to current effective settings for regen.")
        # This fallback is less ideal as it doesn't preserve original randomness intent
        type_data = state.get("selected_type_data")
        style_data = state.get("selected_style_data")
        artist_data = state.get("selected_artist_data")
        aspect_ratio = state.get("selected_ar")
        parsed_settings_for_initiate = {
             "type": type_data, "style": style_data, "artist": artist_data, "ar": aspect_ratio,
             "randomize_type": False, "randomize_style": False, "randomize_artist": False, "style_marker": None
        }
    
    logger.info(f"Regen triggered. Parsed settings for initiate: {parsed_settings_for_initiate}")
    logger.info(f"Prompt for regen API call: '{original_prompt_for_regen[:100]}...'")


    # --- Initiate Generation ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await _initiate_image_generation(
            update=None, context=context, query=query,
            user_prompt=original_prompt_for_regen,
            parsed_settings_data=parsed_settings_for_initiate,
            original_prompt_for_display=original_prompt_for_display,
            base_image_bytes=base_image_bytes_for_api,       # This will be img1 for combo, or single base, or None
            user_image_bytes=user_image_bytes_for_api,      # This will be img2 for combo, or None
            user_uploaded_base_image_file_id=single_base_file_id_to_pass, # Pass original single upload ID
            source_image_file_id_1_for_passthrough=source_1_file_id_to_pass, # Pass original combo ID 1
            source_image_file_id_2_for_passthrough=source_2_file_id_to_pass  # Pass original combo ID 2
        )
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Error calling generation from _handle_regen: {e}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            chat_id = query.message.chat_id
            reply_to = query.message.reply_to_message.message_id if query.message.reply_to_message else None
            await context.bot.send_message(chat_id, "❌ Ошибка перегенерации.", reply_to_message_id=reply_to)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as send_err:
            logger.error(f"Failed send regen error msg: {send_err}")
        return False # Indicate UI update for original message is not needed

    # --- Reset original message state (remains the same) ---
    original_chat_id = query.message.chat_id
    original_msg_id = query.message.message_id
    original_state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{original_chat_id}:{original_msg_id}"
    original_state = context.application.bot_data.get(original_state_key)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if original_state:
        logger.info(f"Resetting state for original message {original_msg_id} after regen.")
        original_api_settings = original_state.get("api_call_settings", {})
        original_user_prompt_reset = original_state.get("original_user_prompt", "")
        original_state["selected_type_data"] = original_api_settings.get("type_data")
        original_state["selected_style_data"] = original_api_settings.get("style_data")
        original_state["selected_artist_data"] = original_api_settings.get("artist_data")
        original_state["selected_ar"] = original_api_settings.get("ar")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_type_data"]: original_state["selected_type_index"] = next((i for i, d in TYPE_INDEX_TO_DATA.items() if d['id'] == original_state["selected_type_data"]['id']), None)
        else: original_state["selected_type_index"] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_style_data"]: original_state["selected_style_abs_index"] = STYLE_NAME_TO_ABSOLUTE_INDEX.get(original_state["selected_style_data"].get('name','').lower())
        else: original_state["selected_style_abs_index"] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_artist_data"]: original_state["selected_artist_abs_index"] = ARTIST_NAME_TO_ABSOLUTE_INDEX.get(original_state["selected_artist_data"].get('name','').lower())
        else: original_state["selected_artist_abs_index"] = None
        original_state["effective_prompt"] = original_user_prompt_reset
        original_state["settings_visible"] = False
        original_state["ar_select_visible"] = False
        original_state["type_select_visible"] = False
        original_state["style_select_visible"] = False
        original_state["artist_select_visible"] = False
        original_state["prompt_action_visible"] = False
        original_state["awaiting_prompt_change"] = False
        original_state["type_page"] = 0; original_state["style_page"] = 0; original_state["artist_page"] = 0
        context.application.bot_data[original_state_key] = original_state
        logger.debug(f"Saved reset state for {original_state_key}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try: await update_caption_and_keyboard(context, original_chat_id, original_msg_id); logger.info(f"Updated UI for original message {original_msg_id} after reset.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e_update: logger.error(f"Failed to update UI for original message {original_msg_id} after reset: {e_update}")
    else: logger.warning(f"Could not find original state for {original_state_key} to reset.")
    return False # Indicate that the main handler should NOT update the UI again
# ================================== _handle_regen() end ==================================


# ================================== _handle_edit(): Handles Apply button (targeted edit) ==================================
async def _handle_edit(state: dict, update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery) -> bool:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not query or not query.message or not query.message.photo or not query.message.chat:
        logger.warning("Apply called without context.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("⚠️ Ошибка: нет инфо.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return False # No UI update needed if context fails
    original_settings = state.get("api_call_settings")
    original_user_prompt = state.get("original_user_prompt", "")
    original_api_prompt = state.get("api_call_prompt", original_user_prompt)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not original_settings:
        logger.error(f"No original settings found state {query.message.message_id}.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("⚠️ Ошибка: нет исх. настроек.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return False # No UI update needed if state fails
    file_id_to_edit = state.get("generated_file_id")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not file_id_to_edit:
        logger.error(f"No file_id found state {query.message.message_id}.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("⚠️ Ошибка: нет файла.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return False # No UI update needed if state fails
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await query.answer("✅ Применяю...")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e_ans:
        logger.warning(f"Error answering apply query: {e_ans}")
    chat = query.message.chat
    dl_status_msg = None
    image_bytes = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        dl_status_msg = await context.bot.send_message(chat.id, "⏳ Загрузка...")
        image_bytes = await get_cached_image_bytes(context, file_id_to_edit, chat)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as dl_exc:
        logger.exception(f"Download error apply {file_id_to_edit}: {dl_exc}")
    finally:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if dl_status_msg:
            await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not image_bytes:
        logger.error(f"Failed download apply {file_id_to_edit}.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("❌ Ошибка загрузки.", show_alert=True)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return False # No UI update needed if download fails
    current_settings = {"type_data": state.get("selected_type_data"), "style_data": state.get("selected_style_data"), "artist_data": state.get("selected_artist_data"), "ar": state.get("selected_ar")}
    current_effective_prompt = state.get("effective_prompt", original_user_prompt)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await _initiate_image_editing(
            context=context, base_image_bytes=image_bytes, current_settings=current_settings, original_settings=original_settings,
            current_effective_prompt=current_effective_prompt, original_user_prompt=original_user_prompt, original_api_prompt=original_api_prompt,
            chat_id=chat.id, user_id=query.from_user.id, user_mention=query.from_user.mention_html(),
            reply_to_msg_id=query.message.message_id, source_message=query.message
        )
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Error calling editing from _handle_edit: {e}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await context.bot.send_message(chat.id, "❌ Ошибка применения.", reply_to_message_id=query.message.message_id)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as send_err:
            logger.error(f"Failed send apply error msg: {send_err}")
        return False # Indicate UI update for original message is not needed

    # --- Reset original message state ---
    original_chat_id = query.message.chat_id
    original_msg_id = query.message.message_id
    original_state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{original_chat_id}:{original_msg_id}"
    original_state = context.application.bot_data.get(original_state_key)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if original_state:
        logger.info(f"Resetting state for original message {original_msg_id} after edit.")
        original_api_settings = original_state.get("api_call_settings", {})
        original_user_prompt_reset = original_state.get("original_user_prompt", "")
        original_state["selected_type_data"] = original_api_settings.get("type_data")
        original_state["selected_style_data"] = original_api_settings.get("style_data")
        original_state["selected_artist_data"] = original_api_settings.get("artist_data")
        original_state["selected_ar"] = original_api_settings.get("ar")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_type_data"]:
            original_state["selected_type_index"] = next((i for i, d in TYPE_INDEX_TO_DATA.items() if d['id'] == original_state["selected_type_data"]['id']), None)
        else:
            original_state["selected_type_index"] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_style_data"]:
            original_state["selected_style_abs_index"] = STYLE_NAME_TO_ABSOLUTE_INDEX.get(original_state["selected_style_data"].get('name','').lower())
        else:
            original_state["selected_style_abs_index"] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if original_state["selected_artist_data"]:
            original_state["selected_artist_abs_index"] = ARTIST_NAME_TO_ABSOLUTE_INDEX.get(original_state["selected_artist_data"].get('name','').lower())
        else:
            original_state["selected_artist_abs_index"] = None
        original_state["effective_prompt"] = original_user_prompt_reset
        original_state["settings_visible"] = False
        original_state["ar_select_visible"] = False
        original_state["type_select_visible"] = False
        original_state["style_select_visible"] = False
        original_state["artist_select_visible"] = False
        original_state["prompt_action_visible"] = False
        original_state["awaiting_prompt_change"] = False
        original_state["type_page"] = 0
        original_state["style_page"] = 0
        original_state["artist_page"] = 0
        context.application.bot_data[original_state_key] = original_state
        logger.debug(f"Saved reset state for {original_state_key}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await update_caption_and_keyboard(context, original_chat_id, original_msg_id)
            logger.info(f"Updated UI for original message {original_msg_id} after reset.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e_update:
            logger.error(f"Failed to update UI for original message {original_msg_id} after reset: {e_update}")
    else:
        logger.warning(f"Could not find original state for {original_state_key} to reset.")
    # --- End Reset ---
    return False # Indicate that the main handler should NOT update the UI again
# ================================== _handle_edit() end ==================================


# ================================== handle_callback_query(): Main callback query dispatcher ==================================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not query or not query.data or not query.message:
        logger.warning("Пустой callback query.")
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("❌ Нет прав.", show_alert=True)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return
    msg_id = query.message.message_id
    chat_id = query.message.chat_id
    parsed_data = parse_callback_data(query.data)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not parsed_data:
        logger.error(f"Не удалось обработать callback: {query.data}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("Ошибка обработки.", show_alert=True)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return
    action = parsed_data["action"]
    value = parsed_data["value"]
    logger.debug(f"Callback: A='{action}', V='{value}', M={msg_id}, C={chat_id}")
    state_key = f"{IMAGE_STATE_CACHE_KEY_PREFIX}{chat_id}:{msg_id}"
    state = context.application.bot_data.get(state_key)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not state:
        logger.warning(f"Состояние {state_key} не найдено.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("⚠️ Состояние истекло.", show_alert=True)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        return
    # Pre-answer non-blocking actions
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if action not in ["enhance", "regen", "edit", "change_prompt_req"]:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer()
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass # Ignore if answering fails for simple toggles
    needs_ui_update = True # Default assumption
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if action == "toggle_settings":
            _handle_toggle_settings(state)
        elif action == "show_ar":
            _handle_show_ar(state)
        elif action == "hide_ar":
            _handle_hide_ar(state)
        elif action == "set_ar":
            _handle_set_ar(state, value)
        elif action == "show_type":
            _handle_show_type(state)
        elif action == "hide_type":
            _handle_hide_type(state)
        elif action == "clear_type":
            _handle_clear_type(state)
        elif action == "set_type":
            _handle_set_type(state, value)
        elif action == "rnd_type":
            _handle_rnd_type(state)
        elif action == "type_page":
            _handle_type_page(state, value)
        elif action == "show_style":
            _handle_show_style(state)
        elif action == "hide_style":
            _handle_hide_style(state)
        elif action == "clear_style":
            _handle_clear_style(state)
        elif action == "set_style":
            _handle_set_style(state, value)
        elif action == "rnd_style":
            _handle_rnd_style(state)
        elif action == "style_page":
            _handle_style_page(state, value)
        elif action == "show_artist":
            _handle_show_artist(state)
        elif action == "hide_artist":
            _handle_hide_artist(state)
        elif action == "clear_artist":
            _handle_clear_artist(state)
        elif action == "set_artist":
            _handle_set_artist(state, value)
        elif action == "rnd_artist":
            _handle_rnd_artist(state)
        elif action == "artist_page":
            _handle_artist_page(state, value)
        elif action == "show_prompt":
            _handle_show_prompt(state)
        elif action == "hide_prompt":
            _handle_hide_prompt(state)
        elif action == "reset_prompt":
            _handle_reset_prompt(state)
        elif action == "change_prompt_req":
            # This action handles its own UI update potentially
            needs_ui_update = await _handle_change_prompt_request(state, context, query)
        elif action == "enhance":
            # This action handles its own UI update potentially
            needs_ui_update = await _handle_enhance(state, context, query)
        elif action == "regen":
            # This action now returns False if it handled the UI update
            needs_ui_update = await _handle_regen(state, update, context, query)
        elif action == "edit":
            # This action now returns False if it handled the UI update
            needs_ui_update = await _handle_edit(state, update, context, query)
        elif action == "noop":
            needs_ui_update = False
        else:
            logger.warning(f"Неизвестное действие: {action}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                await query.answer("Неизв. действие.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception:
                pass
            needs_ui_update = False
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Ошибка обработки '{action}': {e}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            await query.answer("❌ Ошибка.", show_alert=True)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception:
            pass
        needs_ui_update = False # Don't update UI on error
    # Save the potentially modified state (unless it was deleted on expiry check)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if state is not None: # Re-check state exists before saving
        context.application.bot_data[state_key] = state
        logger.debug(f"State {state_key} updated in bot_data.")
        # Conditionally update UI based on the handler's return value or default
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if needs_ui_update:
            await update_caption_and_keyboard(context, chat_id, msg_id)
        else:
            logger.debug(f"Skipping main UI update for action '{action}' on msg {msg_id}")
# ================================== handle_callback_query() end ==================================


# handlers/callbacks.py end