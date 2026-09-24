import hashlib
import hmac
import os
import random
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import telebot
from flask import Flask, abort, request
from telebot import types


# =========================================================
# НАСТРОЙКИ
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))

PRICE = 15
TZ = ZoneInfo("Asia/Yekaterinburg")

WEBHOOK_BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = "/telegram-webhook"

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Нужны переменные BOT_TOKEN и DATABASE_URL в Render")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

WEBHOOK_SECRET = hashlib.sha256(TOKEN.encode()).hexdigest()


# =========================================================
# КАРТЫ
# название / общий смысл / любовь / деньги
# =========================================================

CARDS = [
    (
        "🎒 Шут",
        "Перед тобой открывается возможность посмотреть на привычную ситуацию по-новому. "
        "Не обязательно знать весь путь заранее — иногда достаточно сделать первый разумный шаг.",
        "В чувствах может появиться свежесть или неожиданное развитие. "
        "Не пытайся заранее предугадать всё — искренность и открытость сейчас важнее идеального сценария.",
        "Может появиться новая идея или возможность. "
        "Не спеши рисковать крупной суммой: сначала проверь идею небольшим безопасным шагом.",
    ),
    (
        "🪄 Маг",
        "У тебя уже есть часть необходимых ресурсов и возможностей. "
        "Сейчас полезнее действовать конкретно, чем долго ждать идеального момента.",
        "Инициатива способна многое изменить. "
        "Если человек тебе важен, честный разговор может оказаться эффективнее намёков и ожиданий.",
        "Навыки и инициативность могут помочь улучшить ситуацию. "
        "Сосредоточься на том, что ты реально умеешь контролировать и развивать.",
    ),
    (
        "🔮 Верховная Жрица",
        "Не вся информация сейчас находится на поверхности. "
        "Не торопись с выводами и присмотрись к деталям.",
        "В отношениях могут оставаться невысказанные чувства или вопросы. "
        "Не пытайся читать чужие мысли — лучше создать пространство для спокойного разговора.",
        "Перед денежным решением стоит внимательнее изучить условия. "
        "Особенно важно проверить то, что написано мелким шрифтом или пока кажется неясным.",
    ),
    (
        "👑 Императрица",
        "То, чему ты уделяешь внимание и заботу, имеет шанс постепенно вырасти. "
        "Сейчас важны терпение и последовательность.",
        "Тепло, внимание и забота способны укрепить отношения. "
        "Полезно не только говорить о чувствах, но и показывать их поступками.",
        "Постепенное развитие может оказаться устойчивее попытки получить быстрый результат. "
        "Оцени ресурсы и вкладывай их осознанно.",
    ),
    (
        "🏛 Император",
        "Ситуации может не хватать структуры. "
        "Чёткий план и понятные границы помогут вернуть ощущение контроля.",
        "В отношениях полезно ясно обсудить ожидания и границы. "
        "Определённость сейчас может быть ценнее догадок.",
        "Полезно навести порядок в бюджете и обязательствах. "
        "Перед новыми расходами посмотри на общую финансовую картину.",
    ),
    (
        "📜 Иерофант",
        "Проверенный опыт и знания могут подсказать решение лучше поспешного эксперимента. "
        "Иногда полезно обратиться к тому, что уже доказало свою надёжность.",
        "Общие ценности и представления об отношениях выходят на первый план. "
        "Спокойный разговор о них поможет лучше понять друг друга.",
        "Перед серьёзным решением изучи правила и условия. "
        "Если вопрос сложный, мнение профильного специалиста может быть полезнее догадок.",
    ),
    (
        "❤️ Влюблённые",
        "Перед тобой может стоять выбор, связанный с личными ценностями. "
        "Важно понять не только чего хочется сейчас, но и что действительно важно для тебя.",
        "Карта подчёркивает тему чувств, выбора и честности. "
        "Открытый разговор способен прояснить намерения обеих сторон.",
        "Возможно несколько привлекательных вариантов. "
        "Сравни их не только по обещанной выгоде, но и по рискам и своим реальным целям.",
    ),
    (
        "🏇 Колесница",
        "Определи направление и двигайся последовательно. "
        "Сосредоточенность на одной цели может дать больше, чем попытка решить всё одновременно.",
        "Инициатива может помочь отношениям двигаться вперёд. "
        "При этом важно учитывать желания и темп другого человека.",
        "Выбери одну конкретную финансовую цель и отслеживай результат. "
        "Дисциплина сейчас полезнее хаотичных решений.",
    ),
    (
        "🦁 Сила",
        "Спокойная настойчивость может оказаться эффективнее давления. "
        "Не обязательно действовать резко, чтобы добиться результата.",
        "Терпение и уважительный разговор способны снять часть напряжения. "
        "Мягкость здесь не означает слабость.",
        "Избегай импульсивных трат и решений на эмоциях. "
        "Последовательность поможет сохранить контроль.",
    ),
    (
        "🕯 Отшельник",
        "Небольшая пауза может помочь лучше понять собственные приоритеты. "
        "Не каждую ситуацию нужно решать немедленно.",
        "Возможно, тебе нужно немного пространства, чтобы разобраться в своих чувствах. "
        "После этого разговор станет яснее.",
        "Спокойный анализ доходов, расходов и прошлых решений может показать то, что раньше терялось из виду.",
    ),
    (
        "🎡 Колесо Фортуны",
        "Обстоятельства способны измениться неожиданно. "
        "Гибкость и запасной вариант помогут легче адаптироваться.",
        "В отношениях возможен новый этап или изменение привычной динамики. "
        "Полезно обсудить, чего каждый хочет сейчас.",
        "Финансовая ситуация может меняться. "
        "Лучше не рассчитывать только на удачу и по возможности сохранять резерв.",
    ),
    (
        "⚖️ Справедливость",
        "Посмотри на ситуацию максимально объективно и отдели факты от эмоций. "
        "Ответственность за свою часть решения даст больше ясности.",
        "Честность и равное внимание к потребностям обоих помогут разобраться в разногласиях.",
        "Проверь цифры, документы и условия. "
        "Решение лучше принимать после спокойного сравнения вариантов.",
    ),
    (
        "🙃 Повешенный",
        "Возможно, сейчас полезнее остановиться и посмотреть на проблему под другим углом. "
        "Пауза тоже может быть действием.",
        "Попробуй понять точку зрения другого человека до окончательных выводов.",
        "Если покупка или решение не срочные, небольшая пауза позволит оценить их более трезво.",
    ),
    (
        "🍂 Смерть",
        "Название карты символизирует завершение и перемены, а не буквальное событие. "
        "Что-то привычное может уступать место новому этапу.",
        "Старый сценарий отношений или общения может исчерпывать себя. "
        "Это повод обсудить, что хочется изменить.",
        "Полезно отказаться от устаревших расходов или финансовых привычек, которые больше не служат твоим целям.",
    ),
    (
        "🌿 Умеренность",
        "Сейчас особенно важен устойчивый темп. "
        "Небольшие последовательные шаги могут дать лучший результат, чем резкие перемены.",
        "Компромисс, терпение и спокойный диалог помогут найти баланс.",
        "Разумный баланс расходов и накоплений может оказаться полезнее крайностей.",
    ),
    (
        "⛓ Дьявол",
        "Обрати внимание на привычки или обязательства, которые ограничивают свободу выбора.",
        "Стоит проверить, не слишком ли много места занимают ревность, страх или зависимость. "
        "Здоровые границы сейчас особенно важны.",
        "Будь осторожнее с долгами и предложениями, которые выглядят слишком заманчиво. "
        "Важно понимать реальные обязательства.",
    ),
    (
        "⚡ Башня",
        "Неожиданная перемена может нарушить привычный план. "
        "Сосредоточься сначала на том, что действительно находится под твоим контролем.",
        "Если возник конфликт, не делай окончательных выводов на пике эмоций. "
        "Сначала проясни факты.",
        "Неожиданные расходы возможны в любой момент, поэтому резерв и осторожность особенно полезны.",
    ),
    (
        "⭐ Звезда",
        "Есть смысл сохранять надежду и продолжать движение. "
        "Сформулируй небольшой достижимый следующий шаг.",
        "Искренность и спокойствие могут вернуть ощущение близости и доверия.",
        "Долгосрочная цель станет реальнее, если разбить её на небольшие измеримые этапы.",
    ),
    (
        "🌙 Луна",
        "Не всё сейчас ясно. "
        "Важно отличать предположения и тревоги от того, что известно наверняка.",
        "Не пытайся угадывать чувства другого человека. "
        "Прямой вопрос способен дать больше ясности.",
        "Если условия или цифры вызывают сомнения, не торопись платить или подписывать что-либо до уточнения.",
    ),
    (
        "☀️ Солнце",
        "Ситуация может становиться яснее. "
        "Обрати внимание на то, что уже получается, и используй этот опыт дальше.",
        "Открытость и проявление симпатии способны усилить положительную динамику.",
        "Посмотри, какие действия уже дают результат, и сосредоточь ресурсы на действительно работающих направлениях.",
    ),
    (
        "📣 Суд",
        "Пришло время вернуться к важному вопросу и сделать выводы из прошлого опыта.",
        "Старая тема может снова потребовать разговора. "
        "Честное обсуждение поможет понять, как двигаться дальше.",
        "Проанализируй прошлые решения и используй полученный опыт для корректировки финансовых целей.",
    ),
    (
        "🌍 Мир",
        "Один этап может подходить к завершению. "
        "Полезно признать достигнутый результат и определить следующую цель.",
        "Отношения могут перейти к более понятному этапу. "
        "Обсуждение совместных планов поможет увидеть направление.",
        "Подведи итоги и оцени, насколько ты приблизился к своей цели. "
        "После этого выбери следующий реалистичный шаг.",
    ),
]


