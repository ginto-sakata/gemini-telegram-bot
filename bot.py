# bot.py
# -*- coding: utf-8 -*-
"""
Version=2.1.5
Adds /show_all command combining info lists.
Updates /styles list to show group aliases.
"""

import logging
import sys
import asyncio
import pickle
from pathlib import Path
import signal
from handlers.text_gen import handle_private_text
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, Defaults,
)
from telegram.constants import ParseMode, ChatType
from cachetools import TTLCache
# Reminder: Use new line, not semicolon, for the following block/statement.
try:
    import config
# Reminder: Use new line, not semicolon, for the following block/statement.
except ImportError:
    print("CRITICAL ERROR: config.py not found.", file=sys.stderr)
    sys.exit(1)
# Reminder: Use new line, not semicolon, for the following block/statement.
try:
    from handlers import commands as command_handlers
    from handlers import errors as error_handlers
    from handlers import text_gen as text_gen_handlers
    from handlers import image_gen as image_gen_handlers
    from handlers import media_groups as media_group_handlers
    from handlers import callbacks as callback_handlers
    from handlers import info_commands as info_command_handlers
# Reminder: Use new line, not semicolon, for the following block/statement.
except ImportError as e:
    print(f"CRITICAL ERROR: Failed to import handlers: {e}.", file=sys.stderr)
    sys.exit(1)

logger = logging.getLogger(__name__)

PERSISTENCE_DIR = config.BASE_DIR / "persistence"
BOT_DATA_STATE_FILE = config.BOT_DATA_STATE_FILE
STATE_CACHE_TTL_SECONDS = 12 * 60 * 60
STATE_CACHE_MAXSIZE = 1000
_application_instance: Application | None = None

# ================================== load_bot_data_from_file(): Loads image state from file ==================================
def load_bot_data_from_file() -> dict:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if BOT_DATA_STATE_FILE.is_file():
        logger.info(f"Загрузка state из {BOT_DATA_STATE_FILE}")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            with open(BOT_DATA_STATE_FILE, "rb") as f:
                loaded_data = pickle.load(f)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(loaded_data, dict):
                 image_states = {k: v for k, v in loaded_data.items() if isinstance(k, str) and k.startswith(config.IMAGE_STATE_CACHE_KEY_PREFIX)}
                 logger.info(f"Загружено {len(image_states)} состояний.")
                 return image_states
            else:
                 logger.warning("Загруженный файл не словарь.")
                 return {}
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e:
            logger.error(f"Не удалось загрузить state: {e}.", exc_info=True)
            return {}
    else:
        logger.info("Файл state не найден.")
        return {}
# ================================== load_bot_data_from_file() end ==================================


# ================================== save_bot_data_to_file(): Saves image state to file ==================================
def save_bot_data_to_file(bot_data_cache: TTLCache):
    image_states_to_save = {}
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        for key, value in list(bot_data_cache.items()):
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if isinstance(key, str) and key.startswith(config.IMAGE_STATE_CACHE_KEY_PREFIX):
                image_states_to_save[key] = value
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Ошибка итерации TTLCache: {e}")
    logger.info(f"Сохранение {len(image_states_to_save)} состояний в {BOT_DATA_STATE_FILE}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not image_states_to_save:
        logger.info("Нет состояний для сохранения.")
        return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)
        with open(BOT_DATA_STATE_FILE, "wb") as f:
            pickle.dump(image_states_to_save, f)
        logger.info("Состояния успешно сохранены.")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.error(f"Не удалось сохранить state: {e}", exc_info=True)
# ================================== save_bot_data_to_file() end ==================================


