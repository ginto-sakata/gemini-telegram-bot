# utils/decorators.py
from functools import wraps
from telegram import Update, ChatType
from telegram.ext import ContextTypes
from utils.auth import is_authorized

def restrict_private_unauthorized(handler):
    @wraps(handler)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if chat.type == ChatType.PRIVATE and not await is_authorized(update, context):
            return  # Exit early, message already shown by is_authorized
        return await handler(update, context, *args, **kwargs)
    return wrapped