SPREADS = {
    "love": (
        "💕 Расклад на любовь",
        ("Что влияет на ситуацию", "Что происходит сейчас", "Куда может двигаться ситуация"),
    ),
    "money": (
        "💰 Расклад на деньги",
        ("Текущая ситуация", "Возможность", "На что обратить внимание"),
    ),
    "three": (
        "🔮 Расклад «3 карты»",
        ("Прошлое", "Настоящее", "Возможное будущее"),
    ),
}

NUMBERS = ("1️⃣", "2️⃣", "3️⃣")


# =========================================================
# FLASK / WEBHOOK
# =========================================================

@app.route("/")
def home():
    return "Tarot Orakul Bot is running", 200


@app.post(WEBHOOK_PATH)
def telegram_webhook():
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )

    if not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        abort(403)

    if not request.is_json:
        abort(415)

    update = types.Update.de_json(request.get_data(as_text=True))
    bot.process_new_updates([update])

    return "", 200


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

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
                INSERT INTO users (user_id, three_used)
                VALUES (%s, TRUE)

                ON CONFLICT (user_id)
                DO UPDATE SET three_used = TRUE
                WHERE users.three_used = FALSE

                RETURNING user_id
            """, (user_id,)).fetchone()

        else:
            if field not in ("daily_card", "daily_question"):
                raise ValueError("Неизвестная бесплатная функция")

            today = datetime.now(TZ).date()

            row = conn.execute(f"""
                INSERT INTO users (user_id, {field})
                VALUES (%s, %s)

                ON CONFLICT (user_id)
                DO UPDATE SET {field} = EXCLUDED.{field}
                WHERE users.{field} IS DISTINCT FROM EXCLUDED.{field}

                RETURNING user_id
            """, (user_id, today)).fetchone()

        return row is not None


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    keyboard.row(
        "🔮 Карта дня",
        "❓ Вопрос дня",
    )

    keyboard.row(
        "✨ Сделать расклад",
        "ℹ️ О боте",
    )

    return keyboard


def readings_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "💕 Любовь",
            callback_data="reading_love",
        ),
        types.InlineKeyboardButton(
            "💰 Деньги",
            callback_data="reading_money",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔮 3 карты",
            callback_data="reading_three",
        )
    )

    return keyboard


# =========================================================
# ГЕНЕРАЦИЯ РАСКЛАДОВ
# =========================================================

def spread(kind):
    title, positions = SPREADS[kind]

    chosen = random.sample(CARDS, 3)

    meaning_index = {
        "love": 2,
        "money": 3,
        "three": 1,
    }[kind]

    lines = [
        title,
        "━━━━━━━━━━━━━━",
    ]

    for number, position, card in zip(NUMBERS, positions, chosen):
        name = card[0]
        meaning = card[meaning_index]

        lines.append(
            f"{number} {position}\n"
            f"{name}\n\n"
            f"{meaning}"
        )

    if kind == "love":
        ending = (
            "💕 Итог\n"
            "Посмотри на три карты вместе: они не определяют будущее, "
            "а предлагают взглянуть на чувства и ситуацию с разных сторон.\n\n"
            "✨ Используй расклад как повод для размышления и честного разговора."
        )

    elif kind == "money":
        ending = (
            "💰 Итог\n"
            "Сопоставь подсказки карт со своей реальной финансовой ситуацией "
            "и принимай решения на основе фактов.\n\n"
            "🔮 Это символическая развлекательная интерпретация, "
            "а не финансовая рекомендация."
        )

    else:
        ending = (
            "✨ Итог\n"
            "Прошлое показывает контекст, настоящее — текущую точку, "
            "а третья карта предлагает один из возможных взглядов на дальнейшее развитие.\n\n"
            "🔮 Будущее не предопределено — используй расклад как повод для размышления."
        )

    lines.append(ending)

    return "\n\n".join(lines)


def day_card_text():
    name, meaning, *_ = random.choice(CARDS)

    return (
        "🔮 Твоя карта дня\n\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "✨ Подумай, как этот образ может относиться к твоему сегодняшнему дню.\n\n"
        "Таро здесь используется как развлекательная символическая практика, "
        "а не как точное предсказание."
    )


def question_text():
    name, meaning, *_ = random.choice(CARDS)

    return (
        "❓ Вопрос дня\n\n"
        "Сформулируй вопрос про себя.\n"
        "Не обязательно писать его боту.\n\n"
        "Твоя карта:\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "🔮 Посмотри на карту как на дополнительный ракурс для размышления, "
        "а не как на однозначный ответ."
    )


def answer(call, text=None):
    bot.answer_callback_query(call.id, text=text)


# =========================================================
# ОСНОВНЫЕ КОМАНДЫ
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Каждый день тебе доступны бесплатно:\n"
        "🔮 Карта дня\n"
        "❓ Вопрос дня\n\n"
        "А первый расклад «3 карты» доступен бесплатно один раз.\n\n"
        f"💕 Любовь и 💰 Деньги — {PRICE} ⭐ за расклад.\n"
        f"После бесплатного раза «3 карты» также стоит {PRICE} ⭐.\n\n"
        "Выбери, с чего хочешь начать 👇",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(commands=["myid"])
def myid(message):
    bot.send_message(
        message.chat.id,
        f"Твой Telegram ID: {message.from_user.id}",
    )


@bot.message_handler(commands=["terms"])
def terms(message):
    bot.send_message(
        message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "Бесплатно:\n"
        "• Карта дня — один раз в день.\n"
        "• Вопрос дня — один раз в день.\n"
        "• Первый расклад «3 карты» — один раз на аккаунт.\n\n"
        f"Платно:\n"
        f"• Любовь — {PRICE} Stars.\n"
        f"• Деньги — {PRICE} Stars.\n"
        f"• Последующие расклады «3 карты» — {PRICE} Stars.\n\n"
        "Результат платного расклада отправляется после подтверждения оплаты Telegram.\n\n"
        "Все расклады являются символической развлекательной интерпретацией. "
        "Они не являются точным предсказанием, медицинской, финансовой "
        "или юридической консультацией.\n\n"
        "Если возникла проблема с оплатой или выдачей результата — /paysupport."
    )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

@bot.message_handler(commands=["support", "paysupport"])
def support(message):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, support_pending)
            VALUES (%s, TRUE)

            ON CONFLICT (user_id)
            DO UPDATE SET support_pending = TRUE
        """, (message.from_user.id,))

    bot.send_message(
        message.chat.id,
        "🛟 Опиши проблему одним сообщением.\n\n"
        "Не присылай пароль, токен или данные банковской карты.",
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

    ticket_id = int(parts[1])

    with db() as conn:
        row = conn.execute(
            "SELECT user_id FROM support_tickets WHERE id = %s",
            (ticket_id,),
        ).fetchone()

    if not row:
        bot.send_message(
            message.chat.id,
            "Обращение не найдено.",
        )
        return

    bot.send_message(
        row[0],
        f"🛟 Ответ поддержки по обращению №{ticket_id}:\n\n"
        f"{parts[2]}",
    )

    bot.send_message(
        message.chat.id,
        "Ответ отправлен.",
    )


# =========================================================
# БЕСПЛАТНЫЕ ФУНКЦИИ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🔮 Карта дня")
def card_of_the_day(message):
    if not claim_free(
        message.from_user.id,
        "daily_card",
    ):
        bot.send_message(
            message.chat.id,
            "🔮 Ты уже получил карту дня сегодня.\n\n"
            "Возвращайся завтра ✨",
        )
        return

    bot.send_message(
        message.chat.id,
        day_card_text(),
    )


@bot.message_handler(func=lambda m: m.text == "❓ Вопрос дня")
def question_of_the_day(message):
    if not claim_free(
        message.from_user.id,
        "daily_question",
    ):
        bot.send_message(
            message.chat.id,
            "❓ Ты уже получил Вопрос дня сегодня.\n\n"
            "Возвращайся завтра ✨",
        )
        return

    bot.send_message(
        message.chat.id,
        question_text(),
    )


# =========================================================
# МЕНЮ РАСКЛАДОВ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "✨ Сделать расклад")
def reading(message):
    bot.send_message(
        message.chat.id,
        "✨ Выбери расклад:\n\n"
        f"💕 Любовь — 3 карты о чувствах и развитии ситуации · {PRICE} ⭐\n\n"
        f"💰 Деньги — 3 карты о текущей ситуации, возможности и том, "
        f"на что обратить внимание · {PRICE} ⭐\n\n"
        "🔮 3 карты — прошлое, настоящее и возможное будущее. "
        f"Первый расклад бесплатно, следующие — {PRICE} ⭐.",
        reply_markup=readings_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "ℹ️ О боте")
def about(message):
    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул\n\n"
        "Развлекательный бот с символическими раскладами Таро.\n\n"
        "🎁 Каждый день доступны Карта дня и Вопрос дня.\n"
        "🔮 Первый расклад «3 карты» бесплатный.\n"
        f"⭐ Платные расклады стоят {PRICE} Stars.\n\n"
        "📖 Условия: /terms\n"
        "🛟 Поддержка: /support\n"
        "💳 Проблема с оплатой: /paysupport",
        reply_markup=main_keyboard(),
    )


