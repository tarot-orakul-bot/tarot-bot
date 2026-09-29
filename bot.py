import hashlib
import hmac
import json
import os
import queue
import random
import re
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

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free",
)

if not TOKEN or not DATABASE_URL:
    raise RuntimeError(
        "Нужны переменные BOT_TOKEN и DATABASE_URL в Render"
    )

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

WEBHOOK_SECRET = hashlib.sha256(
    TOKEN.encode()
).hexdigest()

UPDATE_QUEUE = queue.Queue()

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


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
        "00_fool.png.PNG",
        "flip_00_fool.gif",
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
        "01_magician.png.PNG",
        "flip_01_magician.gif",
    ),
    (
        "🔮 Верховная Жрица",
        "Не вся информация сейчас находится на поверхности. "
        "Возможно, стоит немного замедлиться и присмотреться к деталям, "
        "которые раньше оставались незамеченными.",
        "В отношениях могут присутствовать невысказанные вопросы или неясность. "
        "Не стоит угадывать мысли другого человека. Лучше обращать внимание "
        "на реальные поступки и оставлять пространство для спокойного разговора.",
        "В денежных делах особенно важно внимательно изучить условия. "
        "Если что-то кажется непонятным или слишком привлекательным, "
        "полезно сначала получить дополнительную информацию.",
        "02_priestess.png.PNG",
        "flip_02_priestess.gif",
    ),
    (
        "👑 Императрица",
        "Карта связана с развитием, заботой и постепенным ростом. "
        "То, чему уделяется достаточно внимания и времени, может начать приносить результат.",
        "В чувствах Императрица обращает внимание на тепло, заботу и эмоциональную близость. "
        "В рамках расклада это может быть напоминанием о значении поддержки "
        "и внимания к потребностям друг друга.",
        "В финансовой сфере карта напоминает о постепенном росте. "
        "Вместо ожидания мгновенного результата полезно развивать то, "
        "что уже показывает потенциал.",
        "03_empress.png.PNG",
        "flip_03_empress.gif",
    ),
    (
        "🏛 Император",
        "Ситуации может не хватать структуры и ясных правил. "
        "План, последовательность и разумные границы способны вернуть ощущение контроля.",
        "В отношениях Император обращает внимание на границы, договорённости "
        "и ясность ожиданий. Карта не описывает характер конкретного человека, "
        "а предлагает посмотреть, насколько понятны правила взаимодействия.",
        "В денежных вопросах карта предлагает навести порядок. "
        "Бюджет, контроль обязательств и понятная цель могут оказаться "
        "полезнее спонтанных решений.",
        "04_emperor.png.PNG",
        "flip_04_emperor.gif",
    ),
    (
        "📜 Иерофант",
        "Иногда проверенные знания и опыт оказываются полезнее экспериментов. "
        "Посмотри, чему можно научиться у людей, которые уже проходили похожий путь.",
        "В отношениях карта обращает внимание на ценности, договорённости "
        "и представления о серьёзности союза. Полезно понять, совпадают ли ожидания.",
        "В денежных вопросах важно внимательно относиться к правилам, документам "
        "и обязательствам. В сложных ситуациях лучше опираться на проверенную информацию.",
        "05_hierophant.png.PNG",
        "flip_05_hierophant.gif",
    ),
    (
        "❤️ Влюблённые",
        "Перед тобой может стоять выбор, который связан не только с выгодой, "
        "но и с тем, что для тебя действительно важно.",
        "Это карта чувств, выбора и взаимности. "
        "Она предлагает обратить внимание на честность между людьми "
        "и понять, насколько совпадают желания и ожидания.",
        "В финансовой ситуации может быть несколько вариантов. "
        "Сравни их не только по потенциальной выгоде, но и по рискам, "
        "обязательствам и долгосрочным целям.",
        "06_lovers.png.PNG",
        "flip_06_lovers.gif",
    ),
    (
        "🏇 Колесница",
        "Карта говорит о движении и концентрации на цели. "
        "Когда направление выбрано, последовательные действия помогают продвинуться вперёд.",
        "В отношениях Колесница символически связана с движением и инициативой. "
        "Полезно обратить внимание, движутся ли люди в одном направлении "
        "и насколько действия учитывают границы друг друга.",
        "В деньгах полезно выбрать одну конкретную цель и направить усилия именно на неё. "
        "Контроль прогресса поможет понять, что действительно работает.",
        "07_chariot.png.PNG",
        "flip_07_chariot.gif",
    ),
    (
        "🦁 Сила",
        "Настойчивость не обязательно означает давление. "
        "Спокойствие, терпение и способность контролировать импульсивные реакции "
        "могут дать лучший результат.",
        "В отношениях карта предлагает действовать мягко, но уверенно. "
        "Спокойный разговор способен оказаться полезнее попытки доказать свою правоту.",
        "В финансовых вопросах важно контролировать импульсивные решения. "
        "Последовательность и дисциплина сейчас могут быть особенно полезны.",
        "08_strength.png.PNG",
        "flip_08_strength.gif",
    ),
    (
        "🕯 Отшельник",
        "Иногда для следующего шага сначала требуется разобраться в собственных мыслях. "
        "Небольшая пауза может дать больше ясности.",
        "В сфере чувств Отшельник предлагает обратить внимание на потребность "
        "в размышлении и личном пространстве. Сам по себе он не означает "
        "расставание или потерю чувств.",
        "В деньгах карта предлагает спокойно проанализировать прошлые решения, "
        "доходы и расходы прежде, чем менять стратегию.",
        "09_hermit.png.PNG",
        "flip_09_hermit.gif",
    ),
    (
        "🎡 Колесо Фортуны",
        "Обстоятельства могут меняться быстрее, чем ожидалось. "
        "Гибкость позволит использовать новые возможности и легче реагировать на перемены.",
        "В отношениях карта символизирует изменение привычной динамики. "
        "Каким именно будет это изменение, по одной карте определить нельзя, "
        "поэтому особенно важны реальные действия и разговор.",
        "Финансовая ситуация может меняться. "
        "Не стоит полагаться исключительно на удачу — запасной план и резерв "
        "помогают снизить зависимость от обстоятельств.",
        "10_wheel_of_fortune.png.PNG",
        "flip_10_wheel_of_fortune.gif",
    ),
    (
        "⚖️ Справедливость",
        "Попробуй посмотреть на ситуацию максимально объективно. "
        "Отдели факты от предположений и оцени последствия каждого решения.",
        "В отношениях карта обращает внимание на честность, баланс "
        "и взаимную ответственность. Полезно учитывать позицию обеих сторон.",
        "В денежных вопросах особенно важны цифры, документы и условия. "
        "Решение лучше принимать после внимательного сравнения вариантов.",
        "11_justice.png.PNG",
        "flip_11_justice.gif",
    ),
    (
        "🙃 Повешенный",
        "Возможно, сейчас полезнее не ускоряться, а изменить угол зрения. "
        "Пауза может помочь увидеть решение, которое раньше было незаметно.",
        "В отношениях карта предлагает посмотреть на ситуацию с другой стороны. "
        "Она может символизировать паузу или необходимость переосмысления, "
        "но не определяет исход отношений.",
        "Если финансовое решение не срочное, небольшая пауза может защитить "
        "от импульсивного шага и дать время оценить его реальную ценность.",
        "12_hanged_man.png.PNG",
        "flip_12_hanged_man.gif",
    ),
    (
        "🍂 Смерть",
        "Эта карта символизирует завершение этапа и трансформацию, а не буквальное событие. "
        "Что-то привычное может меняться, освобождая место для нового.",
        "В отношениях Смерть символически связана с изменением прежнего сценария. "
        "Это не обязательно означает расставание: речь может идти "
        "о пересмотре привычек, ожиданий или способа общения.",
        "В денежных вопросах полезно пересмотреть устаревшие расходы, обязательства "
        "или планы и направить ресурсы на более актуальные цели.",
        "13_death.png.PNG",
        "flip_13_death.gif",
    ),
    (
        "🌿 Умеренность",
        "Сейчас особенно важен устойчивый темп. "
        "Небольшие последовательные шаги способны привести дальше, чем резкие перемены.",
        "В отношениях карта обращает внимание на терпение, баланс и компромисс. "
        "Не каждый вопрос требует немедленного решения.",
        "В финансовой сфере разумный баланс расходов и накоплений "
        "может оказаться эффективнее крайностей.",
        "14_temperance.png.PNG",
        "flip_14_temperance.gif",
    ),
    (
        "⛓ Дьявол",
        "Обрати внимание на привычки или обязательства, которые могут ограничивать свободу выбора. "
        "Важно понять, что действительно удерживает ситуацию в прежнем состоянии.",
        "В отношениях карта предлагает обратить внимание на темы привязанности, "
        "ревности, контроля или зависимости, но не утверждает, "
        "что они обязательно присутствуют между конкретными людьми.",
        "В денежных вопросах стоит внимательнее относиться к долгам "
        "и слишком заманчивым обещаниям. Условия лучше проверять особенно тщательно.",
        "15_devil.png.PNG",
        "flip_15_devil.gif",
    ),
    (
        "⚡ Башня",
        "Башня символизирует резкую перестройку привычных представлений или обстоятельств. "
        "Это не обязательно означает катастрофу: иногда карта показывает момент, "
        "когда старый взгляд на ситуацию перестаёт работать.",
        "В отношениях Башня может символически указывать на необходимость "
        "прояснить напряжённую или неустойчивую тему. "
        "Она не означает автоматически конфликт, разрыв или расставание.",
        "В финансовой теме карта напоминает о важности запаса прочности "
        "и осторожности с крупными обязательствами.",
        "16_tower.png.PNG",
        "flip_16_tower.gif",
    ),
    (
        "⭐ Звезда",
        "Карта связана с надеждой и восстановлением направления. "
        "Даже если результат ещё далеко, небольшой следующий шаг уже имеет значение.",
        "В чувствах Звезда связана с надеждой, открытостью и восстановлением ясности. "
        "Она предлагает смотреть на реальные возможности, не превращая надежду в уверенность.",
        "В денежных вопросах полезно смотреть на долгосрочную цель. "
        "Раздели её на небольшие измеримые этапы и отмечай прогресс.",
        "17_star.png.PNG",
        "flip_17_star.gif",
    ),
    (
        "🌙 Луна",
        "Ситуация может казаться запутанной, потому что информации пока недостаточно. "
        "Важно отделять реальные факты от страхов и предположений.",
        "В отношениях Луна особенно напоминает не принимать тревогу, "
        "догадки или ожидания за факты. Неопределённость лучше прояснять "
        "через реальные поступки и разговор.",
        "Если цифры или условия непонятны, не торопись принимать финансовое решение. "
        "Сначала получи недостающую информацию.",
        "18_moon.png.JPEG",
        "flip_18_moon.gif",
    ),
    (
        "☀️ Солнце",
        "Карта связана с ясностью, открытостью и пониманием ситуации. "
        "Полезно обратить внимание на то, что уже стало понятнее.",
        "В отношениях Солнце символически связано с открытостью "
        "и возможностью более ясного взаимодействия. "
        "Но конкретный результат всё равно зависит от действий людей.",
        "В финансовых вопросах стоит обратить внимание на действия, "
        "которые уже дают измеримый результат, и развивать именно их.",
        "19_sun.png.PNG",
        "flip_19_sun.gif",
    ),
    (
        "📣 Суд",
        "Пришло время вернуться к важному вопросу и сделать выводы "
        "из накопленного опыта.",
        "В отношениях карта может символизировать возвращение к важной теме "
        "или необходимость окончательно её прояснить. "
        "Она не означает автоматически возвращение конкретного человека.",
        "В финансовой сфере анализ прежних решений поможет скорректировать цели "
        "и не повторять одни и те же ошибки.",
        "20_judgement.png.PNG",
        "flip_20_judgement.gif",
    ),
    (
        "🌍 Мир",
        "Один этап может подходить к завершению. "
        "Полезно увидеть достигнутый результат и определить следующую цель.",
        "В отношениях Мир предлагает посмотреть на ситуацию целиком: "
        "что уже стало понятнее и какой следующий этап действительно нужен.",
        "В денежных вопросах полезно подвести промежуточные итоги, "
        "оценить прогресс и выбрать следующую реалистичную цель.",
        "21_world.png.PNG",
        "flip_21_world.gif",
    ),
]


