import json
import time
import logging
import threading
import requests
import telebot
from telebot import apihelper, types

# ================== НАСТРОЙКИ ==================
API_TOKEN = "7871400456:AAGqreZevm6GpViypbYYQ8wjcs4VnV8ueR0"  # Замени на свой
WATCHFILE = "watchlist.json"
STATE_FILE = "bot_state.json"
CHECK_INTERVAL = 300  # 5 минут
# ================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Увеличиваем таймауты для нестабильных соединений
apihelper.READ_TIMEOUT = 45
apihelper.CONNECT_TIMEOUT = 30
apihelper.RETRY_ON_ERROR = True

bot = telebot.TeleBot(API_TOKEN, threaded=False)  # Отключаем многопоточность

# Глобальная блокировка для работы с файлами
file_lock = threading.Lock()

def load_data():
    with file_lock:
        try:
            with open(WATCHFILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

def save_data(data):
    with file_lock:
        with open(WATCHFILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def load_state():
    with file_lock:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f).get("notified", []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

def save_state(notified_set):
    with file_lock:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"notified": list(notified_set)}, f, ensure_ascii=False)

# Альтернативный источник данных, если API недоступно
MOCK_ITEMS = [
    "Семена огурца", "Семена томата", "Семена перца",
    "Удобрение BioGrow", "Грунт Premium"
]

def fetch_all_items():
    """Запасной вариант, если API не работает"""
    try:
        # Пробуем получить данные с основного API
        resp = requests.get("https://grow-garden-api.herokuapp.com/api/items", timeout=10)
        resp.raise_for_status()
        return [item["name"] for item in resp.json()]
    except Exception as e:
        logger.warning(f"API недоступно, используем mock-данные. Ошибка: {e}")
        return MOCK_ITEMS

def check_stock():
    """Упрощенная проверка без внешнего API"""
    try:
        notified = load_state()
        user_data = load_data()
        
        # В реальном боте здесь должен быть запрос к API
        # Для примера просто возвращаем mock-данные
        mock_stock = [
            {"name": "Семена огурца", "in_stock": True, "price": "149 ₽"},
            {"name": "Удобрение BioGrow", "in_stock": False}
        ]
        
        for user_id, tracked_items in user_data.items():
            for item in mock_stock:
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
        current_items = {i["name"] for i in mock_stock if i.get("in_stock")}
        for item_key in list(notified):
            _, item_name = item_key.split("|", 1)
            if item_name not in current_items:
                notified.remove(item_key)
                save_state(notified)
                
    except Exception as e:
        logger.error(f"Ошибка проверки стока: {e}")

def run_bot():
    logger.info("Запуск бота...")
    
    # Принудительно удаляем все вебхуки
    try:
        bot.remove_webhook()
        time.sleep(2)
        logger.info("Вебхуки удалены")
    except Exception as e:
        logger.error(f"Ошибка удаления вебхуков: {e}")
    
    # Проверяем, не запущен ли уже бот
    try:
        me = bot.get_me()
        logger.info(f"Бот @{me.username} готов к работе")
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        return
    
    # Фоновый мониторинг
    def monitor():
        while True:
            check_stock()
            time.sleep(CHECK_INTERVAL)
    
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    
    # Основной цикл с защитой от падений
    while True:
        try:
            logger.info("Запуск polling...")
            bot.infinity_polling(
                none_stop=True,
                timeout=30,
                long_polling_timeout=20
            )
        except Exception as e:
            logger.error(f"Бот упал: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
