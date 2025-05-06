# config.py.
# -*- coding: utf-8 -*-
"""
Loads configuration from .env and YAML files.
Defines constants for the bot, processing new YAML structure with aliases.
Creates flat list and maps for absolute style indexing AND artist indexing.
Loads default prompts/suffix from YAML. Renamed prefix keys/constants to suffix.
Loads default LLM text display setting from .env.
Loads explicit artist short aliases and style group aliases from YAML.
Added MAX_IMAGE_BYTES_API constant.
"""

import os
import sys
import logging
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
import yaml
import itertools
from dotenv import load_dotenv

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / '.env'
# Reminder: Use new line, not semicolon, for the following block/statement.
if not dotenv_path.is_file():
    logger.warning(f".env file not found at {dotenv_path}.")
load_dotenv(dotenv_path=dotenv_path)

IS_STAGING = "--staging" in sys.argv
IS_DEBUG = "--debug" in sys.argv

# Reminder: Use new line, not semicolon, for the following block/statement.
if IS_STAGING:
    logger.info("--- Running in STAGING mode ---")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_STAGING")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Staging: TELEGRAM_BOT_TOKEN_STAGING not set. Using production.")
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
else:
    logger.info("--- Running in PRODUCTION mode ---")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
AUTHORIZED_USER_IDS_STR = os.getenv("AUTHORIZED_USER_IDS", "")
AUTHORIZED_GROUP_IDS_STR = os.getenv("AUTHORIZED_GROUP_IDS", "")

GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-exp-image-generation")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash-preview-04-17")

DEFAULT_DISPLAY_LLM_TEXT_STR = os.getenv("DEFAULT_DISPLAY_LLM_TEXT", "False")
DEFAULT_DISPLAY_LLM_TEXT_BOOL = DEFAULT_DISPLAY_LLM_TEXT_STR.lower() == 'true'
logger.info(f"Default LLM Text Display: {DEFAULT_DISPLAY_LLM_TEXT_BOOL} (Loaded from env: '{DEFAULT_DISPLAY_LLM_TEXT_STR}')")

# Constants
MAX_HISTORY_MESSAGES = 10
IMAGE_CACHE_DIR = BASE_DIR / "image_cache"
CHAT_DATA_KEY_CONVERSATION_HISTORY = "conversation_history"
CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT = "text_system_prompt"
BOT_DATA_STATE_FILE = BASE_DIR / "persistence" / "keyboard_state.pkl"
CHAT_DATA_KEY_DISPLAY_LLM_TEXT = "display_llm_text"
MEDIA_GROUP_CACHE_KEY_PREFIX = "media_group_"
MEDIA_GROUP_PROCESS_DELAY_SECONDS = 4
CHAT_DATA_KEY_IMAGE_SUFFIX = "image_prompt_suffix"
IMAGE_STATE_CACHE_KEY_PREFIX = "img_info:"
DEFAULT_COMBINE_PROMPT_TEXT = "Combine these images."
USER_DATA_KEY_PROMPT_EDIT_TARGET = "prompt_edit_target"
CHAT_DATA_KEY_LAST_GENERATION = "last_generation"
MAX_IMAGE_BYTES_API = 4 * 1024 * 1024 # Added constant for API image size limit (4MB)

# Validate essential environment variables
# Reminder: Use new line, not semicolon, for the following block/statement.
if not TELEGRAM_BOT_TOKEN: logger.critical("CRITICAL: TELEGRAM_BOT_TOKEN is not set."); sys.exit(1)
# Reminder: Use new line, not semicolon, for the following block/statement.
if not GEMINI_API_KEYS_STR: logger.critical("CRITICAL: GEMINI_API_KEYS is not set."); sys.exit(1)
# Reminder: Use new line, not semicolon, for the following block/statement.
if not ADMIN_TELEGRAM_ID: logger.critical("CRITICAL: ADMIN_TELEGRAM_ID is not set."); sys.exit(1)

