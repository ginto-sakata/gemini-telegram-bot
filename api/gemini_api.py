# api/gemini_api.py
# -*- coding: utf-8 -*-
"""
Handles interactions with the Google Gemini API for text and image generation.
Uses dedicated models from config. Sets thinkingBudget=0 for text models.
Includes timing logs. Includes prompt enhancement function.
Added describe_image_with_gemini function.
"""

import base64
import io
import json
import logging
import asyncio
import time
from typing import Optional, Tuple, Dict, Any, List, AsyncGenerator, Iterator
from html import escape
import requests
from config import (
    GEMINI_API_BASE_URL,
    GEMINI_IMAGE_MODEL,
    GEMINI_TEXT_MODEL,
    SYSTEM_PROMPT_ENHANCE_RESPECT_STYLE,
    api_key_cycler,
    MAX_IMAGE_BYTES_API, # Import MAX_IMAGE_BYTES_API
)
from utils.cache import _guess_mime_type

logger = logging.getLogger(__name__)

MAX_PROMPT_LEN_IMAGE = 4000
# MAX_IMAGE_BYTES_API = 4 * 1024 * 1024 # Already defined in config
REQUEST_TIMEOUT_IMAGE = 240
REQUEST_TIMEOUT_TEXT_SINGLE = 90 # Already defined in config
REQUEST_TIMEOUT_TEXT_STREAM = (10, 180)
REQUEST_TIMEOUT_TEXT_ENHANCE = 60

class StreamError(Exception):
    """Custom exception for errors during streaming API calls."""
    pass

# ================================== _parse_gemini_finish_reason(): Parses API finish reason/safety blocks ==================================
def _parse_gemini_finish_reason(candidate: Dict[str, Any], prompt_feedback: Optional[Dict[str, Any]]) -> Optional[str]:
    finish_reason = candidate.get("finishReason")
    safety_ratings_candidate = candidate.get("safetyRatings")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if prompt_feedback:
        block_reason_prompt = prompt_feedback.get("blockReason")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if block_reason_prompt:
            details = prompt_feedback.get("blockReasonMessage", "")
            logger.warning(f"Gemini API Blocked (PROMPT): {block_reason_prompt}. Details: {details}. Ratings: {prompt_feedback.get('safetyRatings')}")
            return f"❌ Запрос заблокирован (безопасность): {block_reason_prompt} {details}".strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if finish_reason == "SAFETY":
        details = ""
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if safety_ratings_candidate:
            blocked_categories = [r["category"] for r in safety_ratings_candidate if r.get("blocked")]
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if blocked_categories:
                details = f"(Категории: {', '.join(blocked_categories)})"
        logger.warning(f"Gemini API Blocked (FINISH=SAFETY). Details: {details}. Ratings: {safety_ratings_candidate}")
        return f"❌ Ответ заблокирован (безопасность): {details}".strip()
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if finish_reason == "RECITATION":
        logger.warning("Gemini API Blocked (FINISH=RECITATION).")
        return "❌ Ответ заблокирован (цитирование)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if finish_reason and finish_reason not in ["STOP", "MAX_TOKENS", None]:
        logger.warning(f"Gemini API finished unexpectedly: {finish_reason}.")
        return f"❌ Генерация остановлена (причина: {finish_reason})."
    return None
# ================================== _parse_gemini_finish_reason() end ==================================


