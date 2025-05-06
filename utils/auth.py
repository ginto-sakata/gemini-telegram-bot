# utils/auth.py
# -*- coding: utf-8 -*-
"""
Authorization checking logic for Telegram users and groups.
All user-facing and admin notification messages are in Russian.
"""

import logging
from html import escape
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from config import ADMIN_ID_INT, AUTHORIZED_USER_IDS, AUTHORIZED_GROUP_IDS

logger = logging.getLogger(__name__)

# ================================== is_authorized(): Checks if user/group is authorized ==================================
async def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        logger.warning("Auth check failed: Missing user/chat info.")
        return False

    # Admin always allowed
    if user.id == ADMIN_ID_INT:
        logger.debug(f"Auth granted: Admin {user.id}.")
        return True

    # Explicitly authorized user
    if user.id in AUTHORIZED_USER_IDS:
        logger.debug(f"Auth granted: User {user.id} in users.")
        return True

    # Group chat: allow only if in allowed group IDs
    if chat.type != ChatType.PRIVATE and chat.id in AUTHORIZED_GROUP_IDS:
        logger.debug(f"Auth granted: Group {chat.id}.")
        return True

    # Default: unauthorized
    logger.warning(f"Unauthorized access attempt by {user.id} ({user.username}) in chat {chat.id}")

    # Show the exact original unauthorized message
    unauthorized_text = (
        "Извините, у вас нет доступа к генерации изображений.\n"
        "Бот предназначен для работы в группе @ginto_bots.\n"
        "Для запроса доступа к генерации сообщений обратитесь ко мне: @gin7o"
        "Вы можете воспользоваться генерацией текста с помощью новейшей модели Gemini 2.5 Flash. "
        "Просто отправьте сообщение или вопрос!"
    )

    try:
        if update.callback_query:
            await update.callback_query.answer(unauthorized_text, show_alert=True)
        elif update.message:
            await update.message.reply_text(unauthorized_text)
    except Exception:
        pass

    return False
# ================================== is_authorized() end ==================================

# utils/auth.py end
