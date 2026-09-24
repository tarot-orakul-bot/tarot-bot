import os
import random
import threading
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import telebot
from flask import Flask
from telebot import types


TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))
PRICE = 15
TZ = ZoneInfo("Asia/Yekaterinburg")

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Нужны переменные BOT_TOKEN и DATABASE_URL в Render")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

CARDS = [
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

SPREADS = {
    "love": ("💕 Расклад на любовь", ("Прошлое", "Настоящее", "Возможное будущее")),
    "money": ("💰 Расклад на деньги", ("Текущая ситуация", "Возможность", "Совет")),
    "three": ("🔮 Расклад «3 карты»", ("Прошлое", "Настоящее", "Возможное будущее")),
}
NUMBERS = ("1️⃣", "2️⃣", "3️⃣")


@app.route("/")
def home():
    return "Tarot Orakul Bot is running", 200


def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                daily_card DATE,
                daily_question DATE,
                three_used BOOLEAN NOT NULL DEFAULT FALSE,
                terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
                support_pending BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                charge_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                kind TEXT NOT NULL,
                result TEXT NOT NULL,
                delivered BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id BIGINT NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def claim_free(user_id, field):
    with db() as conn:
        if field == "three_used":
            row = conn.execute("""
                INSERT INTO users (user_id, three_used) VALUES (%s, TRUE)
                ON CONFLICT (user_id) DO UPDATE SET three_used = TRUE
                WHERE users.three_used = FALSE
                RETURNING user_id
            """, (user_id,)).fetchone()
        else:
            if field not in ("daily_card", "daily_question"):
                raise ValueError("Неизвестный бесплатный расклад")
            today = datetime.now(TZ).date()
            row = conn.execute(f"""
                INSERT INTO users (user_id, {field}) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET {field} = EXCLUDED.{field}
                WHERE users.{field} IS DISTINCT FROM EXCLUDED.{field}
                RETURNING user_id
            """, (user_id, today)).fetchone()
        return row is not None


def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🔮 Карта дня")
    keyboard.row("✨ Сделать расклад", "ℹ️ О боте")
    return keyboard


def spread(kind):
    title, positions = SPREADS[kind]
    chosen = random.sample(CARDS, 3)
    lines = [title]
    for number, position, (name, meaning) in zip(NUMBERS, positions, chosen):
        lines.append(f"{number} {position} — {name}\n{meaning}")
    ending = (
        "🔮 Символическая интерпретация, а не финансовый совет."
        if kind == "money"
        else "✨ Используй этот расклад как повод для размышления."
    )
    return "\n\n".join(lines + [ending])


def day_card_text():
    name, meaning = random.choice(CARDS)
    return (
        f"🔮 Твоя карта дня:\n\n{name}\n\n{meaning}\n\n"
        "Таро — развлекательная практика, а не точное предсказание."
    )


def question_text():
    name, meaning = random.choice(CARDS)
    return (
        "❓ Вопрос дня\n\n"
        "Сформулируй свой вопрос про себя, затем прочитай карту:\n\n"
        f"{name}\n\n{meaning}\n\n"
        "🔮 Карта предлагает символическую интерпретацию, а не однозначный ответ."
    )


def answer(call, text=None):
    bot.answer_callback_query(call.id, text=text)


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Карта дня и Вопрос дня доступны раз в день. "
        "Первый расклад «3 карты» бесплатный.\n\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(commands=["myid"])
def myid(message):
    bot.send_message(message.chat.id, f"Твой Telegram ID: {message.from_user.id}")


@bot.message_handler(commands=["terms"])
def terms(message):
    bot.send_message(
        message.chat.id,
        "Условия Таро Оракул\n\n"
        "Бесплатно: Карта дня и Вопрос дня — по одному разу в день; "
        "первый расклад «3 карты» — один раз на аккаунт.\n\n"
        f"Платные расклады Любовь, Деньги и последующие «3 карты» стоят "
        f"{PRICE} Stars за каждый расклад. "
        "Результат приходит сразу после успешной оплаты. "
        "Это символическая развлекательная интерпретация, "
        "а не точное предсказание или медицинская, финансовая, "
        "юридическая консультация. Если возникла проблема "
        "с оплатой или результатом, напиши /paysupport.",
    )


@bot.message_handler(commands=["support", "paysupport"])
def support(message):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, support_pending) VALUES (%s, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET support_pending = TRUE
        """, (message.from_user.id,))
    bot.send_message(
        message.chat.id,
        "Опиши проблему одним сообщением. "
        "Не присылай пароль, токен или данные карты.",
    )


@bot.message_handler(commands=["reply"])
def reply_to_ticket(message):
    if message.from_user.id != OWNER_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        bot.send_message(
            message.chat.id,
            "Формат: /reply НОМЕР_ОБРАЩЕНИЯ ответ",
        )
        return

    with db() as conn:
        row = conn.execute(
            "SELECT user_id FROM support_tickets WHERE id = %s",
            (int(parts[1]),),
        ).fetchone()

    if not row:
        bot.send_message(message.chat.id, "Обращение не найдено.")
        return

    bot.send_message(
        row[0],
        f"Ответ поддержки по обращению №{parts[1]}:\n\n{parts[2]}",
    )
    bot.send_message(message.chat.id, "Ответ отправлен.")


@bot.message_handler(func=lambda m: m.text == "🔮 Карта дня")
def card_of_the_day(message):
    if not claim_free(message.from_user.id, "daily_card"):
        bot.send_message(
            message.chat.id,
            "🔮 Ты уже получил карту дня сегодня. Возвращайся завтра ✨",
        )
        return
    bot.send_message(message.chat.id, day_card_text())


@bot.message_handler(func=lambda m: m.text == "✨ Сделать расклад")
def reading(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "💕 Любовь", callback_data="reading_love"
        ),
        types.InlineKeyboardButton(
            "💰 Деньги", callback_data="reading_money"
        ),
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🔮 3 карты", callback_data="reading_three"
        ),
        types.InlineKeyboardButton(
            "❓ Вопрос дня", callback_data="reading_question"
        ),
    )
    bot.send_message(
        message.chat.id,
        "✨ Выбери тип расклада:",
        reply_markup=keyboard,
    )


@bot.message_handler(func=lambda m: m.text == "ℹ️ О боте")
def about(message):
    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул — бот для символических "
        "развлекательных раскладов.\n\n"
        "Условия: /terms. Помощь: /support.",
    )


def offer_payment(chat_id, user_id, kind):
    if not OWNER_ID:
        bot.send_message(
            chat_id,
            "Оплата пока настраивается. Попробуй позже.",
        )
        return

    with db() as conn:
        row = conn.execute(
            "SELECT terms_accepted FROM users WHERE user_id = %s",
            (user_id,),
        ).fetchone()

    if not row or not row[0]:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "📖 Условия", callback_data="show_terms"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Согласен с условиями",
                callback_data=f"agree_{kind}",
            )
        )
        bot.send_message(
            chat_id,
            f"Один расклад стоит {PRICE} Stars. "
            "Перед оплатой ознакомься с условиями /terms.",
            reply_markup=keyboard,
        )
        return

    title = SPREADS[kind][0]
    payload = f"{kind}:{user_id}:{uuid4().hex}"
    bot.send_invoice(
        chat_id,
        title,
        "Один символический расклад Таро из трёх карт.",
        payload,
        None,
        "XTR",
        [types.LabeledPrice(title, PRICE)],
    )


@bot.callback_query_handler(
    func=lambda c: c.data and c.data.startswith("reading_")
)
def reading_callback(call):
    kind = call.data.removeprefix("reading_")

    if kind == "question":
        if not claim_free(call.from_user.id, "daily_question"):
            answer(call, "Вопрос дня уже был сегодня")
            bot.send_message(
                call.message.chat.id,
                "❓ Ты уже получил Вопрос дня сегодня. "
                "Возвращайся завтра ✨",
            )
            return

        answer(call)
        bot.send_message(call.message.chat.id, question_text())
        return

    if kind not in SPREADS:
        answer(call, "Расклад не найден")
        return

    if kind == "three" and claim_free(call.from_user.id, "three_used"):
        answer(call)
        bot.send_message(call.message.chat.id, spread(kind))
        return

    answer(call)
    offer_payment(call.message.chat.id, call.from_user.id, kind)


@bot.callback_query_handler(func=lambda c: c.data == "show_terms")
def show_terms(call):
    answer(call)
    terms(call.message)


@bot.callback_query_handler(
    func=lambda c: c.data and c.data.startswith("agree_")
)
def agree(call):
    kind = call.data.removeprefix("agree_")
    if kind not in SPREADS:
        answer(call, "Неизвестный расклад")
        return

    with db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, terms_accepted)
            VALUES (%s, TRUE)
            ON CONFLICT (user_id)
            DO UPDATE SET terms_accepted = TRUE
        """, (call.from_user.id,))

    answer(call)
    offer_payment(call.message.chat.id, call.from_user.id, kind)


