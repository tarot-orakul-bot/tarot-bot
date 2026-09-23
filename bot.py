import os
import random
import telebot
from telebot import types

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

bot = telebot.TeleBot(TOKEN)

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
    bot.send_message(
        message.chat.id,
        "✨ Раздел раскладов скоро будет доступен.\n\n"
        "Здесь мы добавим несколько видов раскладов и оплату Telegram Stars."
    )


@bot.message_handler(func=lambda message: message.text == "ℹ️ О боте")
def about(message):
    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул — бот для развлекательных раскладов Таро.\n\n"
        "Результаты не являются профессиональной медицинской, "
        "юридической, финансовой или иной консультацией."
    )


bot.infinity_polling(skip_pending=True)