# =========================================================
# РАСКЛАДЫ
# =========================================================

SPREADS = {
    "love": (
        "💕 Расклад на любовь",
        (
            "Что влияет на ситуацию",
            "Что происходит сейчас",
            "Куда может двигаться ситуация",
        ),
    ),
    "money": (
        "💰 Расклад на деньги",
        (
            "Текущая ситуация",
            "Возможность",
            "На что обратить внимание",
        ),
    ),
    "three": (
        "🔮 Расклад «3 карты»",
        (
            "Прошлое",
            "Настоящее",
            "Возможное будущее",
        ),
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
# WEBHOOK + ОЧЕРЕДЬ
# =========================================================

@app.route("/")
def home():
    return "Tarot Orakul Bot is running", 200


@app.post(WEBHOOK_PATH)
def telegram_webhook():
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token",
        "",
    )

    if not hmac.compare_digest(
        received_secret,
        WEBHOOK_SECRET,
    ):
        abort(403)

    if not request.is_json:
        abort(415)

    try:
        update = types.Update.de_json(
            request.get_data(as_text=True)
        )
        UPDATE_QUEUE.put(update)

    except Exception as exc:
        print(
            "Ошибка получения Telegram update:",
            repr(exc),
            flush=True,
        )
        abort(400)

    return "", 200


def telegram_update_worker():
    while True:
        update = UPDATE_QUEUE.get()

        try:
            bot.process_new_updates([update])

        except Exception as exc:
            print(
                "Ошибка обработки Telegram update:",
                repr(exc),
                flush=True,
            )

        finally:
            UPDATE_QUEUE.task_done()


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

def db():
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=5,
    )


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
            conn.execute(
                f"ALTER TABLE users {column}"
            )

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

        payment_columns = [
            "ADD COLUMN IF NOT EXISTS topic TEXT",
            "ADD COLUMN IF NOT EXISTS period TEXT",
            "ADD COLUMN IF NOT EXISTS amount INTEGER",
            "ADD COLUMN IF NOT EXISTS cards_json TEXT",
            "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        ]

        for column in payment_columns:
            conn.execute(
                f"ALTER TABLE payments {column}"
            )

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
                user_id,
                created_at,
                last_seen,
                reminder_sent_at
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
                    user_id,
                    three_used,
                    created_at,
                    last_seen,
                    reminder_sent_at
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
            if field not in (
                "daily_card",
                "daily_question",
            ):
                raise ValueError(
                    "Неизвестная бесплатная функция"
                )

            today = datetime.now(TZ).date()

            row = conn.execute(f"""
                INSERT INTO users (
                    user_id,
                    {field},
                    created_at,
                    last_seen,
                    reminder_sent_at
                )
                VALUES (%s, %s, now(), now(), NULL)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    {field} = EXCLUDED.{field},
                    last_seen = now(),
                    reminder_sent_at = NULL
                WHERE users.{field}
                    IS DISTINCT FROM EXCLUDED.{field}

                RETURNING user_id
            """, (
                user_id,
                today,
            )).fetchone()

        return row is not None


def restore_free_three(user_id):
    try:
        with db() as conn:
            conn.execute("""
                UPDATE users
                SET three_used = FALSE
                WHERE user_id = %s
            """, (user_id,))

    except Exception as exc:
        print(
            "Не удалось вернуть бесплатный расклад:",
            repr(exc),
            flush=True,
        )


def restore_promo_credit(user_id):
    try:
        with db() as conn:
            conn.execute("""
                UPDATE users
                SET promo_credits = promo_credits + 1
                WHERE user_id = %s
            """, (user_id,))

    except Exception as exc:
        print(
            "Не удалось вернуть промокредит:",
            repr(exc),
            flush=True,
        )


def restore_daily_claim(user_id, field):
    if field not in (
        "daily_card",
        "daily_question",
    ):
        return

    try:
        today = datetime.now(TZ).date()

        with db() as conn:
            conn.execute(f"""
                UPDATE users
                SET {field} = NULL
                WHERE user_id = %s
                  AND {field} = %s
            """, (
                user_id,
                today,
            ))

    except Exception as exc:
        print(
            "Не удалось вернуть дневную попытку:",
            repr(exc),
            flush=True,
        )


# =========================================================
# СОСТОЯНИЕ РАСКЛАДА
# =========================================================

def set_pending_reading(
    user_id,
    kind=None,
    topic=None,
    period=None,
):
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
        """, (
            kind,
            topic,
            period,
            user_id,
        ))


def get_pending_reading(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT
                pending_kind,
                pending_topic,
                pending_period
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
        """, (
            step,
            user_id,
        ))


def save_profile_name(user_id, name):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                profile_name = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            name,
            user_id,
        ))


def save_profile_age(user_id, age):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                profile_age = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            age,
            user_id,
        ))


def save_other_name(user_id, name):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                other_name = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            name,
            user_id,
        ))


def save_other_age(user_id, age):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                other_age = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            age,
            user_id,
        ))


def needs_other_person(kind, topic):
    return (
        kind == "love"
        and topic in (
            "current",
            "feelings",
            "ex",
            "future",
        )
    )


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row(
        "🔮 Карта дня",
        "❓ Вопрос дня",
    )

    keyboard.row(
        "✨ Сделать расклад",
        "ℹ️ О боте",
    )

    keyboard.row(
        "🔔 Напоминания"
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


def topics_keyboard(kind):
    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

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
    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

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
    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

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
    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

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
# ИЗОБРАЖЕНИЯ И GIF КАРТ
# =========================================================

def card_image_path(card):
    return os.path.join(
        BASE_DIR,
        card[4],
    )


def card_gif_path(card):
    return os.path.join(
        BASE_DIR,
        card[5],
    )


def send_card_image(
    chat_id,
    card,
    caption=None,
):
    path = card_image_path(card)

    try:
        if not os.path.isfile(path):
            print(
                f"Изображение карты не найдено: {path}",
                flush=True,
            )
            return False

        with open(path, "rb") as photo:
            bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
            )

        return True

    except Exception as exc:
        print(
            "Ошибка отправки изображения карты "
            f"{card[0]}: {repr(exc)}",
            flush=True,
        )
        return False


def send_card_animation(
    chat_id,
    card,
    caption=None,
):
    gif_path = card_gif_path(card)

    try:
        if not os.path.isfile(gif_path):
            print(
                f"GIF карты не найдена: {gif_path}",
                flush=True,
            )
            return send_card_image(
                chat_id,
                card,
                caption=caption,
            )

        with open(gif_path, "rb") as animation:
            sent = bot.send_animation(
                chat_id=chat_id,
                animation=animation,
                caption=caption,
            )

        # НЕ МЕНЯТЬ: проверенное время показа GIF.
        time.sleep(6)

        try:
            bot.delete_message(
                chat_id,
                sent.message_id,
            )
        except Exception as exc:
            print(
                f"Не удалось удалить GIF: {repr(exc)}",
                flush=True,
            )

        return send_card_image(
            chat_id,
            card,
            caption=caption,
        )

    except Exception as exc:
        print(
            "Ошибка отправки GIF карты "
            f"{card[0]}: {repr(exc)}",
            flush=True,
        )

        return send_card_image(
            chat_id,
            card,
            caption=caption,
        )