def invoice_details(payload, user_id):
    parts = payload.split(":")
    if (
        len(parts) != 3
        or parts[0] not in SPREADS
        or parts[1] != str(user_id)
        or len(parts[2]) != 32
    ):
        return None
    return parts[0]


@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(query):
    try:
        kind = invoice_details(
            query.invoice_payload,
            query.from_user.id,
        )
        with db() as conn:
            row = conn.execute(
                "SELECT terms_accepted FROM users WHERE user_id = %s",
                (query.from_user.id,),
            ).fetchone()

        ok = bool(
            OWNER_ID
            and kind
            and row
            and row[0]
            and query.currency == "XTR"
            and query.total_amount == PRICE
        )
        bot.answer_pre_checkout_query(
            query.id,
            ok=ok,
            error_message=(
                None if ok else "Оплата недоступна. Попробуй снова."
            ),
        )
    except Exception:
        bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message="Не удалось проверить оплату. Попробуй позже.",
        )


@bot.message_handler(content_types=["successful_payment"])
def payment_success(message):
    payment = message.successful_payment
    kind = invoice_details(
        payment.invoice_payload,
        message.from_user.id,
    )

    if (
        not kind
        or payment.currency != "XTR"
        or payment.total_amount != PRICE
    ):
        bot.send_message(
            message.chat.id,
            "Платёж получен. Напиши /paysupport "
            "для проверки результата.",
        )
        return

    charge_id = payment.telegram_payment_charge_id
    with db() as conn:
        conn.execute("""
            INSERT INTO payments (charge_id, user_id, kind, result)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (charge_id) DO NOTHING
        """, (
            charge_id,
            message.from_user.id,
            kind,
            spread(kind),
        ))
        row = conn.execute(
            "SELECT user_id, result, delivered "
            "FROM payments WHERE charge_id = %s",
            (charge_id,),
        ).fetchone()

    if row[0] != message.from_user.id or row[2]:
        return

    bot.send_message(message.chat.id, row[1])

    with db() as conn:
        conn.execute(
            "UPDATE payments SET delivered = TRUE "
            "WHERE charge_id = %s",
            (charge_id,),
        )


