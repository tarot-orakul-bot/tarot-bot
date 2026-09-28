import hashlib
import hmac
import os
import random
import threading
import time
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import requests
import telebot
from flask import Flask, abort, request
from telebot import types


# =========================================================
# НАСТРОЙКИ
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("BOT_OWNER_ID") or "0")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

PRICE = 50
TZ = ZoneInfo("Asia/Yekaterinburg")

PROMO_CODE = "FRIEND"
PROMO_CREDITS = 3

REMINDER_AFTER_DAYS = 3
REMINDER_CHECK_SECONDS = 60 * 60

WEBHOOK_BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = "/telegram-webhook"

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Нужны переменные BOT_TOKEN и DATABASE_URL в Render")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

WEBHOOK_SECRET = hashlib.sha256(TOKEN.encode()).hexdigest()


# =========================================================
# КАРТЫ
# =========================================================

CARDS = [
    (
        "🎒 Шут",
        "Перед тобой открывается возможность посмотреть на ситуацию по-новому. "
        "Не обязательно заранее знать весь путь — иногда достаточно позволить себе "
        "сделать первый шаг и посмотреть, куда он приведёт.",
        "В сфере чувств карта говорит о свежести, спонтанности и возможности нового этапа. "
        "Это может быть новое знакомство или изменение привычной динамики отношений. "
        "Сейчас полезнее быть открытым к диалогу, чем пытаться заранее просчитать чужие чувства.",
        "В денежных вопросах может появиться новая идея или возможность. "
        "Она способна заинтересовать, но карта напоминает: энтузиазм лучше сочетать "
        "с проверкой цифр и небольшими безопасными шагами.",
    ),
    (
        "🪄 Маг",
        "У тебя уже есть часть необходимых ресурсов, знаний или возможностей. "
        "Сейчас многое зависит от инициативы и способности направить внимание "
        "на одно конкретное действие.",
        "В отношениях Маг подчёркивает инициативу и общение. "
        "Если ситуация застыла, честный разговор или первый шаг способны изменить динамику. "
        "Важно выражать свои намерения ясно, не пытаясь управлять чувствами другого человека.",
        "В финансовой сфере карта обращает внимание на навыки и инициативность. "
        "Полезно подумать, какие способности уже можно применить для увеличения дохода "
        "или улучшения текущей ситуации.",
    ),
    (
        "🔮 Верховная Жрица",
        "Не вся информация сейчас находится на поверхности. "
        "Возможно, стоит немного замедлиться и присмотреться к деталям, "
        "которые раньше оставались незамеченными.",
        "В отношениях могут присутствовать невысказанные чувства или вопросы. "
        "Не пытайся угадывать мысли другого человека. Лучше оставить пространство "
        "для спокойного и искреннего разговора.",
        "В денежных делах особенно важно внимательно изучить условия. "
        "Если что-то кажется непонятным или слишком привлекательным, "
        "полезно сначала получить дополнительную информацию.",
    ),
    (
        "👑 Императрица",
        "Карта связана с развитием, заботой и постепенным ростом. "
        "То, чему уделяется достаточно внимания и времени, может начать приносить результат.",
        "В чувствах Императрица говорит о тепле, внимании и эмоциональной близости. "
        "Отношения могут укрепляться через заботу, поддержку и способность замечать "
        "потребности друг друга.",
        "В финансовой сфере карта напоминает о постепенном росте. "
        "Вместо ожидания мгновенного результата полезно развивать то, "
        "что уже показывает потенциал.",
    ),
    (
        "🏛 Император",
        "Ситуации может не хватать структуры и ясных правил. "
        "План, последовательность и разумные границы способны вернуть ощущение контроля.",
        "В отношениях важно понимать ожидания друг друга. "
        "Чёткие границы и договорённости могут уменьшить неопределённость "
        "и предотвратить лишние конфликты.",
        "В денежных вопросах карта предлагает навести порядок. "
        "Бюджет, контроль обязательств и понятная цель могут оказаться "
        "полезнее спонтанных решений.",
    ),
    (
        "📜 Иерофант",
        "Иногда проверенные знания и опыт оказываются полезнее экспериментов. "
        "Посмотри, чему можно научиться у людей, которые уже проходили похожий путь.",
        "В отношениях карта обращает внимание на ценности, договорённости и представления "
        "о серьёзности союза. Полезно понять, совпадают ли ваши ожидания.",
        "В денежных вопросах важно внимательно относиться к правилам, документам "
        "и обязательствам. В сложных ситуациях лучше опираться на проверенную информацию.",
    ),
    (
        "❤️ Влюблённые",
        "Перед тобой может стоять выбор, который связан не только с выгодой, "
        "но и с тем, что для тебя действительно важно.",
        "Это карта чувств, выбора и взаимности. "
        "Она предлагает обратить внимание на честность между людьми и понять, "
        "совпадают ли ваши желания и ожидания.",
        "В финансовой ситуации может быть несколько вариантов. "
        "Сравни их не только по потенциальной выгоде, но и по рискам, "
        "обязательствам и своим долгосрочным целям.",
    ),
    (
        "🏇 Колесница",
        "Карта говорит о движении и концентрации на цели. "
        "Когда направление выбрано, последовательные действия помогают продвинуться вперёд.",
        "В отношениях ситуация может начать развиваться активнее. "
        "Инициатива полезна, если она учитывает желания и границы другого человека.",
        "В деньгах полезно выбрать одну конкретную цель и направить усилия именно на неё. "
        "Контроль прогресса поможет понять, что действительно работает.",
    ),
    (
        "🦁 Сила",
        "Настойчивость не обязательно означает давление. "
        "Спокойствие, терпение и способность контролировать импульсивные реакции "
        "могут дать лучший результат.",
        "В отношениях карта предлагает действовать мягко, но уверенно. "
        "Спокойный разговор способен решить больше, чем попытка доказать свою правоту.",
        "В финансовых вопросах важно контролировать импульсивные решения. "
        "Последовательность и дисциплина сейчас могут быть особенно полезны.",
    ),
    (
        "🕯 Отшельник",
        "Иногда для следующего шага сначала требуется разобраться в собственных мыслях. "
        "Небольшая пауза может дать больше ясности.",
        "В сфере чувств может понадобиться пространство для размышления. "
        "Это не обязательно означает отдаление — иногда человеку просто нужно понять себя.",
        "В деньгах карта предлагает спокойно проанализировать прошлые решения, "
        "доходы и расходы прежде, чем менять стратегию.",
    ),
    (
        "🎡 Колесо Фортуны",
        "Обстоятельства могут меняться быстрее, чем ожидалось. "
        "Гибкость позволит использовать новые возможности и легче пережить неожиданные перемены.",
        "В отношениях возможен новый этап или изменение привычной динамики. "
        "Полезно обсудить, чего каждый из вас хочет сейчас.",
        "Финансовая ситуация может изменяться. "
        "Не стоит полагаться исключительно на удачу — запасной план и резерв "
        "помогают снизить зависимость от обстоятельств.",
    ),
    (
        "⚖️ Справедливость",
        "Попробуй посмотреть на ситуацию максимально объективно. "
        "Отдели факты от предположений и оцени последствия каждого решения.",
        "В отношениях карта говорит о честности и взаимной ответственности. "
        "Важно учитывать потребности обеих сторон, а не только собственную позицию.",
        "В денежных вопросах особенно важны цифры, документы и условия. "
        "Решение лучше принимать после внимательного сравнения вариантов.",
    ),
    (
        "🙃 Повешенный",
        "Возможно, сейчас полезнее не ускоряться, а изменить угол зрения. "
        "Пауза может помочь увидеть решение, которое раньше было незаметно.",
        "В отношениях попробуй посмотреть на ситуацию глазами другого человека. "
        "Это не означает отказаться от своей позиции, но может помочь лучше понять происходящее.",
        "Если финансовое решение не срочное, небольшая пауза может защитить "
        "от импульсивного шага и дать время оценить его реальную ценность.",
    ),
    (
        "🍂 Смерть",
        "Эта карта символизирует завершение этапа и трансформацию, а не буквальное событие. "
        "Что-то привычное может уходить, освобождая место для нового.",
        "В отношениях старый способ общения или привычный сценарий может перестать работать. "
        "Это повод понять, что стоит изменить.",
        "В денежных вопросах полезно пересмотреть устаревшие расходы, обязательства "
        "или планы и направить ресурсы на более актуальные цели.",
    ),
    (
        "🌿 Умеренность",
        "Сейчас особенно важен устойчивый темп. "
        "Небольшие последовательные шаги способны привести дальше, чем резкие перемены.",
        "В отношениях компромисс и терпение могут восстановить спокойный диалог. "
        "Не каждый вопрос требует немедленного решения.",
        "В финансовой сфере разумный баланс расходов и накоплений "
        "может оказаться эффективнее крайностей.",
    ),
    (
        "⛓ Дьявол",
        "Обрати внимание на привычки или обязательства, которые ограничивают свободу выбора. "
        "Важно понять, что действительно удерживает тебя в текущей ситуации.",
        "В отношениях стоит обратить внимание на ревность, страх потери, давление "
        "или эмоциональную зависимость. Здоровые границы особенно важны.",
        "В денежных вопросах будь осторожнее с долгами и заманчивыми обещаниями. "
        "Условия, которые выглядят слишком выгодно, стоит проверять особенно внимательно.",
    ),
    (
        "⚡ Башня",
        "Неожиданная перемена может нарушить привычный план. "
        "В такой ситуации полезно сначала определить, что действительно находится под контролем.",
        "В отношениях возможен резкий разговор или изменение привычной динамики. "
        "Не делай окончательных выводов на пике эмоций — сначала проясни факты.",
        "Неожиданные расходы или изменение обстоятельств напоминают о ценности резерва "
        "и осторожности с крупными обязательствами.",
    ),
    (
        "⭐ Звезда",
        "Карта связана с надеждой и восстановлением направления. "
        "Даже если результат ещё далеко, небольшой следующий шаг уже имеет значение.",
        "В чувствах карта говорит о возможности восстановить доверие или ясность. "
        "Искренность и спокойное общение могут приблизить людей.",
        "В денежных вопросах полезно смотреть на долгосрочную цель. "
        "Раздели её на небольшие измеримые этапы и отмечай прогресс.",
    ),
    (
        "🌙 Луна",
        "Ситуация может казаться запутанной, потому что информации пока недостаточно. "
        "Важно отделять реальные факты от страхов и предположений.",
        "В отношениях не стоит пытаться угадывать чувства другого человека. "
        "Неопределённость лучше прояснять вопросами и разговором.",
        "Если цифры или условия непонятны, не торопись принимать финансовое решение. "
        "Сначала получи недостающую информацию.",
    ),
    (
        "☀️ Солнце",
        "Карта связана с ясностью и пониманием результата. "
        "Посмотри, что уже получается, и используй этот опыт дальше.",
        "В отношениях открытость и искреннее проявление симпатии могут усилить "
        "положительную динамику.",
        "В финансовых вопросах стоит обратить внимание на действия, "
        "которые уже дают измеримый результат, и развивать именно их.",
    ),
    (
        "📣 Суд",
        "Пришло время вернуться к важному вопросу и сделать выводы "
        "из накопленного опыта.",
        "Старая тема в отношениях может снова потребовать разговора. "
        "Это возможность наконец понять, что оставить в прошлом, а что развивать дальше.",
        "В финансовой сфере анализ прежних решений поможет скорректировать цели "
        "и не повторять одни и те же ошибки.",
    ),
    (
        "🌍 Мир",
        "Один этап может подходить к завершению. "
        "Полезно увидеть достигнутый результат и определить следующую цель.",
        "В отношениях карта предлагает посмотреть на пройденный вместе путь "
        "и обсудить дальнейшие планы.",
        "В денежных вопросах полезно подвести промежуточные итоги, "
        "оценить прогресс и выбрать следующую реалистичную цель.",
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

TOPICS = {
    "love": {
        "current": "❤️ Отношения сейчас",
        "feelings": "💗 Чувства человека",
        "ex": "💔 Бывший партнёр",
        "new": "💞 Новое знакомство",
        "future": "🔮 Будущее отношений",
    },
    "money": {
        "work": "💼 Работа",
        "income": "💰 Доход",
        "situation": "📊 Финансовая ситуация",
        "opportunity": "✨ Новая возможность",
        "future": "🔮 Финансовое будущее",
    },
    "three": {
        "general": "🌙 Общая ситуация",
        "love": "❤️ Любовь",
        "money": "💰 Деньги",
        "decision": "⚖️ Важное решение",
        "future": "🔮 Ближайшее будущее",
    },
}

PERIODS = {
    "near": "🌙 Ближайшее время",
    "month": "📅 Ближайший месяц",
    "three_months": "🗓 Ближайшие 3 месяца",
    "none": "✨ Без конкретного периода",
}


# =========================================================
# WEBHOOK
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

        columns = [
            "ADD COLUMN IF NOT EXISTS promo_code TEXT",
            "ADD COLUMN IF NOT EXISTS promo_credits INTEGER NOT NULL DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",
            "ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ",
            "ADD COLUMN IF NOT EXISTS pending_kind TEXT",
            "ADD COLUMN IF NOT EXISTS pending_topic TEXT",
            "ADD COLUMN IF NOT EXISTS pending_period TEXT",
            "ADD COLUMN IF NOT EXISTS reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ",
            "ADD COLUMN IF NOT EXISTS profile_name TEXT",
            "ADD COLUMN IF NOT EXISTS profile_age INTEGER",
            "ADD COLUMN IF NOT EXISTS other_name TEXT",
            "ADD COLUMN IF NOT EXISTS other_age INTEGER",
            "ADD COLUMN IF NOT EXISTS form_step TEXT",
        ]

        for column in columns:
            conn.execute(f"ALTER TABLE users {column}")

        conn.execute("""
            UPDATE users
            SET created_at = COALESCE(created_at, now())
            WHERE created_at IS NULL
        """)

        conn.execute("""
            UPDATE users
            SET last_seen = COALESCE(last_seen, created_at, now())
            WHERE last_seen IS NULL
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

        conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS topic TEXT")
        conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS period TEXT")
        conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS amount INTEGER")

        conn.execute("""
            UPDATE payments
            SET amount = %s
            WHERE amount IS NULL
        """, (PRICE,))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id BIGINT NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


# =========================================================
# ПОЛЬЗОВАТЕЛИ
# =========================================================

def touch_user(user_id):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id, created_at, last_seen, reminder_sent_at
            )
            VALUES (%s, now(), now(), NULL)

            ON CONFLICT (user_id)
            DO UPDATE SET
                last_seen = now(),
                reminder_sent_at = NULL
        """, (user_id,))


def claim_free(user_id, field):
    with db() as conn:
        if field == "three_used":
            row = conn.execute("""
                INSERT INTO users (
                    user_id, three_used, created_at, last_seen, reminder_sent_at
                )
                VALUES (%s, TRUE, now(), now(), NULL)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    three_used = TRUE,
                    last_seen = now(),
                    reminder_sent_at = NULL
                WHERE users.three_used = FALSE

                RETURNING user_id
            """, (user_id,)).fetchone()

        else:
            if field not in ("daily_card", "daily_question"):
                raise ValueError("Неизвестная бесплатная функция")

            today = datetime.now(TZ).date()

            row = conn.execute(f"""
                INSERT INTO users (
                    user_id, {field}, created_at, last_seen, reminder_sent_at
                )
                VALUES (%s, %s, now(), now(), NULL)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    {field} = EXCLUDED.{field},
                    last_seen = now(),
                    reminder_sent_at = NULL
                WHERE users.{field} IS DISTINCT FROM EXCLUDED.{field}

                RETURNING user_id
            """, (user_id, today)).fetchone()

        return row is not None


# =========================================================
# СОСТОЯНИЕ РАСКЛАДА
# =========================================================

def set_pending_reading(user_id, kind=None, topic=None, period=None):
    touch_user(user_id)

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                pending_kind = %s,
                pending_topic = %s,
                pending_period = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (kind, topic, period, user_id))


def get_pending_reading(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT pending_kind, pending_topic, pending_period
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if not row:
        return None, None, None

    return row[0], row[1], row[2]


def clear_pending_reading(user_id):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                pending_kind = NULL,
                pending_topic = NULL,
                pending_period = NULL,
                form_step = NULL,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (user_id,))


# =========================================================
# АНКЕТА
# =========================================================

def get_profile(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT
                profile_name,
                profile_age,
                other_name,
                other_age,
                form_step
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if not row:
        return None, None, None, None, None

    return row


def set_form_step(user_id, step):
    touch_user(user_id)

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET form_step = %s
            WHERE user_id = %s
        """, (step, user_id))


def save_profile_name(user_id, name):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET profile_name = %s, last_seen = now(), reminder_sent_at = NULL
            WHERE user_id = %s
        """, (name, user_id))


def save_profile_age(user_id, age):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET profile_age = %s, last_seen = now(), reminder_sent_at = NULL
            WHERE user_id = %s
        """, (age, user_id))


def save_other_name(user_id, name):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET other_name = %s, last_seen = now(), reminder_sent_at = NULL
            WHERE user_id = %s
        """, (name, user_id))