# ================================== main(): Initializes and runs the bot ==================================
def main():
    global _application_instance
    logger.info("Инициализация бота...")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        config.IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Кэш: {config.IMAGE_CACHE_DIR.resolve()}")
        PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Persistence: {PERSISTENCE_DIR.resolve()}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e:
        logger.critical(f"Не удалось создать каталог: {e}", exc_info=True)
        sys.exit(1)
    bot_data_cache = TTLCache(maxsize=STATE_CACHE_MAXSIZE, ttl=STATE_CACHE_TTL_SECONDS)
    loaded_image_states = load_bot_data_from_file()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if loaded_image_states:
        logger.info(f"Слияние {len(loaded_image_states)} состояний.")
        bot_data_cache.update(loaded_image_states)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        bot_defaults = Defaults(parse_mode=ParseMode.HTML)
        application = (ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).defaults(bot_defaults)
                       .connect_timeout(30).read_timeout(30).write_timeout(60).pool_timeout(60).build())
        application.bot_data = bot_data_cache
        _application_instance = application
        logger.info("Данные в памяти."); logger.info("bot_data: TTLCache + ручное сохр/загр.")
        logger.info("Регистрация обработчиков...")
        application.add_error_handler(error_handlers.error_handler)

        # Group 0: Basic / Info / Config Commands
        application.add_handler(CommandHandler("start", command_handlers.start, block=False), group=0)
        application.add_handler(CommandHandler("help", command_handlers.help_command, block=False), group=0)
        application.add_handler(CommandHandler("clear", command_handlers.clear_command, block=False), group=0)
        application.add_handler(CommandHandler("history", command_handlers.show_text_history_command, block=False), group=0)
        application.add_handler(CommandHandler("prompt", command_handlers.set_image_prompt_suffix_command, block=False), group=0)
        application.add_handler(CommandHandler("reset", command_handlers.reset_text_system_prompt_command, block=False), group=0)
        application.add_handler(CommandHandler("toggle_llm", command_handlers.toggle_llm_text_command, block=False), group=0)
        application.add_handler(CommandHandler("types", info_command_handlers.list_types, block=False), group=0)
        application.add_handler(CommandHandler("styles", info_command_handlers.list_styles, block=False), group=0)
        application.add_handler(CommandHandler("artists", info_command_handlers.list_artists, block=False), group=0)
        application.add_handler(CommandHandler("man", info_command_handlers.manual_command, block=False), group=0) # Add /man handler
        application.add_handler(CommandHandler("find", info_command_handlers.find_items, block=False), group=0) # Add /find handler

        # Group 1: Core generation commands
        application.add_handler(CommandHandler("ask", text_gen_handlers.handle_ask_command, block=False), group=1)
        application.add_handler(CommandHandler("img", image_gen_handlers.handle_img_command, block=False), group=1)

        # Group 2: Alias/Shortcut handlers
        application.add_handler(MessageHandler(filters.Regex(r"^\?\s*(.*)") & filters.TEXT & ~filters.COMMAND, text_gen_handlers.handle_ask_shortcut, block=False), group=2)
        img_shortcut_regex = r"^(?:!img|!image|!)\s*(.+)"
        random_img_shortcut_regex = r"^!!\s*(.+)"
        application.add_handler(MessageHandler(filters.Regex(random_img_shortcut_regex) & filters.TEXT & ~filters.COMMAND, image_gen_handlers.handle_random_img_shortcut, block=False), group=2)
        application.add_handler(MessageHandler(filters.Regex(img_shortcut_regex) & filters.TEXT & ~filters.COMMAND, image_gen_handlers.handle_img_shortcut, block=False), group=2)

        # Group 3: Contextual Replies and Specific Actions
        application.add_handler(MessageHandler(filters.TEXT & filters.REPLY & ~filters.COMMAND, text_gen_handlers.handle_text_reply, block=False), group=3)
        application.add_handler(MessageHandler(filters.PHOTO & filters.REPLY & ~filters.COMMAND, image_gen_handlers.handle_photo_reply_to_image, block=False), group=3)
        application.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION & ~filters.COMMAND & ~filters.REPLY, image_gen_handlers.handle_image_with_caption, block=False), group=3)

        # Group 4: Media Group Handling
        application.add_handler(MessageHandler(filters.PHOTO & ~filters.CAPTION & ~filters.REPLY & ~filters.COMMAND & filters.UpdateType.MESSAGE, media_group_handlers.handle_media_group_photo, block=False), group=4)

        # Group 10: Callback Query Handler
        application.add_handler(CallbackQueryHandler(callback_handlers.handle_callback_query, block=False), group=10)

        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_private_text),
            group=3
        )

        logger.info("Регистрация обработчиков завершена.")
        logger.info("Запуск бота (run_polling)...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.critical(f"Критическая ошибка инициализации: {e}", exc_info=True); sys.exit(1)
    finally: logger.info("Выход из main(). Попытка сохранения..."); save_state_on_shutdown()
# ================================== main() end ==================================


# ================================== save_state_on_shutdown(): Saves state before exit ==================================
def save_state_on_shutdown():
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if _application_instance and isinstance(_application_instance.bot_data, TTLCache):
        logger.info("Попытка сохранения state...")
        save_bot_data_to_file(_application_instance.bot_data)
    else: logger.warning("Не удалось сохранить state.")
# ================================== save_state_on_shutdown() end ==================================


# Reminder: Use new line, not semicolon, for the following block/statement.
if __name__ == "__main__":
    logger.info("Запуск основного скрипта...")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try: main()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except KeyboardInterrupt: logger.info("Получен KeyboardInterrupt.")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.critical(f"Критическая ошибка: {e}", exc_info=True)
    finally: logger.info("Скрипт завершил работу.")

# bot.py end