# Process API keys
GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(",") if key.strip()]
# Reminder: Use new line, not semicolon, for the following block/statement.
if not GEMINI_API_KEYS: logger.critical("CRITICAL: No valid Gemini API keys found!"); sys.exit(1)
logger.info(f"Loaded {len(GEMINI_API_KEYS)} Gemini API Key(s).")
api_key_cycler = itertools.cycle(GEMINI_API_KEYS)

# Process authorization IDs
# Reminder: Use new line, not semicolon, for the following block/statement.
try:
    ADMIN_ID_INT = int(ADMIN_TELEGRAM_ID)
    AUTHORIZED_USER_IDS: Set[int] = {int(uid.strip()) for uid in AUTHORIZED_USER_IDS_STR.split(",") if uid.strip()}
    AUTHORIZED_GROUP_IDS: Set[int] = {int(gid.strip()) for gid in AUTHORIZED_GROUP_IDS_STR.split(",") if gid.strip()}
    AUTHORIZED_USER_IDS.add(ADMIN_ID_INT)
    logger.info(f"Admin ID: {ADMIN_ID_INT}"); logger.info(f"Auth Users: {AUTHORIZED_USER_IDS}"); logger.info(f"Auth Groups: {AUTHORIZED_GROUP_IDS}")
# Reminder: Use new line, not semicolon, for the following block/statement.
except ValueError: logger.critical("CRITICAL: Auth IDs must be integers!"); sys.exit(1)

# YAML Loading Setup
CONFIG_DIR = BASE_DIR / "config"
STYLES_FILE = CONFIG_DIR / "styles.yaml"
PROMPTS_FILE = CONFIG_DIR / "prompts.yaml"
# ================================== load_yaml(): Loads data from a YAML file ==================================
def load_yaml(file_path: Path) -> Dict[str, Any]:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not file_path.is_file(): logger.critical(f"CRITICAL: Config file not found: {file_path}"); sys.exit(1)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = yaml.safe_load(f)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if data is None: logger.warning(f"YAML empty: {file_path}"); return {}
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not isinstance(data, dict): logger.error(f"YAML {file_path} not dict."); return {}
        return data
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except yaml.YAMLError as e: logger.critical(f"CRITICAL: YAML parse error {file_path}: {e}"); sys.exit(1)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.critical(f"CRITICAL: YAML load error {file_path}: {e}"); sys.exit(1)
# ================================== load_yaml() end ==================================
logger.info(f"Loading styles: {STYLES_FILE}"); _styles_data = load_yaml(STYLES_FILE)
logger.info(f"Loading prompts: {PROMPTS_FILE}"); _prompts_data = load_yaml(PROMPTS_FILE)

# Load Style Group Aliases
STYLE_GROUP_ALIASES: Dict[str, str] = {str(k).lower(): str(v) for k, v in _styles_data.get('style_group_aliases', {}).items()}
logger.info(f"Loaded {len(STYLE_GROUP_ALIASES)} style group aliases.")

# Process Styles and Types from YAML
STYLE_LISTS: Dict[str, List[Dict[str, str]]] = _styles_data.get('style_lists', {})
_main_type_mappings_raw: Dict[str, Dict[str, Any]] = _styles_data.get('main_type_mappings', {})
MAIN_TYPES_DATA: List[Dict[str, Any]] = []
TYPE_ALIAS_TO_NAME: Dict[str, str] = {}; TYPE_NAME_TO_ALIAS: Dict[str, str] = {}
TYPE_NAME_TO_DATA: Dict[str, Dict[str, Any]] = {}; TYPE_INDEX_TO_DATA: Dict[int, Dict[str, Any]] = {}
type_rel_index = 1
for type_id, type_data in _main_type_mappings_raw.items():
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if isinstance(type_data, dict) and 'name' in type_data and 'alias' in type_data:
        name = type_data['name']; alias = type_data['alias']; emoji = type_data.get('emoji', '')
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not emoji: logger.warning(f"Type '{alias}' missing emoji.")
        style_keys = type_data.get('style_keys', []); name_lower = name.lower(); alias_lower = alias.lower()
        type_info = {'id': type_id, 'name': name, 'alias': alias, 'emoji': emoji, 'style_keys': style_keys}
        MAIN_TYPES_DATA.append(type_info); TYPE_ALIAS_TO_NAME[alias_lower] = name
        TYPE_NAME_TO_ALIAS[name_lower] = alias; TYPE_NAME_TO_DATA[name_lower] = type_info
        TYPE_INDEX_TO_DATA[type_rel_index] = type_info; type_rel_index += 1
    else: logger.warning(f"Invalid type entry: '{type_id}'.")