def save_other_age(user_id, age):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET other_age = %s, last_seen = now(), reminder_sent_at = NULL
            WHERE user_id = %s
        """, (age, user_id))


def needs_other_person(kind, topic):
    return kind == "love" and topic in (
        "current",
        "feelings",
        "ex",
        "future",
    )


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🔮 Карта дня", "❓ Вопрос дня")
    keyboard.row("✨ Сделать расклад", "ℹ️ О боте")
    keyboard.row("🔔 Напоминания")
    return keyboard


def readings_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton("💕 Любовь", callback_data="reading_love"),
        types.InlineKeyboardButton("💰 Деньги", callback_data="reading_money"),
    )

    keyboard.add(
        types.InlineKeyboardButton("🔮 3 карты", callback_data="reading_three")
    )

    return keyboard


def topics_keyboard(kind):
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for topic_key, topic_title in TOPICS[kind].items():
        keyboard.add(
            types.InlineKeyboardButton(
                topic_title,
                callback_data=f"topic:{kind}:{topic_key}",
            )
        )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Отменить",
            callback_data="reading_cancel",
        )
    )

    return keyboard


def periods_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for period_key, period_title in PERIODS.items():
        keyboard.add(
            types.InlineKeyboardButton(
                period_title,
                callback_data=f"period:{period_key}",
            )
        )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Назад к теме",
            callback_data="reading_back_topic",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Отменить",
            callback_data="reading_cancel",
        )
    )

    return keyboard


def profile_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Использовать эти данные",
            callback_data="profile_use",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✏️ Изменить данные",
            callback_data="profile_change",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Отменить",
            callback_data="reading_cancel",
        )
    )

    return keyboard


def other_profile_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Использовать эти данные",
            callback_data="other_use",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✏️ Изменить данные",
            callback_data="other_change",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Отменить",
            callback_data="reading_cancel",
        )
    )

    return keyboard


def reminder_message_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "🔮 Получить карту дня",
            callback_data="reminder_get_card",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔕 Отключить напоминания",
            callback_data="reminders_off",
        )
    )

    return keyboard


def reminder_settings_keyboard(enabled):
    keyboard = types.InlineKeyboardMarkup()

    if enabled:
        keyboard.add(
            types.InlineKeyboardButton(
                "🔕 Отключить напоминания",
                callback_data="reminders_off",
            )
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton(
                "🔔 Включить напоминания",
                callback_data="reminders_on",
            )
        )

    return keyboard


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def topic_name(kind, topic):
    return TOPICS.get(kind, {}).get(topic, "Общая ситуация")


def period_name(period):
    return PERIODS.get(period, "Без конкретного периода")


def valid_reading_params(kind, topic, period):
    return bool(
        kind in SPREADS
        and topic in TOPICS.get(kind, {})
        and period in PERIODS
    )


def reading_positions(kind, topic):
    positions = {
        "love": {
            "current": (
                "Основа отношений",
                "Что происходит между вами",
                "На что обратить внимание",
            ),
            "feelings": (
                "Что формирует отношение человека",
                "Что проявляется сейчас",
                "Возможная эмоциональная динамика",
            ),
            "ex": (
                "Что осталось из прошлого",
                "Что важно понять сейчас",
                "Что поможет двигаться дальше",
            ),
            "new": (
                "Что ты приносишь в знакомство",
                "Как может проявиться связь",
                "На что обратить внимание",
            ),
            "future": (
                "Текущая динамика",
                "Что может повлиять",
                "Возможное направление отношений",
            ),
        },
        "money": {
            "work": (
                "Твоя позиция сейчас",
                "Возможность в работе",
                "На что обратить внимание",
            ),
            "income": (
                "Что влияет на доход",
                "Где может быть возможность",
                "Что требует контроля",
            ),
            "situation": (
                "Текущее положение",
                "Ресурс или возможность",
                "Важный фактор",
            ),
            "opportunity": (
                "Что открывается",
                "Что поможет использовать шанс",
                "Какой риск стоит учесть",
            ),
            "future": (
                "Что формирует ближайший период",
                "Возможность",
                "На что обратить внимание",
            ),
        },
        "three": {
            "general": (
                "Прошлое",
                "Настоящее",
                "Возможное будущее",
            ),
            "love": (
                "Что привело к ситуации",
                "Что важно в чувствах сейчас",
                "Возможное развитие",
            ),
            "money": (
                "Что сформировало ситуацию",
                "Финансовая тема сейчас",
                "Возможное направление",
            ),
            "decision": (
                "Что влияет на выбор",
                "Что важно учесть",
                "К чему может привести выбранный путь",
            ),
            "future": (
                "Что уходит",
                "Что формируется сейчас",
                "Возможное ближайшее направление",
            ),
        },
    }

    return positions.get(kind, {}).get(topic, SPREADS[kind][1])


def personalized_focus(kind, topic):
    focuses = {
        "love": {
            "current":
                "В этом раскладе мы смотрим именно на текущую динамику отношений: "
                "что формирует ситуацию сейчас, что особенно важно заметить "
                "и в каком направлении она может развиваться.",
            "feelings":
                "Этот расклад посвящён теме чувств человека. "
                "Карты не могут достоверно читать чужие мысли, поэтому здесь "
                "мы рассматриваем эмоциональную динамику, проявления, взаимность "
                "и реальные сигналы в общении.",
            "ex":
                "Этот расклад рассматривает историю с бывшим партнёром: "
                "что из прошлого всё ещё влияет на ситуацию, что происходит сейчас "
                "и что может быть важно переосмыслить.",
            "new":
                "Этот расклад посвящён новому знакомству: его атмосфере, "
                "возможной динамике сближения и тому, на что стоит обратить внимание.",
            "future":
                "Этот расклад рассматривает возможное направление отношений. "
                "Это не фиксированное предсказание: развитие зависит от обстоятельств "
                "и действий обоих людей.",
        },
        "money": {
            "work":
                "Этот расклад посвящён работе: текущему положению, "
                "возможностям движения вперёд и фактору, который особенно важно учитывать.",
            "income":
                "Этот расклад рассматривает тему дохода: что влияет на него сейчас, "
                "где может находиться возможность и что требует особого внимания.",
            "situation":
                "Этот расклад посвящён общей финансовой ситуации: "
                "её текущей динамике, возможному ресурсу и важному фактору.",
            "opportunity":
                "Этот расклад рассматривает новую финансовую или рабочую возможность. "
                "Символический взгляд карт полезно сопоставлять с реальными цифрами "
                "и оценкой рисков.",
            "future":
                "Этот расклад рассматривает возможное направление финансовой ситуации. "
                "Он не обещает гарантированный доход или убыток, а предлагает "
                "дополнительный ракурс для размышления.",
        },
        "three": {
            "general":
                "Этот расклад рассматривает ситуацию в целом: "
                "какой прошлый опыт на неё влияет, что важно сейчас "
                "и какое направление может сформироваться дальше.",
            "love":
                "Эти три карты рассматриваются через тему личной жизни: "
                "прошлый эмоциональный контекст, настоящее положение "
                "и возможное развитие.",
            "money":
                "Эти три карты рассматриваются через тему денег и работы: "
                "предыдущие обстоятельства, текущее положение "
                "и возможное дальнейшее направление.",
            "decision":
                "Этот расклад посвящён важному решению. "
                "Карты не выбирают вместо тебя, а помогают посмотреть "
                "на контекст, важные факторы и возможные последствия.",
            "future":
                "Этот расклад посвящён ближайшему будущему. "
                "Карты показывают символическое направление при текущих обстоятельствах, "
                "а не неизбежный сценарий.",
        },
    }

    return focuses.get(kind, {}).get(
        topic,
        "Посмотри на карты как на дополнительный символический ракурс ситуации.",
    )


# =========================================================
# СОЗДАНИЕ РАСКЛАДА — ИИ
# =========================================================

def build_ai_prompt(kind, topic, period, chosen, user_id):
    name, age, other_name, other_age, _ = get_profile(user_id)
    positions = reading_positions(kind, topic)

    cards_text = "\n".join(
        f"{i + 1}. Позиция: {positions[i]}. Карта: {card[0]}"
        for i, card in enumerate(chosen)
    )

    text = (
        "Напиши готовый персонализированный расклад Таро на русском языке.\n"
        "Верни ТОЛЬКО текст самого расклада для пользователя Telegram-бота.\n"
        "Не пиши служебные сообщения, классификации безопасности, комментарии "
        "о запросе, инструкции или фразы вроде User Safety.\n\n"
        f"Имя пользователя: {name or 'не указано'}\n"
        f"Возраст: {age or 'не указан'}\n"
        f"Тема: {topic_name(kind, topic)}\n"
        f"Период: {period_name(period)}\n\n"
        f"Карты и позиции:\n{cards_text}\n"
    )

    if needs_other_person(kind, topic) and other_name and other_age:
        text += (
            f"\nВторой человек: {other_name}, "
            f"{other_age} лет.\n"
        )

    text += (
        "\nПРАВИЛА:\n"
        "1. Пиши именно расклад, а не анализ запроса.\n"
        "2. Обращайся к пользователю по имени, но никогда не угадывай пол по имени. "
        "Если пол явно не указан, используй нейтральные по роду формулировки.\n"
        "3. Не придумывай конкретные события из жизни пользователя.\n"
        "4. Не утверждай, что карты достоверно читают мысли другого человека.\n"
        "5. Будущее описывай только как возможное направление, а не гарантированный факт.\n"
        "6. Пиши красивым, естественным современным русским языком.\n"
        "7. Не используй чрезмерный пафос, бессмысленные метафоры и повторы.\n"
        "8. Каждая карта должна интерпретироваться именно в своей позиции и теме.\n"
        "9. Не выдавай медицинские, юридические или финансовые рекомендации.\n"
        "10. Ответ должен быть от 1200 до 3300 символов.\n\n"
        "СТРУКТУРА:\n"
        f"{SPREADS[kind][0]}\n"
        f"🎯 Тема: {topic_name(kind, topic)}\n"
        f"⏳ Период: {period_name(period)}\n\n"
        "Затем три карты по очереди.\n"
        "Для каждой: номер, название позиции, название карты и содержательная "
        "интерпретация именно применительно к выбранной теме.\n\n"
        "После карт:\n"
        "🔗 Как карты связаны\n"
        "Объясни общую последовательность карт.\n\n"
        "🔮 Общий итог\n"
        "Дай связный итог расклада без категоричных предсказаний.\n\n"
        "💭 Над чем подумать\n"
        "Заверши одним конкретным вопросом для размышления.\n\n"
        "Начинай сразу с названия расклада. Никакого текста до него."
    )

    return text


def is_bad_ai_response(content):
    if not content:
        return True

    cleaned = content.strip()
    lower = cleaned.lower()

    if len(cleaned) < 300:
        return True

    bad_phrases = (
        "user safety:",
        "user safety",
        "safety: safe",
        "safety classification",
        "safety assessment",
        "content safety",
        "policy violation",
        "request is safe",
        "the user request",
        "the user's request",
        "classification:",
    )

    if any(phrase in lower for phrase in bad_phrases):
        return True

    required_markers = (
        "1",
        "2",
        "3",
    )

    if not all(marker in cleaned for marker in required_markers):
        return True

    return False


def request_openrouter(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openrouter/free",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты пишешь готовые тексты развлекательных раскладов Таро "
                        "для Telegram-бота на русском языке. "
                        "Отвечай исключительно готовым текстом расклада. "
                        "Никогда не выводи внутренние классификации, служебные пометки, "
                        "оценки безопасности или фразы вроде User Safety. "
                        "Не объясняй, что ты модель. "
                        "Не анализируй сам запрос. "
                        "Не придумывай реальные факты о пользователе. "
                        "Не выдавай символическую интерпретацию за точное предсказание. "
                        "Если пол пользователя явно не указан, используй "
                        "нейтральные по грамматическому роду формулировки."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.75,
            "max_tokens": 1400,
        },
        timeout=40,
    )

    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []

    if not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")

    if not isinstance(content, str):
        return None

    return content.strip()


def ai_tarot_reading(kind, topic, period, chosen, user_id):
    if not OPENROUTER_API_KEY:
        return None

    prompt = build_ai_prompt(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    # У бесплатного роутера OpenRouter модель может меняться.
    # Поэтому при странном служебном ответе пробуем ещё раз.
    for attempt in range(3):
        try:
            content = request_openrouter(prompt)

            if not is_bad_ai_response(content):
                print(
                    f"OpenRouter: нормальный ответ получен, попытка {attempt + 1}",
                    flush=True,
                )
                return content

            print(
                f"OpenRouter: отброшен некорректный ответ, попытка {attempt + 1}: "
                f"{repr(content[:200] if content else content)}",
                flush=True,
            )

        except Exception as exc:
            print(
                f"Ошибка OpenRouter, попытка {attempt + 1}: {repr(exc)}",
                flush=True,
            )

        if attempt < 2:
            time.sleep(1)

    return None


def spread(kind, topic=None, period=None, user_id=None):
    title = SPREADS[kind][0]

    if topic not in TOPICS.get(kind, {}):
        topic = next(iter(TOPICS[kind]))

    if period not in PERIODS:
        period = "none"

    positions = reading_positions(kind, topic)
    chosen = random.sample(CARDS, 3)

    ai_result = ai_tarot_reading(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    if ai_result:
        return ai_result

    if kind == "love":
        meaning_index = 2
    elif kind == "money":
        meaning_index = 3
    elif topic == "love":
        meaning_index = 2
    elif topic == "money":
        meaning_index = 3
    else:
        meaning_index = 1

    selected_topic = topic_name(kind, topic)
    selected_period = period_name(period)

    profile_lines = []

    if user_id:
        name, age, other_name, other_age, _ = get_profile(user_id)

        if name and age:
            profile_lines.append(f"👤 Для: {name}, {age}")

        if needs_other_person(kind, topic) and other_name and other_age:
            profile_lines.append(
                f"💕 Второй человек: {other_name}, {other_age}"
            )

    lines = [
        title,
        "━━━━━━━━━━━━━━",
        f"🎯 Тема: {selected_topic}",
        f"⏳ Период: {selected_period}",
    ]

    if profile_lines:
        lines.extend(profile_lines)

    lines.extend([
        "",
        personalized_focus(kind, topic),
        "",
        "Перед тобой три карты. "
        "Сначала посмотри на каждую отдельно, "
        "а затем на их общую последовательность.",
    ])

    for number, position, card in zip(NUMBERS, positions, chosen):
        card_name = card[0]
        meaning = card[meaning_index]

        lines.append(
            f"{number} {position}\n\n"
            f"{card_name}\n\n"
            f"{meaning}"
        )

    names = [card[0] for card in chosen]

    connection = (
        "🔗 Как карты связаны\n\n"
        f"Связка {names[0]} → {names[1]} → {names[2]} "
        f"рассматривается через тему «{selected_topic}».\n\n"
        "Первая карта показывает исходный контекст, "
        "вторая — ключевую динамику настоящего, "
        "а третья — одно из возможных направлений развития."
    )

    conclusion = (
        "🔮 Общий итог\n\n"
        f"Период: {selected_period}.\n\n"
        "Расклад показывает символическое направление для размышления, "
        "а не неизбежный сценарий. Решения и обстоятельства "
        "могут менять дальнейшее развитие ситуации.\n\n"
        "💭 Над чем подумать\n"
        "Какой один конкретный шаг сейчас находится под твоим контролем?"
    )

    lines.append(connection)
    lines.append(conclusion)

    return "\n\n".join(lines)


# =========================================================
# КАРТА / ВОПРОС ДНЯ
# =========================================================

def day_card_text():
    name, meaning, *_ = random.choice(CARDS)

    return (
        "🔮 Твоя карта дня\n\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "💭 Вопрос дня:\n"
        "Как эта идея может проявиться в твоём сегодняшнем дне?\n\n"
        "✨ Таро здесь используется как развлекательная "
        "символическая практика, а не как точное предсказание."
    )


def question_text():
    name, meaning, *_ = random.choice(CARDS)

    return (
        "❓ Вопрос дня\n\n"
        "Сформулируй свой вопрос про себя. "
        "Не обязательно писать его боту.\n\n"
        "Твоя карта:\n\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "💭 Попробуй посмотреть на свой вопрос через идею этой карты.\n\n"
        "🔮 Это дополнительный ракурс для размышления, "
        "а не однозначный ответ или предсказание."
    )


def answer(call, text=None):
    bot.answer_callback_query(call.id, text=text)


# =========================================================
# АНКЕТА — ЛОГИКА
# =========================================================

def begin_profile(chat_id, user_id):
    name, age, _, _, _ = get_profile(user_id)

    if name and age:
        set_form_step(user_id, "profile_confirm")

        bot.send_message(
            chat_id,
            "👤 Для персонализации расклада у меня сохранены данные:\n\n"
            f"Имя: {name}\n"
            f"Возраст: {age}\n\n"
            "Использовать их?",
            reply_markup=profile_keyboard(),
        )
        return

    set_form_step(user_id, "name")

    bot.send_message(
        chat_id,
        "👤 Перед раскладом немного персонализируем его.\n\n"
        "Как тебя зовут?\n\n"
        "Напиши только имя.",
    )


def continue_after_main_profile(chat_id, user_id):
    kind, topic, period = get_pending_reading(user_id)

    if not valid_reading_params(kind, topic, period):
        clear_pending_reading(user_id)

        bot.send_message(
            chat_id,
            "Параметры расклада потеряны.\n\nНачни расклад заново.",
            reply_markup=main_keyboard(),
        )
        return

    if needs_other_person(kind, topic):
        _, _, other_name, other_age, _ = get_profile(user_id)

        if other_name and other_age:
            set_form_step(user_id, "other_confirm")

            bot.send_message(
                chat_id,
                "💕 Для этого любовного расклада у меня сохранены данные второго человека:\n\n"
                f"Имя: {other_name}\n"
                f"Возраст: {other_age}\n\n"
                "Использовать их?",
                reply_markup=other_profile_keyboard(),
            )
            return

        set_form_step(user_id, "other_name")

        bot.send_message(
            chat_id,
            "💕 Теперь укажи имя человека, о котором этот расклад.\n\n"
            "Напиши только имя.",
        )
        return

    finish_profile_and_process(chat_id, user_id)


def finish_profile_and_process(chat_id, user_id):
    set_form_step(user_id, None)
    kind, topic, period = get_pending_reading(user_id)

    if not valid_reading_params(kind, topic, period):
        clear_pending_reading(user_id)

        bot.send_message(
            chat_id,
            "Параметры расклада потеряны.\n\nНачни расклад заново.",
            reply_markup=main_keyboard(),
        )
        return

    process_selected_reading(
        chat_id,
        user_id,
        kind,
        topic,
        period,
    )


# =========================================================
# ПРОМО
# =========================================================

def activate_promo(user_id, code):
    normalized_code = code.strip().upper()

    if normalized_code != PROMO_CODE:
        return "invalid", 0

    with db() as conn:
        row = conn.execute("""
            INSERT INTO users (
                user_id, promo_code, promo_credits, created_at, last_seen
            )
            VALUES (%s, %s, %s, now(), now())

            ON CONFLICT (user_id)
            DO UPDATE SET
                promo_code = EXCLUDED.promo_code,
                promo_credits = EXCLUDED.promo_credits,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE users.promo_code IS NULL

            RETURNING promo_credits
        """, (
            user_id,
            PROMO_CODE,
            PROMO_CREDITS,
        )).fetchone()

        if row:
            return "activated", row[0]

        current = conn.execute("""
            UPDATE users
            SET last_seen = now(), reminder_sent_at = NULL
            WHERE user_id = %s
            RETURNING promo_credits
        """, (user_id,)).fetchone()

        return "already", current[0] if current else 0


def claim_promo_credit(user_id):
    with db() as conn:
        row = conn.execute("""
            UPDATE users
            SET
                promo_credits = promo_credits - 1,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
              AND promo_credits > 0
            RETURNING promo_credits
        """, (user_id,)).fetchone()

        if not row:
            return None

        return row[0]


# =========================================================
# НАПОМИНАНИЯ
# =========================================================

def get_reminders_enabled(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT reminders_enabled
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if not row:
        return True

    return bool(row[0])


def set_reminders_enabled(user_id, enabled):
    touch_user(user_id)

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET reminders_enabled = %s, reminder_sent_at = NULL
            WHERE user_id = %s
        """, (enabled, user_id))


