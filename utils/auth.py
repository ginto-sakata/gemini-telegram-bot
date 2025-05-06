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
    user = update.effective_user; chat = update.effective_chat
    if not user or not chat: logger.warning("Auth check failed: Missing user/chat info."); return False
    is_auth = False
    if user.id == ADMIN_ID_INT: is_auth = True; logger.debug(f"Auth granted: Admin {user.id}.")
    elif user.id in AUTHORIZED_USER_IDS: is_auth = True; logger.debug(f"Auth granted: User {user.id} in users.")
    elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and chat.id in AUTHORIZED_GROUP_IDS: is_auth = True; logger.debug(f"Auth granted: Chat {chat.id} ('{chat.title}') in groups.")
    elif not AUTHORIZED_USER_IDS and not AUTHORIZED_GROUP_IDS and user.id != ADMIN_ID_INT: logger.warning(f"Auth denied: Lists empty, only Admin ({ADMIN_ID_INT}) allowed. User: {user.id}"); is_auth = False
    if not is_auth:
        logger.warning(f"Unauthorized access: User={user.id} ('{user.username}'), Chat={chat.id} ('{chat.title}') Type='{chat.type}'")
        try:
            await context.bot.send_message(chat_id=chat.id, text="Извините, у вас нет доступа.\nБот предназначен для работы в группе @gintobots.\nВы можете воспользоваться генерацией текста с помощью новейшей модели Gemini 2.5 Flash. Просто отправьте мне сообщение или вопрос!")
            chat_title_escaped = escape(chat.title) if chat.title else 'Приватный чат'
            admin_notify_msg = (
                f"⚠️ Несанкц. доступ:\nПользователь: {user.mention_html()} (<code>{user.id}</code>)\n"
                f"Чат: {chat_title_escaped} (<code>{chat.id}</code>)\nТип: {chat.type}"
            )
            if ADMIN_ID_INT: await context.bot.send_message(chat_id=ADMIN_ID_INT, text=admin_notify_msg, parse_mode=ParseMode.HTML)
            else: logger.error("Cannot notify admin: ADMIN_ID_INT not configured.")
        except TelegramError as e: logger.error(f"Error sending auth notification (User: {user.id}, Chat: {chat.id}): {e}")
        except Exception as e: logger.error(f"Unexpected error during auth notification: {e}", exc_info=True)
        return False
    return True
# ================================== is_authorized() end ==================================

# utils/auth.py end
