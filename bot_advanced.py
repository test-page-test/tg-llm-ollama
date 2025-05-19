#!/usr/bin/env python3
"""
bot_advanced.py
▸ /start           – привет + выбор модели кнопкой
▸ /m               – вывести клавиатуру моделей
▸ /model <имя>     – вручную задать модель
▸ /clear           – стереть историю
▸ /reset           – стереть и историю, и системный контекст
▸ /ctx add <txt>   – системный промпт +
▸ /ctx del         – системный промпт Ø
▸ /thinking on|off – скрывать <think>…</think> у gemma3:1b
▸ фото + подпись   – vision-запрос (если модель умеет)
"""
import os, tempfile
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
from ollama import Client
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from utils import strip_thinking, supports_vision

# ─────────────── конфигурация ───────────────
load_dotenv()
TOKEN          = os.getenv("BOT_TOKEN")
HOST           = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL  = os.getenv("DEFAULT_MODEL", "qwen3:4b")
ALT_MODEL      = os.getenv("ALT_MODEL",     "gemma3:4b")
THINKING_OFF_OK= {"qwen3:4b"}                 # где актуален /thinking off

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

AVAILABLE = [DEFAULT_MODEL, ALT_MODEL]
client = Client(host=HOST)

# ─────────────── состояние ───────────────────
def new_state():
    return {
        "model":   DEFAULT_MODEL,
        "history": [],
        "context": [],
        "thinking": True,
    }
chats = defaultdict(new_state)

# ─────────────── клавиатура моделей ─────────
def model_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(m, callback_data=f"MODEL|{m}")]
            for m in AVAILABLE]
    return InlineKeyboardMarkup(rows)

async def cb_switch_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, model = q.data.split("|", 1)
    st = chats[q.message.chat_id]
    st["model"] = model
    await q.edit_message_text(
        f"✅ Модель переключена на *{model}*",
        parse_mode="Markdown",
    )

# ─────────────── команды ────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я продвинутый LLM-бот.\n"
        "Команды:\n"
        "• /m – выбрать модель\n"
        "• /clear – очистить историю\n"
        "• /reset – история + контекст = Ø\n"
        "• /ctx add <txt> /ctx del – системный промпт\n"
        "• /thinking on|off – скрывать <think>\n\n"
        "Ниже выберите модель:",
        reply_markup=model_keyboard(),
    )

async def cmd_m(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Сменить модель:", reply_markup=model_keyboard()
    )

async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Используйте /model <имя>")
        return
    chats[update.effective_chat.id]["model"] = ctx.args[0]
    await update.message.reply_text(f"✅ Модель переключена на {ctx.args[0]}")

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
        await update.message.reply_text("/ctx add <текст>  или  /ctx del")
        return
    st = chats[update.effective_chat.id]
    action = ctx.args[0]
    if action == "add":
        text = " ".join(ctx.args[1:])
        st["context"].append({"role": "system", "content": text})
        await update.message.reply_text("➕ Контекст добавлен.")
    elif action == "del":
        st["context"].clear()
        await update.message.reply_text("➖ Контекст удалён.")

async def cmd_thinking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or ctx.args[0] not in ("on", "off"):
        await update.message.reply_text("/thinking on|off")
        return
    chats[update.effective_chat.id]["thinking"] = ctx.args[0] == "on"
    await update.message.reply_text(f"🧠 Режим размышлений: {ctx.args[0]}")

# ─────────────── текст ──────────────────────
async def chat_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    st  = chats[cid]
    st["history"].append({"role": "user", "content": update.message.text})
    msgs = st["context"] + st["history"]

    res = client.chat(model=st["model"], messages=msgs)
    answer = res["message"]["content"]

    if (not st["thinking"]) and (st["model"] in THINKING_OFF_OK):
        answer = strip_thinking(answer)

    st["history"].append({"role": "assistant", "content": answer})
    await update.message.reply_text(answer)

# ─────────────── изображения ────────────────
async def chat_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    st  = chats[cid]

    if not supports_vision(st["model"]):
        await update.message.reply_text("⚠️ Текущая модель не умеет vision.")
        return

    photo = await update.message.photo[-1].get_file()
    tmp = tempfile.mkdtemp()
    img = Path(tmp) / f"{photo.file_id}.jpg"
    await photo.download_to_drive(img)

    prompt = update.message.caption or "Опиши изображение."
    st["history"].append({"role": "user", "content": prompt, "images": [str(img)]})
    msgs = st["context"] + st["history"]

    res = client.chat(model=st["model"], messages=msgs)
    answer = res["message"]["content"]
    st["history"].append({"role": "assistant", "content": answer})
    await update.message.reply_text(answer)

# ─────────────── запуск ─────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("m",         cmd_m))
    app.add_handler(CommandHandler("model",     cmd_model))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("reset",     cmd_reset))
    app.add_handler(CommandHandler("ctx",       cmd_ctx))
    app.add_handler(CommandHandler("thinking",  cmd_thinking))

    app.add_handler(CallbackQueryHandler(cb_switch_model, pattern=r"^MODEL\|"))
    app.add_handler(MessageHandler(filters.PHOTO, chat_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
