# utils/html_helpers.py
# -*- coding: utf-8 -*-
"""
HTML escaping and basic Markdown to Telegram-HTML conversion utilities.
"""

import logging
import re
from html import escape

logger = logging.getLogger(__name__)

# ================================== convert_basic_markdown_to_html(): Converts basic MD to HTML ==================================
def convert_basic_markdown_to_html(text: str) -> str:
    if not text: return ""
    try:
        escaped_text = escape(text)
        escaped_text = re.sub(r'```(.*?)\s*```', r'<pre>\1</pre>', escaped_text, flags=re.DOTALL | re.IGNORECASE)
        escaped_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped_text)
        escaped_text = re.sub(r'\_(.*?)\_', r'<i>\1</i>', escaped_text)
        escaped_text = re.sub(r'(?<![\w*])\*(?!\s)(.*?)(?<!\s)\*(?![\w*])', r'<i>\1</i>', escaped_text)
        escaped_text = re.sub(r'`(.*?)`', r'<code>\1</code>', escaped_text)
        escaped_text = re.sub(r'\n\s*\n+', '\n\n', escaped_text)
        return escaped_text.strip()
    except Exception as e:
        logger.error(f"Ошибка при конвертации Markdown->HTML: {e}. Исходный текст escape.", exc_info=True)
        return escape(text)
# ================================== convert_basic_markdown_to_html() end ==================================

# utils/html_helpers.py end