def send_inactivity_reminders():
    cutoff = datetime.now(TZ) - timedelta(days=REMINDER_AFTER_DAYS)

    try:
        with db() as conn:
            rows = conn.execute("""
                SELECT user_id
                FROM users
                WHERE reminders_enabled = TRUE
                  AND last_seen IS NOT NULL
                  AND last_seen <= %s
                  AND reminder_sent_at IS NULL
                ORDER BY last_seen ASC
                LIMIT 100
            """, (cutoff,)).fetchall()

        for row in rows:
            user_id = row[0]

            with db() as conn:
                claimed = conn.execute("""
                    UPDATE users
                    SET reminder_sent_at = now()
                    WHERE user_id = %s
                      AND reminders_enabled = TRUE
                      AND last_seen <= %s
                      AND reminder_sent_at IS NULL
                    RETURNING user_id
                """, (user_id, cutoff)).fetchone()

            if not claimed:
                continue

            try:
                bot.send_message(
                    user_id,
                    "🔮 Заглянем в карты?\n\n"
                    "Твоя бесплатная Карта дня ждёт тебя ✨",
                    reply_markup=reminder_message_keyboard(),
                )

            except Exception:
                with db() as conn:
                    conn.execute("""
                        UPDATE users
                        SET reminders_enabled = FALSE
                        WHERE user_id = %s
                    """, (user_id,))

            time.sleep(0.2)

    except Exception as exc:
        print(
            "Ошибка проверки напоминаний:",
            repr(exc),
            flush=True,
        )