def send_spread_images(
    chat_id,
    chosen,
    positions,
):
    success = True

    for index, card in enumerate(chosen):
        card_sent = send_card_animation(
            chat_id,
            card,
            caption=(
                f"{NUMBERS[index]} {positions[index]}\n"
                f"{card[0]}"
            ),
        )

        if not card_sent:
            success = False

        time.sleep(0.4)

    return success


def send_long_message(
    chat_id,
    text,
    reply_markup=None,
):
    if not isinstance(text, str):
        text = str(text)

    text = text.strip()

    if not text:
        return False

    max_length = 3900
    parts = []

    while len(text) > max_length:
        split_at = text.rfind(
            "\n\n",
            0,
            max_length,
        )

        if split_at < 1000:
            split_at = text.rfind(
                "\n",
                0,
                max_length,
            )

        if split_at < 1000:
            split_at = text.rfind(
                " ",
                0,
                max_length,
            )

        if split_at < 1:
            split_at = max_length

        parts.append(
            text[:split_at].strip()
        )

        text = text[split_at:].strip()

    if text:
        parts.append(text)

    try:
        for index, part in enumerate(parts):
            bot.send_message(
                chat_id,
                part,
                reply_markup=(
                    reply_markup
                    if index == len(parts) - 1
                    else None
                ),
            )

        return True

    except Exception as exc:
        print(
            "Ошибка отправки текста:",
            repr(exc),
            flush=True,
        )
        return False


# =========================================================
# КОНЕЦ ЧАСТИ 1/3
# =========================================================
# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ
# =========================================================

def topic_name(kind, topic):
    return TOPICS.get(kind, {}).get(
        topic,
        topic or "Без темы",
    )


def period_name(period):
    return PERIODS.get(
        period,
        period or "Без конкретного периода",
    )


def valid_reading_params(
    kind,
    topic,
    period,
):
    return (
        kind in SPREADS
        and topic in TOPICS.get(kind, {})
        and period in PERIODS
    )


def reading_positions(kind, topic=None):
    if kind == "love":
        if topic == "feelings":
            return (
                "Что влияет на его/её отношение",
                "Что проявляется между вами сейчас",
                "Как может развиваться динамика",
            )

        if topic == "ex":
            return (
                "Что осталось в прошлом",
                "Что важно понять сейчас",
                "Куда может двигаться ситуация",
            )

        if topic == "new":
            return (
                "Твоя готовность к знакомству",
                "Что может проявиться",
                "На что обратить внимание",
            )

        if topic == "future":
            return (
                "Основа ситуации",
                "Что формируется сейчас",
                "Возможное направление отношений",
            )

    if kind == "money":
        if topic == "work":
            return (
                "Твоя рабочая ситуация",
                "Возможность для развития",
                "На что обратить внимание",
            )

        if topic == "income":
            return (
                "Что влияет на доход",
                "Где может быть возможность",
                "Что поможет двигаться дальше",
            )

        if topic == "opportunity":
            return (
                "Что уже есть",
                "Новая возможность",
                "Как лучше с ней работать",
            )

        if topic == "future":
            return (
                "Текущая основа",
                "Что может измениться",
                "Возможное направление",
            )

    return SPREADS[kind][1]


def personalized_focus(user_id):
    try:
        (
            profile_name,
            profile_age,
            other_name,
            other_age,
            _,
        ) = get_profile(user_id)

    except Exception:
        return ""

    parts = []

    if profile_name:
        own = f"Пользователя зовут {profile_name}"

        if profile_age:
            own += f", возраст: {profile_age}"

        parts.append(own + ".")

    if other_name:
        other = (
            "В вопросе также участвует человек "
            f"по имени {other_name}"
        )

        if other_age:
            other += f", возраст: {other_age}"

        parts.append(other + ".")

    if not parts:
        return ""

    return (
        "\nПерсональный контекст:\n"
        + "\n".join(parts)
        + "\nИспользуй эти данные естественно и деликатно. "
        "Не повторяй возраст без необходимости."
    )


