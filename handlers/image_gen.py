# handlers/image_gen.py
# -*- coding: utf-8 -*-
"""
Handlers related to image generation, editing, and combining.
Contains separate functions for new generation, targeted editing, and combination.
Includes shortcuts !<prompt> and !!<prompt> (random).
Handles artist index and short alias. Handles style group aliases.
Uses default suffix from config, passed to constructor.
Differentiates Apply/Re-Gen randomness. Defines marker constants.
Includes auto-description for flags-only captions.
"""

import logging
import re
from typing import Tuple, Dict, Any
import asyncio
import random
from typing import Optional, List, Dict, Tuple, Any
from html import escape # Import escape
from telegram import Update, CallbackQuery, Message, Chat
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from telegram.error import TelegramError
from utils.auth import is_authorized
from utils.cache import get_cached_image_bytes, get_cached_image_bytes_by_id
from utils.telegram_helpers import delete_message_safely
from utils.prompt_helpers import construct_prompt_with_style, get_style_detail
# Import describe_image_with_gemini
from api.gemini_api import generate_image_with_gemini, describe_image_with_gemini
from ui.messages import send_image_generation_response
from config import (
    ARTIST_ABSOLUTE_INDEX_TO_DATA, CHAT_DATA_KEY_IMAGE_SUFFIX, GEMINI_IMAGE_MODEL,
    MAIN_TYPES_DATA, STYLE_ABSOLUTE_INDEX_TO_DATA, TYPE_ALIAS_TO_NAME,
    TYPE_INDEX_TO_DATA, TYPE_NAME_TO_DATA, STYLE_LISTS, STYLE_ALIAS_TO_NAME,
    STYLE_NAME_TO_DATA, STYLE_NAME_TO_ALIAS, TYPE_NAME_TO_ALIAS, ALL_STYLES_DATA,
    STYLE_NAME_TO_ABSOLUTE_INDEX, ALL_ARTISTS_DATA, ARTIST_ALIAS_TO_NAME,
    ARTIST_NAME_TO_DATA, ARTIST_NAME_TO_ABSOLUTE_INDEX, DEFAULT_COMBINE_PROMPT_TEXT,
    DEFAULT_IMAGE_PROMPT_SUFFIX, ARTIST_SHORT_ALIAS_TO_NAME,
    STYLE_GROUP_ALIASES, DEFAULT_COMBINE_PROMPT_TEXT
)
import config
from ui.messages import update_caption_and_keyboard, send_image_generation_response

from utils.decorators import restrict_private_unauthorized


logger = logging.getLogger(__name__)

SUPPORTED_ASPECT_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4"}

# Define Marker Constants at Module Level
RANDOM_MARKER_RELATIVE_STYLE = "RANDOM_RELATIVE"
RANDOM_MARKER_GLOBAL_STYLE = "RANDOM_GLOBAL"
RANDOM_MARKER_GROUP_STYLE_PREFIX = "RANDOM_GROUP:"

