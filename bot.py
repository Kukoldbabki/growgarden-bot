import json
import time
import logging
import threading
import requests
import telebot
from telebot import apihelper, types

# ================== НАСТРОЙКИ ==================
API_TOKEN = "7871400456:AAGqreZevm6GpViypbYYQ8wjcs4VnV8ueR0"  # Замени на свой токен
WATCHFILE = "watchlist.json"
STATE_FILE = "bot_state.json"
API_BASE = "https://grow-garden-api.herokuapp.com/api"
CHECK_INTERVAL = 300  # 5 минут (в секундах)
# ================================================

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Устанавливаем таймауты для запросов к Telegram API
apihelper.READ_TIMEOUT = 30
apihelper.CONNECT_TIMEOUT = 10

bot = telebot.TeleBot(API_TOKEN)

# --------- ХРАНИЛИЩЕ ДАННЫХ ---------
def load_data():
    try:
        with open(WATCHFILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    with open(WATCHFILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("notified", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_state(notified_set):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"notified": list(notified_set)}, f, ensure_ascii=False)

# --------- ПАРСИНГ API ---------
def fetch_all_items():
    try:
        resp = requests.get(f"{API_BASE}/items", timeout=10)
        resp.raise_for_status()
        return [item["name"] for item in resp.json()]
    except Exception as e:
        logger.error(f"Ошибка получения предметов: {e}")
        return []

# --------- ТЕЛЕГРАМ-ИНТЕРФЕЙС ---------
def main_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🔔 Отслеживать", callback_data="track"),
        types.InlineKeyboardButton("📋 Просмотр", callback_data="view"),
    )
    return kb

def items_keyboard(user_id):
    available = fetch_all_items()
    user_data = load_data().get(str(user_id), [])
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    for name in available:
        status = "✅" if name in user_data else "➕"
        kb.add(types.InlineKeyboardButton(
            f"{status} {name}", 
            callback_data=f"tog|{name}"
        ))
    
    kb.row(types.InlineKeyboardButton("◀️ Назад", callback_data="back"))
    return kb

# --------- ОБРАБОТЧИКИ КОМАНД ---------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "🌱 *Бот отслеживания семян Grow Garden*\n"
        "Нажми 🔔 чтобы выбрать семена для отслеживания",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "track")
def track_callback(call):
    bot.edit_message_text(
        "🔍 Выбери предметы:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=items_keyboard(call.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: call.data == "view")
def view_callback(call):
    user_items = load_data().get(str(call.from_user.id), [])
    text = "📋 Ваш список отслеживания:\n" + "\n".join(f"• {item}" for item in user_items) if user_items else "_Список пуст_"
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tog|"))
def toggle_item(call):
    _, item_name = call.data.split("|", 1)
    data = load_data()
    user_id = str(call.from_user.id)
    user_items = set(data.get(user_id, []))
    
    if item_name in user_items:
        user_items.remove(item_name)
    else:
        user_items.add(item_name)
    
    data[user_id] = list(user_items)
    save_data(data)
    bot.answer_callback_query(call.id, f"{'❌ Удалено' if item_name in user_items else '✅ Добавлено'} {item_name}")
    bot.edit_message_reply_markup(
        call.message.chat.id,
        call.message.message_id,
        reply_markup=items_keyboard(call.from_user.id)
    )

# --------- МОНИТОРИНГ ИЗМЕНЕНИЙ ---------
def check_stock():
    notified = load_state()
    user_data = load_data()
    
    try:
        resp = requests.get(f"{API_BASE}/stock", timeout=15)
        resp.raise_for_status()
        current_stock = resp.json()
        
        for user_id, tracked_items in user_data.items():
            for item in current_stock:
                if item["name"] in tracked_items and item.get("in_stock"):
                    item_key = f"{user_id}|{item['name']}"
                    
                    if item_key not in notified:
                        try:
                            bot.send_message(
                                int(user_id),
                                f"🌱 *ДОСТУПНО!* {item['name']}\n"
                                f"💵 Цена: {item.get('price', '?')}",
                                parse_mode="Markdown"
                            )
                            notified.add(item_key)
                            save_state(notified)
                        except Exception as e:
                            logger.error(f"Ошибка отправки: {e}")
        
        # Очистка устаревших уведомлений
        for item_key in list(notified):
            user_id, item_name = item_key.split("|", 1)
            if not any(i["name"] == item_name and i.get("in_stock") for i in current_stock):
                notified.remove(item_key)
                save_state(notified)
                
    except Exception as e:
        logger.error(f"Ошибка проверки стока: {e}")

# --------- ЗАПУСК БОТА ---------
def run_bot():
    logger.info("Запуск бота...")
    
    # Удаляем все вебхуки перед стартом
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        logger.error(f"Ошибка удаления вебхука: {e}")
    
    # Запускаем мониторинг в фоне
    def background_monitor():
        while True:
            check_stock()
            time.sleep(CHECK_INTERVAL)
    
    monitor_thread = threading.Thread(target=background_monitor, daemon=True)
    monitor_thread.start()
    
    # Основной цикл бота (с перезапуском при ошибках)
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            logger.error(f"Бот упал: {e}")
            time.sleep(5)  # Пауза перед перезапуском

if __name__ == "__main__":
    run_bot()