# =========================================================
# ПРЕДЛОЖЕНИЕ ОПЛАТЫ
# =========================================================

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
                "📖 Условия",
                callback_data="show_terms",
            )
        )

        keyboard.add(
            types.InlineKeyboardButton(
                "✅ Согласен с условиями",
                callback_data=f"agree_{kind}",
            )
        )

        bot.send_message(
            chat_id,
            f"⭐ Стоимость этого расклада — {PRICE} Stars.\n\n"
            "После успешной оплаты бот сразу отправит расклад из трёх карт.\n\n"
            "Перед оплатой ознакомься с условиями.",
            reply_markup=keyboard,
        )

        return

    send_invoice(chat_id, user_id, kind)


def send_invoice(chat_id, user_id, kind):
    title = SPREADS[kind][0]

    payload = f"{kind}:{user_id}:{uuid4().hex}"

    bot.send_invoice(
        chat_id,
        title,
        "Один символический расклад Таро из трёх карт.",
        payload,
        None,
        "XTR",
        [
            types.LabeledPrice(
                title,
                PRICE,
            )
        ],
    )


# =========================================================
# CALLBACK РАСКЛАДОВ
# =========================================================

@bot.callback_query_handler(
    func=lambda c: c.data and c.data.startswith("reading_")
)
def reading_callback(call):
    kind = call.data.removeprefix("reading_")

    if kind not in SPREADS:
        answer(
            call,
            "Расклад не найден",
        )
        return

    # Первый расклад "3 карты" бесплатный.
    if kind == "three":
        if claim_free(
            call.from_user.id,
            "three_used",
        ):
            answer(call)

            bot.send_message(
                call.message.chat.id,
                "🎁 Это твой первый расклад «3 карты», поэтому он бесплатный.",
            )

            bot.send_message(
                call.message.chat.id,
                spread(kind),
            )

            return

    answer(call)

    offer_payment(
        call.message.chat.id,
        call.from_user.id,
        kind,
    )


