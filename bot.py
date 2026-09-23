import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Здесь ты сможешь получить карту дня и сделать расклад Таро."
    )

bot.infinity_polling()
