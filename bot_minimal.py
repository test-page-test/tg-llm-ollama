#!/usr/bin/env python3
"""
bot_minimal.py
▸ /start   – привет + кнопки моделей
▸ /m       – показать кнопки ещё раз
▸ /model   – переключить вручную
История держится в RAM, пока скрипт запущен.
"""
import os
from collections import defaultdict
from dotenv import load_dotenv
from ollama import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─────────────── конфигурация ───────────────
load_dotenv()                                       # читаем .env
TOKEN   = os.getenv("BOT_TOKEN")
HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_A = os.getenv("MODEL_A", "qwen3:4b")
MODEL_B = os.getenv("MODEL_B", "gemma3:4b")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

AVAILABLE = [MODEL_A, MODEL_B]                      # список разрешённых
client = Client(host=HOST)

# ─────────────── состояние чатов ──────────────
chats = defaultdict(lambda: {"model": MODEL_A, "history": []})

# ─────────────── клавиатура ───────────────────
def model_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(m, callback_data=f"MODEL|{m}")] for m in AVAILABLE]
    )

# ─────────────── callback кнопок ──────────────
async def cb_switch_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, model = query.data.split("|", 1)
    st = chats[query.message.chat_id]
    st["model"] = model
    await query.edit_message_text(
        f"✅ Модель переключена на *{model}*",
        parse_mode="Markdown",
    )

# ─────────────── команды ──────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я локальный LLM-бот.\n"
        "Нажмите кнопку, чтобы выбрать модель.",
        reply_markup=model_keyboard(),
    )

async def cmd_m(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Сменить модель:", reply_markup=model_keyboard()
    )

async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Используйте /model <имя_модели>")
        return
    name = ctx.args[0]
    if name not in AVAILABLE:
        await update.message.reply_text(f"Неизвестная модель. Доступно: {', '.join(AVAILABLE)}")
        return
    chats[update.effective_chat.id]["model"] = name
    await update.message.reply_text(f"✅ Модель переключена на {name}")

# ─────────────── чат ─────────────────────────
async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid   = update.effective_chat.id
    state = chats[cid]
    state["history"].append({"role": "user", "content": update.message.text})

    res = client.chat(model=state["model"], messages=state["history"])
    answer = res["message"]["content"]

    state["history"].append({"role": "assistant", "content": answer})
    await update.message.reply_text(answer)

# ─────────────── запуск ──────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("m",     cmd_m))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CallbackQueryHandler(cb_switch_model, pattern=r"^MODEL\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
