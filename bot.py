import json
import time
import requests
from bs4 import BeautifulSoup
import os
import telebot
import schedule

# ================== Настройки ==================
API_TOKEN  = os.getenv("API_TOKEN")  # из Render environment
YOUR_CHAT  = int(os.getenv("YOUR_CHAT_ID"))  # из Render environment
WATCHFILE  = "watchlist.json"
# URL публичного API из репозитория XanaOG
API_BASE   = os.getenv("API_BASE", "https://grow-garden-api.herokuapp.com/api")  # или свой API URL
CHECK_FREQ = 5  # минуты 5  # минуты

bot = telebot.TeleBot(API_TOKEN)
notified = set()

# --------- Работа с локальным JSON-хранилищем ---------
def load_data():
    try:
        return json.load(open(WATCHFILE, "r", encoding="utf-8"))
    except:
        return {}

def save_data(d):
    json.dump(d, open(WATCHFILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# --------- Вытягиваем все доступные предметы ---------
def fetch_all_items():
    """
    Запрос к API, возвращающему список всех предметов:
    GET {API_BASE}/items
    Ответ: [{ id, name, category, ... }, ...]
    """
    resp = requests.get(f"{API_BASE}/items")
    resp.raise_for_status()
    return [item["name"] for item in resp.json()]

# --------- Telegram-меню ---------
def main_kb():
    kb = telebot.types.InlineKeyboardMarkup()
    kb.row(
        telebot.types.InlineKeyboardButton("🔔 Отслеживать", callback_data="track"),
        telebot.types.InlineKeyboardButton("📋 Просмотр", callback_data="view"),
    )
    return kb

# Кнопки для выбора предметов
def items_kb(user_id):
    available = fetch_all_items()
    data = load_data().get(str(user_id), [])
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    for name in available:
        mark = "✅" if name in data else "➕"
        kb.insert(
            telebot.types.InlineKeyboardButton(f"{mark} {name}", callback_data=f"tog|{name}")
        )
    kb.row(telebot.types.InlineKeyboardButton("◀️ Назад", callback_data="back"))
    return kb

# --------- Хэндлеры ---------  
@bot.message_handler(commands=["start"])
def cmd_start(m):
    bot.send_message(m.chat.id, "🌱 Главное меню:", reply_markup=main_kb())

@bot.callback_query_handler(lambda c: c.data == "track")
def cb_track(c):
    bot.edit_message_text(
        "🔍 Выбери предметы:", c.from_user.id, c.message.message_id,
        reply_markup=items_kb(c.from_user.id)
    )

@bot.callback_query_handler(lambda c: c.data == "view")
def cb_view(c):
    wl = load_data().get(str(c.from_user.id), [])
    text = "📋 Твой список:\n" + ("\n".join(f"• {x}" for x in wl) if wl else "_пусто_")
    bot.edit_message_text(text, c.from_user.id, c.message.message_id, parse_mode="Markdown", reply_markup=main_kb())

@bot.callback_query_handler(lambda c: c.data.startswith("tog|"))
def cb_toggle(c):
    _, name = c.data.split("|", 1)
    d = load_data()
    uid = str(c.from_user.id)
    wl = set(d.get(uid, []))
    if name in wl: wl.remove(name)
    else: wl.add(name)
    d[uid] = list(wl)
    save_data(d)
    # Обновляем меню
    bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=items_kb(c.from_user.id))

# --------- Мониторинг стока ---------
def check_stock():
    d = load_data()
    if not d: return
    # GET /listings или /stock в API
    resp = requests.get(f"{API_BASE}/stock")
    resp.raise_for_status()
    stocks = resp.json()  # ожидаем [{ name, price, in_stock }, ...]
    for uid, wl in d.items():
        for item in stocks:
            if item["name"] in wl and item.get("in_stock"):
                key = f"{uid}|{item['name']}"
                if key not in notified:
                    bot.send_message(int(uid), f"🔔 {item['name']} в наличии за {item['price']}!", parse_mode="Markdown")
                    notified.add(key)
    # Очищаем ушедшие
    for key in list(notified):
        uid, name = key.split('|',1)
        if name not in [i['name'] for i in stocks if i.get('in_stock')]:
            notified.remove(key)

# --------- Старт ---------
if __name__ == "__main__":
    schedule.every(CHECK_FREQ).minutes.do(check_stock)
    # Запускаем расписание в фоне
    import _thread
    def loop():
        while True:
            schedule.run_pending()
            time.sleep(1)
    _thread.start_new_thread(loop, ())
    bot.infinity_polling()