def reminder_worker():
    time.sleep(15)

    while True:
        send_inactivity_reminders()
        time.sleep(REMINDER_CHECK_SECONDS)


# =========================================================
# INVOICE
# =========================================================

def make_invoice_payload(kind, topic, period, user_id):
    return (
        f"{kind}:{topic}:{period}:{user_id}:{uuid4().hex}"
    )


def invoice_details(payload, user_id):
    parts = payload.split(":")

    if len(parts) != 5:
        return None

    kind, topic, period, payload_user_id, payment_nonce = parts

    if not valid_reading_params(kind, topic, period):
        return None

    if payload_user_id != str(user_id):
        return None

    if len(payment_nonce) != 32:
        return None

    return kind, topic, period


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    touch_user(message.from_user.id)
    clear_pending_reading(message.from_user.id)

    try:
        gif_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "9062F346-A2BF-4C00-9A56-9599938CD487.MP4",
        )

        with open(gif_path, "rb") as animation:
            bot.send_animation(
                chat_id=message.chat.id,
                animation=animation,
                caption="🔮 ТАРО ОРАКУЛ",
            )

    except Exception as exc:
        print(
            "Ошибка приветственной GIF:",
            repr(exc),
            flush=True,
        )

    bot.send_message(
        message.chat.id,
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Каждый день бесплатно:\n"
        "🔮 Карта дня\n"
        "❓ Вопрос дня\n\n"
        "🎁 Первый расклад «3 карты» — бесплатно.\n\n"
        f"💕 Любовь — {PRICE} ⭐\n"
        f"💰 Деньги — {PRICE} ⭐\n"
        f"🔮 Следующие расклады «3 карты» — {PRICE} ⭐\n\n"
        "Выбери, с чего хочешь начать 👇",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(commands=["myid"])
def myid(message):
    touch_user(message.from_user.id)

    bot.send_message(
        message.chat.id,
        f"Твой Telegram ID: {message.from_user.id}",
    )


# =========================================================
# ОСНОВНЫЕ КНОПКИ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🔮 Карта дня")
def card_of_the_day(message):
    touch_user(message.from_user.id)

    if not claim_free(message.from_user.id, "daily_card"):
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
    touch_user(message.from_user.id)

    if not claim_free(message.from_user.id, "daily_question"):
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


@bot.message_handler(func=lambda m: m.text == "✨ Сделать расклад")
def reading(message):
    touch_user(message.from_user.id)
    clear_pending_reading(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "✨ Выбери расклад:\n\n"
        f"💕 Любовь — {PRICE} ⭐\n"
        f"💰 Деньги — {PRICE} ⭐\n"
        f"🔮 3 карты — первый бесплатно, затем {PRICE} ⭐.",
        reply_markup=readings_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "ℹ️ О боте")
def about(message):
    touch_user(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул\n\n"
        "Развлекательный бот с символическими раскладами Таро.\n\n"
        "🎁 Карта дня и Вопрос дня — бесплатно каждый день.\n"
        "🔮 Первый расклад «3 карты» — бесплатно.\n"
        f"⭐ Платные расклады — {PRICE} Stars.\n\n"
        "📖 Условия: /terms\n"
        "🛟 Поддержка: /support\n"
        "💳 Проблема с оплатой: /paysupport",
        reply_markup=main_keyboard(),
    )


# =========================================================
# ВЫБОР РАСКЛАДА
# =========================================================

@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("reading_")
    and c.data not in (
        "reading_cancel",
        "reading_back_topic",
    )
)
def reading_callback(call):
    touch_user(call.from_user.id)

    kind = call.data.removeprefix("reading_")

    if kind not in SPREADS:
        answer(call, "Расклад не найден")
        return

    set_pending_reading(
        call.from_user.id,
        kind=kind,
    )

    answer(call)

    bot.send_message(
        call.message.chat.id,
        f"{SPREADS[kind][0]}\n\n"
        "🎯 Выбери тему:",
        reply_markup=topics_keyboard(kind),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("topic:")
)
def topic_callback(call):
    touch_user(call.from_user.id)

    parts = call.data.split(":", maxsplit=2)

    if len(parts) != 3:
        answer(call, "Ошибка выбора")
        return

    _, kind, topic = parts

    if kind not in TOPICS or topic not in TOPICS[kind]:
        answer(call, "Тема не найдена")
        return

    pending_kind, _, _ = get_pending_reading(
        call.from_user.id
    )

    if pending_kind != kind:
        answer(
            call,
            "Этот выбор уже неактуален",
        )
        return

    set_pending_reading(
        call.from_user.id,
        kind=kind,
        topic=topic,
        period=None,
    )

    answer(call)

    bot.send_message(
        call.message.chat.id,
        "🎯 Тема выбрана:\n"
        f"{topic_name(kind, topic)}\n\n"
        "⏳ Теперь выбери период:",
        reply_markup=periods_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "reading_back_topic"
)
def back_to_topic(call):
    kind, _, _ = get_pending_reading(
        call.from_user.id
    )

    if kind not in SPREADS:
        answer(
            call,
            "Расклад уже завершён",
        )
        return

    set_pending_reading(
        call.from_user.id,
        kind=kind,
    )

    answer(call)

    bot.send_message(
        call.message.chat.id,
        "🎯 Выбери другую тему:",
        reply_markup=topics_keyboard(kind),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "reading_cancel"
)
def cancel_reading(call):
    clear_pending_reading(
        call.from_user.id
    )

    answer(
        call,
        "Расклад отменён",
    )

    bot.send_message(
        call.message.chat.id,
        "❌ Расклад отменён.\n\n"
        "Ничего не списано.",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("period:")
)
def period_callback(call):
    period = call.data.removeprefix("period:")
    kind, topic, _ = get_pending_reading(
        call.from_user.id
    )

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        answer(
            call,
            "Этот выбор уже неактуален",
        )
        return

    set_pending_reading(
        call.from_user.id,
        kind=kind,
        topic=topic,
        period=period,
    )

    answer(call)

    begin_profile(
        call.message.chat.id,
        call.from_user.id,
    )


