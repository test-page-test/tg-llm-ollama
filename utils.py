"""
utils.py
▸ strip_thinking()  — удаляет <think>…</think> из ответа
▸ supports_vision() — проверка, умеет ли модель работать с изображением
"""
import re

# --- вырезаем «мысленные» блоки ------------------------------------------------
_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Удаляет все вложенные <think></think>."""
    while _THINK_TAG.search(text):
        text = _THINK_TAG.sub("", text)
    return text


# --- список vision-моделей -----------------------------------------------------
VISION_MODELS = {
    "gemma3:4b",
    "llava:7b",
    "llama3.2-vision:11b",
}


def supports_vision(model: str) -> bool:
    """True, если модель входит в набор vision-совместимых тегов."""
    return any(tag in model for tag in VISION_MODELS)
