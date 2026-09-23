import os
import random
import threading
from datetime import date

import telebot
from flask import Flask
from telebot import types


TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)
last_card_date = {}



@app.route("/")
def home():
    return "Tarot Orakul Bot is running", 200


cards = [
    ("☀️ Солнце", "Сегодня день ясности, энергии и хороших возможностей."),
    ("🌙 Луна", "Прислушайся к интуиции. Не всё сегодня будет таким, каким кажется."),
    ("⭐ Звезда", "Сохраняй надежду. Ты движешься в правильном направлении."),
    ("❤️ Влюблённые", "Сегодня важную роль могут сыграть чувства и отношения."),
    ("🎡 Колесо Фортуны", "Возможен неожиданный поворот событий. Будь открыт переменам."),
    ("🪄 Маг", "У тебя есть возможности повлиять на ситуацию и сделать первый шаг."),
    ("👑 Императрица", "Хороший день для заботы о себе, творчества и новых идей."),
    ("🦁 Сила", "Спокойствие и уверенность помогут справиться с трудностями."),
    ("🌍 Мир", "Что-то подходит к завершению и освобождает место для нового."),
]


def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🔮 Карта дня")
    keyboard.row("✨ Сделать расклад", "ℹ️ О боте")
    return keyboard


@bot.message_handler(commands=["start"])
def start(message):
    text = (
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Здесь ты можешь получить карту дня и сделать расклад Таро.\n\n"
        "✨ Нажми кнопку ниже, чтобы начать."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == "🔮 Карта дня")
def card_of_the_day(message):
    user_id = message.from_user.id
    today = date.today()

    if last_card_date.get(user_id) == today:
        bot.send_message(
            message.chat.id,
            "🔮 Ты уже получил карту дня сегодня.\n\n"
            "Возвращайся завтра за новой картой ✨"
        )
        return

    last_card_date[user_id] = today

    card, meaning = random.choice(cards)

    text = (
        f"🔮 Твоя карта дня:\n\n"
        f"{card}\n\n"
        f"{meaning}\n\n"
        "Помни: Таро — развлекательная и рефлексивная практика, "
        "а не точное предсказание будущего."
    )

    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda message: message.text == "✨ Сделать расклад")
def reading(message):
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton("💕 Любовь", callback_data="reading_love"),
        types.InlineKeyboardButton("💰 Деньги", callback_data="reading_money")
    )

    keyboard.add(
        types.InlineKeyboardButton("🔮 3 карты", callback_data="reading_three"),
        types.InlineKeyboardButton("❓ Вопрос дня", callback_data="reading_question")
    )

    bot.send_message(
        message.chat.id,
        "✨ Выбери тип расклада:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("reading_"))
def reading_callback(call):
    readings = {
        "reading_love": (
            "💕 Расклад на любовь\n\n"
            "Прошлое — что повлияло на ситуацию.\n"
            "Настоящее — что происходит сейчас.\n"
            "Будущее — возможное направление развития."
        ),
        "reading_money": (
            "💰 Расклад на деньги\n\n"
            "Текущая ситуация — что происходит с финансами.\n"
            "Возможность — где может появиться шанс.\n"
            "Совет — на что стоит обратить внимание."
        ),
        "reading_three": (
            "🔮 Расклад «3 карты»\n\n"
            "1️⃣ Прошлое\n"
            "2️⃣ Настоящее\n"
            "3️⃣ Возможное будущее"
        ),
        "reading_question": (
            "❓ Расклад на вопрос дня\n\n"
            "Сформулируй вопрос про себя и ситуацию, "
            "а карты дадут символическую интерпретацию."
        ),
    }

    result = readings.get(call.data, "Расклад не найден.")

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, result)
    
@bot.message_handler(func=lambda message: message.text == "ℹ️ О боте")
def about(message):
    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул — бот для развлекательных раскладов Таро.\n\n"
        "Результаты не являются профессиональной медицинской, "
        "юридической, финансовой или иной консультацией."
    )


def run_bot():
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