# =========================================================
# АНКЕТА CALLBACK
# =========================================================

@bot.callback_query_handler(
    func=lambda c:
    c.data == "profile_use"
)
def profile_use(call):
    answer(call)

    continue_after_main_profile(
        call.message.chat.id,
        call.from_user.id,
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "profile_change"
)
def profile_change(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        "name",
    )

    bot.send_message(
        call.message.chat.id,
        "✏️ Как тебя зовут?\n\n"
        "Напиши только имя.",
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "other_use"
)
def other_use(call):
    answer(call)

    finish_profile_and_process(
        call.message.chat.id,
        call.from_user.id,
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "other_change"
)
def other_change(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        "other_name",
    )

    bot.send_message(
        call.message.chat.id,
        "✏️ Напиши имя человека, "
        "о котором этот расклад.",
    )


# =========================================================
# ОБРАБОТКА РАСКЛАДА
# =========================================================

def process_selected_reading(
    chat_id,
    user_id,
    kind,
    topic,
    period,
):
    if kind == "three":
        if claim_free(
            user_id,
            "three_used",
        ):
            result = spread(
                kind,
                topic,
                period,
                user_id,
            )

            clear_pending_reading(
                user_id
            )

            bot.send_message(
                chat_id,
                "🎁 Это твой первый расклад "
                "«3 карты», поэтому он бесплатный.",
            )

            bot.send_message(
                chat_id,
                result,
            )
            return

    remaining = claim_promo_credit(
        user_id
    )

    if remaining is not None:
        result = spread(
            kind,
            topic,
            period,
            user_id,
        )

        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "🎁 Использован бесплатный расклад "
            "по промокоду.\n\n"
            f"Осталось бесплатных раскладов: {remaining}.",
        )

        bot.send_message(
            chat_id,
            result,
        )
        return

    offer_payment(
        chat_id,
        user_id,
        kind,
        topic,
        period,
    )


