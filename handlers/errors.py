# handlers/errors.py
# -*- coding: utf-8 -*-
"""
Global error handler for the Telegram bot application.
"""

import logging
import html
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import ADMIN_ID_INT

logger = logging.getLogger(__name__)

# ================================== error_handler(): Global error handler ==================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Исключение при обработке обновления {update}", exc_info=context.error)
    if ADMIN_ID_INT:
        try:
            error_type = type(context.error).__name__; error_str = str(context.error)
            escaped_error = html.escape(error_str[:1000]) + ('...' if len(error_str) > 1000 else '')
            update_details = "N/A"
            if isinstance(update, Update):
                user_info = f"User: {update.effective_user.id}" if update.effective_user else "User: N/A"
                chat_info = f"Chat: {update.effective_chat.id}" if update.effective_chat else "Chat: N/A"
                update_details = f"{user_info}, {chat_info}"
            else:
                try: update_details = str(update)[:500]
                except Exception: update_details = "(Не удалось получить инфо об обновлении)"
            tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
            tb_string = "".join(tb_list); escaped_tb = html.escape(tb_string[-2000:])
            admin_msg = (
                f"🆘 Обнаружена ошибка бота!\n\n"
                f"<b>Тип Ошибки:</b> {html.escape(error_type)}\n"
                f"<b>Ошибка:</b>\n<pre>{escaped_error}</pre>\n\n"
                f"<b>Обновление:</b>\n<pre>{html.escape(update_details)}</pre>\n\n"
                f"<b>Traceback (последние строки):</b>\n<pre>{escaped_tb}</pre>"
            )
            await context.bot.send_message(chat_id=ADMIN_ID_INT, text=admin_msg, parse_mode=ParseMode.HTML)
        except Exception as admin_err: logger.error(f"Крит. ошибка: Не удалось уведомить админа ({ADMIN_ID_INT}): {admin_err}", exc_info=True)
# ================================== error_handler() end ==================================

# handlers/errors.py end