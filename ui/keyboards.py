# ui/keyboards.py
# -*- coding: utf-8 -*-
"""
Generates inline keyboards for image generation messages.
Updated layout, button names, and Prompt action row.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import (
    MAIN_TYPES_DATA, STYLE_LISTS, ALL_STYLES_DATA, ALL_ARTISTS_DATA,
    TYPE_INDEX_TO_DATA, STYLE_ABSOLUTE_INDEX_TO_DATA, ARTIST_ABSOLUTE_INDEX_TO_DATA,
    TYPE_NAME_TO_DATA, STYLE_NAME_TO_DATA, ARTIST_NAME_TO_DATA,
    STYLE_NAME_TO_ABSOLUTE_INDEX, ARTIST_NAME_TO_ABSOLUTE_INDEX
)
import config

logger = logging.getLogger(__name__)
ITEMS_PER_ROW_AR = 3
ITEMS_PER_ROW_TYPE = 3
ITEMS_PER_ROW_STYLE = 3
ITEMS_PER_ROW_ARTIST = 3
ITEMS_PER_ROW_PROMPT = 4
ITEMS_PER_PAGE_TYPE = 18
ITEMS_PER_PAGE_STYLE = 18
ITEMS_PER_PAGE_ARTIST = 18

# ================================== _chunk_list(): Splits a list into chunks ==================================
def _chunk_list(data: List[Any], size: int) -> List[List[Any]]:
    if not data: return []
    return [data[i:i + size] for i in range(0, len(data), size)]
# ================================== _chunk_list() end ==================================


# ================================== _get_button_label(): Truncates button label ==================================
def _get_button_label(label: str, max_len: int = 25) -> str:
    if len(label) > max_len: return label[:max_len-1] + "…"
    return label
# ================================== _get_button_label() end ==================================


# ================================== generate_main_keyboard(): Generates main view keyboard ==================================
def generate_main_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; settings_visible = state.get("settings_visible", False)
    ar_sel = state.get("ar_select_visible", False); type_sel = state.get("type_select_visible", False)
    style_sel = state.get("style_select_visible", False); artist_sel = state.get("artist_select_visible", False)
    prompt_sel = state.get("prompt_action_visible", False)
    selection_active = ar_sel or type_sel or style_sel or artist_sel or prompt_sel
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"),
        InlineKeyboardButton("📐 AR", callback_data=f"show_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"),
        InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    if settings_visible and not selection_active:
        row2 = [
            InlineKeyboardButton("🎨 Тип", callback_data=f"show_type|{msg_id}"),
            InlineKeyboardButton("🖌️ Стиль", callback_data=f"show_style|{msg_id}"),
            InlineKeyboardButton("👨‍🎨 Художник", callback_data=f"show_artist|{msg_id}"),
            InlineKeyboardButton("📝 Промпт", callback_data=f"show_prompt|{msg_id}"),
        ]; keyboard.append(row2)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_main_keyboard() end ==================================


# ================================== generate_ar_selection_keyboard(): Generates AR selection keyboard ==================================
def generate_ar_selection_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; settings_visible = state.get("settings_visible", False)
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"),
        InlineKeyboardButton("📐 AR", callback_data=f"hide_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"),
        InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    row2 = [ InlineKeyboardButton("🚫 Сброс", callback_data=f"set_ar|reset|{msg_id}"), InlineKeyboardButton("4:3", callback_data=f"set_ar|4:3|{msg_id}"), InlineKeyboardButton("16:9", callback_data=f"set_ar|16:9|{msg_id}") ]; keyboard.append(row2)
    row3 = [ InlineKeyboardButton("1:1", callback_data=f"set_ar|1:1|{msg_id}"), InlineKeyboardButton("3:4", callback_data=f"set_ar|3:4|{msg_id}"), InlineKeyboardButton("9:16", callback_data=f"set_ar|9:16|{msg_id}") ]; keyboard.append(row3)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_ar_selection_keyboard() end ==================================


# ================================== generate_type_selection_keyboard(): Generates Type selection keyboard (with index) ==================================
def generate_type_selection_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; current_page = state.get("type_page", 0); settings_visible = state.get("settings_visible", False)
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"), InlineKeyboardButton("📐 AR", callback_data=f"show_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"), InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    row2 = [ InlineKeyboardButton("🎨 Тип", callback_data=f"hide_type|{msg_id}"), InlineKeyboardButton("🖌️ Стиль", callback_data=f"show_style|{msg_id}"), InlineKeyboardButton("👨‍🎨 Художник", callback_data=f"show_artist|{msg_id}"), InlineKeyboardButton("📝 Промпт", callback_data=f"show_prompt|{msg_id}"), ]; keyboard.append(row2)
    row3 = [ InlineKeyboardButton("🚫 Сброс", callback_data=f"clear_type|{msg_id}"), InlineKeyboardButton("🎲 Случ.", callback_data=f"rnd_type|{msg_id}"), InlineKeyboardButton("✅ OK", callback_data=f"hide_type|{msg_id}") ]; keyboard.append(row3)
    start_index = current_page * ITEMS_PER_PAGE_TYPE; end_index = start_index + ITEMS_PER_PAGE_TYPE
    types_on_page = MAIN_TYPES_DATA[start_index:end_index]; total_pages = (len(MAIN_TYPES_DATA) + ITEMS_PER_PAGE_TYPE - 1) // ITEMS_PER_PAGE_TYPE
    type_buttons = []
    for type_data in types_on_page:
        # Find the absolute index (should always match position + 1 in TYPE_INDEX_TO_DATA keys)
        absolute_index = next((idx for idx, data in TYPE_INDEX_TO_DATA.items() if data['id'] == type_data['id']), None)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if absolute_index is None: logger.warning(f"Could not find index for type {type_data.get('id')}"); continue # Skip if index not found
        alias = type_data.get('alias', f'Тип {absolute_index}'); emoji = type_data.get('emoji', '')
        # Prepend index: "[N] [emoji] Alias"
        button_label = f"[{absolute_index}] {emoji} {_get_button_label(alias)}".strip()
        type_buttons.append(InlineKeyboardButton(button_label, callback_data=f"set_type|{absolute_index}|{msg_id}"))
    keyboard.extend(_chunk_list(type_buttons, ITEMS_PER_ROW_TYPE))
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if total_pages > 1:
        pagination_row = []
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page > 0: pagination_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"type_page|{current_page - 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page < total_pages - 1: pagination_row.append(InlineKeyboardButton("След. ➡️", callback_data=f"type_page|{current_page + 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        keyboard.append(pagination_row)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_type_selection_keyboard() end ==================================


# ================================== generate_style_selection_keyboard(): Generates Style selection keyboard (with index) ==================================
def generate_style_selection_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; current_page = state.get("style_page", 0); settings_visible = state.get("settings_visible", False); current_type_data = state.get("selected_type_data")
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"), InlineKeyboardButton("📐 AR", callback_data=f"show_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"), InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    row2 = [ InlineKeyboardButton("🎨 Тип", callback_data=f"show_type|{msg_id}"), InlineKeyboardButton("🖌️ Стиль", callback_data=f"hide_style|{msg_id}"), InlineKeyboardButton("👨‍🎨 Художник", callback_data=f"show_artist|{msg_id}"), InlineKeyboardButton("📝 Промпт", callback_data=f"show_prompt|{msg_id}"), ]; keyboard.append(row2)
    row3 = [ InlineKeyboardButton("🚫 Сброс", callback_data=f"clear_style|{msg_id}"), InlineKeyboardButton("🎲 Случ.", callback_data=f"rnd_style|{msg_id}"), InlineKeyboardButton("✅ OK", callback_data=f"hide_style|{msg_id}") ]; keyboard.append(row3)
    styles_to_display = []
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_type_data:
        relevant_keys = current_type_data.get('style_keys', []); seen_names = set()
        for key in relevant_keys:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if key == 'artists': continue
            style_list_for_key = config.STYLE_LISTS.get(key, [])
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(style_list_for_key, list):
                for style_data in style_list_for_key:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if isinstance(style_data, dict) and 'name' in style_data and 'alias' in style_data:
                        name_lower = style_data['name'].lower()
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        if name_lower not in seen_names: styles_to_display.append(style_data); seen_names.add(name_lower)
        logger.debug(f"Отобр. {len(styles_to_display)} рел. стилей для '{current_type_data.get('alias')}'")
    else: styles_to_display = ALL_STYLES_DATA; logger.debug(f"Тип не выбран, отобр. все {len(styles_to_display)} стили.")
    start_index = current_page * ITEMS_PER_PAGE_STYLE; end_index = start_index + ITEMS_PER_PAGE_STYLE
    styles_on_page = styles_to_display[start_index:end_index]; total_pages = (len(styles_to_display) + ITEMS_PER_PAGE_STYLE - 1) // ITEMS_PER_PAGE_STYLE
    style_buttons = []
    for style_data in styles_on_page:
        alias = style_data.get('alias', 'N/A'); name = style_data.get('name')
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if name:
            name_lower = name.lower(); abs_index = STYLE_NAME_TO_ABSOLUTE_INDEX.get(name_lower)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if abs_index is not None:
                 # Prepend index: "[N] Alias"
                 display_label = f"[{abs_index}] {_get_button_label(alias)}".strip()
                 style_buttons.append(InlineKeyboardButton(display_label, callback_data=f"set_style|{abs_index}|{msg_id}"))
            else: logger.warning(f"Стиль '{name}' не найден в карте индексов.")
    keyboard.extend(_chunk_list(style_buttons, ITEMS_PER_ROW_STYLE))
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if total_pages > 1:
        pagination_row = []
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page > 0: pagination_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"style_page|{current_page - 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page < total_pages - 1: pagination_row.append(InlineKeyboardButton("След. ➡️", callback_data=f"style_page|{current_page + 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        keyboard.append(pagination_row)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_style_selection_keyboard() end ==================================


# ================================== generate_artist_selection_keyboard(): Generates Artist selection keyboard (with index and short alias) ==================================
def generate_artist_selection_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; current_page = state.get("artist_page", 0); settings_visible = state.get("settings_visible", False)
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"), InlineKeyboardButton("📐 AR", callback_data=f"show_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"), InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    row2 = [ InlineKeyboardButton("🎨 Тип", callback_data=f"show_type|{msg_id}"), InlineKeyboardButton("🖌️ Стиль", callback_data=f"show_style|{msg_id}"), InlineKeyboardButton("👨‍🎨 Художник", callback_data=f"hide_artist|{msg_id}"), InlineKeyboardButton("📝 Промпт", callback_data=f"show_prompt|{msg_id}"), ]; keyboard.append(row2)
    row3 = [ InlineKeyboardButton("🚫 Сброс", callback_data=f"clear_artist|{msg_id}"), InlineKeyboardButton("🎲 Случ.", callback_data=f"rnd_artist|{msg_id}"), InlineKeyboardButton("✅ OK", callback_data=f"hide_artist|{msg_id}") ]; keyboard.append(row3)
    artists_to_display = ALL_ARTISTS_DATA; start_index = current_page * ITEMS_PER_PAGE_ARTIST; end_index = start_index + ITEMS_PER_PAGE_ARTIST
    artists_on_page = artists_to_display[start_index:end_index]; total_pages = (len(artists_to_display) + ITEMS_PER_PAGE_ARTIST - 1) // ITEMS_PER_PAGE_ARTIST
    artist_buttons = []
    for artist_data in artists_on_page:
        # Use explicit alias_short for button label, fallback to full alias
        button_alias = artist_data.get('alias_short', artist_data.get('alias', 'N/A'))
        name = artist_data.get('name'); emoji = artist_data.get('emoji', '') # Get emoji
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if name:
            name_lower = name.lower(); abs_index = ARTIST_NAME_TO_ABSOLUTE_INDEX.get(name_lower)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if abs_index is not None:
                 # Prepend index and emoji: "[N] emoji ShortAlias"
                 display_label = f"[{abs_index}] {emoji} {_get_button_label(button_alias)}".strip()
                 artist_buttons.append(InlineKeyboardButton(display_label, callback_data=f"set_artist|{abs_index}|{msg_id}"))
            else: logger.warning(f"Художник '{name}' не найден в карте индексов.")
    keyboard.extend(_chunk_list(artist_buttons, ITEMS_PER_ROW_ARTIST))
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if total_pages > 1:
        pagination_row = []
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page > 0: pagination_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"artist_page|{current_page - 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if current_page < total_pages - 1: pagination_row.append(InlineKeyboardButton("След. ➡️", callback_data=f"artist_page|{current_page + 1}|{msg_id}"))
        else: pagination_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        keyboard.append(pagination_row)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_artist_selection_keyboard() end ==================================


# ================================== generate_prompt_action_keyboard(): Generates Prompt action keyboard ==================================
def generate_prompt_action_keyboard(state: dict, msg_id: int) -> InlineKeyboardMarkup:
    keyboard = []; settings_visible = state.get("settings_visible", False)
    row1 = [
        InlineKeyboardButton("✅ Применить", callback_data=f"edit|{msg_id}"), InlineKeyboardButton("📐 AR", callback_data=f"show_ar|{msg_id}"),
        InlineKeyboardButton("🔄 Заново", callback_data=f"regen|{msg_id}"), InlineKeyboardButton("⚙️ Настройки" if not settings_visible else "⬆️ Свернуть", callback_data=f"toggle_settings|{msg_id}"),
    ]; keyboard.append(row1)
    row2 = [ InlineKeyboardButton("🎨 Тип", callback_data=f"show_type|{msg_id}"), InlineKeyboardButton("🖌️ Стиль", callback_data=f"show_style|{msg_id}"), InlineKeyboardButton("👨‍🎨 Художник", callback_data=f"show_artist|{msg_id}"), InlineKeyboardButton("📝 Промпт", callback_data=f"hide_prompt|{msg_id}"), ]; keyboard.append(row2)
    row3 = [ InlineKeyboardButton("🚫 Сброс", callback_data=f"reset_prompt|{msg_id}"), InlineKeyboardButton("✨ Улучшить", callback_data=f"enhance|{msg_id}"), InlineKeyboardButton("✏️ Изменить", callback_data=f"change_prompt_req|{msg_id}"), InlineKeyboardButton("✅ OK", callback_data=f"hide_prompt|{msg_id}") ]; keyboard.append(row3)
    return InlineKeyboardMarkup(keyboard)
# ================================== generate_prompt_action_keyboard() end ==================================

# ui/keyboards.py end