# =========================================================
# ОПЛАТА
# =========================================================

def send_invoice(
    chat_id,
    user_id,
    kind,
    topic,
    period,
):
    title = SPREADS[kind][0]

    payload = make_invoice_payload(
        kind,
        topic,
        period,
        user_id,
    )

    bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=(
            f"{topic_name(kind, topic)} · "
            f"{period_name(period)}. "
            "Персонализированный расклад "
            "Таро из трёх карт."
        ),
        invoice_payload=payload,
        provider_token="",
        currency="XTR",
        prices=[
            types.LabeledPrice(
                label=title,
                amount=PRICE,
            )
        ],
    )


def offer_payment(
    chat_id,
    user_id,
    kind,
    topic,
    period,
):
    touch_user(user_id)

    set_pending_reading(
        user_id,
        kind=kind,
        topic=topic,
        period=period,
    )

    with db() as conn:
        row = conn.execute("""
            SELECT terms_accepted
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if row and row[0]:
        send_invoice(
            chat_id,
            user_id,
            kind,
            topic,
            period,
        )
        return

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
            callback_data=(
                f"agree:{kind}:{topic}:{period}"
            ),
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Отменить",
            callback_data="reading_cancel",
        )
    )

    bot.send_message(
        chat_id,
        f"⭐ Стоимость расклада — {PRICE} Stars.\n\n"
        f"🎯 Тема: {topic_name(kind, topic)}\n"
        f"⏳ Период: {period_name(period)}\n\n"
        "После успешной оплаты результат "
        "придёт автоматически.",
        reply_markup=keyboard,
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "show_terms"
)
def show_terms(call):
    answer(call)

    bot.send_message(
        call.message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "Карта дня и Вопрос дня доступны "
        "бесплатно раз в день.\n"
        "Первый расклад «3 карты» бесплатный.\n"
        f"Платные расклады стоят {PRICE} Stars.\n\n"
        "Все расклады являются развлекательной "
        "символической интерпретацией.",
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("agree:")
)
def agree(call):
    parts = call.data.split(
        ":",
        maxsplit=3,
    )

    if len(parts) != 4:
        answer(
            call,
            "Ошибка параметров",
        )
        return

    _, kind, topic, period = parts

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        answer(
            call,
            "Расклад уже неактуален",
        )
        return

    with db() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id,
                terms_accepted,
                created_at,
                last_seen
            )
            VALUES (%s, TRUE, now(), now())

            ON CONFLICT (user_id)
            DO UPDATE SET
                terms_accepted = TRUE,
                last_seen = now(),
                reminder_sent_at = NULL
        """, (call.from_user.id,))

    answer(
        call,
        "Условия приняты",
    )

    send_invoice(
        call.message.chat.id,
        call.from_user.id,
        kind,
        topic,
        period,
    )