@bot.message_handler(
    content_types=["text"],
    func=lambda m: True,
)
def other_text(message):
    with db() as conn:
        row = conn.execute(
            "SELECT support_pending FROM users WHERE user_id = %s",
            (message.from_user.id,),
        ).fetchone()

        if not row or not row[0]:
            bot.send_message(
                message.chat.id,
                "Нажми /start, чтобы открыть меню.",
            )
            return

        ticket = conn.execute("""
            INSERT INTO support_tickets (user_id, body)
            VALUES (%s, %s) RETURNING id
        """, (
            message.from_user.id,
            message.text[:3500],
        )).fetchone()[0]

        conn.execute(
            "UPDATE users SET support_pending = FALSE "
            "WHERE user_id = %s",
            (message.from_user.id,),
        )

    bot.send_message(
        message.chat.id,
        f"Обращение №{ticket} принято. Ответ придёт сюда.",
    )

    if OWNER_ID:
        bot.send_message(
            OWNER_ID,
            f"Обращение №{ticket} от "
            f"{message.from_user.id}:\n"
            f"{message.text[:3500]}\n\n"
            f"Ответ: /reply {ticket} текст",
        )


def run_bot():
    while True:
        try:
            bot.infinity_polling(
                skip_pending=False,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "pre_checkout_query",
                ],
            )
        except Exception as exc:
            print(f"Bot error: {exc}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    init_db()
    threading.Thread(
        target=run_bot,
        daemon=True,
    ).start()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
