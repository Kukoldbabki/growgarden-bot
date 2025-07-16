import os
import telebot
import requests
import json
from flask import Flask, request

API_TOKEN = os.getenv("API_TOKEN")
YOUR_CHAT = int(os.getenv("YOUR_CHAT_ID"))
WATCHFILE = "watchlist.json"
API_BASE = os.getenv("API_BASE", "https://grow-garden-api.herokuapp.com/api")
CHECK_FREQ = 5

bot = telebot.TeleBot(API_TOKEN)

# --- Webhook Setup ---
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://your-service-name.onrender.com")
WEBHOOK_PATH = f"/{API_TOKEN}/"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

@app.route('/')
def index():
    return 'Bot is running!'

# --- Logic ---
def load_watchlist():
    try:
        with open(WATCHFILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_watchlist(data):
    with open(WATCHFILE, 'w') as f:
        json.dump(data, f)

def fetch_items():
    res = requests.get(f"{API_BASE}/stocks.php")
    if res.status_code == 200:
        return res.json()
    return []

@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📈 Отслеживать", "👁️ Просмотр")
    bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "👁️ Просмотр")
def show_watchlist(message):
    items = load_watchlist()
    if items:
        msg = '\n'.join(items)
        bot.send_message(message.chat.id, f"🎯 Отслеживаемые предметы:\n{msg}")
    else:
        bot.send_message(message.chat.id, "Ничего не отслеживается")

@bot.message_handler(func=lambda m: m.text == "📈 Отслеживать")
def track_items(message):
    items = fetch_items()
    if not items:
        bot.send_message(message.chat.id, "Ошибка загрузки предметов")
        return
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for item in items[:10]:
        keyboard.add(item.get("name", "Неизвестно"))
    bot.send_message(message.chat.id, "Выбери предмет для отслеживания:", reply_markup=keyboard)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if message.text:
        watchlist = load_watchlist()
        if message.text not in watchlist:
            watchlist.append(message.text)
            save_watchlist(watchlist)
            bot.send_message(message.chat.id, f"✅ Добавлено в отслеживание: {message.text}")
        else:
            bot.send_message(message.chat.id, f"Уже отслеживается: {message.text}")

# --- Start ---
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
