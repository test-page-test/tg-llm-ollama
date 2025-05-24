# Beginner Lil-bot for all!
"""
bot_minimal.py
▸ /start – привет + кнопки моделей
▸ /m     – показать кнопки ещё раз
История держится в RAM, пока скрипт запущен.
"""
import os
from typing import List
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

# ─────────────── конфигурация ─────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

# клиент для Ollama по умолчанию на localhost:11434
client = Client(host="http://localhost:11434")

# состояние чатов
chats = defaultdict(lambda: {"model": None, "history": []})

# ─────────────── динамическое получение моделей ─
async def list_models() -> List[str]:
    # запрашиваем список моделей через HTTP
    base_url = "http://localhost:11434"
    url = f"{base_url}/api/tags"
    async with httpx.AsyncClient() as session:
        resp = await session.get(url)
        resp.raise_for_status()
        tags = resp.json()
    raw = tags.get("models", [])
    # извлекаем имена моделей
    models = [m.get("name") for m in raw if isinstance(m, dict) and "name" in m]
    return sorted(models)

# ─────────────── клавиатура ───────────────────
async def model_keyboard() -> InlineKeyboardMarkup:
    models = await list_models()
    buttons = [[InlineKeyboardButton(m, callback_data=f"MODEL|{m}")] for m in models]
    return InlineKeyboardMarkup(buttons)

# ─────────────── callback кнопок ──────────────
async def cb_switch_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, model = query.data.split("|", 1)
    chats[query.message.chat_id]["model"] = model
    await query.edit_message_text(
        f"✅ Модель переключена на *{model}*",
        parse_mode="Markdown",
    )

# ─────────────── команды ──────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    # инициализируем модель по умолчанию при первом запросе
    if chats[cid]["model"] is None:
        models = await list_models()
        chats[cid]["model"] = models[0] if models else None
    text = (
        "👋 Привет! Я локальный LLM-бот.\n"
        "Нажмите кнопку, чтобы выбрать модель, или используйте /m для повторного показа списка."
    )
    await update.message.reply_text(
        text, reply_markup=await model_keyboard()
    )

async def cmd_m(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Сменить модель:", reply_markup=await model_keyboard()
    )

# ─────────────── чат ─────────────────────────
async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    state = chats[cid]
    if state.get("model") is None:
        # если модель не выбрана, предлагаем клавиатуру
        await update.message.reply_text(
            "Пожалуйста, выберите модель сначала.",
            reply_markup=await model_keyboard(),
        )
        return
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
    app.add_handler(CallbackQueryHandler(cb_switch_model, pattern=r"^MODEL\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()