# ================================== parse_img_args_prompt_first(): Parses /img args (Handles -t, -s, -a, -r, -s0, style groups, combinations, spaceless, short aliases) ==================================
def parse_img_args_prompt_first(full_text: str) -> Tuple[str, Dict[str, Any]]:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    import config # Ensure config is accessible
    import random # Needed for list choice later if resolver calls it, but parser stores list
    parsed_settings_data = {
        "type": None, "style": None, "artist": None, "ar": None,
        "randomize_type": False, "randomize_style": False, "randomize_artist": False,
        "style_marker": None, # Captures specific style, global random, relative random, or group random
        "type_choice_list": None, # Stores list of type indices like [6, 7, 9]
        "style_choice_list": None, # Stores list of style indices
        "artist_choice_list": None, # Stores list of artist indices
    }
    text = full_text.strip()
    prompt_text = text
    args_part = ""
    ARG_FLAGS_FULL_MAP = {
        "--type": "type", "—type": "type", "-t": "type",
        "--style": "style", "—style": "style", "-s": "style",
        "--artist": "artist", "—artist": "artist", "-a": "artist",
        "--ar": "ar", "—ar": "ar",
        "--random": "random", "—random": "random", "-r": "random",
    }
    # Order flags by length (longest first)
    ARG_FLAGS_ORDERED = sorted(ARG_FLAGS_FULL_MAP.keys(), key=len, reverse=True)
    FLAG_START_PATTERN_STR = r"|".join(re.escape(f) for f in ARG_FLAGS_ORDERED)

    # Find the first potential flag to split prompt and args
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        first_match = None; first_match_pos = len(text)
        for flag in ARG_FLAGS_ORDERED:
             # Reminder: Use new line, not semicolon, for the following block/statement.
             try:
                 for match in re.finditer(re.escape(flag), text, re.IGNORECASE):
                     pos = match.start()
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     if pos > 0 and not text[pos-1].isspace(): continue # Must be preceded by space or be at start of args
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     if pos < first_match_pos: first_match_pos = pos; first_match = flag; break
             # Reminder: Use new line, not semicolon, for the following block/statement.
             except Exception as find_err: logger.warning(f"Error finding flag {flag}: {find_err}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if first_match:
            prompt_text = text[:first_match_pos].strip(); args_part = text[first_match_pos:].strip()
            logger.debug(f"Split prompt: '{prompt_text}', Args: '{args_part}'")
        else:
            prompt_text = text; args_part = ""
            logger.debug("No argument flags found.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not prompt_text.startswith("!") and not prompt_text.startswith("/"): return full_text, parsed_settings_data
            return prompt_text, parsed_settings_data # Early exit if no args
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.error(f"Error during prompt/arg splitting: {e}"); return prompt_text, parsed_settings_data
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not args_part: return prompt_text, parsed_settings_data

    # --- Pre-processing Flags ---
    processed_pre_flags = set() # Flags handled by special cases below

    # --- SPECIAL CASE 1: Direct handling for -t<num>s<num> ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        direct_pattern = r'(-t(\d+)s(\d+))'; direct_match = re.search(direct_pattern, args_part, re.IGNORECASE)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if direct_match:
            matched_segment = direct_match.group(1); type_value = direct_match.group(2); style_value = direct_match.group(3)
            logger.debug(f"Found direct pattern: {matched_segment}")
            args_part = args_part.replace(matched_segment, " ", 1) # Remove segment
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                type_id = int(type_value); style_id = int(style_value)
                type_data = config.TYPE_INDEX_TO_DATA.get(type_id); style_data = config.STYLE_ABSOLUTE_INDEX_TO_DATA.get(style_id)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if type_data: parsed_settings_data["type"] = type_data; processed_pre_flags.add("-t"); logger.debug(f"Directly parsed Type: {type_data.get('alias')}")
                else: logger.warning(f"Direct pattern: Type index '{type_id}' not found.")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if style_data: parsed_settings_data["style"] = style_data; parsed_settings_data["style_marker"] = style_data; processed_pre_flags.add("-s"); logger.debug(f"Directly parsed Style: {style_data.get('alias')}")
                else: logger.warning(f"Direct pattern: Style index '{style_id}' not found.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except ValueError: logger.warning(f"Invalid numeric values in direct pattern: {matched_segment}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as e_direct: logger.error(f"Error processing direct pattern: {e_direct}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except re.error as e_re: logger.error(f"Regex error in direct pattern search: {e_re}")
    # --- End of Special Case 1 ---

    # --- SPECIAL CASE 2: Handling for -t(list), -s(list), -a(list) ---
    # Corrected patterns to look for the right flags
    list_patterns = {
        'type': r'-t\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)',
        'style': r'-s\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)',   # Corrected to -s
        'artist': r'-a\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)', # Corrected to -a
    }

    # For dynamic creation if you prefer (alternative to above)
    # flags_chars = {'type': 't', 'style': 's', 'artist': 'a'}
    # list_patterns = {
    #     key: rf'-{char}\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)'
    #     for key, char in flags_chars.items()
    # }

    for key, pattern in list_patterns.items():
        if f'-{key[0]}' in processed_pre_flags: # Check if the simple flag (e.g., -t) was already handled
            continue

        try:
            # Use re.search to find the pattern anywhere in args_part
            list_match = re.search(pattern, args_part, re.IGNORECASE)

            if list_match:
                # group(0) is the entire matched segment, e.g., "-t(1,2,3)" or "-s(5)"
                full_matched_segment = list_match.group(0)
                # group(1) is the string of numbers inside the parentheses, e.g., "1,2,3" or "5"
                indices_str = list_match.group(1)

                logger.debug(f"Found list pattern for {key}: '{full_matched_segment}', extracting indices: '{indices_str}'")

                # Remove the entire processed segment from args_part
                args_part = args_part.replace(full_matched_segment, " ", 1)
                logger.debug(f"args_part after removing '{full_matched_segment}': '{args_part}'")

                try:
                    # Split the string of numbers by comma, strip whitespace, and convert to int
                    # Filter out empty strings that might result from "1,,2" or trailing commas if not handled by regex
                    indices = [int(x.strip()) for x in indices_str.split(',') if x.strip()]

                    if indices:
                        parsed_settings_data[f"{key}_choice_list"] = indices
                        # Mark the base flag (e.g., -t, -s, -a) as handled to avoid double processing
                        # if you have other logic that handles simple flags like -t without a list.
                        processed_pre_flags.add(f'-{key[0].lower()}') # Use lower() if IGNORECASE can lead to -T
                        logger.debug(f"Parsed {key} choice list: {indices}")
                    else:
                        logger.warning(f"Empty or invalid index list for {key} from string: '{indices_str}'")
                except ValueError:
                    logger.warning(f"Invalid numbers in index list for {key}: '{indices_str}'")
                except Exception as e_list:
                    logger.error(f"Error processing {key} list ('{indices_str}'): {e_list}")
        except re.error as e_re_list:
            logger.error(f"Regex error searching for {key} list with pattern '{pattern}': {e_re_list}")
    # --- End of Special Case 2 ---

    # --- Iterative Parsing of REMAINING args_part ---
    processed_args = {} # Maps flag -> value_string or None
    remaining_args = args_part.strip()
    while remaining_args:
        current_arg = remaining_args.lstrip() # Use a temporary var for the current state
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not current_arg: break
        matched_flag = None; flag_len = 0
        for flag in ARG_FLAGS_ORDERED:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if current_arg.lower().startswith(flag.lower()): matched_flag = flag; flag_len = len(flag); break
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not matched_flag: logger.warning(f"Could not find known flag at start of remaining args: '{current_arg[:20]}...'"); break

        # Check if flag was handled by pre-processing
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if matched_flag in processed_pre_flags:
            logger.debug(f"Skipping flag '{matched_flag}' as it was handled by pre-processing.")
            # Consume just the flag so loop continues
            remaining_args = remaining_args[len(matched_flag):]
            continue

        logger.debug(f"Iterative: Found flag: '{matched_flag}'")
        arg_after_flag = current_arg[flag_len:]; consumed_len = flag_len; current_value = None
        m_val = re.match(r"^\s*([\w:]+)", arg_after_flag)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if m_val:
            potential_value = m_val.group(1); is_another_flag = False
            for f in ARG_FLAGS_ORDERED:
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if potential_value.lower() == f.lower(): is_another_flag = True; break
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not is_another_flag:
                current_value = potential_value; consumed_len += m_val.end(0)
                logger.debug(f"Iterative: Extracted value: '{current_value}'")
            else: logger.debug(f"Iterative: Potential value '{potential_value}' is another flag, treating '{matched_flag}' as boolean.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        else: logger.debug(f"Iterative: No value found after '{matched_flag}', treating as boolean.")

        # Reminder: Use new line, not semicolon, for the following block/statement.
        if matched_flag not in processed_args: processed_args[matched_flag] = current_value
        else: logger.debug(f"Flag '{matched_flag}' already processed, skipping.")

        remaining_args = remaining_args[consumed_len:]

    # --- Process the collected arguments map ---
    processed_flags_yielded = set(processed_pre_flags) # Start with flags handled by special cases
    # Handle combined/random flags first
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if '-r' in processed_args or '--random' in processed_args:
        parsed_settings_data["randomize_type"] = True; parsed_settings_data["randomize_style"] = True
        parsed_settings_data["style_marker"] = RANDOM_MARKER_GLOBAL_STYLE; parsed_settings_data["randomize_artist"] = True
        logger.debug("Found -r or --random, enabling full randomization.")
        processed_flags_yielded.update(['-r', '--random', '-t', '--type', '-s', '--style', '-a', '--artist'])
    # Check for combined short flags
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if '-r' not in processed_flags_yielded:
        combined_keys = [k for k, v in processed_args.items() if v is None and k.startswith('-') and len(k) > 2 and all(c in 'tsar' for c in k[1:])]
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if combined_keys:
            combined_flag = combined_keys[0]; logger.debug(f"Found combined flag: {combined_flag}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if 't' in combined_flag[1:]: parsed_settings_data["randomize_type"] = True; processed_flags_yielded.add('-t'); processed_flags_yielded.add('--type')
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if 's' in combined_flag[1:]: parsed_settings_data["randomize_style"] = True; parsed_settings_data["style_marker"] = RANDOM_MARKER_GLOBAL_STYLE; processed_flags_yielded.add('-s'); processed_flags_yielded.add('--style')
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if 'a' in combined_flag[1:]: parsed_settings_data["randomize_artist"] = True; processed_flags_yielded.add('-a'); processed_flags_yielded.add('--artist')
            processed_flags_yielded.add(combined_flag)

    # Process remaining flags from the iterative step
    processed_flags_this_pass = set()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    for flag in processed_args:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if flag in processed_flags_yielded or flag in processed_flags_this_pass: continue
        value_str = processed_args.get(flag); setting_key = ARG_FLAGS_FULL_MAP.get(flag)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not setting_key: continue
        flag_aliases = {f for f, sk in ARG_FLAGS_FULL_MAP.items() if sk == setting_key}

        # Apply settings logic (same as before, uses config lookups)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if setting_key == "ar":
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if value_str:
                 norm_ar = value_str.replace('x', ':')
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if norm_ar in config.SUPPORTED_ASPECT_RATIOS: parsed_settings_data["ar"] = norm_ar; logger.debug(f"Parsed AR: {norm_ar}")
                 else: logger.warning(f"Invalid AR '{value_str}'."); parsed_settings_data["ar"] = None
             else: logger.warning(f"AR flag '{flag}' found without value.")
             processed_flags_this_pass.update(flag_aliases)
        elif setting_key == "type":
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if value_str is None: parsed_settings_data["randomize_type"] = True; logger.debug(f"Flag '{flag}' implies random Type.")
             elif parsed_settings_data["type"] is None and not parsed_settings_data["type_choice_list"]: # Process only if not set by special cases
                resolved_type_data = None; value_lower = value_str.lower()
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try: idx = int(value_str); data = config.TYPE_INDEX_TO_DATA.get(idx); resolved_type_data = data if data else None
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except ValueError: name = config.TYPE_ALIAS_TO_NAME.get(value_lower) or value_str; data = config.TYPE_NAME_TO_DATA.get(name.lower()); resolved_type_data = data if data else None
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if resolved_type_data: parsed_settings_data["type"] = resolved_type_data; logger.debug(f"Parsed Type: {resolved_type_data.get('alias')}")
                else: logger.warning(f"Type '{value_str}' not found.")
             processed_flags_this_pass.update(flag_aliases)
        elif setting_key == "style":
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if value_str is None: parsed_settings_data["randomize_style"] = True; parsed_settings_data["style_marker"] = RANDOM_MARKER_GLOBAL_STYLE; logger.debug(f"Flag '{flag}' implies GLOBAL random Style.")
             elif value_str == '0': parsed_settings_data["randomize_style"] = True; parsed_settings_data["style_marker"] = RANDOM_MARKER_RELATIVE_STYLE; logger.debug(f"Value '0' implies RELATIVE random Style.")
             elif parsed_settings_data["style"] is None and parsed_settings_data["style_marker"] is None and not parsed_settings_data["style_choice_list"]: # Process only if not set by special cases
                 group_key = config.STYLE_GROUP_ALIASES.get(value_str.lower())
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if group_key:
                     parsed_settings_data["randomize_style"] = True; parsed_settings_data["style_marker"] = f"{RANDOM_MARKER_GROUP_STYLE_PREFIX}{group_key}"; logger.debug(f"Value '{value_str}' implies GROUP random Style ('{group_key}').")
                 else:
                     resolved_style_data = None
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     try:
                         idx = int(value_str)
                         # Reminder: Use new line, not semicolon, for the following block/statement.
                         if idx > 0: data = config.STYLE_ABSOLUTE_INDEX_TO_DATA.get(idx); resolved_style_data = data if data else None
                         else: logger.warning("Style index must be > 0.")
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     except ValueError: name = config.STYLE_ALIAS_TO_NAME.get(value_str.lower()) or value_str; data = config.STYLE_NAME_TO_DATA.get(name.lower()); resolved_style_data = data if data else None
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     if resolved_style_data: parsed_settings_data["style"] = resolved_style_data; parsed_settings_data["style_marker"] = resolved_style_data; logger.debug(f"Parsed Style: {resolved_style_data.get('alias')}")
                     else: logger.warning(f"Style value '{value_str}' not found as index, alias, name, or group.")
             processed_flags_this_pass.update(flag_aliases)
        elif setting_key == "artist":
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if value_str is None: parsed_settings_data["randomize_artist"] = True; logger.debug(f"Flag '{flag}' implies random Artist.")
             elif parsed_settings_data["artist"] is None and not parsed_settings_data["artist_choice_list"]: # Process only if not set by special case
                 resolved_artist_data = None; value_lower = value_str.lower()
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 try:
                      idx = int(value_str)
                      # Reminder: Use new line, not semicolon, for the following block/statement.
                      if idx > 0: data = config.ARTIST_ABSOLUTE_INDEX_TO_DATA.get(idx); resolved_artist_data = data if data else None
                      else: logger.warning("Artist index must be > 0.")
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 except ValueError:
                      name_from_short_alias = config.ARTIST_SHORT_ALIAS_TO_NAME.get(value_lower)
                      # Reminder: Use new line, not semicolon, for the following block/statement.
                      if name_from_short_alias: data = config.ARTIST_NAME_TO_DATA.get(name_from_short_alias.lower())
                      else: name_from_full_alias = config.ARTIST_ALIAS_TO_NAME.get(value_lower); data = config.ARTIST_NAME_TO_DATA.get(name_from_full_alias.lower()) if name_from_full_alias else config.ARTIST_NAME_TO_DATA.get(value_lower)
                      resolved_artist_data = data if data else None
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if resolved_artist_data: parsed_settings_data["artist"] = resolved_artist_data; logger.debug(f"Parsed Artist: {resolved_artist_data.get('alias')}")
                 else: logger.warning(f"Artist '{value_str}' not found.")
             processed_flags_this_pass.update(flag_aliases)

    # Final checks (remain the same)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if parsed_settings_data["randomize_type"] and (parsed_settings_data["type"] is not None or parsed_settings_data["type_choice_list"] is not None) : logger.warning("Random type flag set, but specific type/list also provided. Specific type/list ignored."); parsed_settings_data["type"] = None; parsed_settings_data["type_choice_list"] = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if parsed_settings_data["randomize_style"] and (parsed_settings_data["style"] is not None or parsed_settings_data["style_choice_list"] is not None): logger.warning("Random style flag/group set, but specific style/list also provided. Specific style/list ignored."); parsed_settings_data["style"] = None; parsed_settings_data["style_choice_list"] = None; parsed_settings_data["style_marker"] = RANDOM_MARKER_GLOBAL_STYLE # Ensure marker reflects random choice
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if parsed_settings_data["randomize_artist"] and (parsed_settings_data["artist"] is not None or parsed_settings_data["artist_choice_list"] is not None): logger.warning("Random artist flag set, but specific artist/list also provided. Specific artist/list ignored."); parsed_settings_data["artist"] = None; parsed_settings_data["artist_choice_list"] = None

    # Clean up prompt text if it starts with command triggers like !, /img
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if prompt_text.startswith("!") or prompt_text.startswith("/img"):
        prompt_text = re.sub(r"^(?:!|/img)\s*", "", prompt_text, count=1)

    logger.debug(f"Final parsed settings data: {parsed_settings_data}")
    return prompt_text, parsed_settings_data
# ================================== parse_img_args_prompt_first() end ==================================


# ================================== _determine_context(): Helper to get chat/user/reply info ==================================
def _determine_context(update: Optional[Update], query: Optional[CallbackQuery]) -> Tuple[Optional[Chat], Optional[Any], Optional[int], Optional[Message]]:
    chat = None
    user = None
    reply_to_msg_id = None
    source_message_for_reply = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if query and query.message:
        chat = query.message.chat
        user = query.from_user
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if query.message.reply_to_message:
            reply_to_msg_id = query.message.reply_to_message.message_id
            source_message_for_reply = query.message.reply_to_message
        else:
            reply_to_msg_id = query.message.message_id
            source_message_for_reply = query.message
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not user:
            user = query.message.from_user
            logger.warning("Using query.message.from_user.")
        logger.debug(f"Context from Query: Chat={chat.id if chat else 'N/A'}, User={user.id if user else 'N/A'}, ReplyTo={reply_to_msg_id}")
    elif update and update.effective_chat and update.effective_user and update.message:
        chat = update.effective_chat
        user = update.effective_user
        reply_to_msg_id = update.message.message_id
        source_message_for_reply = update.message
        logger.debug(f"Context from Update: Chat={chat.id if chat else 'N/A'}, User={user.id if user else 'N/A'}, ReplyTo={reply_to_msg_id}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not chat or not user or not reply_to_msg_id or not source_message_for_reply:
        logger.error(f"Failed determine context. C:{chat is not None} U:{user is not None} R:{reply_to_msg_id} S:{source_message_for_reply is not None}")
        return None, None, None, None
    return chat, user, reply_to_msg_id, source_message_for_reply
# ================================== _determine_context() end ==================================


# ================================== _send_processing_message(): Sends the initial "processing" message ==================================
# This function is called from contexts where the source_message might not be a 'live' object,
# so we should use context.bot.send_message explicitly.
async def _send_processing_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, reply_to_message_id: int, user_mention: str, action_text: str = "генерирую изображение") -> Optional[Message]:
    """
    Sends an initial 'processing' message as a reply to a specific message ID.
    Returns the sent Message object or None on failure.
    """
    processing_msg = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        # Use context.bot.send_message directly, specifying chat_id and reply_to_message_id
        processing_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ {action_text}...",
            parse_mode=ParseMode.HTML, # Use HTML for user_mention
            reply_to_message_id=reply_to_message_id
        )
        logger.debug(f"Sent '{action_text}' msg {processing_msg.message_id} reply to {reply_to_message_id}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Failed send '{action_text}' reply msg to chat {chat_id}, replying to {reply_to_message_id}: {e}", exc_info=True)
        # If even this fails, there's not much more we can do to inform the user here.
        processing_msg = None # Ensure processing_msg is None if sending fails

    return processing_msg
# ================================== _send_processing_message() end ==================================


# ================================== _resolve_settings(): Resolves parsed settings, handling randomization markers & groups ==================================
def _resolve_settings(parsed_settings_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int | None, int | None, int | None]:
    """Resolves final type, style, artist based on parsed data, including randomization flags, choice lists, and markers."""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    import config # Ensure config is accessible
    import random # Ensure random is imported

    # Start with values explicitly set by the parser (could be None)
    type_data = parsed_settings_data.get("type")
    style_data = parsed_settings_data.get("style") # Specific style data if provided
    artist_data = parsed_settings_data.get("artist")
    selected_ar = parsed_settings_data.get("ar")

    # Get choice lists and randomization flags
    type_choice_list = parsed_settings_data.get("type_choice_list")
    style_choice_list = parsed_settings_data.get("style_choice_list")
    artist_choice_list = parsed_settings_data.get("artist_choice_list")

    should_randomize_type = parsed_settings_data.get("randomize_type", False)
    should_randomize_artist = parsed_settings_data.get("randomize_artist", False)
    style_marker = parsed_settings_data.get("style_marker") # None, RANDOM_GLOBAL, RANDOM_RELATIVE, RANDOM_GROUP:<key>, or specific data

    resolved_type_data = type_data
    resolved_style_data = style_data if style_marker is style_data else None # Start with specific style ONLY if marker points to it
    resolved_artist_data = artist_data

    # --- Resolve Type (Priority: List -> Specific -> Random Flag) ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if type_choice_list:
        logger.debug(f"Resolving random Type from list: {type_choice_list}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            chosen_type_index = random.choice(type_choice_list)
            resolved_type_data = config.TYPE_INDEX_TO_DATA.get(chosen_type_index)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if resolved_type_data: logger.info(f"Random type from list resolved: [{chosen_type_index}] {resolved_type_data.get('alias')}")
            else: logger.warning(f"Chosen type index {chosen_type_index} from list not found in config. Falling back."); resolved_type_data = None # Fallback needed
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except IndexError: logger.warning("Type choice list was empty. Falling back."); resolved_type_data = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: logger.error(f"Error choosing from type list: {e}"); resolved_type_data = None
        # If list choice failed, allow fallback to general randomization if flag was set
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not resolved_type_data and should_randomize_type: logger.debug("List choice failed, fallback to general random type flag.")
        elif resolved_type_data: should_randomize_type = False # Don't use general random flag if list choice succeeded

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not resolved_type_data and should_randomize_type: # Handle general random flag only if no list/specific type chosen
        logger.debug("Resolving general random Type.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if config.MAIN_TYPES_DATA: resolved_type_data = random.choice(config.MAIN_TYPES_DATA); logger.info(f"Random type resolved: {resolved_type_data.get('alias')}")
        else: logger.error("Cannot select random type: MAIN_TYPES_DATA is empty."); resolved_type_data = None
    elif not resolved_type_data and type_data: # Use specific type if list/random flags didn't apply/succeed
         resolved_type_data = type_data; logger.debug(f"Using specific Type: {type_data.get('alias')}")


    # --- Resolve Style (Priority: List -> Specific -> Markers -> Random Flag) ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if style_choice_list:
        logger.debug(f"Resolving random Style from list: {style_choice_list}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            chosen_style_index = random.choice(style_choice_list)
            resolved_style_data = config.STYLE_ABSOLUTE_INDEX_TO_DATA.get(chosen_style_index)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if resolved_style_data:
                 logger.info(f"Random style from list resolved: [{chosen_style_index}] {resolved_style_data.get('alias')}")
                 style_marker = resolved_style_data # Mark specific style chosen
            else: logger.warning(f"Chosen style index {chosen_style_index} from list not found in config. Falling back."); resolved_style_data = None; style_marker = None # Fallback needed
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except IndexError: logger.warning("Style choice list was empty. Falling back."); resolved_style_data = None; style_marker = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: logger.error(f"Error choosing from style list: {e}"); resolved_style_data = None; style_marker = None
        # If list choice failed, allow fallback to marker/flag logic
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not resolved_style_data and style_marker is not None: logger.debug("List choice failed, fallback to style marker/flag logic.")
        # Otherwise, if list succeeded, subsequent marker/flag logic will be skipped because style_marker is now specific data

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not resolved_style_data: # Only proceed if list choice didn't succeed or wasn't present
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if style_marker == RANDOM_MARKER_RELATIVE_STYLE:
            logger.debug("Resolving RELATIVE random Style.")
            possible_styles = []; type_styles_failed = False
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if resolved_type_data:
                type_name = resolved_type_data.get('name'); type_config = config.TYPE_NAME_TO_DATA.get(type_name.lower()) if type_name else None
                style_keys = type_config.get('style_keys', []) if type_config else []; seen_style_names = set()
                for key in style_keys:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if key == 'artists': continue
                    style_list = config.STYLE_LISTS.get(key, [])
                    for item in style_list:
                        name_lower = item.get('name','').lower()
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        if name_lower and name_lower not in seen_style_names: possible_styles.append(item); seen_style_names.add(name_lower)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not possible_styles: type_styles_failed = True; logger.warning(f"No relevant styles for type '{resolved_type_data.get('alias')}' found for relative random. Falling back to global.")
            else: type_styles_failed = True; logger.warning("Relative random style requested (-s0) but no Type resolved. Falling back to global.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if type_styles_failed: style_marker = RANDOM_MARKER_GLOBAL_STYLE # Fallback marker
            elif possible_styles: resolved_style_data = random.choice(possible_styles); logger.info(f"Random relative style resolved: {resolved_style_data.get('alias')}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        elif isinstance(style_marker, str) and style_marker.startswith(RANDOM_MARKER_GROUP_STYLE_PREFIX):
            group_key = style_marker.split(':', 1)[1]
            logger.debug(f"Resolving GROUP random Style for group key: '{group_key}'.")
            style_list = config.STYLE_LISTS.get(group_key, [])
            group_styles_failed = False
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if style_list and isinstance(style_list, list):
                valid_styles_in_group = [item for item in style_list if isinstance(item, dict) and 'name' in item]
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if valid_styles_in_group: resolved_style_data = random.choice(valid_styles_in_group); logger.info(f"Random group '{group_key}' style resolved: {resolved_style_data.get('alias')}")
                else: group_styles_failed = True; logger.warning(f"Style group '{group_key}' is empty. Falling back to global random.")
            else: group_styles_failed = True; logger.warning(f"Style group key '{group_key}' not found or not a list. Falling back to global random.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if group_styles_failed: style_marker = RANDOM_MARKER_GLOBAL_STYLE # Fallback marker
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if style_marker == RANDOM_MARKER_GLOBAL_STYLE: # Handles -s flag OR fallback from relative/group
             logger.debug("Resolving GLOBAL random Style.")
             # Reminder: Use new line, not semicolon, for the following block/statement.
             if config.ALL_STYLES_DATA: resolved_style_data = random.choice(config.ALL_STYLES_DATA); logger.info(f"Random global style resolved: {resolved_style_data.get('alias')}")
             else: logger.error("Cannot select global random style: ALL_STYLES_DATA is empty."); resolved_style_data = None
        elif style_marker and style_marker not in [RANDOM_MARKER_GLOBAL_STYLE, RANDOM_MARKER_RELATIVE_STYLE] and not isinstance(style_marker, str): # Specific style object was set as marker
             logger.debug(f"Using specific Style from marker: {style_marker.get('alias')}")
             resolved_style_data = style_marker # Use the data stored as the marker
        elif not style_marker and style_data: # Fallback to specifically parsed style data if no marker applied
            logger.debug(f"Using specific Style from initial parse data: {style_data.get('alias')}")
            resolved_style_data = style_data

    # --- Resolve Artist (Priority: List -> Specific -> Random Flag) ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if artist_choice_list:
        logger.debug(f"Resolving random Artist from list: {artist_choice_list}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            chosen_artist_index = random.choice(artist_choice_list)
            resolved_artist_data = config.ARTIST_ABSOLUTE_INDEX_TO_DATA.get(chosen_artist_index)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if resolved_artist_data: logger.info(f"Random artist from list resolved: [{chosen_artist_index}] {resolved_artist_data.get('alias')}")
            else: logger.warning(f"Chosen artist index {chosen_artist_index} from list not found in config. Falling back."); resolved_artist_data = None # Fallback needed
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except IndexError: logger.warning("Artist choice list was empty. Falling back."); resolved_artist_data = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: logger.error(f"Error choosing from artist list: {e}"); resolved_artist_data = None
        # If list choice failed, allow fallback to general randomization if flag was set
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not resolved_artist_data and should_randomize_artist: logger.debug("List choice failed, fallback to general random artist flag.")
        elif resolved_artist_data: should_randomize_artist = False # Don't use general random flag if list choice succeeded

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not resolved_artist_data and should_randomize_artist: # Handle general random flag only if no list/specific artist chosen
        logger.debug("Resolving general random Artist.")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if config.ALL_ARTISTS_DATA: resolved_artist_data = random.choice(config.ALL_ARTISTS_DATA); logger.info(f"Random artist resolved: {resolved_artist_data.get('alias')}")
        else: logger.error("Cannot select random artist: ALL_ARTISTS_DATA is empty."); resolved_artist_data = None
    elif not resolved_artist_data and artist_data: # Use specific artist if list/random flags didn't apply/succeed
         resolved_artist_data = artist_data; logger.debug(f"Using specific Artist: {artist_data.get('alias')}")


    # --- Determine Indices ---
    type_idx = None; style_idx = None; artist_idx = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if resolved_type_data: type_idx = next((i for i, d in config.TYPE_INDEX_TO_DATA.items() if d.get('id') == resolved_type_data.get('id')), None)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if resolved_style_data: style_idx = config.STYLE_NAME_TO_ABSOLUTE_INDEX.get(resolved_style_data.get('name','').lower())
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if resolved_artist_data: artist_idx = config.ARTIST_NAME_TO_ABSOLUTE_INDEX.get(resolved_artist_data.get('name','').lower())

    # --- Combine final results ---
    final_settings = {"type_data": resolved_type_data, "style_data": resolved_style_data, "artist_data": resolved_artist_data, "ar": selected_ar}
    logger.debug(f"Resolved settings: Type={resolved_type_data.get('alias') if resolved_type_data else 'N/A'} (#{type_idx}), Style={resolved_style_data.get('alias') if resolved_style_data else 'N/A'} (#{style_idx}), Artist={resolved_artist_data.get('alias') if resolved_artist_data else 'N/A'} (#{artist_idx}), AR={selected_ar}")
    return final_settings, type_idx, style_idx, artist_idx
# ================================== _resolve_settings() end ==================================


async def _initiate_image_generation(
    update: Optional[Update], context: ContextTypes.DEFAULT_TYPE, query: Optional[CallbackQuery],
    user_prompt: str, parsed_settings_data: Dict[str, Any], original_prompt_for_display: str,
    base_image_bytes: Optional[bytes] = None, user_image_bytes: Optional[bytes] = None,
    user_uploaded_base_image_file_id: Optional[str] = None,
    source_image_file_id_1_for_passthrough: Optional[str] = None,
    source_image_file_id_2_for_passthrough: Optional[str] = None
):
    chat, user, reply_to_msg_id, source_message = _determine_context(update, query) # source_message is used for context, reply_to_msg_id is for the actual reply
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not chat or not user or not reply_to_msg_id: # Ensure reply_to_msg_id is also valid
        logger.error("Generation failed: Could not determine context (chat, user, or reply_to_msg_id).")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if query and query.message: # Try to send error to query user if possible
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try: await query.message.reply_text("❌ Ошибка: не удалось определить контекст для генерации.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as e_reply: logger.error(f"Failed to send context error message: {e_reply}")
        elif update and update.message:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try: await update.message.reply_text("❌ Ошибка: не удалось определить контекст для генерации.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as e_reply: logger.error(f"Failed to send context error message: {e_reply}")
        return

    user_mention = user.mention_html()
    
    # Call the updated _send_processing_message
    processing_msg = await _send_processing_message(
        context=context,
        chat_id=chat.id,
        reply_to_message_id=reply_to_msg_id, # Use the determined reply_to_msg_id
        user_mention=user_mention,
        action_text="генерирую изображение"
    )

    # Resolve the settings based on parsed data (handles randomization)
    resolved_settings, type_idx, style_idx, artist_idx = _resolve_settings(parsed_settings_data)
    resolved_settings_tuple = (resolved_settings, type_idx, style_idx, artist_idx)
    
    # Get chat-specific image suffix from chat_data (or default)
    # Since this function can be called from various contexts (direct command, callback, job),
    # we need to robustly access chat_data.
    # For direct handlers (update is not None), context.chat_data is fine.
    # For callbacks (query is not None), context.chat_data might be available via query.message.chat_id.
    # For jobs, we'd need to pass chat_id and use application.bot_data.
    # Let's assume for now that if this function is called, chat.id is valid.
    system_suffix = ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if context.application.bot_data.get('chat_data') and chat.id in context.application.bot_data['chat_data']:
        system_suffix = context.application.bot_data['chat_data'][chat.id].get(CHAT_DATA_KEY_IMAGE_SUFFIX, DEFAULT_IMAGE_PROMPT_SUFFIX)
    else: # Fallback if chat_data for this specific chat isn't initialized in bot_data yet
        system_suffix = DEFAULT_IMAGE_PROMPT_SUFFIX
        logger.debug(f"Chat data for {chat.id} not found in bot_data for suffix, using default.")


    # Construct the prompt using RESOLVED settings
    final_api_prompt = construct_prompt_with_style(
        base_prompt=user_prompt, 
        selected_type_data=resolved_settings["type_data"],
        selected_style_data=resolved_settings["style_data"],
        selected_artist_data=resolved_settings["artist_data"],
        selected_ar=resolved_settings["ar"],
        suffix_text=system_suffix
    )
    logger.info(f"Constructed API prompt (Gen): '{final_api_prompt[:200]}...'")

    api_text, api_img, api_err = await generate_image_with_gemini(
        final_api_prompt, 
        input_image_original=base_image_bytes, 
        input_image_user=user_image_bytes
    )
    
    await send_image_generation_response(
        context, chat.id, reply_to_msg_id, processing_msg.message_id if processing_msg else None,
        api_text, api_img, api_err,
        original_prompt_for_display, 
        resolved_settings_tuple, 
        final_api_prompt,
        original_parsed_settings_data=parsed_settings_data,
        base_image_file_id_for_regen=user_uploaded_base_image_file_id,
        source_image_file_id_1_for_regen=source_image_file_id_1_for_passthrough,
        source_image_file_id_2_for_regen=source_image_file_id_2_for_passthrough
    )
# ================================== _initiate_image_generation() end ==================================


# ================================== _initiate_image_editing(): For targeted edits (Apply button, /edit, arg-only reply) ==================================
async def _initiate_image_editing(
    context: ContextTypes.DEFAULT_TYPE, base_image_bytes: bytes,
    current_settings: Dict[str, Any], original_settings: Dict[str, Any],
    current_effective_prompt: str, original_user_prompt: str, original_api_prompt: str,
    chat_id: int, user_id: int, user_mention: str, reply_to_msg_id: int, source_message: Message
):
    processing_msg = await _send_processing_message(
        context=context,
        chat_id=chat_id, # Use the passed chat_id
        reply_to_message_id=reply_to_msg_id, # This is the ID of the user's message triggering the edit
        user_mention=user_mention,
        action_text="применяю изменения"
    )
    changed_params = []; edit_instructions = []
    current_ar = current_settings.get("ar"); original_ar = original_settings.get("ar")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_ar != original_ar: changed_params.append("AR"); edit_instructions.append(f"Set aspect ratio to {current_ar}" if current_ar else "Remove aspect ratio constraint")
    current_type_data = current_settings.get("type_data"); original_type_data = original_settings.get("type_data")
    current_type_id = (current_type_data or {}).get('id'); original_type_id = (original_type_data or {}).get('id')
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_type_id != original_type_id: changed_params.append("Type"); edit_instructions.append(f"Change type to '{current_type_data['name']}'" if current_type_data else "Remove type specification")
    current_style_data = current_settings.get("style_data"); original_style_data = original_settings.get("style_data")
    current_style_name = (current_style_data or {}).get('name'); original_style_name = (original_style_data or {}).get('name')
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_style_name != original_style_name: changed_params.append("Style"); edit_instructions.append(f"Apply style '{current_style_data['name']}'" if current_style_data else "Remove style specification")
    current_artist_data = current_settings.get("artist_data"); original_artist_data = original_settings.get("artist_data")
    current_artist_name = (current_artist_data or {}).get('name'); original_artist_name = (original_artist_data or {}).get('name')
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_artist_name != original_artist_name: changed_params.append("Artist"); edit_instructions.append(f"Apply artist style '{current_artist_data['name']}'" if current_artist_data else "Remove artist specification")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if current_effective_prompt != original_user_prompt: changed_params.append("Prompt"); edit_instructions.append(f"Use description: '{current_effective_prompt}'")

    logger.info(f"Edit diff: Changed params = {changed_params}")
    final_edit_prompt = ""; num_changes = len(changed_params); description_request = " Describe changes you made in Russian."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if num_changes == 0: final_edit_prompt = "Redraw the provided image." + description_request; logger.info(f"Edit prompt: No changes detected.")
    elif num_changes == 1: final_edit_prompt = f"Edit the provided image: {edit_instructions[0]}." + description_request; logger.info(f"Edit prompt (single: {changed_params[0]}): {final_edit_prompt}")
    else: instruction_str = " - " + "\n - ".join(edit_instructions); final_edit_prompt = f"Edit the provided image with the following changes:\n{instruction_str}" + description_request; logger.info(f"Edit prompt (multiple: {changed_params}): {final_edit_prompt}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not final_edit_prompt.strip().startswith(("Edit", "Redraw")): logger.warning("Unexpected edit prompt format."); final_edit_prompt = "Redraw the provided image." + description_request

    api_text, api_img, api_err = await generate_image_with_gemini(final_edit_prompt, base_image_bytes, None)

    # Re-resolve indices based on the 'current_settings' which ARE the resolved settings for this edit
    resolved_settings_direct = current_settings # These are already resolved
    type_idx_direct = None; style_idx_direct = None; artist_idx_direct = None
    type_data_direct = resolved_settings_direct.get("type_data")
    style_data_direct = resolved_settings_direct.get("style_data")
    artist_data_direct = resolved_settings_direct.get("artist_data")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if type_data_direct: type_idx_direct = next((i for i, d in TYPE_INDEX_TO_DATA.items() if d['id'] == type_data_direct['id']), None)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if style_data_direct: style_idx_direct = STYLE_NAME_TO_ABSOLUTE_INDEX.get(style_data_direct.get('name','').lower())
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if artist_data_direct: artist_idx_direct = ARTIST_NAME_TO_ABSOLUTE_INDEX.get(artist_data_direct.get('name','').lower())
    resolved_settings_tuple = (resolved_settings_direct, type_idx_direct, style_idx_direct, artist_idx_direct)

    # For edited images, we don't have original *parsed* settings readily available
    # Storing None for original_parsed_settings to signify it was an edit/apply action
    # Re-Gen won't work correctly on messages generated by "Apply" if this is None,
    # but Apply itself only depends on the current state.
    # A potential improvement could be to pass the original message's state here.
    original_parsed_settings_for_state = None
    logger.debug("Setting original_parsed_settings to None for state of 'Apply' result.")

    await send_image_generation_response(
        context, chat_id, reply_to_msg_id, processing_msg.message_id if processing_msg else None,
        api_text, api_img, api_err,
        original_user_prompt, 
        resolved_settings_tuple, 
        final_edit_prompt, 
        original_parsed_settings_data=None, 
        base_image_file_id_for_regen=None 
    )
# ================================== _initiate_image_editing() end ==================================


# ================================== _initiate_image_combination(): For combining two images ==================================
async def _initiate_image_combination(
    context: ContextTypes.DEFAULT_TYPE, base_image_bytes: bytes, user_image_bytes: bytes,
    user_prompt: str, chat_id: int, user_id: int, user_mention: str, reply_to_msg_id: int, source_message: Message,
    original_file_id_1: str, original_file_id_2: str # <<< ADD THESE
):
    processing_msg = await _send_processing_message(
        context=context,
        chat_id=chat_id, # Use the passed chat_id
        reply_to_message_id=reply_to_msg_id, # This is the ID of the first message in group or user's reply
        user_mention=user_mention,
        action_text="комбинирую изображения"
    )
    final_api_prompt = user_prompt
    logger.info(f"API prompt (Combine): '{final_api_prompt[:200]}...'")

    # generate_image_with_gemini already accepts two images
    api_text, api_img, api_err = await generate_image_with_gemini(
        prompt=final_api_prompt,
        input_image_original=base_image_bytes, # First image
        input_image_user=user_image_bytes      # Second image
    )

    # For combined images, the "settings" are effectively null as it's a direct operation
    final_settings_for_state = {"type_data": None, "style_data": None, "artist_data": None, "ar": None}
    
    await send_image_generation_response(
        context=context,
        chat_id=chat_id,
        reply_to_message_id=reply_to_msg_id,
        processing_msg_id=processing_msg.message_id if processing_msg else None,
        api_text_result=api_text,
        api_image_bytes=api_img,
        api_error_message=api_err,
        original_user_prompt=user_prompt if user_prompt != DEFAULT_COMBINE_PROMPT_TEXT else "",
        resolved_settings_tuple=(final_settings_for_state, None, None, None),
        prompt_used_for_api=final_api_prompt,
        original_parsed_settings_data=None,
        source_image_file_id_1_for_regen=original_file_id_1,
        source_image_file_id_2_for_regen=original_file_id_2
    )
# ================================== _initiate_image_combination() end ==================================


# ================================== handle_img_command(): Handles /img command ==================================
@restrict_private_unauthorized
async def handle_img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_user:
        return
    full_text = " ".join(context.args).strip() if context.args else ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not full_text:
        await update.message.reply_text("⚠️ Укажите запрос после /img.")
        return
    user_prompt, parsed_settings_data = parse_img_args_prompt_first(full_text)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user_prompt and not any(v is not None for k,v in parsed_settings_data.items() if k!='randomize'):
        await update.message.reply_text("⚠️ Укажите текст или аргументы.")
        return
    elif not user_prompt and any(v is not None for k,v in parsed_settings_data.items() if k!='randomize'):
        await update.message.reply_text("⚠️ Укажите текст перед аргументами.")
        return
    logger.info(f"/img запрос. Args: {parsed_settings_data}, Prompt: '{user_prompt[:100]}...'")
    await _initiate_image_generation(
        update=update, context=context, query=None, user_prompt=user_prompt,
        parsed_settings_data=parsed_settings_data, original_prompt_for_display=user_prompt
    )
# ================================== handle_img_command() end ==================================


# ================================== handle_img_shortcut(): Handles ! shortcut ==================================
@restrict_private_unauthorized
async def handle_img_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.message.text or not update.effective_user:
        return
    full_text = ""
    match = context.matches[0] if context.matches else None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if match and len(match.groups()) >= 1:
        full_text = match.group(1).strip()
    else:
        logger.warning(f"Не удалось извлечь текст из '!': {update.message.text}")
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not full_text:
        await update.message.reply_text("⚠️ Укажите запрос после !")
        return
    user_prompt, parsed_settings_data = parse_img_args_prompt_first(full_text)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user_prompt and not any(v is not None for k,v in parsed_settings_data.items() if k!='randomize'):
        await update.message.reply_text("⚠️ Укажите текст или аргументы.")
        return
    elif not user_prompt and any(v is not None for k,v in parsed_settings_data.items() if k!='randomize'):
        await update.message.reply_text("⚠️ Укажите текст перед аргументами.")
        return
    logger.info(f"! shortcut. Args: {parsed_settings_data}, Prompt: '{user_prompt[:100]}...'")
    await _initiate_image_generation(
        update=update, context=context, query=None, user_prompt=user_prompt,
        parsed_settings_data=parsed_settings_data, original_prompt_for_display=user_prompt
    )
# ================================== handle_img_shortcut() end ==================================


# ================================== handle_random_img_shortcut(): Handles !! shortcut ==================================
async def handle_random_img_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context):
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.message.text or not update.effective_user:
        return
    full_text = ""
    match = context.matches[0] if context.matches else None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if match and len(match.groups()) >= 1:
        full_text = match.group(1).strip()
    else:
        logger.warning(f"Не удалось извлечь текст из '!!': {update.message.text}")
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not full_text:
        await update.message.reply_text("⚠️ Укажите запрос после !!")
        return
    user_prompt, parsed_settings_data = parse_img_args_prompt_first(full_text)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user_prompt:
        user_prompt = "random"
    # Explicitly set randomization flags for !!
    parsed_settings_data["randomize_type"] = True
    parsed_settings_data["randomize_style"] = True
    parsed_settings_data["style_marker"] = RANDOM_MARKER_GLOBAL_STYLE # !! implies global style random
    parsed_settings_data["randomize_artist"] = True
    logger.info(f"!! shortcut (random). Args: {parsed_settings_data}, Prompt: '{user_prompt[:100]}...'")
    await _initiate_image_generation(
        update=update, context=context, query=None, user_prompt=user_prompt,
        parsed_settings_data=parsed_settings_data, original_prompt_for_display=user_prompt
    )
# ================================== handle_random_img_shortcut() end ==================================


# ================================== handle_image_with_caption(): Handles single photo + caption (with flags or auto-describe) ==================================
@restrict_private_unauthorized
async def handle_image_with_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.message.photo or not update.message.caption: return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if update.message.media_group_id or update.message.reply_to_message: return
    chat = update.effective_chat; user = update.effective_user; message = update.message
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not chat or not user: return
    photo = message.photo[-1]; file_id = photo.file_id
    full_text_caption = message.caption.strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not full_text_caption: await message.reply_text("⚠️ Добавьте подпись к фото."); return

    # --- Download Image Bytes Early ---
    dl_status_msg = await message.reply_text("⏳ Загрузка фото...")
    image_bytes = await get_cached_image_bytes(context, file_id, chat)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if dl_status_msg: await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not image_bytes: await message.reply_text(f"❌ Ошибка загрузки фото ({file_id})."); return

    # --- Parse Caption ---
    user_prompt, parsed_settings_data = parse_img_args_prompt_first(full_text_caption)
    api_prompt_to_use = user_prompt # Default: use parsed prompt
    original_prompt_for_display = user_prompt # Default: display parsed prompt

    # --- Check for Flags-Only Case ---
    has_meaningful_args = (
        parsed_settings_data.get("type") is not None or
        parsed_settings_data.get("style") is not None or
        parsed_settings_data.get("artist") is not None or
        parsed_settings_data.get("ar") is not None or
        parsed_settings_data.get("randomize_type") or
        parsed_settings_data.get("randomize_style") or # Covers -s, -s0, -s group
        parsed_settings_data.get("randomize_artist")
    )

    # --- If ONLY flags are present, try to describe the image ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user_prompt and has_meaningful_args:
        logger.info(f"Caption contained only flags ('{full_text_caption}'). Trying to describe image {file_id}...")
        describe_status_msg = await message.reply_text("⏳ Описываю фото...")
        description, desc_error = await describe_image_with_gemini(image_bytes)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if describe_status_msg: await delete_message_safely(context, describe_status_msg.chat_id, describe_status_msg.message_id)

        # Reminder: Use new line, not semicolon, for the following block/statement.
        if description:
            api_prompt_to_use = description.strip()
            original_prompt_for_display = description.strip() # Use description for display too
            logger.info(f"Auto-description successful. Using as prompt: '{api_prompt_to_use[:100]}...'")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            pass
        else:
            # Fallback if description fails
            fallback_api_prompt = "redraw with specified style"
            api_prompt_to_use = fallback_api_prompt
            original_prompt_for_display = "" # FIX: Use empty string, not flags
            logger.warning(f"Auto-description failed ({desc_error}). Falling back to API prompt: '{fallback_api_prompt}', display prompt: ''")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            pass

    elif user_prompt:
        # If there was a prompt, display only the prompt part, not the flags
        original_prompt_for_display = user_prompt
        logger.info(f"Фото с подписью. Промпт: '{user_prompt[:100]}...', Args: {parsed_settings_data}")
    else:
        # No prompt and no meaningful flags, treat caption as prompt
        api_prompt_to_use = full_text_caption
        original_prompt_for_display = full_text_caption
        logger.info(f"Фото с подписью без флагов. Промпт: '{full_text_caption[:100]}...'")


    # --- Initiate Generation ---
    await _initiate_image_generation(
        update=update, context=context, query=None,
        user_prompt=api_prompt_to_use, # Use the determined prompt for API
        parsed_settings_data=parsed_settings_data,
        original_prompt_for_display=original_prompt_for_display, # Show original text or description
        base_image_bytes=image_bytes, # Pass the downloaded image bytes
        user_uploaded_base_image_file_id=file_id # Pass the file_id of the user's uploaded image
    )
# ================================== handle_image_with_caption() end ==================================


# ================================== handle_photo_reply_to_image(): Handles photo reply to bot image ==================================
@restrict_private_unauthorized
async def handle_photo_reply_to_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if not await is_authorized(update, context):
         return
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if not (update.message and update.message.photo and update.message.reply_to_message):
         return
     replied_msg = update.message.reply_to_message
     user = update.effective_user
     chat = update.effective_chat
     message = update.message
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if not (user and chat and replied_msg.from_user and replied_msg.from_user.is_bot and replied_msg.from_user.id == context.bot.id and replied_msg.photo):
         return
     user_prompt = DEFAULT_COMBINE_PROMPT_TEXT
     prompt_source = "стандарт (комбинация)"
     caption_text = message.caption.strip() if message.caption else ""
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if caption_text:
         user_prompt = caption_text
         prompt_source = "подпись"
     logger.info(f"Фото-ответ ({prompt_source})... -> Комбинация")
     # Reminder: Use new line, not semicolon, for the following block/statement.
     try:
         original_bot_photo = replied_msg.photo[-1]
         user_reply_photo = message.photo[-1]
         original_file_id = original_bot_photo.file_id
         user_file_id = user_reply_photo.file_id
     # Reminder: Use new line, not semicolon, for the following block/statement.
     except Exception as e:
         logger.error(f"Ошибка file_id: {e}")
         await message.reply_text("❌ Ошибка info фото.")
         return
     dl_status_msg = await message.reply_text("⏳ Загрузка...")
     img_bytes_original, img_bytes_user = None, None
     # Reminder: Use new line, not semicolon, for the following block/statement.
     try:
         img_bytes_original, img_bytes_user = await asyncio.gather(get_cached_image_bytes(context, original_file_id, chat), get_cached_image_bytes(context, user_file_id, chat), return_exceptions=True)
     finally:
         # Reminder: Use new line, not semicolon, for the following block/statement.
         if dl_status_msg: await delete_message_safely(context, dl_status_msg.chat_id, dl_status_msg.message_id)
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if isinstance(img_bytes_original, Exception) or not img_bytes_original:
         logger.error(f"Ошибка загрузки оригинала ({original_file_id}): {img_bytes_original}")
         img_bytes_original = None
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if isinstance(img_bytes_user, Exception) or not img_bytes_user:
         logger.error(f"Ошибка загрузки ответа ({user_file_id}): {img_bytes_user}")
         img_bytes_user = None
     # Reminder: Use new line, not semicolon, for the following block/statement.
     if not img_bytes_original or not img_bytes_user:
         await _initiate_image_combination(
         context=context, 
         base_image_bytes=img_bytes_original, # Bytes of the first image
         user_image_bytes=img_bytes_user,      # Bytes of the second image
         user_prompt=user_prompt, 
         chat_id=chat.id, 
         user_id=user.id, 
         user_mention=user.mention_html(),
         reply_to_msg_id=message.message_id, 
         source_message=message,
         original_file_id_1=original_file_id, # <<< Pass the file ID of the bot's original photo
         original_file_id_2=user_file_id      # <<< Pass the file ID of the user's reply photo
     )
# ================================== handle_photo_reply_to_image() end ==================================


# handlers/image_gen.py end
