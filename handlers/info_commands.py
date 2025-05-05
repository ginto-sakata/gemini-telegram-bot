# handlers/info_commands.py
# -*- coding: utf-8 -*-
"""
Handlers for informational commands listing types, styles, artists,
and a combined list. Includes style group aliases.
"""
import logging
from html import escape
import re
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.auth import is_authorized
import config
from utils.telegram_helpers import delete_message_safely # Import config to access the loaded data

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096

# ================================== send_long_message(): Splits long messages ==================================
async def send_long_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, title: str):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message: return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if len(text) <= MAX_MESSAGE_LENGTH:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try: await update.message.reply_html(text)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: logger.error(f"Ошибка отправки сообщения ({title}): {e}"); await update.message.reply_text(f"❌ Ошибка отображения списка '{title}'.")
    else:
        logger.warning(f"Сообщение '{title}' слишком длинное ({len(text)}), будет разбито.")
        parts = []
        current_part = f"<b>{escape(title)}</b>\n\n" # Start first part with title
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            lines = text.split('\n')
            # Start from the line after the title if it's present (it should be)
            start_line_index = 1 if lines[0] == f"<b>{escape(title)}</b>" else 0
            # Reminder: Use new line, not semicolon, for the following block/statement.
            for line in lines[start_line_index:]: # Skip original title line
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not line.strip() and not current_part.strip().endswith("\n\n"): # Prevent excessive blank lines
                      current_part += "\n"
                      continue
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if len(current_part) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                    parts.append(current_part.strip())
                    # Start new part *without* title, title added later
                    current_part = line + "\n"
                else:
                    current_part += line + "\n"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if current_part.strip(): parts.append(current_part.strip())
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not parts: parts.append("<i>(Пусто)</i>") # Handle empty case after splitting
            # Reminder: Use new line, not semicolon, for the following block/statement.
            for i, part in enumerate(parts):
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try:
                    part_title = f"<b>{escape(title)} (Часть {i+1}/{len(parts)})</b>\n\n" if len(parts) > 1 else f"<b>{escape(title)}</b>\n\n"
                    # Ensure content starts cleanly
                    part_content = part.strip()
                    await update.message.reply_html(f"{part_title}{part_content}")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except Exception as e_part: logger.error(f"Ошибка отправки части {i+1} ({title}): {e_part}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e_split: logger.error(f"Ошибка разбивки сообщения ({title}): {e_split}")
# ================================== send_long_message() end ==================================


# ================================== _get_types_list_text(): Generates text for types list ==================================
def _get_types_list_text() -> str:
    lines = ["<b>🎨 Доступные Типы:</b>\n"]
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not config.TYPE_INDEX_TO_DATA:
        lines.append("<i>(Нет доступных типов)</i>")
    else:
        # Pre-compute reverse group alias mapping for efficiency
        group_key_to_alias = {v: k for k, v in config.STYLE_GROUP_ALIASES.items()}
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, type_data in sorted(config.TYPE_INDEX_TO_DATA.items()):
            alias = type_data.get('alias', 'N/A'); emoji = type_data.get('emoji', '')
            type_line = f"<code>[{index}]</code> {emoji} {escape(alias)}"
            # Find applicable style group aliases
            style_keys = type_data.get('style_keys', [])
            group_aliases_for_type = []
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if style_keys:
                seen_groups = set()
                # Reminder: Use new line, not semicolon, for the following block/statement.
                for key in style_keys:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if key == 'artists': continue # Skip artist list
                    # Find the alias corresponding to this style key
                    group_alias = group_key_to_alias.get(key)
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if group_alias and group_alias not in seen_groups:
                        group_aliases_for_type.append(f"<code>{escape(group_alias)}</code>")
                        seen_groups.add(group_alias)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if group_aliases_for_type:
                 # Sort aliases alphabetically
                 group_aliases_for_type.sort()
                 type_line += f" (Группы: {', '.join(group_aliases_for_type)})"
            lines.append(type_line)
    return "\n".join(lines)
# ================================== _get_types_list_text() end ==================================


# ================================== list_types(): Handles /types command ==================================
async def list_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    logger.info("/types command received")
    text = _get_types_list_text()
    await send_long_message(update, context, text, "🎨 Доступные Типы")
# ================================== list_types() end ==================================


      
      
# ================================== _build_find_context_string(): Creates data string for LLM search ==================================
def _build_find_context_string() -> str:
    lines = []
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if config.TYPE_INDEX_TO_DATA:
        lines.append("\n**Типы:**")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, data in sorted(config.TYPE_INDEX_TO_DATA.items()):
            lines.append(f"[{index}] {data.get('emoji','')} {data.get('alias', 'N/A')}")

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if config.STYLE_ABSOLUTE_INDEX_TO_DATA:
        lines.append("\n**Стили:**")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, data in sorted(config.STYLE_ABSOLUTE_INDEX_TO_DATA.items()):
            lines.append(f"[{index}] {data.get('alias', 'N/A')}")

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if config.ARTIST_ABSOLUTE_INDEX_TO_DATA:
        lines.append("\n**Художники:**")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, data in sorted(config.ARTIST_ABSOLUTE_INDEX_TO_DATA.items()):
            short_alias_part = f" ({data['alias_short']})" if data.get('alias_short') and data['alias_short'] != data.get('alias') else ""
            lines.append(f"[{index}] {data.get('emoji','')} {data.get('alias', 'N/A')}{short_alias_part}")

    # --- Add Style Groups ---
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if config.STYLE_GROUP_ALIASES:
        lines.append("\n**Группы стилей:**")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for alias, group_key in sorted(config.STYLE_GROUP_ALIASES.items()):
             lines.append(f"- {alias} (Группа: {group_key})") # List the alias the user would type

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not lines:
        return "(No items available)"
    return "\n".join(lines)
# ================================== _build_find_context_string() end ==================================

    


# ================================== find_items(): Handles /find command using LLM search ==================================
async def find_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    # Imports needed within function scope if not at top-level
    import json
    from html import escape
    import re # Ensure re is imported

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message or not update.effective_user: return

    user_query = " ".join(context.args).strip() if context.args else ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not user_query:
        await update.message.reply_text("❓ Пожалуйста, укажите ваш поисковый запрос после команды /find.\nНапример: `/find стили для чертежей`")
        return

    logger.info(f"/find query from {update.effective_user.id}: '{user_query}'")

    # Build context and prompt
    data_context_str = _build_find_context_string()
    # Use the JSON output system prompt (corrected version)
    system_prompt_template = config._prompts_data.get('find_items_system_prompt', '')

    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not system_prompt_template:
        logger.error("System prompt 'find_items_system_prompt' not found in prompts.yaml!")
        await update.message.reply_text("❌ Ошибка конфигурации: не найден системный промпт для поиска.")
        return

    # Format the system prompt for the LLM
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        final_system_prompt = system_prompt_template.format(data_context=data_context_str)
        final_user_prompt = user_query # The actual user query
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Error formatting find prompt: {e}")
        await update.message.reply_text("❌ Ошибка подготовки запроса к LLM.")
        return

    # Send status message
    status_msg = None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        status_msg = await update.message.reply_text(f"🔎 Ищу по запросу: \"{escape(user_query)}\"...")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception: pass # Ignore if sending status fails

    # Call LLM
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        from api.gemini_api import generate_text_with_gemini_single # Local import for clarity
        llm_response, error_msg = await generate_text_with_gemini_single(
            user_prompt=final_user_prompt,
            system_prompt_text=final_system_prompt
        )

        # Delete status message
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if status_msg: await delete_message_safely(context, status_msg.chat_id, status_msg.message_id)

        # Reminder: Use new line, not semicolon, for the following block/statement.
        if error_msg:
            logger.error(f"LLM search failed: {error_msg}")
            await update.message.reply_html(f"❌ Ошибка при поиске: <pre>{escape(error_msg)}</pre>")
        elif llm_response:
            parsed_data = None
            human_readable_output = ""
            final_command_string = ""
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                # Clean the LLM response
                cleaned_llm_response = llm_response.strip()
                cleaned_llm_response = re.sub(r"^\s*```(?:json)?\s*\n?", "", cleaned_llm_response)
                cleaned_llm_response = re.sub(r"\n?\s*```\s*$", "", cleaned_llm_response)
                cleaned_llm_response = cleaned_llm_response.strip()

                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not cleaned_llm_response.startswith(("{", "[")):
                     raise json.JSONDecodeError("Doesn't start with { or [", cleaned_llm_response, 0)

                parsed_data = json.loads(cleaned_llm_response)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not isinstance(parsed_data, dict): raise ValueError("Root is not a dictionary")

                logger.debug(f"Successfully parsed JSON: {parsed_data}")

                # Extract data safely
                types_list = parsed_data.get("types", [])
                styles_list = parsed_data.get("styles", [])
                artists_list = parsed_data.get("artists", [])

                # --- Format Human-Readable List ---
                response_parts = []
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if types_list and isinstance(types_list, list):
                    response_parts.append("<b>Типы:</b>")
                    for item in types_list:
                         # Reminder: Use new line, not semicolon, for the following block/statement.
                         if isinstance(item, dict) and 'index' in item and 'name' in item:
                              emoji = item.get('emoji', '')
                              response_parts.append(f"<code>[{item['index']}]</code> {escape(emoji)} {escape(item['name'])}")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if styles_list and isinstance(styles_list, list):
                    response_parts.append("\n<b>Стили:</b>")
                    for item in styles_list:
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        if isinstance(item, dict) and 'index' in item and 'name' in item:
                            response_parts.append(f"<code>[{item['index']}]</code> {escape(item['name'])}")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if artists_list and isinstance(artists_list, list):
                     response_parts.append("\n<b>Художники:</b>")
                     for item in artists_list:
                         # Reminder: Use new line, not semicolon, for the following block/statement.
                         if isinstance(item, dict) and 'index' in item and 'name' in item:
                              emoji = item.get('emoji', '')
                              response_parts.append(f"<code>[{item['index']}]</code> {escape(emoji)} {escape(item['name'])}")

                human_readable_output = "\n".join(response_parts)

                # --- Generate Command String ---
                # Start with an empty list, flags will be added if indices exist
                command_string_parts = []
                type_indices = sorted([item['index'] for item in types_list if isinstance(item, dict) and 'index' in item])
                style_indices = sorted([item['index'] for item in styles_list if isinstance(item, dict) and 'index' in item])
                artist_indices = sorted([item['index'] for item in artists_list if isinstance(item, dict) and 'index' in item])

                # Reminder: Use new line, not semicolon, for the following block/statement.
                if type_indices: command_string_parts.append(f"-t({','.join(map(str, type_indices))})")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if style_indices: command_string_parts.append(f"-s({','.join(map(str, style_indices))})")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if artist_indices: command_string_parts.append(f"-a({','.join(map(str, artist_indices))})")

                # Reminder: Use new line, not semicolon, for the following block/statement.
                if command_string_parts: # Only add if any flags were generated
                     raw_command = ' '.join(command_string_parts)
                     escaped_command = escape(raw_command)
                     final_command_string = f"\n---\n<code>{escaped_command}</code>" # Wrap escaped args in <code>
                     logger.debug(f"Generated command string part: {final_command_string}")
                else:
                     logger.debug("No indices found, command string part not generated.")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from LLM: {e}\nOriginal Response: {llm_response}\nCleaned Response: {cleaned_llm_response}")
                human_readable_output = f"❌ Ошибка: LLM вернул невалидный JSON.\n<pre>{escape(llm_response)}</pre>"
                final_command_string = "" # Don't attempt command string on JSON error
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except (ValueError, TypeError, KeyError) as e: # Catch potential structure errors
                 logger.error(f"Invalid JSON structure or data: {e}\nResponse: {llm_response}", exc_info=True)
                 human_readable_output = f"❌ Ошибка: LLM вернул JSON с неверной структурой.\n<pre>{escape(llm_response)}</pre>"
                 final_command_string = "" # Don't attempt command string on structure error

            # --- Combine and Send ---
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if not human_readable_output.strip(): # Check if the formatted list is empty
                 await update.message.reply_text("🤷 По вашему запросу ничего не найдено в списке.")
            else:
                 final_output = human_readable_output + final_command_string
                 # Truncate if needed
                 # Reminder: Use new line, not semicolon, for the following block/statement.
                 if len(final_output) > 4096:
                     truncate_point = final_output.rfind('\n', 0, 4080)
                     # Reminder: Use new line, not semicolon, for the following block/statement.
                     if truncate_point == -1: truncate_point = 4080
                     final_output = final_output[:truncate_point] + "\n..."
                     logger.warning("Truncated /find output message.")
                 await update.message.reply_html(final_output)

        else: # Handle empty LLM response
             logger.warning("LLM search returned empty response string without error.")
             await update.message.reply_text("🤷 LLM не вернул ответ.")

    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.exception(f"Unexpected error during /find execution: {e}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if status_msg: await delete_message_safely(context, status_msg.chat_id, status_msg.message_id)
        await update.message.reply_text("❌ Произошла внутренняя ошибка при поиске.")
# ================================== find_items() end ==================================

    


# ================================== _get_styles_list_text(): Generates text for styles list ==================================
def _get_styles_list_text() -> str:
    lines = ["<b>🖌️ Доступные Стили:</b>\n"]
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not config.STYLE_ABSOLUTE_INDEX_TO_DATA:
        lines.append("<i>(Нет доступных стилей)</i>")
    else:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, style_data in sorted(config.STYLE_ABSOLUTE_INDEX_TO_DATA.items()):
            alias = style_data.get('alias', 'N/A')
            lines.append(f"<code>[{index}]</code> {escape(alias)}")

    # Add Style Group Aliases
    lines.append("\n<b>✨ Группы Стилей (для случайного выбора, напр. <code>-s craft</code>):</b>\n")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not config.STYLE_GROUP_ALIASES:
        lines.append("<i>(Нет доступных групп)</i>")
    else:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for alias, group_key in sorted(config.STYLE_GROUP_ALIASES.items()):
            # Attempt to find a representative name/alias for the group key (optional)
            # For simplicity, we might just list alias -> key
             lines.append(f"<code>{escape(alias)}</code> (Группа: {escape(group_key)})")

    lines.append("\n<i>Используйте <code>-s0</code> для случайного стиля из применимых к выбранному типу.</i>")
    return "\n".join(lines)
# ================================== _get_styles_list_text() end ==================================


# ================================== list_styles(): Handles /styles command ==================================
async def list_styles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    logger.info("/styles command received")
    text = _get_styles_list_text()
    await send_long_message(update, context, text, "🖌️ Доступные Стили и Группы")
# ================================== list_styles() end ==================================


# ================================== _get_artists_list_text(): Generates text for artists list ==================================
def _get_artists_list_text() -> str:
    lines = ["<b>👨‍🎨 Доступные Художники:</b>\n"]
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not config.ARTIST_ABSOLUTE_INDEX_TO_DATA:
        lines.append("<i>(Нет доступных художников)</i>")
    else:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for index, artist_data in sorted(config.ARTIST_ABSOLUTE_INDEX_TO_DATA.items()):
            alias = artist_data.get('alias', 'N/A'); emoji = artist_data.get('emoji', '')
            alias_short = artist_data.get('alias_short', '')
            display_name = f"{emoji} {escape(alias)}"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if alias_short and alias_short != alias: display_name += f" (<code>{escape(alias_short)}</code>)" # Show short alias in code
            lines.append(f"<code>[{index}]</code> {display_name.strip()}")
    return "\n".join(lines)
# ================================== _get_artists_list_text() end ==================================


# ================================== list_artists(): Handles /artists command ==================================
async def list_artists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    logger.info("/artists command received")
    text = _get_artists_list_text()
    await send_long_message(update, context, text, "👨‍🎨 Доступные Художники")
# ================================== list_artists() end ==================================


# ================================== _get_types_styles_list_text(): Generates text for types+styles list ==================================
def _get_types_styles_list_text() -> str:
    lines = ["<b>🎨 Типы и их Стили:</b>\n"]
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not config.TYPE_INDEX_TO_DATA:
        lines.append("<i>(Нет доступных типов)</i>")
    else:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        for type_index, type_data in sorted(config.TYPE_INDEX_TO_DATA.items()):
            type_alias = type_data.get('alias', 'N/A'); type_emoji = type_data.get('emoji', '')
            lines.append(f"\n<b><code>[{type_index}]</code> {type_emoji} {escape(type_alias)}</b>")
            relevant_keys = type_data.get('style_keys', [])
            relevant_styles = []
            seen_style_names = set()
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if relevant_keys:
                # Reminder: Use new line, not semicolon, for the following block/statement.
                for key in relevant_keys:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if key == 'artists': continue # Skip artist list here
                    style_list = config.STYLE_LISTS.get(key, [])
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if isinstance(style_list, list):
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        for style_item in style_list:
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            if isinstance(style_item, dict) and 'name' in style_item:
                                style_name_lower = style_item['name'].lower()
                                # Reminder: Use new line, not semicolon, for the following block/statement.
                                if style_name_lower not in seen_style_names:
                                    style_abs_index = config.STYLE_NAME_TO_ABSOLUTE_INDEX.get(style_name_lower)
                                    # Reminder: Use new line, not semicolon, for the following block/statement.
                                    if style_abs_index is not None:
                                        relevant_styles.append({"index": style_abs_index, "alias": style_item.get('alias', 'N/A')})
                                        seen_style_names.add(style_name_lower)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if relevant_styles:
                relevant_styles.sort(key=lambda x: x['index'])
                # Reminder: Use new line, not semicolon, for the following block/statement.
                for style in relevant_styles: lines.append(f"  <code>[{style['index']}]</code> {escape(style['alias'])}")
            else: lines.append("  <i>(Нет применимых стилей)</i>")
    return "\n".join(lines)
# ================================== _get_types_styles_list_text() end ==================================


# ================================== list_types_styles(): Handles /ts command ==================================
async def list_types_styles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    logger.info("/ts command received")
    text = _get_types_styles_list_text()
    await send_long_message(update, context, text, "🎨 Типы и их Стили")
# ================================== list_types_styles() end ==================================


# ================================== show_all(): Handles /show_all command ==================================
async def show_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    logger.info("/show_all command received")

    # Regenerate the text content for each section
    types_text = _get_types_list_text()
    styles_text = _get_styles_list_text()
    artists_text = _get_artists_list_text()
    ts_text = _get_types_styles_list_text()

    # Combine the text, removing individual titles and adding separators
    combined_lines = []
    combined_lines.extend(types_text.splitlines()[1:]) # Skip title
    combined_lines.append("\n" + "="*20 + "\n") # Separator
    combined_lines.extend(styles_text.splitlines()[1:]) # Skip title
    combined_lines.append("\n" + "="*20 + "\n") # Separator
    combined_lines.extend(artists_text.splitlines()[1:]) # Skip title
    combined_lines.append("\n" + "="*20 + "\n") # Separator
    combined_lines.extend(ts_text.splitlines()[1:]) # Skip title

    # Add the main title at the beginning
    full_text = "<b>📜 Сводный Список Настроек</b>\n\n" + "\n".join(combined_lines)

    await send_long_message(update, context, full_text, "📜 Сводный Список Настроек")
# ================================== show_all() end ==================================



# ================================== manual_command(): Handles /man command (Informative Explanation - Style Aligned) ==================================
async def manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not await is_authorized(update, context): return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not update.message: return

    logger.info("/man command received")

    # Informative explanation, matching the user's example style
    manual_text = """
В боте есть несколько способов влиять на генерацию картинок. Основное - это команда <code>!</code> (или <code>/img</code>) и ваш текстовый запрос.

Пример: <code>!рыжий кот сидит на крыше</code>

К этому можно добавлять флаги для уточнения:

<b>Типы (<code>-t</code>)</b>
Задают общую категорию: Фото, Арт, Аниме и т.д. (см. <code>/types</code>).
   • <code>!кот -t 1</code> — Тип по номеру (здесь [1] Фото).
   • <code>!кот -t Аниме</code> — Можно и названием типа.
   • <code>!кот -t</code> — Случайный тип.
   • Если указан тип, и стиль указан как <code>-s0</code>), то стиль будет выбран случайно, но <i>подходящий</i> для этого типа.

<b>Стили (<code>-s</code>)</b>
Определяют визуальный стиль: Пиксель-арт, Импрессионизм и т.д. (см. <code>/styles</code>).
   • <code>!кот -s 72</code> — Стиль по номеру (здесь [72] Пиксель-арт).
   • <code>!кот -s</code> — Случайный стиль из <i>всех</i> существующих.
   • <code>!кот -s0</code> — Случайный стиль из тех, что <i>подходят к типу</i> (если тип выбран). Если тип не выбран, работает как <code>-s</code>.
   • <code>!кот -s craft</code> — Случайный стиль из <i>группы</i> 'craft' (список групп в <code>/styles</code>).
   • Названием стиля тоже можно, если оно есть в списке.

<b>Художники (<code>-a</code>)</b>
Применяет стиль определенного художника (см. <code>/artists</code>). Сильно влияет!
   • <code>!кот -a 90</code> — Художник по номеру (здесь [90] Ван Гог).
   • <code>!кот -a Ван Гог</code> — Можно по короткому псевдониму (указан в скобках в <code>/artists</code>).
   • <code>!кот -a</code> — Случайный художник.

<b>Комбинации и Рандом</b>
   • Флаги можно сочетать: <code>!кот -t 1 -s 72 -a 90</code>
   • Можно писать слитно (если с номерами): <code>!кот -t1s72a90</code>
   • Полный рандом для типа, стиля (глобально) и художника: <code>!!кот</code> или <code>!кот -r</code> (или <code>-tsa</code>).

<b>Кнопки под картинкой</b>
   • Ими можно выбрать/изменить Тип, Стиль, Художника, AR (соотношение сторон), Промпт.
   • <code>✅ Применить</code>: Перерисовывает <i>текущую</i> картинку с <i>выбранными сейчас</i> настройками. Создается новая картинка, ее настройки уже будут *этими*, без истории рандома.
   • <code>🔄 Заново</code>: Генерирует <i>новую</i> картинку, но использует <i>изначальный</i> запрос и флаги, с которыми была создана картинка с кнопкой. Если в изначальном запросе был рандом (<code>-t</code>, <code>-s</code>, <code>-a</code>, <code>-r</code>, <code>-s0</code>), он будет применен <i>заново</i>.

<b>Редактирование ответом</b>
   • Можно ответить на картинку бота текстом, указав флаги. Бот попытается перерисовать картинку с этими флагами.
   Пример ответа: <code>В красной шапке -t1 -s50</code> (добавит шапку, применит тип Фото и стиль 50).
   Пример ответа: <code>-r</code> (перерисует с полным рандомом).

Номера [N] для типов, стилей, художников видны в списках команд (<code>/types</code>, <code>/styles</code>, <code>/artists</code>) и на кнопках выбора.
"""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        await update.message.reply_html(manual_text, disable_web_page_preview=True)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Ошибка отправки /man: {e}")
        await update.message.reply_text("❌ Ошибка при отображении руководства.")
# ================================== manual_command() end ==================================

# handlers/info_commands.py end