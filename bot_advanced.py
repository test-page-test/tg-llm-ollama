# Average bot for strongest people!
"""
bot_advanced.py
▸ /start         – привет + вывод списка команд и выбор модели кнопкой
▸ /m             – вывести клавиатуру моделей
▸ /help          – вывести справку по доступным командам
▸ /clear         – стереть историю
▸ /reset         – стереть историю и системный контекст
▸ /ctx add <txt> – добавить системный промпт
▸ /ctx del       – удалить системный промпт
▸ /thinking on|off – включить/выключить скрытие <think>
▸ изображение (jpg/png/gif/…) + подпись – vision-запрос
"""
import os
import tempfile
import mimetypes
import re
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
from ollama import Client
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─────────────── вспомогательные функции ───────────
_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL)

def strip_thinking(text: str) -> str:
    """Удаляет все вложенные <think></think>."""
    while _THINK_TAG.search(text):
        text = _THINK_TAG.sub("", text)
    return text

VISION_FAMILIES = {"gemma3", "llava", "llama3.2-vision"}

def supports_vision(model: str) -> bool:
    """True, если модель способна обрабатывать изображения."""
    family = model.split(":", 1)[0]
    if family in VISION_FAMILIES:
        return True
    return any(tag in model for tag in VISION_FAMILIES)

# ─────────────── конфигурация ─────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
client = Client(host="http://localhost:11434")

# ─────────────── состояние чатов ─────────────────
def new_state():
    return {"model": None, "history": [], "context": [], "thinking": True}
chats = defaultdict(new_state)

# ─────────────── динамическое получение моделей ────
async def list_models() -> list[str]:
    async with httpx.AsyncClient() as session:
        resp = await session.get("http://localhost:11434/api/tags")
        resp.raise_for_status()
        tags = resp.json()
    raw = tags.get("models", [])
    return sorted([m.get("name") for m in raw if isinstance(m, dict) and "name" in m])

# ─────────────── клавиатура моделей ───────────────
async def model_keyboard() -> InlineKeyboardMarkup:
    models = await list_models()
    buttons = [[InlineKeyboardButton(m, callback_data=f"MODEL|{m}")] for m in models]
    return InlineKeyboardMarkup(buttons)

async def cb_switch_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, model = q.data.split("|", 1)
    st = chats[q.message.chat_id]
    st["model"] = model
    await q.edit_message_text(f"✅ Модель переключена на *{model}*", parse_mode="Markdown")

# ─────────────── команды ─────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Я продвинутый LLM-бот.\n"
        "Команды:\n"
        "• /m – выбрать модель\n"
        "• /clear – очистить историю\n"
        "• /reset – история+контекст=Ø\n"
        "• /ctx add <txt> /ctx del – системный промпт\n"
        "• /thinking on|off – скрывать <think>"
    )
    await update.message.reply_text(text)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    st = chats[cid]
    if st["model"] is None:
        models = await list_models()
        st["model"] = models[0] if models else None
    text = (
        "👋 Я продвинутый LLM-бот.\n"
        "Команды:\n"
        "• /help – вызов списка команд\n"
        "• /m – выбрать модель\n"
        "• /clear – очистить историю\n"
        "• /reset – история+контекст=Ø\n"
        "• /ctx add <txt> /ctx del – системный промпт\n"
        "• /thinking on|off – скрывать <think>\n\n"
        "Ниже выберите модель или используйте /m."
    )
    await update.message.reply_text(text, reply_markup=await model_keyboard())

async def cmd_m(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Сменить модель:", reply_markup=await model_keyboard())

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chats[update.effective_chat.id]["history"].clear()
    await update.message.reply_text("🗑️ История очищена.")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st = chats[update.effective_chat.id]
    st["history"].clear()
    st["context"].clear()
    await update.message.reply_text("🔄 История и контекст удалены.")

async def cmd_ctx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 1:
        await update.message.reply_text("Используйте /ctx add <txt> или /ctx del")
        return
    st = chats[update.effective_chat.id]
    if ctx.args[0] == "add":
        text = " ".join(ctx.args[1:])
        st["context"].append({"role": "system", "content": text})
        await update.message.reply_text("➕ Контекст добавлен.")
    else:
        st["context"].clear()
        await update.message.reply_text("➖ Контекст удалён.")

async def cmd_thinking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or ctx.args[0] not in ("on", "off"):
        await update.message.reply_text("Используйте /thinking on|off")
        return
    chats[update.effective_chat.id]["thinking"] = ctx.args[0] == "on"
    await update.message.reply_text(f"🧠 Режим размышлений: {ctx.args[0]}")

# ─────────────── обработка текста ───────────────
async def chat_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    st = chats[cid]
    if st["model"] is None:
        await update.message.reply_text(
            "Пожалуйста, выберите модель:",
            reply_markup=await model_keyboard(),
        )
        return
    st["history"].append({"role": "user", "content": update.message.text})
    msgs = st["context"] + st["history"]
    res = client.chat(model=st["model"], messages=msgs)
    answer = res["message"]["content"]
    # Если режим размышлений выключен, удаляем все теги <think>...</think> из ответа
    if not st.get("thinking", True):
        answer = strip_thinking(answer)
    # Фильтруем иероглифы (CJK Unified Ideographs)
    answer = re.sub(r"[一-鿿]+", "", answer)
    st["history"].append({"role": "assistant", "content": answer})
    await update.message.reply_text(answer)

# ─────────────── обработка изображений ────────
async def chat_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    st = chats[cid]
    if st["model"] is None:
        await update.message.reply_text("Пожалуйста, выберите модель сначала.")
        return
    if not supports_vision(st["model"]):
        await update.message.reply_text("⚠️ Текущая модель не поддерживает обработку изображений.")
        return
    try:
        file_obj = None
        ext = None
        if update.message.photo:
            largest = update.message.photo[-1]
            await update.message.reply_photo(largest.file_id, caption="Обрабатываю изображение...")
            file_obj = await largest.get_file()
            ext = ".jpg"
        elif update.message.document and update.message.document.mime_type.startswith("image/"):
            doc = update.message.document
            await update.message.reply_document(doc.file_id, caption="Обрабатываю изображение...")
            file_obj = await doc.get_file()
            ext = Path(doc.file_name).suffix or mimetypes.guess_extension(doc.mime_type) or ""
        else:
            await update.message.reply_text("Пожалуйста, отправьте изображение (jpg/png/gif/…)")
            return
        tmp = tempfile.mkdtemp()
        img_path = Path(tmp) / f"{file_obj.file_id}{ext}"
        await file_obj.download_to_drive(img_path)
        prompt = update.message.caption or "Опиши изображение."
        st["history"].append({"role": "user", "content": prompt, "images": [str(img_path)]})
        msgs = st["context"] + st["history"]
        res = client.chat(model=st["model"], messages=msgs)
        answer = res["message"]["content"]
        if not st.get("thinking", True):
            answer = strip_thinking(answer)
        st["history"].append({"role": "assistant", "content": answer})
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обработке изображения: {e}")

# ─────────────── запуск ───────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("m", cmd_m))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("ctx", cmd_ctx))
    app.add_handler(CommandHandler("thinking", cmd_thinking))
    app.add_handler(CallbackQueryHandler(cb_switch_model, pattern=r"^MODEL\|"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, chat_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()