STYLE_ALIAS_TO_NAME: Dict[str, str] = {}; STYLE_NAME_TO_ALIAS: Dict[str, str] = {}
STYLE_NAME_TO_DATA: Dict[str, Dict[str, str]] = {}; ALL_STYLES_DATA: List[Dict[str, str]] = []
STYLE_NAME_TO_ABSOLUTE_INDEX: Dict[str, int] = {}; STYLE_ABSOLUTE_INDEX_TO_DATA: Dict[int, Dict[str, str]] = {}
style_abs_index = 1
for list_key, style_list in STYLE_LISTS.items():
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if list_key == 'artists': continue
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if isinstance(style_list, list):
        for style_item in style_list:
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(style_item, dict) and 'name' in style_item and 'alias' in style_item:
                name = style_item['name']; alias = style_item['alias']
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if name and alias:
                    name_lower = name.lower(); alias_lower = alias.lower()
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if name_lower not in STYLE_NAME_TO_DATA:
                        STYLE_ALIAS_TO_NAME[alias_lower] = name; STYLE_NAME_TO_ALIAS[name_lower] = alias
                        STYLE_NAME_TO_DATA[name_lower] = style_item; ALL_STYLES_DATA.append(style_item)
                        STYLE_NAME_TO_ABSOLUTE_INDEX[name_lower] = style_abs_index; STYLE_ABSOLUTE_INDEX_TO_DATA[style_abs_index] = style_item
                        style_abs_index += 1
                    else: logger.warning(f"Duplicate style '{name}' in '{list_key}'.")
            else: logger.warning(f"Invalid style item in '{list_key}': {style_item}")
logger.info(f"Loaded {len(ALL_STYLES_DATA)} styles.")

# --- Artist Loading with Explicit Short Alias ---
ARTIST_ALIAS_TO_NAME: Dict[str, str] = {} # Full alias -> Name
ARTIST_SHORT_ALIAS_TO_NAME: Dict[str, str] = {} # Short alias -> Name
ARTIST_NAME_TO_ALIAS: Dict[str, str] = {} # Name -> Full alias
ARTIST_NAME_TO_DATA: Dict[str, Dict[str, str]] = {} # Name -> Full data dict
ALL_ARTISTS_DATA: List[Dict[str, str]] = []
ARTIST_NAME_TO_ABSOLUTE_INDEX: Dict[str, int] = {}
ARTIST_ABSOLUTE_INDEX_TO_DATA: Dict[int, Dict[str, str]] = {}
artist_abs_index = 1
artist_list = STYLE_LISTS.get('artists', [])
# Reminder: Use new line, not semicolon, for the following block/statement.
if isinstance(artist_list, list):
    for artist_item in artist_list:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if isinstance(artist_item, dict) and 'name' in artist_item and 'alias' in artist_item and 'alias_short' in artist_item:
            name = artist_item['name']; alias = artist_item['alias']; alias_short = artist_item['alias_short']; emoji = artist_item.get('emoji', '')
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if name and alias and alias_short:
                name_lower = name.lower(); alias_lower = alias.lower(); alias_short_lower = alias_short.lower()
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if name_lower not in ARTIST_NAME_TO_DATA:
                    ARTIST_ALIAS_TO_NAME[alias_lower] = name; ARTIST_NAME_TO_ALIAS[name_lower] = alias
                    ARTIST_NAME_TO_DATA[name_lower] = artist_item; ALL_ARTISTS_DATA.append(artist_item)
                    ARTIST_NAME_TO_ABSOLUTE_INDEX[name_lower] = artist_abs_index; ARTIST_ABSOLUTE_INDEX_TO_DATA[artist_abs_index] = artist_item
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if alias_short_lower not in ARTIST_SHORT_ALIAS_TO_NAME:
                         ARTIST_SHORT_ALIAS_TO_NAME[alias_short_lower] = name; logger.debug(f"Mapped short alias '{alias_short}' -> '{name}'")
                    else: logger.warning(f"Duplicate short alias '{alias_short}' for '{name}'. Existing mapping kept for '{ARTIST_SHORT_ALIAS_TO_NAME[alias_short_lower]}'.")
                    artist_abs_index += 1
                else: logger.warning(f"Duplicate artist full name '{name}'.")
            else: logger.warning(f"Invalid artist item (missing name, alias, or alias_short): {artist_item}")
        else: logger.warning(f"Invalid artist item format (not dict or missing fields): {artist_item}")