def normalize_for_check(text):
    if not text:
        return ""

    text = str(text).lower()
    text = text.replace("ё", "е")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_heading(text):
    if not text:
        return ""

    text = normalize_for_check(text)

    text = re.sub(
        r"[^\wа-я]+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def allowed_latin_words():
    return {
        "ai",
        "api",
        "telegram",
        "stars",
        "star",
    }


def unwanted_english_words(text):
    words = re.findall(
        r"\b[A-Za-z]{3,}\b",
        text or "",
    )

    allowed = allowed_latin_words()

    return [
        word
        for word in words
        if word.lower() not in allowed
    ]


def contains_formal_address(text):
    normalized = normalize_for_check(text)

    patterns = [
        r"\bвы\b",
        r"\bвам\b",
        r"\bвас\b",
        r"\bваш\b",
        r"\bваша\b",
        r"\bваше\b",
        r"\bваши\b",
        r"\bвашего\b",
        r"\bвашей\b",
        r"\bвашему\b",
        r"\bвашим\b",
        r"\bвашими\b",
    ]

    return any(
        re.search(pattern, normalized)
        for pattern in patterns
    )


def section_present(text, heading):
    wanted = normalize_heading(heading)

    for line in (text or "").splitlines():
        if normalize_heading(line) == wanted:
            return True

    return False


def title_line_matches(text, title):
    lines = [
        line.strip()
        for line in (text or "").splitlines()
        if line.strip()
    ]

    if not lines:
        return False

    return (
        normalize_heading(lines[0])
        == normalize_heading(title)
    )


# =========================================================
# OPENROUTER / AI-РАСКЛАД
# =========================================================

def build_ai_prompt(
    kind,
    topic,
    period,
    chosen,
    user_id,
):
    title = SPREADS[kind][0]
    positions = reading_positions(
        kind,
        topic,
    )

    card_lines = []

    for index, card in enumerate(chosen):
        card_lines.append(
            f"{NUMBERS[index]} {positions[index]} — {card[0]}"
        )

    cards_text = "\n".join(card_lines)

    return f"""
Ты пишешь персональный развлекательный расклад Таро
для Telegram-бота «Таро Оракул».

ВАЖНЫЕ ПРАВИЛА:
1. Пиши только на русском языке.
2. Обращайся к пользователю ТОЛЬКО на «ты».
3. Никогда не используй обращения «вы», «вам», «вас», «ваш».
4. Не утверждай, что карты точно предсказывают будущее.
5. Не утверждай как факт мысли, чувства, намерения или действия другого человека.
6. Не давай медицинских, юридических или инвестиционных гарантий.
7. Не пиши служебные комментарии, объяснения задания или рассуждения о правилах.
8. Не используй Markdown-заголовки с #.
9. Не начинай ответ со слов «Конечно», «Вот расклад» или похожего вступления.
10. Первая непустая строка ответа должна ТОЧНО совпадать с названием:
{title}

Тема:
{topic_name(kind, topic)}

Период:
{period_name(period)}

Карты:
{cards_text}

{personalized_focus(user_id)}

СТРУКТУРА ОТВЕТА:

{title}

🎯 Тема: {topic_name(kind, topic)}

⏳ Период: {period_name(period)}

Короткое вступление на 2–4 предложения именно по теме пользователя.

{NUMBERS[0]} {positions[0]}

{chosen[0][0]}

Интерпретация первой карты: примерно 80–150 слов.

{NUMBERS[1]} {positions[1]}

{chosen[1][0]}

Интерпретация второй карты: примерно 80–150 слов.

{NUMBERS[2]} {positions[2]}

{chosen[2][0]}

Интерпретация третьей карты: примерно 80–150 слов.

🔗 Как карты связаны

Свяжи три карты в единую последовательность.
Не повторяй дословно предыдущие абзацы.

🔮 Общий итог

Дай содержательный итог расклада.
Формулируй возможные направления, а не неизбежные события.

💭 Над чем подумать

Заверши одним конкретным вопросом для размышления.

Никакого текста после последнего вопроса.
""".strip()


def clean_ai_response(
    text,
    expected_title=None,
):
    if not text:
        return ""

    text = str(text).replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    text = text.strip()

    text = re.sub(
        r"^```(?:text|markdown|md)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    if expected_title:
        lines = text.splitlines()

        start_index = None

        for index, line in enumerate(lines):
            if (
                normalize_heading(line)
                == normalize_heading(expected_title)
            ):
                start_index = index
                break

        if start_index is not None:
            text = "\n".join(
                lines[start_index:]
            ).strip()

        else:
            position = normalize_for_check(text).find(
                normalize_for_check(expected_title)
            )

            if position > 0:
                text = text[position:].strip()

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def validate_ai_response(
    text,
    kind,
    topic,
    period,
    chosen,
):
    if not text:
        return False, "empty"

    title = SPREADS[kind][0]

    if not title_line_matches(
        text,
        title,
    ):
        return False, "wrong_start"

    

    normalized = normalize_for_check(text)

    service_phrases = [
        "system prompt",
        "developer message",
        "assistant message",
        "я не могу выполнить",
        "не могу выполнить этот запрос",
        "не могу помочь с этим запросом",
        "как языковая модель",
        "как искусственный интеллект",
        "служебная инструкция",
        "внутренняя инструкция",
    ]

    if any(
        phrase in normalized
        for phrase in service_phrases
    ):
        return False, "service_output"


    english = unwanted_english_words(text)

    if len(english) >= 3:
        return False, "english"

    if len(text) < 900:
        return False, "too_short"

    if len(text) > 9000:
        return False, "too_long"

    positions = reading_positions(
        kind,
        topic,
    )

    for index, card in enumerate(chosen):
        if normalize_heading(card[0]) not in normalize_heading(text):
            return (
                False,
                f"missing_card_{index + 1}",
            )

        if (
            normalize_heading(positions[index])
            not in normalize_heading(text)
        ):
            return (
                False,
                f"missing_position_{index + 1}",
            )

    return True, "ok"


def extract_openrouter_content(data):
    try:
        choices = data.get("choices")

        if not isinstance(choices, list):
            return ""

        if not choices:
            return ""

        message = choices[0].get("message")

        if not isinstance(message, dict):
            return ""

        content = message.get("content")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == "text":
                    value = item.get("text")

                    if isinstance(value, str):
                        parts.append(value)

            return "\n".join(parts).strip()

    except Exception:
        pass

    return ""


def request_openrouter(prompt):
    if not OPENROUTER_API_KEY:
        print(
            "OPENROUTER_API_KEY не задан. "
            "Использую встроенный расклад.",
            flush=True,
        )
        return ""

    headers = {
        "Authorization": (
            f"Bearer {OPENROUTER_API_KEY}"
        ),
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.45,
        "max_tokens": 1400,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=35,
        )

        if response.status_code != 200:
            print(
                "OpenRouter HTTP:",
                response.status_code,
                response.text[:1000],
                flush=True,
            )
            return ""

        data = response.json()

        return extract_openrouter_content(data)

    except Exception as exc:
        print(
            "Ошибка OpenRouter:",
            repr(exc),
            flush=True,
        )
        return ""


def retry_instruction(reason):
    if reason == "empty":
        return (
            "\n\nПредыдущая попытка вернула пустой ответ. "
            "Сразу выдай полный расклад по заданной структуре."
        )

    if reason == "wrong_start":
        return (
            "\n\nВАЖНО: начни ответ непосредственно "
            "с точного названия расклада, без вступления перед ним."
        )

    if reason == "formal_address":
        return (
            "\n\nКРИТИЧЕСКИ ВАЖНО: обращайся к пользователю "
            "только на «ты». Не используй «вы», «вам», "
            "«вас», «ваш» ни в каком контексте."
        )

    if reason.startswith("missing_section"):
        return (
            "\n\nВ предыдущей попытке отсутствовал обязательный раздел. "
            "Соблюдай всю указанную структуру полностью."
        )

    if reason.startswith("missing_card"):
        return (
            "\n\nОбязательно назови все три выпавшие карты "
            "в соответствующих разделах."
        )

    if reason.startswith("missing_position"):
        return (
            "\n\nОбязательно сохрани точные названия "
            "всех трёх позиций расклада."
        )

    if reason == "too_short":
        return (
            "\n\nПредыдущий ответ был слишком коротким. "
            "Дай полноценную содержательную интерпретацию "
            "каждой из трёх карт."
        )

    if reason == "english":
        return (
            "\n\nПиши исключительно по-русски. "
            "Не вставляй английские фразы."
        )

    return (
        "\n\nПовтори ответ строго по исходной структуре. "
        "Не добавляй никаких служебных комментариев."
    )


def ai_tarot_reading(
    kind,
    topic,
    period,
    chosen,
    user_id,
):
    prompt = build_ai_prompt(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    last_reason = "unknown"

    for attempt in range(1, 4):
        attempt_prompt = prompt

        if attempt > 1:
            attempt_prompt += retry_instruction(
                last_reason
            )

        raw = request_openrouter(
            attempt_prompt
        )

        cleaned = clean_ai_response(
            raw,
            SPREADS[kind][0],
        )

        valid, reason = validate_ai_response(
            cleaned,
            kind,
            topic,
            period,
            chosen,
        )

        if valid:
            print(
                "OpenRouter: качественный ответ получен, "
                f"попытка {attempt}, длина {len(cleaned)}",
                flush=True,
            )

            return cleaned

        last_reason = reason

        print(
            "OpenRouter: ответ отклонён, "
            f"попытка {attempt}, "
            f"причина: {reason}, "
            f"raw: {len(raw)}, "
            f"clean: {len(cleaned)}",
            flush=True,
        )

        if attempt < 3:
            time.sleep(1)

    print(
        "OpenRouter: качественный ответ не получен "
        "после трёх попыток. "
        "Использую встроенный резервный расклад.",
        flush=True,
    )

    return ""


# =========================================================
# ВСТРОЕННЫЙ РЕЗЕРВНЫЙ РАСКЛАД
# =========================================================

def fallback_card_text(
    card,
    kind,
):
    if kind == "love":
        return card[2]

    if kind == "money":
        return card[3]

    return card[1]


def fallback_spread(
    kind,
    topic,
    period,
    chosen,
):
    title = SPREADS[kind][0]
    positions = reading_positions(
        kind,
        topic,
    )

    lines = [
        title,
        "",
        "━━━━━━━━━━━━━━",
        "",
        f"🎯 Тема: {topic_name(kind, topic)}",
        "",
        f"⏳ Период: {period_name(period)}",
        "",
    ]

    if kind == "three":
        lines.extend([
            "Этот расклад рассматривает ситуацию в целом: "
            "какой прошлый опыт на неё влияет, "
            "что важно сейчас и какое направление "
            "может сформироваться дальше.",
            "",
            "Перед тобой три карты. "
            "Сначала посмотри на каждую отдельно, "
            "а затем на их общую последовательность.",
            "",
        ])

    elif kind == "love":
        lines.extend([
            "Этот расклад предлагает символически посмотреть "
            "на выбранную тему отношений с трёх сторон. "
            "Карты не читают мысли другого человека "
            "и не определяют будущее заранее.",
            "",
        ])

    else:
        lines.extend([
            "Этот расклад помогает символически посмотреть "
            "на финансовую или рабочую ситуацию. "
            "Карты не заменяют расчёты и реальные финансовые решения, "
            "но могут подсказать вопросы для размышления.",
            "",
        ])

    for index, card in enumerate(chosen):
        lines.extend([
            f"{NUMBERS[index]} {positions[index]}",
            "",
            card[0],
            "",
            fallback_card_text(
                card,
                kind,
            ),
            "",
        ])

    card_names = ", ".join(
        card[0]
        for card in chosen
    )

    lines.extend([
        "🔗 Как карты связаны",
        "",
        f"{card_names} создают последовательность "
        "из трёх символических тем. "
        "Первая карта показывает основу ситуации, "
        "вторая помогает увидеть её текущее состояние, "
        "а третья предлагает обратить внимание "
        "на возможное направление дальнейших действий.",
        "",
        "🔮 Общий итог",
        "",
        "Сочетание карт предлагает рассмотреть ситуацию "
        "не как заранее определённый сценарий, "
        "а как набор обстоятельств и вариантов. "
        "Полезнее всего сопоставить символы расклада "
        "с тем, что происходит в реальности, "
        "и опираться на собственные решения.",
        "",
        "💭 Над чем подумать",
        "",
        "Какой конкретный шаг сейчас зависит от тебя "
        "и способен сделать ситуацию яснее?",
    ])

    return "\n".join(lines)


def spread(
    kind,
    topic,
    period,
    user_id,
    chosen=None,
):
    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        raise ValueError(
            "Некорректные параметры расклада"
        )

    if chosen is None:
        chosen = random.sample(
            CARDS,
            3,
        )

    ai_text = ai_tarot_reading(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    if ai_text:
        return ai_text, chosen

    return (
        fallback_spread(
            kind,
            topic,
            period,
            chosen,
        ),
        chosen,
    )


# =========================================================
# СОХРАНЕНИЕ КАРТ
# =========================================================

def card_indices(chosen):
    indices = []

    for card in chosen:
        try:
            indices.append(
                CARDS.index(card)
            )

        except ValueError:
            return []

    return indices


def cards_from_json(cards_json):
    if not cards_json:
        return []

    try:
        values = json.loads(
            cards_json
        )

        if not isinstance(values, list):
            return []

        if len(values) != 3:
            return []

        cards = []

        for value in values:
            index = int(value)

            if index < 0 or index >= len(CARDS):
                return []

            cards.append(
                CARDS[index]
            )

        return cards

    except Exception:
        return []


# =========================================================
# ОТПРАВКА ГОТОВОГО РАСКЛАДА
# =========================================================

def send_reading_result(
    chat_id,
    kind,
    topic,
    result,
    chosen,
):
    try:
        positions = reading_positions(
            kind,
            topic,
        )

        images_ok = send_spread_images(
            chat_id,
            chosen,
            positions,
        )

        text_ok = send_long_message(
            chat_id,
            result,
            reply_markup=main_keyboard(),
        )

        return (
            images_ok
            and text_ok
        )

    except Exception as exc:
        print(
            "Ошибка отправки расклада:",
            repr(exc),
            flush=True,
        )
        return False


# =========================================================
# КАРТА ДНЯ
# =========================================================

def choose_day_card():
    return random.choice(
        CARDS
    )


def day_card_text(card):
    return (
        "🔮 Карта дня\n\n"
        f"{card[0]}\n\n"
        f"{card[1]}\n\n"
        "✨ Не воспринимай карту как неизбежное предсказание. "
        "Используй её как символическую тему дня."
    )


def send_daily_card(
    chat_id,
    user_id,
):
    if not claim_free(
        user_id,
        "daily_card",
    ):
        bot.send_message(
            chat_id,
            "🔮 Ты уже получил карту дня сегодня. "
            "Возвращайся завтра ✨",
            reply_markup=main_keyboard(),
        )
        return False

    card = choose_day_card()

    try:
        animation_ok = send_card_animation(
            chat_id,
            card,
            caption=(
                "🔮 Карта дня\n"
                f"{card[0]}"
            ),
        )

        text_ok = send_long_message(
            chat_id,
            day_card_text(card),
            reply_markup=main_keyboard(),
        )

        if not (
            animation_ok
            and text_ok
        ):
            restore_daily_claim(
                user_id,
                "daily_card",
            )
            return False

        return True

    except Exception:
        restore_daily_claim(
            user_id,
            "daily_card",
        )
        raise


# =========================================================
# ВОПРОС ДНЯ
# =========================================================

DAILY_QUESTIONS = [
    "Что сегодня действительно находится под твоим контролем?",
    "Какой небольшой шаг сегодня может приблизить тебя к важной цели?",
    "Что сегодня стоит отпустить, чтобы освободить внимание для более важного?",
    "Какой разговор ты давно откладываешь и почему?",
    "Что сегодня может помочь тебе почувствовать больше ясности?",
    "На что ты тратишь силы, хотя это почти ничего тебе не даёт?",
    "Какое решение станет проще, если отделить факты от предположений?",
    "Что хорошее уже происходит, но ты редко это замечаешь?",
    "Какую привычку сегодня можно сделать хотя бы немного полезнее?",
    "Чего ты действительно хочешь от ближайшего времени?",
    "Какое действие сегодня зависит только от тебя?",
    "Где тебе сейчас важнее проявить терпение, а не торопиться?",
]


def send_daily_question(
    chat_id,
    user_id,
):
    if not claim_free(
        user_id,
        "daily_question",
    ):
        bot.send_message(
            chat_id,
            "❓ Ты уже получил Вопрос дня сегодня. "
            "Возвращайся завтра ✨",
            reply_markup=main_keyboard(),
        )
        return False

    question = random.choice(
        DAILY_QUESTIONS
    )

    try:
        sent = send_long_message(
            chat_id,
            (
                "❓ Вопрос дня\n\n"
                f"{question}\n\n"
                "Не обязательно отвечать сразу. "
                "Иногда полезно просто оставить этот вопрос "
                "с собой на некоторое время."
            ),
            reply_markup=main_keyboard(),
        )

        if not sent:
            restore_daily_claim(
                user_id,
                "daily_question",
            )
            return False

        return True

    except Exception:
        restore_daily_claim(
            user_id,
            "daily_question",
        )
        raise


# =========================================================
# АНКЕТА ПЕРЕД РАСКЛАДОМ
# =========================================================

def profile_summary(
    name,
    age,
):
    return (
        "👤 Твои данные\n\n"
        f"Имя: {name or 'не указано'}\n"
        f"Возраст: {age or 'не указан'}"
    )


def other_profile_summary(
    name,
    age,
):
    return (
        "💕 Данные второго человека\n\n"
        f"Имя: {name or 'не указано'}\n"
        f"Возраст: {age or 'не указан'}"
    )


def begin_profile(
    chat_id,
    user_id,
):
    (
        profile_name,
        profile_age,
        _,
        _,
        _,
    ) = get_profile(user_id)

    if (
        profile_name
        and profile_age
    ):
        set_form_step(
            user_id,
            "profile_confirm",
        )

        bot.send_message(
            chat_id,
            profile_summary(
                profile_name,
                profile_age,
            ),
            reply_markup=profile_keyboard(),
        )
        return

    set_form_step(
        user_id,
        "profile_name",
    )

    bot.send_message(
        chat_id,
        "👤 Перед раскладом напиши своё имя.\n\n"
        "Например: Роман",
    )


def continue_after_profile(
    chat_id,
    user_id,
):
    kind, topic, period = (
        get_pending_reading(
            user_id
        )
    )

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Не удалось восстановить выбранный расклад. "
            "Выбери его ещё раз.",
            reply_markup=main_keyboard(),
        )
        return

    if needs_other_person(
        kind,
        topic,
    ):
        (
            _,
            _,
            other_name,
            other_age,
            _,
        ) = get_profile(user_id)

        if (
            other_name
            and other_age
        ):
            set_form_step(
                user_id,
                "other_confirm",
            )

            bot.send_message(
                chat_id,
                other_profile_summary(
                    other_name,
                    other_age,
                ),
                reply_markup=other_profile_keyboard(),
            )
            return

        set_form_step(
            user_id,
            "other_name",
        )

        bot.send_message(
            chat_id,
            "💕 Напиши имя человека, "
            "о котором будет расклад.",
        )
        return

    finish_profile_flow(
        chat_id,
        user_id,
    )


def finish_profile_flow(
    chat_id,
    user_id,
):
    set_form_step(
        user_id,
        None,
    )

    kind, topic, period = (
        get_pending_reading(
            user_id
        )
    )

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Не удалось восстановить выбранный расклад. "
            "Попробуй выбрать его заново.",
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
# ПРОМОКОДЫ
# =========================================================

def activate_promo(
    user_id,
    code,
):
    normalized = (
        code or ""
    ).strip().upper()

    if normalized != PROMO_CODE:
        return "invalid"

    with db() as conn:
        row = conn.execute("""
            SELECT promo_code
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

        if not row:
            touch_user(user_id)

            row = conn.execute("""
                SELECT promo_code
                FROM users
                WHERE user_id = %s
            """, (user_id,)).fetchone()

        if row and row[0]:
            return "already"

        conn.execute("""
            UPDATE users
            SET
                promo_code = %s,
                promo_credits = %s,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            PROMO_CODE,
            PROMO_CREDITS,
            user_id,
        ))

    return "activated"


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

    return row is not None


def promo_credits(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT promo_credits
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if not row:
        return 0

    return int(
        row[0] or 0
    )


# =========================================================
# НАПОМИНАНИЯ
# =========================================================

def reminders_enabled(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT reminders_enabled
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    if not row:
        return True

    return bool(row[0])


def set_reminders(
    user_id,
    enabled,
):
    touch_user(user_id)

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                reminders_enabled = %s,
                reminder_sent_at = NULL,
                last_seen = now()
            WHERE user_id = %s
        """, (
            bool(enabled),
            user_id,
        ))


def reminder_candidates():
    cutoff = (
        datetime.now(TZ)
        - timedelta(
            days=REMINDER_AFTER_DAYS
        )
    )

    with db() as conn:
        rows = conn.execute("""
            SELECT user_id
            FROM users
            WHERE reminders_enabled = TRUE
              AND last_seen IS NOT NULL
              AND last_seen < %s
              AND (
                    reminder_sent_at IS NULL
                    OR reminder_sent_at < last_seen
                  )
            ORDER BY last_seen ASC
            LIMIT 100
        """, (cutoff,)).fetchall()

    return [
        int(row[0])
        for row in rows
    ]


def mark_reminder_sent(user_id):
    with db() as conn:
        conn.execute("""
            UPDATE users
            SET reminder_sent_at = now()
            WHERE user_id = %s
        """, (user_id,))


def reminder_worker():
    while True:
        try:
            for user_id in reminder_candidates():
                try:
                    bot.send_message(
                        user_id,
                        (
                            "🔮 Давно не заглядывал в Таро Оракул.\n\n"
                            "Если захочешь, сегодня тебя уже ждёт "
                            "новая бесплатная Карта дня."
                        ),
                        reply_markup=reminder_message_keyboard(),
                    )

                    mark_reminder_sent(
                        user_id
                    )

                    time.sleep(0.15)

                except Exception as exc:
                    print(
                        "Ошибка напоминания "
                        f"{user_id}: {repr(exc)}",
                        flush=True,
                    )

        except Exception as exc:
            print(
                "Ошибка reminder worker:",
                repr(exc),
                flush=True,
            )

        time.sleep(
            REMINDER_CHECK_SECONDS
        )


# =========================================================
# TELEGRAM STARS / INVOICE
# =========================================================

def make_invoice_payload(
    user_id,
    kind,
    topic,
    period,
):
    nonce = uuid4().hex[:12]

    return (
        f"tarot|{user_id}|{kind}|"
        f"{topic}|{period}|{nonce}"
    )


def invoice_details(
    payload,
    expected_user_id=None,
):
    try:
        parts = (
            payload or ""
        ).split("|")

        if len(parts) != 6:
            return None

        prefix = parts[0]
        user_id = int(parts[1])
        kind = parts[2]
        topic = parts[3]
        period = parts[4]
        nonce = parts[5]

        if prefix != "tarot":
            return None

        if not nonce:
            return None

        if (
            expected_user_id is not None
            and user_id != expected_user_id
        ):
            return None

        if not valid_reading_params(
            kind,
            topic,
            period,
        ):
            return None

        return {
            "user_id": user_id,
            "kind": kind,
            "topic": topic,
            "period": period,
            "nonce": nonce,
        }

    except Exception:
        return None


# =========================================================
# КОНЕЦ ЧАСТИ 2/3
# =========================================================
# =========================================================
# ЧАСТЬ 3/3
# =========================================================


# =========================================================
# ОПЛАТА — СОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ
# =========================================================

def get_payment(charge_id):
    with db() as conn:
        return conn.execute("""
            SELECT
                charge_id,
                user_id,
                kind,
                topic,
                period,
                result,
                delivered,
                amount,
                cards_json
            FROM payments
            WHERE charge_id = %s
        """, (charge_id,)).fetchone()


def create_payment_placeholder(
    charge_id,
    user_id,
    kind,
    topic,
    period,
    amount,
    chosen,
):
    indices = card_indices(chosen)

    if len(indices) != 3:
        return False

    with db() as conn:
        row = conn.execute("""
            INSERT INTO payments (
                charge_id,
                user_id,
                kind,
                topic,
                period,
                result,
                delivered,
                amount,
                cards_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                '', FALSE, %s, %s, now()
            )
            ON CONFLICT (charge_id)
            DO NOTHING
            RETURNING charge_id
        """, (
            charge_id,
            user_id,
            kind,
            topic,
            period,
            amount,
            json.dumps(indices),
        )).fetchone()

    return row is not None


def set_payment_cards(
    charge_id,
    chosen,
):
    indices = card_indices(chosen)

    if len(indices) != 3:
        return False

    with db() as conn:
        conn.execute("""
            UPDATE payments
            SET cards_json = %s
            WHERE charge_id = %s
        """, (
            json.dumps(indices),
            charge_id,
        ))

    return True


def save_payment_result(
    charge_id,
    result,
):
    if not result:
        return False

    with db() as conn:
        row = conn.execute("""
            UPDATE payments
            SET result = %s
            WHERE charge_id = %s
              AND COALESCE(result, '') = ''
            RETURNING charge_id
        """, (
            result,
            charge_id,
        )).fetchone()

    return row is not None


def mark_payment_delivered(
    charge_id,
):
    with db() as conn:
        conn.execute("""
            UPDATE payments
            SET delivered = TRUE
            WHERE charge_id = %s
        """, (charge_id,))


def send_saved_payment(
    chat_id,
    payment_row,
):
    if not payment_row:
        return False

    (
        charge_id,
        _user_id,
        kind,
        topic,
        period,
        result,
        delivered,
        _amount,
        cards_json,
    ) = payment_row

    if delivered:
        return True

    if not result or not result.strip():
        return False

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        return False

    chosen = cards_from_json(
        cards_json
    )

    if len(chosen) != 3:
        return False

    success = send_reading_result(
        chat_id,
        kind,
        topic,
        result,
        chosen,
    )

    if success:
        mark_payment_delivered(
            charge_id
        )

    return success


# =========================================================
# ОТПРАВКА СЧЁТА
# =========================================================

def send_paid_invoice(
    chat_id,
    user_id,
    kind,
    topic,
    period,
):
    payload = make_invoice_payload(
        user_id,
        kind,
        topic,
        period,
    )

    try:
        bot.send_invoice(
            chat_id=chat_id,
            title=SPREADS[kind][0],
            description=(
                f"{topic_name(kind, topic)}\n"
                f"{period_name(period)}\n\n"
                "Персональный развлекательный "
                "расклад из трёх карт."
            ),
            invoice_payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                types.LabeledPrice(
                    label="Расклад Таро",
                    amount=PRICE,
                )
            ],
        )

        return True

    except Exception as exc:
        print(
            "Ошибка отправки Stars invoice:",
            repr(exc),
            flush=True,
        )

        bot.send_message(
            chat_id,
            "Не удалось открыть оплату Stars.\n\n"
            "Попробуй ещё раз немного позже.",
            reply_markup=main_keyboard(),
        )

        return False


# =========================================================
# ЗАПУСК ВЫБРАННОГО РАСКЛАДА
# =========================================================

def process_selected_reading(
    chat_id,
    user_id,
    kind,
    topic,
    period,
):
    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Не удалось восстановить параметры расклада.\n\n"
            "Выбери расклад заново.",
            reply_markup=main_keyboard(),
        )
        return

    # Первый расклад «3 карты» бесплатный.
    if kind == "three":
        free_claimed = claim_free(
            user_id,
            "three_used",
        )

        if free_claimed:
            bot.send_message(
                chat_id,
                "✨ Первый расклад «3 карты» бесплатный.\n\n"
                "Готовлю твой расклад…",
            )

            try:
                result, chosen = spread(
                    kind,
                    topic,
                    period,
                    user_id,
                )

                delivered = send_reading_result(
                    chat_id,
                    kind,
                    topic,
                    result,
                    chosen,
                )

                if delivered:
                    clear_pending_reading(
                        user_id
                    )

                    return

                restore_free_three(
                    user_id
                )

                bot.send_message(
                    chat_id,
                    "Не удалось полностью отправить расклад.\n\n"
                    "Бесплатная попытка возвращена.",
                    reply_markup=main_keyboard(),
                )

            except Exception as exc:
                print(
                    "Ошибка бесплатного расклада:",
                    repr(exc),
                    flush=True,
                )

                restore_free_three(
                    user_id
                )

                bot.send_message(
                    chat_id,
                    "Произошла техническая ошибка.\n\n"
                    "Бесплатная попытка не потеряна.",
                    reply_markup=main_keyboard(),
                )

            return

    # Промокредит используется до Stars.
    if claim_promo_credit(
        user_id
    ):
        bot.send_message(
            chat_id,
            "🎁 Использую один бесплатный расклад "
            "по промокоду.\n\n"
            "Готовлю расклад…",
        )

        try:
            result, chosen = spread(
                kind,
                topic,
                period,
                user_id,
            )

            delivered = send_reading_result(
                chat_id,
                kind,
                topic,
                result,
                chosen,
            )

            if delivered:
                clear_pending_reading(
                    user_id
                )

                return

            restore_promo_credit(
                user_id
            )

            bot.send_message(
                chat_id,
                "Не удалось полностью отправить расклад.\n\n"
                "Промокредит возвращён.",
                reply_markup=main_keyboard(),
            )

        except Exception as exc:
            print(
                "Ошибка проморасклада:",
                repr(exc),
                flush=True,
            )

            restore_promo_credit(
                user_id
            )

            bot.send_message(
                chat_id,
                "Произошла техническая ошибка.\n\n"
                "Промокредит возвращён.",
                reply_markup=main_keyboard(),
            )

        return

    send_paid_invoice(
        chat_id,
        user_id,
        kind,
        topic,
        period,
    )


# =========================================================
# УСЛОВИЯ
# =========================================================

def terms_text():
    return (
        "📜 Условия «Таро Оракул»\n\n"
        "Бесплатно: Карта дня и Вопрос дня — "
        "по одному разу в день; первый расклад "
        "«3 карты» — один раз на аккаунт.\n\n"
        f"Платные расклады стоят {PRICE} Stars "
        "за каждый расклад. Результат приходит "
        "после успешной оплаты.\n\n"
        "Расклады являются развлекательной "
        "символической интерпретацией, "
        "а не точным предсказанием или медицинской, "
        "финансовой либо юридической консультацией.\n\n"
        "Если возникла проблема с оплатой "
        "или результатом, напиши /paysupport."
    )


def terms_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Принимаю условия",
            callback_data="terms_accept",
        )
    )

    return keyboard


def terms_accepted(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT terms_accepted
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    return bool(
        row
        and row[0]
    )


def accept_terms(user_id):
    touch_user(user_id)

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                terms_accepted = TRUE,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (user_id,))


# =========================================================
# /START
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def start_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    touch_user(
        user_id
    )

    if not terms_accepted(
        user_id
    ):
        bot.send_message(
            chat_id,
            terms_text(),
            reply_markup=terms_keyboard(),
        )
        return

    bot.send_message(
        chat_id,
        "🔮 Добро пожаловать в Таро Оракул!\n\n"
        "Карта дня и Вопрос дня доступны раз в день.\n"
        "Первый расклад «3 карты» бесплатный.",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "terms_accept"
)
def terms_accept_handler(call):
    answer(call)

    accept_terms(
        call.from_user.id
    )

    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None,
        )
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        "✅ Условия приняты.\n\n"
        "Добро пожаловать в Таро Оракул 🔮",
        reply_markup=main_keyboard(),
    )


# =========================================================
# КАРТА ДНЯ / ВОПРОС ДНЯ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "🔮 Карта дня"
)
def daily_card_handler(message):
    touch_user(
        message.from_user.id
    )

    send_daily_card(
        message.chat.id,
        message.from_user.id,
    )


@bot.message_handler(
    func=lambda message:
        message.text == "❓ Вопрос дня"
)
def daily_question_handler(message):
    touch_user(
        message.from_user.id
    )

    send_daily_question(
        message.chat.id,
        message.from_user.id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reminder_get_card"
)
def reminder_get_card_handler(call):
    answer(call)

    touch_user(
        call.from_user.id
    )

    send_daily_card(
        call.message.chat.id,
        call.from_user.id,
    )


# =========================================================
# МЕНЮ РАСКЛАДОВ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "✨ Сделать расклад"
)
def reading_menu_handler(message):
    touch_user(
        message.from_user.id
    )

    bot.send_message(
        message.chat.id,
        "✨ Выбери расклад:",
        reply_markup=readings_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data in (
            "reading_love",
            "reading_money",
            "reading_three",
        )
)
def reading_kind_handler(call):
    answer(call)

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    touch_user(
        user_id
    )

    kind = call.data.replace(
        "reading_",
        "",
        1,
    )

    set_pending_reading(
        user_id,
        kind=kind,
        topic=None,
        period=None,
    )

    bot.send_message(
        chat_id,
        "🎯 Выбери тему:",
        reply_markup=topics_keyboard(
            kind
        ),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("topic:")
)
def topic_handler(call):
    answer(call)

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        _prefix, kind, topic = (
            call.data.split(
                ":",
                2,
            )
        )

    except ValueError:
        return

    if (
        kind not in SPREADS
        or topic not in TOPICS.get(
            kind,
            {},
        )
    ):
        return

    set_pending_reading(
        user_id,
        kind=kind,
        topic=topic,
        period=None,
    )

    bot.send_message(
        chat_id,
        "⏳ Выбери период:",
        reply_markup=periods_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("period:")
)
def period_handler(call):
    answer(call)

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    period = call.data.split(
        ":",
        1,
    )[1]

    kind, topic, _ = (
        get_pending_reading(
            user_id
        )
    )

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Не удалось восстановить выбранный расклад.\n\n"
            "Попробуй ещё раз.",
            reply_markup=main_keyboard(),
        )
        return

    set_pending_reading(
        user_id,
        kind=kind,
        topic=topic,
        period=period,
    )

    begin_profile(
        chat_id,
        user_id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reading_back_topic"
)
def reading_back_topic_handler(call):
    answer(call)

    user_id = call.from_user.id

    kind, _, _ = (
        get_pending_reading(
            user_id
        )
    )

    if kind not in SPREADS:
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            call.message.chat.id,
            "Начни выбор расклада заново.",
            reply_markup=main_keyboard(),
        )
        return

    set_pending_reading(
        user_id,
        kind=kind,
        topic=None,
        period=None,
    )

    bot.send_message(
        call.message.chat.id,
        "🎯 Выбери тему:",
        reply_markup=topics_keyboard(
            kind
        ),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reading_cancel"
)
def reading_cancel_handler(call):
    answer(call)

    clear_pending_reading(
        call.from_user.id
    )

    bot.send_message(
        call.message.chat.id,
        "Расклад отменён.",
        reply_markup=main_keyboard(),
    )


# =========================================================
# CALLBACK АНКЕТЫ
# =========================================================

@bot.callback_query_handler(
    func=lambda call:
        call.data == "profile_use"
)
def profile_use_handler(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        None,
    )

    continue_after_profile(
        call.message.chat.id,
        call.from_user.id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "profile_change"
)
def profile_change_handler(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        "profile_name",
    )

    bot.send_message(
        call.message.chat.id,
        "👤 Напиши своё имя:",
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "other_use"
)
def other_use_handler(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        None,
    )

    finish_profile_flow(
        call.message.chat.id,
        call.from_user.id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "other_change"
)
def other_change_handler(call):
    answer(call)

    set_form_step(
        call.from_user.id,
        "other_name",
    )

    bot.send_message(
        call.message.chat.id,
        "💕 Напиши имя человека:",
    )


# =========================================================
# НАПОМИНАНИЯ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "🔔 Напоминания"
)
def reminders_handler(message):
    user_id = message.from_user.id

    touch_user(
        user_id
    )

    enabled = reminders_enabled(
        user_id
    )

    if enabled:
        text = (
            "🔔 Напоминания включены.\n\n"
            "Если ты несколько дней не заходишь в бот, "
            "он может ненавязчиво напомнить "
            "о бесплатной Карте дня."
        )

    else:
        text = (
            "🔕 Напоминания отключены.\n\n"
            "Ты можешь включить их снова."
        )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=reminder_settings_keyboard(
            enabled
        ),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reminders_off"
)
def reminders_off_handler(call):
    answer(call)

    set_reminders(
        call.from_user.id,
        False,
    )

    bot.send_message(
        call.message.chat.id,
        "🔕 Напоминания отключены.",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reminders_on"
)
def reminders_on_handler(call):
    answer(call)

    set_reminders(
        call.from_user.id,
        True,
    )

    bot.send_message(
        call.message.chat.id,
        "🔔 Напоминания включены.",
        reply_markup=main_keyboard(),
    )


# =========================================================
# О БОТЕ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "ℹ️ О боте"
)
def about_handler(message):
    touch_user(
        message.from_user.id
    )

    bot.send_message(
        message.chat.id,
        "🔮 Таро Оракул — бот для "
        "развлекательных раскладов Таро.\n\n"
        "Карта дня и Вопрос дня доступны бесплатно "
        "раз в день.\n"
        "Первый расклад «3 карты» — бесплатно.\n"
        f"Платные расклады стоят {PRICE} Stars.\n\n"
        "Расклады являются символической "
        "интерпретацией и не заменяют "
        "профессиональные консультации.\n\n"
        "Поддержка по оплате: /paysupport",
        reply_markup=main_keyboard(),
    )


# =========================================================
# ПРОМОКОД
# =========================================================

@bot.message_handler(
    commands=["promo"]
)
def promo_handler(message):
    user_id = message.from_user.id

    touch_user(
        user_id
    )

    parts = message.text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        bot.send_message(
            message.chat.id,
            "Использование:\n"
            "/promo КОД",
            reply_markup=main_keyboard(),
        )
        return

    status = activate_promo(
        user_id,
        parts[1],
    )

    if status == "activated":
        bot.send_message(
            message.chat.id,
            "🎁 Промокод активирован!\n\n"
            f"Ты получил {PROMO_CREDITS} "
            "бесплатных платных расклада.",
            reply_markup=main_keyboard(),
        )

    elif status == "already":
        bot.send_message(
            message.chat.id,
            "Этот промокод уже был активирован.\n\n"
            f"Осталось бесплатных раскладов: "
            f"{promo_credits(user_id)}",
            reply_markup=main_keyboard(),
        )

    else:
        bot.send_message(
            message.chat.id,
            "Такого промокода нет.",
            reply_markup=main_keyboard(),
        )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

def support_pending(user_id):
    with db() as conn:
        row = conn.execute("""
            SELECT support_pending
            FROM users
            WHERE user_id = %s
        """, (user_id,)).fetchone()

    return bool(
        row
        and row[0]
    )


def save_support_ticket(
    user_id,
    body,
):
    with db() as conn:
        row = conn.execute("""
            INSERT INTO support_tickets (
                user_id,
                body
            )
            VALUES (%s, %s)
            RETURNING id
        """, (
            user_id,
            body,
        )).fetchone()

        conn.execute("""
            UPDATE users
            SET
                support_pending = FALSE,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (user_id,))

    return row[0]


@bot.message_handler(
    commands=["paysupport"]
)
def paysupport_handler(message):
    user_id = message.from_user.id

    touch_user(
        user_id
    )

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET support_pending = TRUE
            WHERE user_id = %s
        """, (user_id,))

    bot.send_message(
        message.chat.id,
        "🛟 Опиши проблему одним сообщением.\n\n"
        "Например: оплата прошла, "
        "но расклад не пришёл.",
    )


@bot.message_handler(
    commands=["reply"]
)
def support_reply_handler(message):
    if (
        not OWNER_ID
        or message.from_user.id != OWNER_ID
    ):
        return

    parts = message.text.split(
        maxsplit=2
    )

    if len(parts) != 3:
        bot.send_message(
            message.chat.id,
            "Формат:\n"
            "/reply ID_ОБРАЩЕНИЯ текст ответа",
        )
        return

    try:
        ticket_id = int(
            parts[1]
        )

    except ValueError:
        bot.send_message(
            message.chat.id,
            "ID обращения должен быть числом.",
        )
        return

    with db() as conn:
        row = conn.execute("""
            SELECT user_id
            FROM support_tickets
            WHERE id = %s
        """, (ticket_id,)).fetchone()

    if not row:
        bot.send_message(
            message.chat.id,
            "Обращение не найдено.",
        )
        return

    success = send_long_message(
        row[0],
        "🛟 Ответ поддержки\n\n"
        + parts[2].strip(),
        reply_markup=main_keyboard(),
    )

    bot.send_message(
        message.chat.id,
        (
            "✅ Ответ отправлен."
            if success
            else "❌ Не удалось отправить ответ."
        ),
    )


# =========================================================
# ТЕСТ РАСКЛАДА ВЛАДЕЛЬЦА
# =========================================================

@bot.message_handler(
    commands=["testreading"]
)
def test_reading_handler(message):
    if (
        not OWNER_ID
        or message.from_user.id != OWNER_ID
    ):
        return

    parts = message.text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        bot.send_message(
            message.chat.id,
            "Использование:\n"
            "/testreading love\n"
            "/testreading money\n"
            "/testreading three",
        )
        return

    kind = parts[1].strip().lower()

    if kind not in SPREADS:
        bot.send_message(
            message.chat.id,
            "Доступно: love, money, three",
        )
        return

    topic = next(
        iter(TOPICS[kind])
    )

    period = "near"

    bot.send_message(
        message.chat.id,
        "🧪 Тестовый расклад. "
        "Stars не списываются, "
        "бесплатная попытка не расходуется.",
    )

    try:
        result, chosen = spread(
            kind,
            topic,
            period,
            message.from_user.id,
        )

        success = send_reading_result(
            message.chat.id,
            kind,
            topic,
            result,
            chosen,
        )

        print(
            "Тестовый расклад отправлен:",
            success,
            flush=True,
        )

        if not success:
            bot.send_message(
                message.chat.id,
                "⚠️ Расклад отправился не полностью.",
            )

    except Exception as exc:
        print(
            "Ошибка /testreading:",
            repr(exc),
            flush=True,
        )

        bot.send_message(
            message.chat.id,
            "❌ Не удалось выполнить тестовый расклад.",
        )


# =========================================================
# PRE-CHECKOUT
# =========================================================

@bot.pre_checkout_query_handler(
    func=lambda query: True
)
def pre_checkout_handler(query):
    try:
        details = invoice_details(
            query.invoice_payload,
            query.from_user.id,
        )

        valid = (
            details is not None
            and query.currency == "XTR"
            and query.total_amount == PRICE
        )

        if valid:
            bot.answer_pre_checkout_query(
                query.id,
                ok=True,
            )

        else:
            bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=(
                    "Счёт больше недействителен. "
                    "Создай расклад заново."
                ),
            )

    except Exception as exc:
        print(
            "Ошибка pre_checkout:",
            repr(exc),
            flush=True,
        )

        try:
            bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=(
                    "Не удалось проверить платёж. "
                    "Попробуй ещё раз."
                ),
            )
        except Exception:
            pass


# =========================================================
# УСПЕШНАЯ ОПЛАТА
# =========================================================

@bot.message_handler(
    content_types=["successful_payment"]
)
def successful_payment_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    touch_user(
        user_id
    )

    payment = message.successful_payment

    if not payment:
        return

    if (
        payment.currency != "XTR"
        or payment.total_amount != PRICE
    ):
        print(
            "Некорректная сумма successful_payment",
            flush=True,
        )

        bot.send_message(
            chat_id,
            "Оплата получена, но данные платежа "
            "требуют проверки.\n\n"
            "Напиши /paysupport. "
            "Повторно платить не нужно.",
            reply_markup=main_keyboard(),
        )
        return

    details = invoice_details(
        payment.invoice_payload,
        user_id,
    )

    if not details:
        bot.send_message(
            chat_id,
            "Оплата получена, но параметры расклада "
            "не удалось восстановить.\n\n"
            "Напиши /paysupport. "
            "Повторно платить не нужно.",
            reply_markup=main_keyboard(),
        )
        return

    charge_id = (
        payment.telegram_payment_charge_id
    )

    if not charge_id:
        bot.send_message(
            chat_id,
            "Оплата подтверждена Telegram, "
            "но идентификатор платежа не получен.\n\n"
            "Напиши /paysupport. "
            "Повторно платить не нужно.",
            reply_markup=main_keyboard(),
        )
        return

    kind = details["kind"]
    topic = details["topic"]
    period = details["period"]

    existing = get_payment(
        charge_id
    )

    if existing:
        if existing[1] != user_id:
            print(
                "Несовпадение user_id платежа:",
                charge_id,
                flush=True,
            )
            return

        if existing[6]:
            return

        stored_kind = existing[2]
        stored_topic = existing[3]
        stored_period = existing[4]
        stored_amount = existing[7]

        if (
            stored_kind != kind
            or stored_topic != topic
            or stored_period != period
            or (
                stored_amount is not None
                and stored_amount != PRICE
            )
        ):
            bot.send_message(
                chat_id,
                "Оплата сохранена, но данные платежа "
                "требуют проверки.\n\n"
                "Напиши /paysupport. "
                "Повторно платить не нужно.",
                reply_markup=main_keyboard(),
            )
            return

    else:
        chosen = random.sample(
            CARDS,
            3,
        )

        created = create_payment_placeholder(
            charge_id,
            user_id,
            kind,
            topic,
            period,
            payment.total_amount,
            chosen,
        )

        existing = get_payment(
            charge_id
        )

        if not created and not existing:
            bot.send_message(
                chat_id,
                "Оплата прошла, но расклад временно "
                "не удалось сохранить.\n\n"
                "Напиши /paysupport. "
                "Повторно платить не нужно.",
                reply_markup=main_keyboard(),
            )
            return

    if existing[6]:
        return

    chosen = cards_from_json(
        existing[8]
    )

    if len(chosen) != 3:
        chosen = random.sample(
            CARDS,
            3,
        )

        if not set_payment_cards(
            charge_id,
            chosen,
        ):
            bot.send_message(
                chat_id,
                "Оплата сохранена, но расклад "
                "требует восстановления.\n\n"
                "Напиши /paysupport. "
                "Повторно платить не нужно.",
                reply_markup=main_keyboard(),
            )
            return

        existing = get_payment(
            charge_id
        )

    result = (
        existing[5] or ""
    ).strip()

    if not result:
        bot.send_message(
            chat_id,
            "⭐ Оплата получена. "
            "Готовлю твой расклад…",
        )

        try:
            result, _ = spread(
                kind,
                topic,
                period,
                user_id,
                chosen=chosen,
            )

            save_payment_result(
                charge_id,
                result,
            )

        except Exception as exc:
            print(
                "Ошибка генерации оплаченного расклада:",
                repr(exc),
                flush=True,
            )

            bot.send_message(
                chat_id,
                "Оплата сохранена, но сейчас не удалось "
                "подготовить расклад.\n\n"
                "Напиши /paysupport. "
                "Повторно платить не нужно.",
                reply_markup=main_keyboard(),
            )
            return

        existing = get_payment(
            charge_id
        )

    delivered = send_saved_payment(
        chat_id,
        existing,
    )

    if delivered:
        clear_pending_reading(
            user_id
        )

    else:
        bot.send_message(
            chat_id,
            "⭐ Оплата сохранена, но расклад "
            "не удалось полностью доставить.\n\n"
            "Напиши /paysupport. "
            "Повторно платить не нужно.",
            reply_markup=main_keyboard(),
        )


# =========================================================
# ТЕКСТ АНКЕТЫ / ПОДДЕРЖКА
# =========================================================

def clean_person_name(value):
    value = (
        value or ""
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    if not (
        2 <= len(value) <= 40
    ):
        return None

    if not re.fullmatch(
        r"[A-Za-zА-Яа-яЁё"
        r"\-'’ ]+",
        value,
    ):
        return None

    return value


def parse_age(value):
    try:
        age = int(
            (value or "").strip()
        )

    except Exception:
        return None

    if not (
        18 <= age <= 100
    ):
        return None

    return age


@bot.message_handler(
    content_types=["text"]
)
def general_text_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    touch_user(
        user_id
    )

    if support_pending(
        user_id
    ):
        body = (
            message.text or ""
        ).strip()

        if not body:
            bot.send_message(
                chat_id,
                "Напиши описание проблемы текстом.",
            )
            return

        if len(body) > 3000:
            bot.send_message(
                chat_id,
                "Сообщение слишком длинное. "
                "Сократи его до 3000 символов.",
            )
            return

        ticket_id = save_support_ticket(
            user_id,
            body,
        )

        bot.send_message(
            chat_id,
            "✅ Сообщение отправлено в поддержку.\n\n"
            f"Номер обращения: {ticket_id}",
            reply_markup=main_keyboard(),
        )

        if OWNER_ID:
            try:
                send_long_message(
                    OWNER_ID,
                    "🛟 Новое обращение\n\n"
                    f"ID: {ticket_id}\n"
                    f"User ID: {user_id}\n\n"
                    f"{body}\n\n"
                    "Для ответа:\n"
                    f"/reply {ticket_id} текст",
                )
            except Exception:
                pass

        return

    (
        _profile_name,
        _profile_age,
        _other_name,
        _other_age,
        form_step,
    ) = get_profile(
        user_id
    )

    if form_step == "profile_name":
        name = clean_person_name(
            message.text
        )

        if not name:
            bot.send_message(
                chat_id,
                "Напиши только имя — "
                "от 2 до 40 символов.",
            )
            return

        save_profile_name(
            user_id,
            name,
        )

        set_form_step(
            user_id,
            "profile_age",
        )

        bot.send_message(
            chat_id,
            f"Приятно познакомиться, {name} ✨\n\n"
            "Теперь напиши свой возраст числом.",
        )
        return

    if form_step == "profile_age":
        age = parse_age(
            message.text
        )

        if age is None:
            bot.send_message(
                chat_id,
                "Напиши возраст числом от 18 до 100.",
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

        continue_after_profile(
            chat_id,
            user_id,
        )
        return

    if form_step == "other_name":
        name = clean_person_name(
            message.text
        )

        if not name:
            bot.send_message(
                chat_id,
                "Напиши только имя человека.",
            )
            return

        save_other_name(
            user_id,
            name,
        )

        set_form_step(
            user_id,
            "other_age",
        )

        bot.send_message(
            chat_id,
            "Теперь напиши возраст этого человека числом.",
        )
        return

    if form_step == "other_age":
        age = parse_age(
            message.text
        )

        if age is None:
            bot.send_message(
                chat_id,
                "Напиши возраст числом от 18 до 100.",
            )
            return

        save_other_age(
            user_id,
            age,
        )

        set_form_step(
            user_id,
            None,
        )

        finish_profile_flow(
            chat_id,
            user_id,
        )
        return

    if form_step in (
        "profile_confirm",
        "other_confirm",
    ):
        bot.send_message(
            chat_id,
            "Используй кнопки под предыдущим сообщением.",
        )
        return

    bot.send_message(
        chat_id,
        "Выбери действие в меню 👇",
        reply_markup=main_keyboard(),
    )


# =========================================================
# WEBHOOK / ЗАПУСК
# =========================================================

def setup_webhook():
    if not WEBHOOK_BASE_URL:
        print(
            "RENDER_EXTERNAL_URL отсутствует.",
            flush=True,
        )
        return

    webhook_url = (
        WEBHOOK_BASE_URL.rstrip("/")
        + WEBHOOK_PATH
    )

    try:
        bot.remove_webhook()

        time.sleep(0.5)

        result = bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=[
                "message",
                "callback_query",
                "pre_checkout_query",
            ],
        )

        print(
            "Webhook установлен:",
            result,
            flush=True,
        )

    except Exception as exc:
        print(
            "Ошибка установки webhook:",
            repr(exc),
            flush=True,
        )


def start_background_workers():
    threading.Thread(
        target=telegram_update_worker,
        daemon=True,
        name="telegram-update-worker",
    ).start()

    threading.Thread(
        target=reminder_worker,
        daemon=True,
        name="reminder-worker",
    ).start()


# =========================================================
# ИНИЦИАЛИЗАЦИЯ
# =========================================================

init_db()
setup_webhook()
start_background_workers()


if __name__ == "__main__":
    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )


# =========================================================
# КОНЕЦ ЧАСТИ 3/3
# =========================================================