@bot.pre_checkout_query_handler(
    func=lambda query: True
)
def pre_checkout(query):
    try:
        details = invoice_details(
            query.invoice_payload,
            query.from_user.id,
        )

        ok = bool(
            details
            and query.currency == "XTR"
            and query.total_amount == PRICE
        )

        if ok:
            bot.answer_pre_checkout_query(
                query.id,
                ok=True,
            )

        else:
            bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=(
                    "Не удалось проверить оплату."
                ),
            )

    except Exception:
        bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message=(
                "Не удалось проверить оплату."
            ),
        )


@bot.message_handler(
    content_types=["successful_payment"]
)
def payment_success(message):
    touch_user(
        message.from_user.id
    )

    payment = message.successful_payment

    details = invoice_details(
        payment.invoice_payload,
        message.from_user.id,
    )

    if (
        not details
        or payment.currency != "XTR"
        or payment.total_amount != PRICE
    ):
        bot.send_message(
            message.chat.id,
            "⚠️ Платёж получен, но результат "
            "требует проверки.\n\n"
            "Напиши /paysupport.",
        )
        return

    kind, topic, period = details
    charge_id = (
        payment.telegram_payment_charge_id
    )

    with db() as conn:
        existing = conn.execute("""
            SELECT user_id, result, delivered
            FROM payments
            WHERE charge_id = %s
        """, (charge_id,)).fetchone()

    if existing:
        if (
            existing[0] != message.from_user.id
            or existing[2]
        ):
            return

        result = existing[1]

    else:
        result = spread(
            kind,
            topic,
            period,
            message.from_user.id,
        )

        with db() as conn:
            conn.execute("""
                INSERT INTO payments (
                    charge_id,
                    user_id,
                    kind,
                    result,
                    delivered,
                    topic,
                    period,
                    amount
                )
                VALUES (
                    %s, %s, %s, %s,
                    FALSE, %s, %s, %s
                )
                ON CONFLICT (charge_id)
                DO NOTHING
            """, (
                charge_id,
                message.from_user.id,
                kind,
                result,
                topic,
                period,
                payment.total_amount,
            ))

    try:
        bot.send_message(
            message.chat.id,
            "✅ Оплата успешно получена!\n\n"
            "🔮 Твой расклад готов.",
        )

        bot.send_message(
            message.chat.id,
            result,
        )

    except Exception as exc:
        print(
            "Ошибка отправки оплаченного расклада:",
            repr(exc),
            flush=True,
        )
        return

    with db() as conn:
        conn.execute("""
            UPDATE payments
            SET delivered = TRUE
            WHERE charge_id = %s
        """, (charge_id,))

    clear_pending_reading(
        message.from_user.id
    )


# =========================================================
# УСЛОВИЯ / ПОДДЕРЖКА / ПРОМО
# =========================================================

@bot.message_handler(commands=["terms"])
def terms(message):
    touch_user(
        message.from_user.id
    )

    bot.send_message(
        message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "• Карта дня — бесплатно раз в день.\n"
        "• Вопрос дня — бесплатно раз в день.\n"
        "• Первый расклад «3 карты» — бесплатно.\n"
        f"• Платные расклады — {PRICE} Stars.\n\n"
        "Расклады являются развлекательной "
        "символической интерпретацией, "
        "а не точным предсказанием.\n\n"
        "Проблема с оплатой: /paysupport.",
    )