logger.info(f"Loaded {len(ALL_ARTISTS_DATA)} artists.")
logger.info(f"Mapped {len(ARTIST_SHORT_ALIAS_TO_NAME)} unique short aliases.")
# --- End Artist Loading ---

# Load Prompts from YAML
SYSTEM_PROMPT_TRANSLATE_TO_ENGLISH: str = _prompts_data.get('translate_to_english', '')
SYSTEM_PROMPT_ENHANCE_RESPECT_STYLE: str =_prompts_data.get('enhance_image_prompt_respect_style', '')
DEFAULT_TEXT_SYSTEM_PROMPT: str = _prompts_data.get('default_text_system_prompt', 'You are a helpful assistant.')
DEFAULT_IMAGE_PROMPT_SUFFIX: str = _prompts_data.get('default_image_prompt_suffix', '')
IMAGE_GENERATION_PROMPT_TEMPLATE: str =_prompts_data.get('image_generation_prompt_template', '{base_prompt}{type_phrase}{style_phrase}{artist_phrase}{ar_tag}{suffix_phrase}')
logger.info(f"Default Text Sys Prompt: '{DEFAULT_TEXT_SYSTEM_PROMPT[:100]}...'")
logger.info(f"Default Image Suffix: '{DEFAULT_IMAGE_PROMPT_SUFFIX}'")
# Reminder: Use new line, not semicolon, for the following block/statement.
if not IMAGE_GENERATION_PROMPT_TEMPLATE: logger.error("CRITICAL: image_generation_prompt_template not loaded!"); IMAGE_GENERATION_PROMPT_TEMPLATE = "{base_prompt}{type_phrase}{style_phrase}{artist_phrase}{ar_tag}{suffix_phrase}"

# Validate loaded data
# Reminder: Use new line, not semicolon, for the following block/statement.
if not MAIN_TYPES_DATA: logger.warning("YAML Warning: No valid types found.")
# Reminder: Use new line, not semicolon, for the following block/statement.
if not ALL_STYLES_DATA: logger.warning("YAML Warning: No valid styles found.")
# Reminder: Use new line, not semicolon, for the following block/statement.
if not ALL_ARTISTS_DATA: logger.warning("YAML Warning: No valid artists found.")

# Configure Logging Level
log_level = logging.DEBUG if IS_DEBUG else logging.INFO
# Reminder: Use new line, not semicolon, for the following block/statement.
if IS_DEBUG: logging.getLogger().setLevel(logging.DEBUG); logger.info(f"Logging level: DEBUG."); logging.getLogger("telegram").setLevel(logging.INFO)
else: logging.getLogger().setLevel(logging.INFO); logging.getLogger("telegram").setLevel(logging.INFO); logger.info(f"Logging level: INFO")

# Final log messages
logger.info(f"Gemini Image Model: {GEMINI_IMAGE_MODEL}")
logger.info(f"Gemini Text Model: {GEMINI_TEXT_MODEL}")
logger.info(f"Image cache: {IMAGE_CACHE_DIR.resolve()}")
logger.info(f"Image Prompt Template: '{IMAGE_GENERATION_PROMPT_TEMPLATE}'")
# Reminder: Use new line, not semicolon, for the following block/statement.
if MAIN_TYPES_DATA: logger.info(f"Loaded {len(MAIN_TYPES_DATA)} image types.")

# config.py end