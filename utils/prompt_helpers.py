# utils/prompt_helpers.py
# -*- coding: utf-8 -*-
"""
Utility functions related to prompt generation, style selection,
using data loaded from configuration files. Updated constructor for suffix.
"""
import random
import logging
from typing import Any, Dict, List, Optional
from config import (
    MAIN_TYPES_DATA, STYLE_LISTS, TYPE_NAME_TO_DATA, STYLE_NAME_TO_DATA,
    IMAGE_GENERATION_PROMPT_TEMPLATE, STYLE_NAME_TO_ABSOLUTE_INDEX, ALL_STYLES_DATA
)

logger = logging.getLogger(__name__)

# Reminder: Use new line, not semicolon, for the following block/statement.
if not MAIN_TYPES_DATA:
    logger.error("Prompt Helpers: MAIN_TYPES_DATA пуст.")
# Reminder: Use new line, not semicolon, for the following block/statement.
if not STYLE_LISTS:
    logger.error("Prompt Helpers: STYLE_LISTS пуст.")
# Reminder: Use new line, not semicolon, for the following block/statement.
if not IMAGE_GENERATION_PROMPT_TEMPLATE:
    logger.error("Prompt Helpers: IMAGE_GENERATION_PROMPT_TEMPLATE пуст.")

# ================================== get_style_detail(): Selects a relevant style based on type name ==================================
def get_style_detail(type_name: Optional[str]) -> str:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not isinstance(type_name, str) or not type_name:
        logger.warning(f"get_style_detail неверный type_name: {type_name}.")
        return _get_fallback_style()
    type_data = TYPE_NAME_TO_DATA.get(type_name.lower())
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not type_data:
        logger.warning(f"get_style_detail: type_name '{type_name}' не найден. Fallback.")
        return _get_fallback_style()
    relevant_list_keys = type_data.get('style_keys', [])
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not relevant_list_keys:
        logger.warning(f"Нет ключей стилей для '{type_name}'. Fallback.")
        return _get_fallback_style()
    possible_details_data: List[Dict[str,str]] = []
    seen_names = set()
    for key in relevant_list_keys:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if key == 'artists':
            continue
        details_list = STYLE_LISTS.get(key)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if details_list and isinstance(details_list, list):
            for style_item in details_list:
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if isinstance(style_item, dict) and 'name' in style_item:
                     name_lower = style_item['name'].lower()
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     if name_lower not in seen_names:
                         possible_details_data.append(style_item)
                         seen_names.add(name_lower)
        else:
            logger.warning(f"Ключ '{key}' для '{type_name}' не найден/не список.")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if possible_details_data:
        chosen_style_data = random.choice(possible_details_data)
        return chosen_style_data.get('name', 'Unknown Style')
    else:
        logger.warning(f"Все списки для '{type_name}' пусты/отсутствуют. Fallback.")
        return _get_fallback_style()
# ================================== get_style_detail() end ==================================


# ================================== _get_fallback_style(): Provides a fallback style name ==================================
def _get_fallback_style() -> str:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if ALL_STYLES_DATA:
        chosen_fallback_data = random.choice(ALL_STYLES_DATA)
        return chosen_fallback_data.get('name', 'Default Style')
    else:
        logger.error("Fallback style failed: ALL_STYLES_DATA пуст.")
        return "Default Style"
# ================================== _get_fallback_style() end ==================================


# ================================== construct_prompt_with_style(): Builds the final prompt using the single template ==================================
def construct_prompt_with_style(
        base_prompt: str, selected_type_data: Optional[Dict[str, Any]], selected_style_data: Optional[Dict[str, Any]],
        selected_artist_data: Optional[Dict[str, Any]], selected_ar: Optional[str], suffix_text: Optional[str] = None
    ) -> str:
    template = IMAGE_GENERATION_PROMPT_TEMPLATE
    base_prompt_str = str(base_prompt).strip() if base_prompt else ""
    type_phrase = ""
    style_phrase = ""
    artist_phrase = ""
    ar_tag = ""
    suffix_phrase = "" # Initialize suffix phrase
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if selected_type_data and 'name' in selected_type_data:
        type_name = selected_type_data['name']
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if type_name.lower() not in base_prompt_str.lower():
            type_phrase = f", a {type_name}"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if selected_style_data and 'name' in selected_style_data:
        style_phrase = f", in the style of {selected_style_data['name']}"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if selected_artist_data and 'name' in selected_artist_data:
        artist_phrase = f", by {selected_artist_data['name']}"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if selected_ar:
        ar_tag = f" --ar {selected_ar}"
    # Construct suffix phrase only if suffix_text is provided
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if suffix_text and suffix_text.strip():
        suffix_phrase = f", {suffix_text.strip()}" # Add comma separation
        logger.debug(f"Adding suffix phrase: '{suffix_phrase}'")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        # Format the template including the new suffix_phrase
        final_prompt = template.format(
            base_prompt=base_prompt_str, type_phrase=type_phrase, style_phrase=style_phrase,
            artist_phrase=artist_phrase, ar_tag=ar_tag, suffix_phrase=suffix_phrase
        ).strip()
        # Clean up extra spaces and commas
        final_prompt = ' '.join(final_prompt.split())
        final_prompt = final_prompt.replace(" ,", ",").replace(",,", ",")
        return final_prompt
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except KeyError as e:
        logger.error(f"KeyError форматирования шаблона: {e}. Шаблон: '{template}'.")
        fallback_prompt = base_prompt_str + type_phrase + style_phrase + artist_phrase + ar_tag + suffix_phrase
        return ' '.join(fallback_prompt.split()).strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Ошибка конструирования промпта: {e}")
        return base_prompt_str
# ================================== construct_prompt_with_style() end ==================================


# utils/prompt_helpers.py end