@bot.message_handler(commands=["promo"])
def promo(message):
    parts = message.text.split(
        maxsplit=1
    )

    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "🎁 Введи:\n\n"
            "/promo КОД",
        )
        return

    status, credits = activate_promo(
        message.from_user.id,
        parts[1],
    )

    if status == "invalid":
        bot.send_message(
            message.chat.id,
            "❌ Такой промокод не найден.",
        )
        return

    if status == "already":
        bot.send_message(
            message.chat.id,
            "🎁 Промокод уже был активирован.\n\n"
            f"Осталось бесплатных раскладов: {credits}.",
        )
        return

    bot.send_message(
        message.chat.id,
        "🎉 Промокод активирован!\n\n"
        f"Доступно бесплатных раскладов: {credits}.",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(
    commands=["support", "paysupport"]
)
def support(message):
    touch_user(
        message.from_user.id
    )

    clear_pending_reading(
        message.from_user.id
    )

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET support_pending = TRUE
            WHERE user_id = %s
        """, (message.from_user.id,))

    bot.send_message(
        message.chat.id,
        "🛟 Опиши проблему одним сообщением.\n\n"
        "Не присылай пароль, токен "
        "или данные банковской карты.",
    )


# =========================================================
# ТЕСТ ВЛАДЕЛЬЦА
# =========================================================

@bot.message_handler(commands=["testreading"])
def testreading(message):
    if (
        not OWNER_ID
        or message.from_user.id != OWNER_ID
    ):
        return

    touch_user(
        message.from_user.id
    )

    parts = message.text.split(
        maxsplit=1
    )

    if (
        len(parts) < 2
        or parts[1].strip().lower()
        not in SPREADS
    ):
        bot.send_message(
            message.chat.id,
            "🧪 Тест:\n\n"
            "/testreading love\n"
            "/testreading money\n"
            "/testreading three",
        )
        return

    kind = parts[1].strip().lower()
    test_topic = next(
        iter(TOPICS[kind])
    )

    bot.send_message(
        message.chat.id,
        "🧪 Тестовый режим владельца. "
        "Stars не списываются.",
    )

    result = spread(
        kind,
        test_topic,
        "near",
        message.from_user.id,
    )

    bot.send_message(
        message.chat.id,
        result,
    )


# =========================================================
# НАПОМИНАНИЯ
# =========================================================

@bot.message_handler(
    func=lambda m:
    m.text == "🔔 Напоминания"
)
def reminders_settings(message):
    touch_user(
        message.from_user.id
    )

    enabled = get_reminders_enabled(
        message.from_user.id
    )

    text = (
        "🔔 Напоминания включены."
        if enabled
        else "🔕 Напоминания выключены."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=reminder_settings_keyboard(
            enabled
        ),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "reminders_off"
)
def reminders_off(call):
    set_reminders_enabled(
        call.from_user.id,
        False,
    )

    answer(
        call,
        "Напоминания выключены",
    )

    bot.send_message(
        call.message.chat.id,
        "🔕 Готово. Напоминания выключены.",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "reminders_on"
)
def reminders_on(call):
    set_reminders_enabled(
        call.from_user.id,
        True,
    )

    answer(
        call,
        "Напоминания включены",
    )

    bot.send_message(
        call.message.chat.id,
        "🔔 Напоминания включены.",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data == "reminder_get_card"
)
def reminder_get_card(call):
    touch_user(
        call.from_user.id
    )

    answer(call)

    if not claim_free(
        call.from_user.id,
        "daily_card",
    ):
        bot.send_message(
            call.message.chat.id,
            "🔮 Ты уже получил карту дня сегодня.\n\n"
            "Возвращайся завтра ✨",
            reply_markup=main_keyboard(),
        )
        return

    bot.send_message(
        call.message.chat.id,
        day_card_text(),
        reply_markup=main_keyboard(),
    )


# =========================================================
# ТЕКСТОВЫЕ СООБЩЕНИЯ / АНКЕТА
# =========================================================

@bot.message_handler(
    content_types=["text"],
    func=lambda m: True,
)
def other_text(message):
    touch_user(
        message.from_user.id
    )

    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()

    with db() as conn:
        row = conn.execute("""
            SELECT support_pending, form_step
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    support_pending = bool(
        row and row[0]
    )

    form_step = (
        row[1]
        if row
        else None
    )

    if support_pending:
        with db() as conn:
            ticket = conn.execute("""
                INSERT INTO support_tickets (
                    user_id,
                    body
                )
                VALUES (%s, %s)
                RETURNING id
            """, (
                user_id,
                text[:3500],
            )).fetchone()[0]

            conn.execute("""
                UPDATE users
                SET support_pending = FALSE
                WHERE user_id = %s
            """, (user_id,))

        bot.send_message(
            chat_id,
            f"🛟 Обращение №{ticket} принято.\n\n"
            "Ответ поддержки придёт сюда.",
            reply_markup=main_keyboard(),
        )

        if OWNER_ID:
            try:
                bot.send_message(
                    OWNER_ID,
                    f"🛟 Обращение №{ticket}\n\n"
                    f"Пользователь: {user_id}\n\n"
                    f"{text[:3500]}",
                )
            except Exception:
                pass

        return

    if form_step == "name":
        if (
            len(text) < 2
            or len(text) > 40
            or any(
                char.isdigit()
                for char in text
            )
            or text.startswith("/")
        ):
            bot.send_message(
                chat_id,
                "👤 Напиши имя буквами, "
                "от 2 до 40 символов.",
            )
            return

        name = text.capitalize()

        save_profile_name(
            user_id,
            name,
        )

        set_form_step(
            user_id,
            "age",
        )

        bot.send_message(
            chat_id,
            f"Приятно познакомиться, {name} ✨\n\n"
            "Теперь напиши свой возраст цифрами.",
        )
        return

    if form_step == "age":
        if not text.isdigit():
            bot.send_message(
                chat_id,
                "🎂 Напиши возраст только цифрами.",
            )
            return

        age = int(text)

        if age < 18 or age > 100:
            bot.send_message(
                chat_id,
                "🎂 Укажи возраст от 18 до 100 лет.",
            )
            return

        save_profile_age(
            user_id,
            age,
        )

        set_form_step(
            user_id,
            None,
        )

        bot.send_message(
            chat_id,
            "✅ Данные сохранены.",
        )

        continue_after_main_profile(
            chat_id,
            user_id,
        )
        return

    if form_step == "other_name":
        if (
            len(text) < 2
            or len(text) > 40
            or any(
                char.isdigit()
                for char in text
            )
            or text.startswith("/")
        ):
            bot.send_message(
                chat_id,
                "💕 Напиши имя человека буквами, "
                "от 2 до 40 символов.",
            )
            return

        other_name = text.capitalize()

        save_other_name(
            user_id,
            other_name,
        )

        set_form_step(
            user_id,
            "other_age",
        )

        bot.send_message(
            chat_id,
            f"💕 {other_name} — принято.\n\n"
            "Теперь напиши возраст этого "
            "человека цифрами.",
        )
        return

    if form_step == "other_age":
        if not text.isdigit():
            bot.send_message(
                chat_id,
                "🎂 Напиши возраст только цифрами.",
            )
            return

        other_age = int(text)

        if (
            other_age < 18
            or other_age > 100
        ):
            bot.send_message(
                chat_id,
                "🎂 Укажи возраст от 18 до 100 лет.",
            )
            return

        save_other_age(
            user_id,
            other_age,
        )

        set_form_step(
            user_id,
            None,
        )

        bot.send_message(
            chat_id,
            "✅ Данные сохранены.\n\n"
            "Перемешиваю колоду… 🔮",
        )

        finish_profile_and_process(
            chat_id,
            user_id,
        )
        return

    bot.send_message(
        chat_id,
        "Я не понял сообщение 🙂\n\n"
        "Используй меню ниже 👇",
        reply_markup=main_keyboard(),
    )


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":
    init_db()

    if not WEBHOOK_BASE_URL:
        raise RuntimeError(
            "Render не предоставил "
            "RENDER_EXTERNAL_URL"
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

    reminder_thread = threading.Thread(
        target=reminder_worker,
        daemon=True,
        name="reminder-worker",
    )

    reminder_thread.start()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000,
            )
        ),
    )
