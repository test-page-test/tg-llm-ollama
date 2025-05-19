# llm-telegram-demo

Два Telegram-бота с локальными LLM с Ollama:
* **bot_minimal.py** — переключение между 2 моделями.
* **bot_advanced.py** — история, контекст, vision, cut-thinking.

## Быстрый старт
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # впишите свой BOT_TOKEN
ollama serve 
python bot_minimal.py
```