# =========================================================
# УСЛОВИЯ
# =========================================================

@bot.callback_query_handler(
    func=lambda c: c.data == "show_terms"
)
def show_terms(call):
    answer(call)

    bot.send_message(
        call.message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "Бесплатно:\n"
        "• Карта дня — раз в день.\n"
        "• Вопрос дня — раз в день.\n"
        "• Первый расклад «3 карты» — один раз.\n\n"
        f"Платные расклады стоят {PRICE} Stars.\n\n"
        "Расклады являются символической развлекательной интерпретацией "
        "и не являются медицинской, финансовой или юридической консультацией.\n\n"
        "Проблемы с оплатой: /paysupport."
    )


@bot.callback_query_handler(
    func=lambda c: c.data and c.data.startswith("agree_")
)
def agree(call):
    kind = call.data.removeprefix("agree_")

    if kind not in SPREADS:
        answer(
            call,
            "Неизвестный расклад",
        )
        return

    with db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, terms_accepted)
            VALUES (%s, TRUE)

            ON CONFLICT (user_id)
            DO UPDATE SET terms_accepted = TRUE
        """, (call.from_user.id,))

    answer(
        call,
        "Условия приняты",
    )

    send_invoice(
        call.message.chat.id,
        call.from_user.id,
        kind,
    )


# =========================================================
# ПРОВЕРКА ПЛАТЕЖА
# =========================================================

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


@bot.pre_checkout_query_handler(
    func=lambda query: True
)
def pre_checkout(query):
    try:
        kind = invoice_details(
            query.invoice_payload,
            query.from_user.id,
        )

        with db() as conn:
            row = conn.execute(
                "SELECT terms_accepted "
                "FROM users WHERE user_id = %s",
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
                None
                if ok
                else "Оплата недоступна. Попробуй снова."
            ),
        )

    except Exception:
        bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message=(
                "Не удалось проверить оплату. Попробуй позже."
            ),
        )


# =========================================================
# УСПЕШНАЯ ОПЛАТА
# =========================================================

@bot.message_handler(
    content_types=["successful_payment"]
)
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
            "Платёж получен, но результат требует проверки.\n\n"
            "Напиши /paysupport.",
        )
        return

    charge_id = payment.telegram_payment_charge_id

    with db() as conn:
        conn.execute("""
            INSERT INTO payments (
                charge_id,
                user_id,
                kind,
                result
            )
            VALUES (%s, %s, %s, %s)

            ON CONFLICT (charge_id)
            DO NOTHING
        """, (
            charge_id,
            message.from_user.id,
            kind,
            spread(kind),
        ))

        row = conn.execute(
            "SELECT user_id, result, delivered "
            "FROM payments "
            "WHERE charge_id = %s",
            (charge_id,),
        ).fetchone()

    if not row:
        bot.send_message(
            message.chat.id,
            "Платёж получен, но возникла ошибка выдачи.\n"
            "Напиши /paysupport.",
        )
        return

    if row[0] != message.from_user.id:
        return

    if row[2]:
        return

    bot.send_message(
        message.chat.id,
        "✅ Оплата успешно получена!\n\n"
        "Твой расклад готов 🔮",
    )

    bot.send_message(
        message.chat.id,
        row[1],
    )

    with db() as conn:
        conn.execute(
            "UPDATE payments "
            "SET delivered = TRUE "
            "WHERE charge_id = %s",
            (charge_id,),
        )


# =========================================================
# ПРОЧИЕ СООБЩЕНИЯ / ПОДДЕРЖКА
# =========================================================

@bot.message_handler(
    content_types=["text"],
    func=lambda m: True,
)
def other_text(message):
    with db() as conn:
        row = conn.execute(
            "SELECT support_pending "
            "FROM users "
            "WHERE user_id = %s",
            (message.from_user.id,),
        ).fetchone()

        if not row or not row[0]:
            bot.send_message(
                message.chat.id,
                "Я не понял сообщение 🙂\n\n"
                "Используй кнопки меню ниже.",
                reply_markup=main_keyboard(),
            )
            return

        ticket = conn.execute("""
            INSERT INTO support_tickets (
                user_id,
                body
            )
            VALUES (%s, %s)
            RETURNING id
        """, (
            message.from_user.id,
            message.text[:3500],
        )).fetchone()[0]

        conn.execute(
            "UPDATE users "
            "SET support_pending = FALSE "
            "WHERE user_id = %s",
            (message.from_user.id,),
        )

    bot.send_message(
        message.chat.id,
        f"🛟 Обращение №{ticket} принято.\n\n"
        "Ответ поддержки придёт сюда.",
        reply_markup=main_keyboard(),
    )

    if OWNER_ID:
        try:
            bot.send_message(
                OWNER_ID,
                f"🛟 Обращение №{ticket}\n\n"
                f"Пользователь: {message.from_user.id}\n\n"
                f"{message.text[:3500]}\n\n"
                f"Ответить:\n/reply {ticket} текст",
            )
        except Exception:
            pass


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":
    init_db()

    if not WEBHOOK_BASE_URL:
        raise RuntimeError(
            "Render не предоставил RENDER_EXTERNAL_URL"
        )

    bot.set_webhook(
        url=(
            WEBHOOK_BASE_URL.rstrip("/")
            + WEBHOOK_PATH
        ),
        allowed_updates=[
            "message",
            "callback_query",
            "pre_checkout_query",
        ],
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=False,
        max_connections=1,
    )

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000,
            )
        ),
    )