# ================================== generate_image_with_gemini(): Generates image (+ optional text) via Gemini API ==================================
async def generate_image_with_gemini(
    prompt: str,
    input_image_original: Optional[bytes] = None,
    input_image_user: Optional[bytes] = None,
    model_name: str = GEMINI_IMAGE_MODEL,
) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    api_key = next(api_key_cycler)
    api_url = f"{GEMINI_API_BASE_URL.strip('/')}/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    logger.debug(f"Вызов Gemini Image API: {api_url}, Модель: {model_name}")
    parts = []
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if len(prompt) > MAX_PROMPT_LEN_IMAGE:
        logger.warning(f"Длина промпта изображения {len(prompt)} > {MAX_PROMPT_LEN_IMAGE}. Обрезается.")
        prompt = prompt[:MAX_PROMPT_LEN_IMAGE] + "..."
    parts.append({"text": prompt})
    logger.debug(f"Промпт изображения (длина {len(prompt)}): '{prompt[:100]}...'")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    def add_image_part(image_bytes: bytes, image_label: str) -> Optional[str]:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            mime_type, _ = _guess_mime_type(image_bytes)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if len(image_bytes) > MAX_IMAGE_BYTES_API:
                size_mb = len(image_bytes) / (1024 * 1024); limit_mb = MAX_IMAGE_BYTES_API / (1024 * 1024)
                error_msg = f"Размер '{image_label}' ({size_mb:.1f}MB) > лимита ({limit_mb:.1f}MB)."; logger.error(error_msg); return error_msg
            encoded_image = base64.b64encode(image_bytes).decode("utf-8")
            parts.append({"inlineData": {"mimeType": mime_type, "data": encoded_image}})
            logger.debug(f"Добавлено '{image_label}' ({len(image_bytes)} байт, {mime_type})")
            return None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: error_msg = f"Ошибка '{image_label}': {e}"; logger.error(error_msg, exc_info=True); return error_msg
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if input_image_original:
        error = add_image_part(input_image_original, "основное")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if error: return None, None, f"Ошибка изображения: {error}"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if input_image_user:
        error = add_image_part(input_image_user, "пользовательское")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if error: return None, None, f"Ошибка изображения: {error}"
    payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"candidateCount": 1, "responseModalities": ["TEXT", "IMAGE"]}}
    logger.debug(f"Отправка Payload (Image API). Частей: {len(parts)}")
    response_text_content = "(ответ не получен)"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        start_time = time.time()
        response = await asyncio.to_thread(requests.post, api_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_IMAGE)
        end_time = time.time(); logger.info(f"IMAGE API Call took {end_time - start_time:.3f}s (Status {response.status_code})")
        logger.debug(f"Статус ответа API: {response.status_code}"); response_text_content = response.text
        response.raise_for_status()
        res_json = response.json(); logger.debug(f"Ответ API (JSON начало): {str(res_json)[:500]}...")
        generated_text: Optional[str] = None; output_image_bytes: Optional[bytes] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "error" in res_json:
            error_info = res_json["error"]; error_message = error_info.get("message", "Неизвестная ошибка API")
            logger.error(f"Ошибка Gemini API (в JSON): {error_message}"); return None, None, f"Ошибка API: {error_message}"
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "candidates" in res_json and res_json["candidates"]:
            candidate = res_json["candidates"][0]; prompt_feedback = res_json.get("promptFeedback")
            safety_error = _parse_gemini_finish_reason(candidate, prompt_feedback)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if safety_error: return None, None, safety_error
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if "content" in candidate and "parts" in candidate["content"]:
                for part in candidate["content"]["parts"]:
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if "text" in part: generated_text = part["text"]; logger.debug("API вернул текст.")
                    elif "inlineData" in part:
                        data = part["inlineData"]
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        if data.get("mimeType", "").startswith("image/"):
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            try: output_image_bytes = base64.b64decode(data["data"]); logger.debug(f"API вернул изображение ({len(output_image_bytes)} байт).")
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            except Exception as e: decode_error = f"Ошибка декодирования: {e}"; logger.error(decode_error); error_text = f"Ошибка API: Не удалось декодировать изображение. ({e})"; return generated_text, None, error_text
            else: logger.warning("Candidate has no 'content' or 'parts'.")
        else: logger.warning(f"Ответ API ОК, но нет кандидатов. Ответ: {res_json}"); return None, None, "Ошибка API: Нет данных ответа."
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if not output_image_bytes and not generated_text:
            finish_reason = candidate.get('finishReason', 'N/A') if 'candidate' in locals() else 'N/A'
            logger.warning(f"API OK, но нет контента (текст/изобр). FinishReason: {finish_reason}"); return None, None, "Ошибка API: Не удалось сгенерировать контент."
        return generated_text, output_image_bytes, None
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.Timeout: logger.error(f"Тайм-аут Image API ({REQUEST_TIMEOUT_IMAGE} сек)."); return None, None, f"Ошибка: Тайм-аут запроса к API ({REQUEST_TIMEOUT_IMAGE}с)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.RequestException as e:
        status_code_str = "N/A"; error_detail = str(e)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if e.response is not None:
            status_code = e.response.status_code; status_code_str = str(status_code)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                response_text = response_text_content
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try: err_json = json.loads(response_text); error_message = err_json.get("error", {}).get("message", response_text); error_detail = error_message
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except (json.JSONDecodeError, AttributeError): error_detail = response_text
                logger.error(f"Ошибка Image API (HTTP {status_code}): {error_detail[:500]}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as read_err: error_detail = f"(Не удалось прочитать ответ: {read_err})"; logger.error(f"Ошибка Image API (HTTP {status_code}): Не удалось прочитать ответ.")
        else: logger.error(f"Сетевая ошибка Image API: {e}")
        user_error = f"Ошибка сети API ({status_code_str}): {escape(error_detail[:200])}"; return None, None, user_error
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except json.JSONDecodeError as e:
        resp_text = response_text_content; logger.error(f"Ошибка декодирования JSON от Image API. Ответ: {resp_text[:500]}... Exception: {e}", exc_info=False)
        return None, None, "Ошибка: Некорректный формат ответа API."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.exception(f"Неожиданная ошибка при вызове Image API: {e}"); return None, None, "Неожиданная внутренняя ошибка API."
# ================================== generate_image_with_gemini() end ==================================


_sentinel = object()
# ================================== generate_text_with_gemini_stream(): Generates text via Gemini streaming API ==================================
async def generate_text_with_gemini_stream(
    history_contents: List[Dict[str, Any]], current_prompt: str, system_prompt_text: Optional[str], model_name: str = GEMINI_TEXT_MODEL
) -> AsyncGenerator[Tuple[Optional[str], Optional[str]], None]:
    api_key = next(api_key_cycler)
    api_url = f"{GEMINI_API_BASE_URL.strip('/')}/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={api_key}"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    contents_payload = history_contents + [{"role": "user", "parts": [{"text": current_prompt}]}]
    generation_config = {"candidateCount": 1, "thinkingConfig": {"thinkingBudget": 0}}
    logger.info(f"Text Stream API: Model={model_name}, thinkingBudget=0")
    payload = {"contents": contents_payload, "generationConfig": generation_config}
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if system_prompt_text: payload["system_instruction"] = {"parts": [{"text": system_prompt_text}]}; logger.debug(f"Сис.инстр. текста: '{system_prompt_text[:100]}...'")
    else: logger.debug("Сис.инстр. текста не задана.")
    logger.debug(f"Вызов Text API (stream): {api_url}, Контента: {len(contents_payload)}")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    def stream_request() -> Iterator[bytes]:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try:
            with requests.Session() as session:
                start_time = time.time(); logger.debug(f"STREAM API Call START")
                with session.post(api_url, headers=headers, json=payload, stream=True, timeout=REQUEST_TIMEOUT_TEXT_STREAM) as response:
                    end_time = time.time(); logger.info(f"STREAM API Response (Status {response.status_code}) took {end_time - start_time:.3f}s"); logger.debug(f"Поток подключен (статус {response.status_code}).")
                    response.raise_for_status()
                    for line_bytes in response.iter_lines():
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        if line_bytes: yield line_bytes
                    logger.debug("Завершение потока (iter_lines).")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except requests.exceptions.Timeout as err: logger.error(f"Тайм-аут Text API: {err}"); raise StreamError(f"Тайм-аут API ({REQUEST_TIMEOUT_TEXT_STREAM[1]}с)") from err
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except requests.exceptions.RequestException as err:
            error_details = str(err); status_code_str = "N/A"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if err.response is not None:
                status_code = err.response.status_code; status_code_str = str(status_code)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try:
                    response_text = err.response.text
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    try: err_json = json.loads(response_text); msg = err_json.get("error", {}).get("message", response_text[:500])
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    except json.JSONDecodeError: msg = response_text[:500]
                    error_details = f"HTTP {status_code}: {msg}"
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except Exception: error_details = f"HTTP {status_code} (не чит. ответ)"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if status_code_str == '404' or 'not found' in error_details.lower(): logger.error(f"Ошибка Text API: Endpoint не найден '{model_name}'."); raise StreamError(f"Модель '{model_name}' не поддерживает стриминг.") from err
            else: logger.error(f"Ошибка Text API: {error_details}"); raise StreamError(f"Ошибка сети API ({status_code_str}): {escape(error_details)}") from err
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as err: logger.exception(f"Неизвестная ошибка Text API: {err}"); raise StreamError(f"Неизвестная ошибка потока: {err}") from err
    # Reminder: Use new line, not semicolon, for the following block/statement.
    def _blocking_next(iterator: Iterator) -> Any:
        # Reminder: Use new line, not semicolon, for the following block/statement.
        try: return next(iterator)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except StopIteration: return _sentinel
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except StreamError as e: raise e
        # Reminder: Use new line, not semicolon, for the following block/statement.
        except Exception as e: logger.error(f"Ошибка итератора потока: {e}", exc_info=True); raise StreamError(f"Ошибка итератора: {e}") from e
    blocking_iterator = None; full_response_text = ""
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        blocking_iterator = await asyncio.to_thread(stream_request); logger.debug("Получен итератор потока.")
        while True:
            line_bytes = None
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                line_bytes = await asyncio.to_thread(_blocking_next, blocking_iterator)
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if line_bytes is _sentinel: logger.debug("Итератор завершен (sentinel)."); break
                decoded_line = line_bytes.decode("utf-8", errors="ignore").strip()
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if decoded_line.startswith("data:"):
                    data_str = decoded_line[len("data:") :].strip()
                    # Reminder: Use new line, not semicolon, for the following block/statement.
                    if data_str:
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        try:
                            json_data = json.loads(data_str)
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            if "error" in json_data:
                                error_info = json_data["error"]; error_message = error_info.get("message", "Неизв. ошибка потока")
                                logger.error(f"Ошибка потока Gemini API: {error_message}"); yield None, f"Ошибка API в потоке: {error_message}"; return
                            candidates = json_data.get("candidates", []); text_chunk = ""; safety_error_msg = None
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            if candidates:
                                candidate = candidates[0]; prompt_feedback = json_data.get("promptFeedback")
                                safety_error_msg = _parse_gemini_finish_reason(candidate, prompt_feedback)
                                # Reminder: Use new line, not semicolon, for the following block/statement.
                                if not safety_error_msg:
                                    content = candidate.get("content")
                                    # Reminder: Use new line, not semicolon, for the following block/statement.
                                    if content and "parts" in content and content["parts"]: text_chunk = content["parts"][0].get("text", "")
                            else: prompt_feedback = json_data.get("promptFeedback"); safety_error_msg = _parse_gemini_finish_reason({}, prompt_feedback)
                            # Reminder: Use new line, not semicolon, for the following block/statement.
                            if safety_error_msg: logger.warning(f"Поток остановлен: {safety_error_msg}"); yield None, safety_error_msg; return
                            elif text_chunk: full_response_text += text_chunk; yield text_chunk, None
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        except json.JSONDecodeError: logger.warning(f"Не декодирован JSON-фрагмент: {data_str}")
                        # Reminder: Use new line, not semicolon, for the following block/statement.
                        except Exception as e: logger.exception(f"Ошибка JSON-фрагмента: {e} - Data: {data_str}"); yield None, f"Ошибка данных потока: {escape(str(e))}"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except StreamError as stream_err: logger.error(f"Ошибка итерации потока: {stream_err}"); yield None, str(stream_err); return
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as iter_err: logger.exception(f"Неожиданная ошибка итерации: {iter_err}"); yield None, f"Неожиданная ошибка потока: {escape(str(iter_err))}"; return
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except StreamError as setup_err: logger.error(f"Ошибка установки потока: {setup_err}"); yield None, str(setup_err)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as setup_err: logger.exception(f"Неож. ошибка установки потока: {setup_err}"); yield None, f"Неож. ошибка установки потока: {escape(str(setup_err))}"
# ================================== generate_text_with_gemini_stream() end ==================================


# ================================== generate_text_with_gemini_single(): Generates single text response ==================================
async def generate_text_with_gemini_single(
    user_prompt: str, system_prompt_text: Optional[str], model_name: str = GEMINI_TEXT_MODEL
) -> Tuple[Optional[str], Optional[str]]:
    api_key = next(api_key_cycler)
    api_url = f"{GEMINI_API_BASE_URL.strip('/')}/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    logger.debug(f"Вызов Text API (single): {api_url}, Модель: {model_name}")
    generation_config = {"candidateCount": 1, "temperature": 0.7, "thinkingConfig": {"thinkingBudget": 0}}
    logger.info(f"Text Single API: Model={model_name}, thinkingBudget=0")
    payload = {"contents": [{"role": "user", "parts": [{"text": user_prompt}]}], "generationConfig": generation_config}
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if system_prompt_text: payload["system_instruction"] = {"parts": [{"text": system_prompt_text}]}; logger.debug(f"Сис.инстр. (single): '{system_prompt_text[:100]}...'")
    response_text_content = "(ответ не получен)"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        start_time = time.time(); logger.debug(f"SINGLE API Call START")
        response = await asyncio.to_thread(requests.post, api_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_TEXT_SINGLE)
        end_time = time.time(); logger.info(f"SINGLE API Call took {end_time - start_time:.3f}s (Status {response.status_code})")
        logger.debug(f"Статус ответа API (single): {response.status_code}"); response_text_content = response.text
        response.raise_for_status()
        res_json = response.json(); logger.debug(f"Ответ API (single, JSON начало): {str(res_json)[:500]}...")
        generated_text: Optional[str] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "error" in res_json:
            error_info = res_json["error"]; error_message = error_info.get("message", "Неизвестная ошибка API")
            logger.error(f"Ошибка Gemini API (single, JSON): {error_message}"); return None, f"Ошибка API: {error_message}"
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "candidates" in res_json and res_json["candidates"]:
            candidate = res_json["candidates"][0]; prompt_feedback = res_json.get("promptFeedback")
            safety_error = _parse_gemini_finish_reason(candidate, prompt_feedback)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if safety_error: return None, safety_error
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if "content" in candidate and "parts" in candidate["content"]:
                all_text_parts = [part.get("text", "") for part in candidate["content"]["parts"] if "text" in part]
                generated_text = "".join(all_text_parts).strip(); logger.debug("API вернул текст (single)."); return generated_text, None
            else: logger.warning("Ответ API (single) нет content/parts."); return None, "Некорректная структура ответа API."
        else: logger.warning(f"Ответ API ОК (single), но нет кандидатов: {res_json}"); return None, "Ошибка API: Нет данных ответа."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.Timeout: logger.error(f"Тайм-аут Text API (single, {REQUEST_TIMEOUT_TEXT_SINGLE} сек)."); return None, f"Ошибка: Тайм-аут API ({REQUEST_TIMEOUT_TEXT_SINGLE}с)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.RequestException as e:
        status_code_str = "N/A"; error_detail = str(e)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if e.response is not None:
            status_code = e.response.status_code; status_code_str = str(status_code)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                response_text = response_text_content
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try: err_json = json.loads(response_text); error_message = err_json.get("error", {}).get("message", response_text); error_detail = error_message
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except (json.JSONDecodeError, AttributeError): error_detail = response_text
                logger.error(f"Ошибка Text API (single, HTTP {status_code}): {error_detail[:500]}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as read_err: error_detail = f"(Не удалось прочитать ответ: {read_err})"; logger.error(f"Ошибка Text API (single, HTTP {status_code}): Не удалось прочитать ответ.")
        else: logger.error(f"Сетевая ошибка Text API (single): {e}")
        user_error = f"Ошибка сети API ({status_code_str}): {escape(error_detail[:200])}"; return None, user_error
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except json.JSONDecodeError as e:
        resp_text = response_text_content; logger.error(f"Ошибка декодирования JSON Text API (single). Ответ: {resp_text[:500]}... Exception: {e}", exc_info=False)
        return None, "Ошибка: Некорректный формат ответа API."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.exception(f"Неожиданная ошибка Text API (single): {e}"); return None, "Неожиданная внутренняя ошибка API."
# ================================== generate_text_with_gemini_single() end ==================================


# ================================== enhance_prompt_with_gemini(): Enhances image prompt via LLM ==================================
async def enhance_prompt_with_gemini(
    original_prompt: str, selected_type_data: Optional[Dict] = None, selected_style_data: Optional[Dict] = None, model_name: str = GEMINI_TEXT_MODEL
) -> Tuple[Optional[str], Optional[str]]:
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not original_prompt: return None, "Невозможно улучшить пустой промпт."
    llm_input_parts = [f"User Request: {original_prompt}\n---"]; context_added = False
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if selected_type_data or selected_style_data:
        llm_input_parts.append("Style Context:")
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_type_data: llm_input_parts.append(f"- Type: {selected_type_data.get('name', 'N/A')}"); context_added = True
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if selected_style_data: llm_input_parts.append(f"- Style: {selected_style_data.get('name', 'N/A')}"); context_added = True
        llm_input_parts.append("---")
    else: llm_input_parts.append("Style Context: None")
    user_prompt_for_llm = "\n".join(llm_input_parts); logger.debug(f"Prompt для улучшения LLM:\n{user_prompt_for_llm}")
    system_prompt = SYSTEM_PROMPT_ENHANCE_RESPECT_STYLE
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not system_prompt: logger.error("Сист. промпт улучшения не загружен!"); return None, "Ошибка конфигурации: Проблема с промптом улучшения."
    enhanced_prompt, error_message = await generate_text_with_gemini_single(user_prompt=user_prompt_for_llm, system_prompt_text=system_prompt, model_name=model_name)
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if error_message: logger.error(f"Ошибка при улучшении: {error_message}"); return None, f"Ошибка LLM при улучшении: {error_message}"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    if not enhanced_prompt: logger.warning("Улучшение не вернуло текст."); return None, "LLM не вернул улучшенный промпт."
    cleaned_enhanced_prompt = enhanced_prompt.strip(); logger.info(f"Улучшенный промпт: '{cleaned_enhanced_prompt[:150]}...'")
    return cleaned_enhanced_prompt, None
# ================================== enhance_prompt_with_gemini() end ==================================


# ================================== describe_image_with_gemini(): Asks Gemini to describe an image ==================================
async def describe_image_with_gemini(image_bytes: bytes, model_name: str = GEMINI_IMAGE_MODEL) -> Tuple[Optional[str], Optional[str]]:
    """
    Sends an image to Gemini and asks for a textual description.
    Uses the standard generateContent endpoint with the specified (likely multimodal) model.
    """
    api_key = next(api_key_cycler)
    api_url = f"{GEMINI_API_BASE_URL.strip('/')}/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    logger.debug(f"Вызов Gemini Describe API: {api_url}, Модель: {model_name}")
    describe_prompt = "Describe this image in detail, focusing on the main subject, setting, actions, and overall mood. Provide only the description."
    parts = [{"text": describe_prompt}]
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        mime_type, _ = _guess_mime_type(image_bytes)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if len(image_bytes) > MAX_IMAGE_BYTES_API:
            size_mb = len(image_bytes) / (1024 * 1024); limit_mb = MAX_IMAGE_BYTES_API / (1024 * 1024)
            error_msg = f"Размер изображения для описания ({size_mb:.1f}MB) > лимита ({limit_mb:.1f}MB)."; logger.error(error_msg); return None, error_msg
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({"inlineData": {"mimeType": mime_type, "data": encoded_image}})
        logger.debug(f"Добавлено изображение ({len(image_bytes)} байт, {mime_type}) для описания.")
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: error_msg = f"Ошибка подготовки изображения для описания: {e}"; logger.error(error_msg, exc_info=True); return None, error_msg
    payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"candidateCount": 1}} # Requesting only text implicitly
    logger.debug(f"Отправка Payload (Describe API). Частей: {len(parts)}")
    response_text_content = "(ответ не получен)"
    # Reminder: Use new line, not semicolon, for the following block/statement.
    try:
        start_time = time.time()
        # Use a reasonable timeout for text generation
        response = await asyncio.to_thread(requests.post, api_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_TEXT_SINGLE)
        end_time = time.time(); logger.info(f"DESCRIBE API Call took {end_time - start_time:.3f}s (Status {response.status_code})")
        logger.debug(f"Статус ответа API (Describe): {response.status_code}"); response_text_content = response.text
        response.raise_for_status()
        res_json = response.json(); logger.debug(f"Ответ API (Describe, JSON начало): {str(res_json)[:500]}...")
        generated_text: Optional[str] = None
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "error" in res_json:
            error_info = res_json["error"]; error_message = error_info.get("message", "Неизвестная ошибка API (Describe)")
            logger.error(f"Ошибка Gemini API (Describe, в JSON): {error_message}"); return None, f"Ошибка API описания: {error_message}"
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if "candidates" in res_json and res_json["candidates"]:
            candidate = res_json["candidates"][0]; prompt_feedback = res_json.get("promptFeedback")
            safety_error = _parse_gemini_finish_reason(candidate, prompt_feedback)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if safety_error: return None, f"Ошибка безопасности описания: {safety_error}"
            # Reminder: Use new line, not semicolon, for the following block/statement.
            if "content" in candidate and "parts" in candidate["content"]:
                # Extract only the text part
                all_text_parts = [part.get("text", "") for part in candidate["content"]["parts"] if "text" in part]
                generated_text = "".join(all_text_parts).strip()
                logger.debug("API вернул текст описания.")
                # Reminder: Use new line, not semicolon, for the following block/statement.
                if not generated_text: logger.warning("Описание API вернуло пустой текст."); return None, "API вернул пустое описание."
                return generated_text, None # Success
            else: logger.warning("Candidate (Describe) has no 'content' or 'parts'."); return None, "Некорректная структура ответа API (описание)."
        else: logger.warning(f"Ответ API ОК (Describe), но нет кандидатов. Ответ: {res_json}"); return None, "Ошибка API: Нет данных ответа (описание)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.Timeout: logger.error(f"Тайм-аут Describe API ({REQUEST_TIMEOUT_TEXT_SINGLE} сек)."); return None, f"Ошибка: Тайм-аут API описания ({REQUEST_TIMEOUT_TEXT_SINGLE}с)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except requests.exceptions.RequestException as e:
        status_code_str = "N/A"; error_detail = str(e)
        # Reminder: Use new line, not semicolon, for the following block/statement.
        if e.response is not None:
            status_code = e.response.status_code; status_code_str = str(status_code)
            # Reminder: Use new line, not semicolon, for the following block/statement.
            try:
                response_text = response_text_content
                # Reminder: Use new line, not semicolon, for the following block/statement.
                try: err_json = json.loads(response_text); error_message = err_json.get("error", {}).get("message", response_text); error_detail = error_message
                # Reminder: Use new line, not semicolon, for the following block/statement.
                except (json.JSONDecodeError, AttributeError): error_detail = response_text
                logger.error(f"Ошибка Describe API (HTTP {status_code}): {error_detail[:500]}")
            # Reminder: Use new line, not semicolon, for the following block/statement.
            except Exception as read_err: error_detail = f"(Не удалось прочитать ответ: {read_err})"; logger.error(f"Ошибка Describe API (HTTP {status_code}): Не удалось прочитать ответ.")
        else: logger.error(f"Сетевая ошибка Describe API: {e}")
        user_error = f"Ошибка сети API Описания ({status_code_str}): {escape(error_detail[:200])}"; return None, user_error
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except json.JSONDecodeError as e:
        resp_text = response_text_content; logger.error(f"Ошибка декодирования JSON от Describe API. Ответ: {resp_text[:500]}... Exception: {e}", exc_info=False)
        return None, "Ошибка: Некорректный формат ответа API (описание)."
    # Reminder: Use new line, not semicolon, for the following block/statement.
    except Exception as e: logger.exception(f"Неожиданная ошибка при вызове Describe API: {e}"); return None, "Неожиданная внутренняя ошибка API (описание)."
# ================================== describe_image_with_gemini() end ==================================


# api/gemini_api.py end