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

        print(
            f"Бесплатный расклад возвращён пользователю {user_id}",
            flush=True,
        )

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

        print(
            f"Промокредит возвращён пользователю {user_id}",
            flush=True,
        )

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

        print(
            f"Дневная попытка {field} возвращена пользователю {user_id}",
            flush=True,
        )

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

        # 6 секунд — уже проверенное время.
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
    return TOPICS.get(
        kind,
        {},
    ).get(
        topic,
        "Общая ситуация",
    )


def period_name(period):
    return PERIODS.get(
        period,
        "Без конкретного периода",
    )


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
                "Что задаёт эмоциональный контекст",
                "Что проявляется сейчас",
                "На что обратить внимание",
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

    return positions.get(
        kind,
        {},
    ).get(
        topic,
        SPREADS[kind][1],
    )


def personalized_focus(kind, topic):
    focuses = {
        "love": {
            "current":
                "Этот расклад помогает посмотреть на текущую динамику отношений: "
                "что формирует ситуацию, что особенно важно сейчас "
                "и на какой аспект стоит обратить внимание.",

            "feelings":
                "Этот расклад посвящён теме чувств человека. "
                "Карты не могут достоверно читать чужие мысли, поэтому "
                "их смысл рассматривается как символический ракурс ситуации.",

            "ex":
                "Этот расклад рассматривает историю с бывшим партнёром: "
                "что из прошлого всё ещё влияет на ситуацию, "
                "что важно сейчас и что может помочь двигаться дальше.",

            "new":
                "Этот расклад посвящён новому знакомству: его возможной динамике "
                "и тому, на что стоит обратить внимание.",

            "future":
                "Этот расклад рассматривает возможное направление отношений. "
                "Это не фиксированное предсказание: дальнейшее развитие "
                "зависит от обстоятельств и действий людей.",
        },

        "money": {
            "work":
                "Этот расклад посвящён работе: текущему положению, "
                "возможностям движения вперёд и важным факторам.",

            "income":
                "Этот расклад рассматривает тему дохода: что влияет на него сейчас, "
                "где может находиться возможность и что требует внимания.",

            "situation":
                "Этот расклад посвящён общей финансовой ситуации: "
                "её текущей динамике, возможному ресурсу и важному фактору.",

            "opportunity":
                "Этот расклад рассматривает новую финансовую или рабочую возможность. "
                "Символический смысл карт стоит сопоставлять с реальными цифрами и рисками.",

            "future":
                "Этот расклад рассматривает возможное направление финансовой ситуации. "
                "Он не обещает гарантированный доход или убыток.",
        },

        "three": {
            "general":
                "Этот расклад рассматривает ситуацию в целом: "
                "какой прошлый контекст на неё влияет, "
                "что важно сейчас и какое направление может сформироваться дальше.",

            "love":
                "Эти три карты рассматриваются через тему личной жизни: "
                "прошлый контекст, настоящее положение и возможное развитие.",

            "money":
                "Эти три карты рассматриваются через тему денег и работы: "
                "предыдущие обстоятельства, текущее положение "
                "и возможное дальнейшее направление.",

            "decision":
                "Этот расклад посвящён важному решению. "
                "Карты не выбирают вместо тебя, а помогают посмотреть "
                "на контекст и возможные последствия.",

            "future":
                "Этот расклад посвящён ближайшему будущему. "
                "Карты показывают символическое направление "
                "при текущих обстоятельствах, а не неизбежный сценарий.",
        },
    }

    return focuses.get(
        kind,
        {},
    ).get(
        topic,
        "Посмотри на карты как на дополнительный символический ракурс ситуации.",
    )


# =========================================================
# ИИ — ОЧИСТКА И ПРОВЕРКА
# =========================================================

def normalize_for_check(text):
    if not isinstance(text, str):
        return ""

    normalized = text.lower().replace(
        "ё",
        "е",
    )

    normalized = re.sub(
        r"[^а-я0-9\s]",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )

    return re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()


def normalize_heading(text):
    if not isinstance(text, str):
        return ""

    value = text.lower().replace(
        "ё",
        "е",
    )

    value = re.sub(
        r"[*_`#>~]",
        "",
        value,
    )

    value = re.sub(
        r"[^а-я0-9\s]",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def allowed_latin_words(user_id):
    """
    Латиница допускается только внутри имени,
    если пользователь сам ввёл имя латиницей.
    """
    allowed = set()

    if not user_id:
        return allowed

    try:
        (
            name,
            _,
            other_name,
            _,
            _,
        ) = get_profile(user_id)

        for value in (
            name,
            other_name,
        ):
            if not value:
                continue

            for word in re.findall(
                r"[A-Za-z]+",
                value,
            ):
                if len(word) >= 2:
                    allowed.add(
                        word.lower()
                    )

    except Exception as exc:
        print(
            "Не удалось получить допустимые "
            "латинские имена:",
            repr(exc),
            flush=True,
        )

    return allowed


def unwanted_english_words(
    text,
    user_id=None,
):
    if not isinstance(text, str):
        return []

    words = re.findall(
        r"\b[A-Za-z][A-Za-z'-]{1,}\b",
        text,
    )

    if not words:
        return []

    allowed = allowed_latin_words(
        user_id
    )

    unwanted = []

    for word in words:
        normalized = word.lower()

        if normalized not in allowed:
            unwanted.append(word)

    return unwanted


def section_present(
    text,
    variants,
):
    """
    Ищем именно отдельный заголовок,
    но допускаем Markdown, эмодзи,
    двоеточие и безопасные варианты названия.
    """
    if isinstance(variants, str):
        variants = (variants,)

    expected = {
        normalize_heading(item)
        for item in variants
    }

    for line in text.splitlines():
        heading = normalize_heading(
            line
        )

        if heading in expected:
            return True

    return False


def title_line_matches(
    line,
    expected_title,
):
    return (
        normalize_heading(line)
        == normalize_heading(expected_title)
    )


def build_ai_prompt(
    kind,
    topic,
    period,
    chosen,
    user_id,
):
    (
        name,
        age,
        other_name,
        other_age,
        _,
    ) = get_profile(user_id)

    positions = reading_positions(
        kind,
        topic,
    )

    cards_text = "\n".join(
        f"{i + 1}. Позиция: {positions[i]}. "
        f"Карта: {chosen[i][0]}"
        for i in range(3)
    )

    profile_text = (
        f"Имя пользователя: {name or 'не указано'}\n"
        f"Возраст пользователя: {age or 'не указан'}\n"
    )

    if (
        needs_other_person(kind, topic)
        and other_name
        and other_age
    ):
        profile_text += (
            f"Имя второго человека: {other_name}\n"
            f"Возраст второго человека: {other_age}\n"
        )

    return f"""
Напиши готовый персонализированный развлекательный расклад Таро
на естественном современном русском языке.

КРИТИЧЕСКИ ВАЖНО:
Верни только готовый текст расклада для пользователя.
Не показывай анализ задания, внутренние рассуждения,
процесс составления ответа или служебные комментарии.
Не пересказывай эти инструкции.

Пиши полностью на русском языке.
Не используй английские слова, англоязычные вставки,
английские термины или случайные слова латиницей.
Если имя пользователя или второго человека изначально написано
латиницей, само это имя можно оставить без изменений.
Весь остальной текст должен быть только на русском языке.

Обращайся к пользователю только на «ты».
Не переходи на «вы».
Не используй неестественные буквальные переводы с английского.
Избегай канцелярита, повторов и фраз вроде
«завершить завершённое».

Первая строка ответа должна быть:
{SPREADS[kind][0]}

ДАННЫЕ:
{profile_text}
Тема: {topic_name(kind, topic)}
Период: {period_name(period)}

Выпавшие карты:
{cards_text}

ТРЕБОВАНИЯ:

1. Напиши полный законченный расклад.
Каждой из трёх карт посвяти отдельный содержательный абзац.

2. После трёх карт обязательно должны быть:
«Как карты связаны»,
«Общий итог»,
«Над чем подумать».

3. Ты знаешь о людях только указанные имя и возраст.
Не придумывай характер, чувства, поступки, прошлое,
работу, намерения или жизненные обстоятельства.

4. Имя и возраст используй только для лёгкой
естественной персонализации.

5. Значение карты описывай как символическую тему,
возможный ракурс или повод задуматься.

6. Не утверждай, что второй человек что-либо чувствует,
думает, скрывает, хочет, планирует или обязательно сделает.

7. Не утверждай неизвестные факты об отношениях.

8. Будущее описывай как возможное направление,
а не как гарантированное событие.

9. Не определяй пол по имени.

10. Каждую карту связывай именно с её позицией.

11. В разделе «Как карты связаны» объясни взаимодействие
именно выпавших трёх карт, а не используй общий шаблон.

12. В разделе «Общий итог» сделай конкретный вывод
из сочетания именно этих трёх карт.

13. Последний вопрос должен быть коротким,
понятным и практичным.

14. Не давай медицинских, юридических
или конкретных инвестиционных рекомендаций.

15. Все три названия выпавших карт обязательно
должны присутствовать в ответе.

16. Желаемый объём — примерно 1200–2400 символов.
Не растягивай текст служебными фразами.

СТРУКТУРА:

{SPREADS[kind][0]}

🎯 Тема: {topic_name(kind, topic)}
⏳ Период: {period_name(period)}

1️⃣ {positions[0]}

{chosen[0][0]}

Интерпретация.

2️⃣ {positions[1]}

{chosen[1][0]}

Интерпретация.

3️⃣ {positions[2]}

{chosen[2][0]}

Интерпретация.

🔗 Как карты связаны

Связь именно этих трёх карт.

🔮 Общий итог

Конкретный общий смысл сочетания.

💭 Над чем подумать

Один конкретный вопрос.

Верни только готовый текст.
Начни сразу с:
{SPREADS[kind][0]}
""".strip()


def clean_ai_response(
    content,
    kind,
):
    if not isinstance(content, str):
        return None

    cleaned = content.strip()

    if not cleaned:
        return None

    # Убираем Markdown-ограждение кода.
    if cleaned.startswith("```"):
        first_newline = cleaned.find(
            "\n"
        )

        if first_newline != -1:
            cleaned = cleaned[
                first_newline + 1:
            ].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    expected_title = SPREADS[kind][0]

    # Ищем последнюю строку, которая является
    # нашим заголовком. Это позволяет принимать
    # **🔮 Расклад...**, # 🔮 Расклад... и т.п.,
    # но не произвольное вступление модели.
    lines = cleaned.splitlines()
    title_index = None

    for index, line in enumerate(lines):
        if title_line_matches(
            line,
            expected_title,
        ):
            title_index = index

    if title_index is not None:
        lines = lines[
            title_index:
        ]

        # Всегда приводим первую строку
        # к нашему точному заголовку.
        lines[0] = expected_title

        cleaned = "\n".join(
            lines
        ).strip()

    else:
        # Запасной вариант для ответа,
        # где точный заголовок присутствует
        # непосредственно в тексте.
        exact_position = cleaned.rfind(
            expected_title
        )

        if exact_position != -1:
            cleaned = cleaned[
                exact_position:
            ].strip()

    # Если после законченного ответа модель
    # внезапно начала печатать служебные рассуждения,
    # отрезаем такой хвост.
    trailing_markers = (
        "\nhere's a thinking process",
        "\nhere is a thinking process",
        "\nthinking process:",
        "\nanalysis:",
        "\nreasoning:",
        "\nlet's analyze",
        "\nlet's craft",
        "\nwe need to",
        "\ninternal reasoning",
        "\nassistant analysis",
        "\nпроцесс рассуждения:",
        "\nанализ запроса:",
        "\nвнутренние рассуждения:",
    )

    lower = cleaned.lower()
    cut_positions = []

    for marker in trailing_markers:
        position = lower.find(
            marker,
            1,
        )

        if position != -1:
            cut_positions.append(
                position
            )

    if cut_positions:
        cleaned = cleaned[
            :min(cut_positions)
        ].strip()

    return cleaned or None


def validate_ai_response(
    content,
    chosen,
    kind,
    user_id=None,
):
    if not isinstance(content, str):
        return False, "empty"

    cleaned = content.strip()

    if not cleaned:
        return False, "empty"

    expected_title = SPREADS[kind][0]

    first_nonempty = next(
        (
            line.strip()
            for line in cleaned.splitlines()
            if line.strip()
        ),
        "",
    )

    if not title_line_matches(
        first_nonempty,
        expected_title,
    ):
        return False, "wrong_start"

    if len(cleaned) < 700:
        return False, "too_short"

    if len(cleaned) > 5200:
        return False, "too_long"

    lower = cleaned.lower()

    bad_phrases = (
        "here's a thinking process",
        "here is a thinking process",
        "thinking process:",
        "analysis:",
        "reasoning:",
        "internal reasoning",
        "assistant analysis",
        "let's analyze",
        "let's craft",
        "we need to",
        "analyze user input",
        "user input:",
        "role:",
        "constraints:",
        "requirements:",
        "safety:",
        "user safety:",
        "safety classification",
        "safety assessment",
        "content safety classification",
        "policy violation",
        "request classification",
        "system prompt",
        "developer message",
        "as an ai",
        "as a language model",
        "языковая модель",
        "процесс рассуждения",
        "внутренние рассуждения",
        "анализ запроса",
        "разберём запрос",
        "инструкции пользователя",
        "я не могу выполнить",
        "я не могу предоставить",
    )

    if any(
        phrase in lower
        for phrase in bad_phrases
    ):
        return False, "service_output"

    unwanted = unwanted_english_words(
        cleaned,
        user_id=user_id,
    )

    if unwanted:
        print(
            "OpenRouter: найдены английские слова:",
            ", ".join(unwanted[:10]),
            flush=True,
        )

        return (
            False,
            "english_text:"
            + ",".join(unwanted[:5]),
        )

    normalized = normalize_for_check(
        cleaned
    )

    for card in chosen:
        card_name = card[0]

        parts = card_name.split(
            " ",
            maxsplit=1,
        )

        plain_name = (
            parts[1]
            if len(parts) == 2
            else card_name
        )

        if normalize_for_check(
            plain_name
        ) not in normalized:
            return (
                False,
                f"missing_card:{plain_name}",
            )

    for marker in (
        "1️⃣",
        "2️⃣",
        "3️⃣",
    ):
        if marker not in cleaned:
            return (
                False,
                f"missing_section:{marker}",
            )

    section_groups = (
        (
            "connection",
            (
                "как карты связаны",
                "как связаны карты",
                "связь карт",
                "взаимосвязь карт",
                "взаимосвязь карт в раскладе",
            ),
        ),
        (
            "summary",
            (
                "общий итог",
                "итог расклада",
                "общий вывод",
                "вывод расклада",
            ),
        ),
        (
            "reflection",
            (
                "над чем подумать",
                "вопрос для размышления",
                "для размышления",
                "вопрос к себе",
            ),
        ),
    )

    for section_key, variants in section_groups:
        if not section_present(
            cleaned,
            variants,
        ):
            return (
                False,
                f"missing_section:{section_key}",
            )

    return True, "ok"


def extract_openrouter_content(content):
    if isinstance(content, str):
        cleaned = content.strip()

        return (
            cleaned
            if cleaned
            else None
        )

    if isinstance(content, list):
        text_parts = []

        for part in content:
            if isinstance(part, str):
                text_parts.append(
                    part
                )

            elif isinstance(part, dict):
                part_text = part.get(
                    "text"
                )

                if isinstance(
                    part_text,
                    str,
                ):
                    text_parts.append(
                        part_text
                    )

        combined = "\n".join(
            part.strip()
            for part in text_parts
            if part.strip()
        ).strip()

        return (
            combined
            if combined
            else None
        )

    return None


def request_openrouter(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization":
                f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type":
                "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты пишешь качественные "
                        "развлекательные расклады Таро "
                        "на естественном русском языке. "
                        "Возвращай только готовый текст "
                        "для пользователя. "
                        "Не показывай анализ, внутренние "
                        "рассуждения, процесс составления "
                        "ответа или служебные комментарии. "
                        "Пиши по-русски без английских слов "
                        "и случайных вставок латиницей. "
                        "Обращайся к пользователю только "
                        "на «ты», не переходи на «вы». "
                        "Ответ должен быть законченным. "
                        "Раскрой все три карты, их связь, "
                        "общий итог и финальный вопрос. "
                        "Не придумывай неизвестные факты "
                        "о пользователе или другом человеке. "
                        "Не утверждай, что знаешь чужие "
                        "мысли, чувства или намерения. "
                        "Не делай гарантированных "
                        "предсказаний. Карты трактуй "
                        "как символические темы "
                        "и возможные ракурсы."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.5,
            "max_tokens": 1400,
        },
        timeout=35,
    )

    response.raise_for_status()

    data = response.json()

    choices = (
        data.get("choices")
        or []
    )

    if not choices:
        print(
            "OpenRouter: choices отсутствует",
            flush=True,
        )
        return None

    message = (
        choices[0].get("message")
        or {}
    )

    # КРИТИЧЕСКИ:
    # пользователю передаём только message.content.
    # reasoning / reasoning_content не используются.
    return extract_openrouter_content(
        message.get("content")
    )


def retry_instruction(reason):
    if reason.startswith(
        "english_text"
    ):
        return (
            "\n\nПОВТОРНАЯ ПРОВЕРКА ЯЗЫКА:\n"
            "Предыдущий вариант содержал английское слово. "
            "Перепиши весь расклад полностью по-русски. "
            "Не используй ни одного английского слова "
            "или англоязычной вставки. "
            "Сохрани все обязательные разделы."
        )

    if reason.startswith(
        "missing_section"
    ):
        return (
            "\n\nПОВТОРНАЯ ПРОВЕРКА СТРУКТУРЫ:\n"
            "В предыдущем варианте отсутствовал обязательный раздел. "
            "Обязательно включи после трёх карт отдельные разделы:\n"
            "🔗 Как карты связаны\n"
            "🔮 Общий итог\n"
            "💭 Над чем подумать"
        )

    if reason == "wrong_start":
        return (
            "\n\nПОВТОРНАЯ ПРОВЕРКА НАЧАЛА:\n"
            "Начни ответ сразу с точного названия расклада, "
            "без вступления, пояснений и Markdown перед ним."
        )

    if reason == "too_short":
        return (
            "\n\nПОВТОРНАЯ ПРОВЕРКА ПОЛНОТЫ:\n"
            "Предыдущий ответ был слишком коротким. "
            "Раскрой содержательно все три карты, "
            "их взаимосвязь, общий итог и вопрос."
        )

    if reason.startswith(
        "missing_card"
    ):
        return (
            "\n\nПОВТОРНАЯ ПРОВЕРКА КАРТ:\n"
            "В предыдущем ответе было пропущено название "
            "одной из выпавших карт. "
            "Обязательно назови и раскрой все три карты."
        )

    return (
        "\n\nПОВТОРНАЯ ПРОВЕРКА:\n"
        "Сформируй ответ заново и строго соблюди "
        "все требования к языку, структуре и содержанию."
    )


def ai_tarot_reading(
    kind,
    topic,
    period,
    chosen,
    user_id,
):
    if not OPENROUTER_API_KEY:
        print(
            "OpenRouter: OPENROUTER_API_KEY отсутствует",
            flush=True,
        )
        return None

    base_prompt = build_ai_prompt(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    extra_instruction = ""

    # Три попытки:
    # 1 — обычная;
    # 2 — исправление конкретной найденной ошибки;
    # 3 — последняя корректирующая попытка.
    #
    # Пустой ответ OpenRouter не считается
    # качественным результатом и также повторяется.
    for attempt in range(3):
        try:
            prompt = (
                base_prompt
                + extra_instruction
            )

            raw_content = request_openrouter(
                prompt
            )

            content = clean_ai_response(
                raw_content,
                kind,
            )

            valid, reason = (
                validate_ai_response(
                    content,
                    chosen,
                    kind,
                    user_id=user_id,
                )
            )

            if valid:
                print(
                    "OpenRouter: качественный ответ, "
                    f"попытка {attempt + 1}, "
                    f"raw={len(raw_content) if raw_content else 0}, "
                    f"clean={len(content)} символов",
                    flush=True,
                )

                return content

            print(
                "OpenRouter: ответ отклонён, "
                f"попытка {attempt + 1}, "
                f"причина: {reason}, "
                f"raw: {len(raw_content) if raw_content else 0}, "
                f"clean: {len(content) if content else 0}",
                flush=True,
            )

            extra_instruction = retry_instruction(
                reason
            )

        except requests.Timeout:
            print(
                "OpenRouter: превышено время ожидания, "
                f"попытка {attempt + 1}",
                flush=True,
            )

            extra_instruction = (
                "\n\nВерни полный законченный расклад "
                "сразу, без служебного текста."
            )

        except requests.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else "unknown"
            )

            print(
                "OpenRouter HTTP ошибка: "
                f"{status_code}, "
                f"попытка {attempt + 1}",
                flush=True,
            )

        except Exception as exc:
            print(
                "OpenRouter ошибка:",
                repr(exc),
                f"попытка {attempt + 1}",
                flush=True,
            )

        if attempt < 2:
            time.sleep(1)

    print(
        "OpenRouter: качественный ответ не получен "
        "после трёх попыток. "
        "Использую встроенный резервный расклад.",
        flush=True,
    )

    return None


# =========================================================
# РАСКЛАД
# =========================================================

def spread(
    kind,
    topic=None,
    period=None,
    user_id=None,
    chosen=None,
):
    if kind not in SPREADS:
        raise ValueError(
            f"Неизвестный тип расклада: {kind}"
        )

    if topic not in TOPICS.get(
        kind,
        {},
    ):
        topic = next(
            iter(TOPICS[kind])
        )

    if period not in PERIODS:
        period = "none"

    positions = reading_positions(
        kind,
        topic,
    )

    if chosen is None:
        chosen = random.sample(
            CARDS,
            3,
        )

    ai_result = ai_tarot_reading(
        kind,
        topic,
        period,
        chosen,
        user_id,
    )

    if ai_result:
        return ai_result, chosen

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

    selected_topic = topic_name(
        kind,
        topic,
    )

    selected_period = period_name(
        period
    )

    profile_lines = []

    if user_id:
        (
            name,
            age,
            other_name,
            other_age,
            _,
        ) = get_profile(
            user_id
        )

        if name and age:
            profile_lines.append(
                f"👤 Для: {name}, {age}"
            )

        if (
            needs_other_person(
                kind,
                topic,
            )
            and other_name
            and other_age
        ):
            profile_lines.append(
                f"💕 Второй человек: "
                f"{other_name}, {other_age}"
            )

    lines = [
        SPREADS[kind][0],
        "━━━━━━━━━━━━━━",
        f"🎯 Тема: {selected_topic}",
        f"⏳ Период: {selected_period}",
    ]

    if profile_lines:
        lines.extend(
            profile_lines
        )

    lines.extend([
        "",
        personalized_focus(
            kind,
            topic,
        ),
        "",
    ])

    for number, position, card in zip(
        NUMBERS,
        positions,
        chosen,
    ):
        lines.append(
            f"{number} {position}\n\n"
            f"{card[0]}\n\n"
            f"{card[meaning_index]}"
        )

    names = [
        card[0]
        for card in chosen
    ]

    lines.append(
        "🔗 Как карты связаны\n\n"
        f"{names[0]}, {names[1]} и {names[2]} "
        "создают последовательность из трёх символических тем. "
        "Первая карта показывает исходный контекст, "
        "вторая помогает посмотреть на то, что важно сейчас, "
        "а третья указывает на аспект, который стоит учитывать дальше. "
        "Полезно сопоставить значения всех трёх карт "
        "с реальными обстоятельствами ситуации."
    )

    lines.append(
        "🔮 Общий итог\n\n"
        f"Сочетание карт {names[0]}, {names[1]} "
        f"и {names[2]} предлагает рассмотреть ситуацию "
        "не как заранее определённый сценарий, "
        "а как несколько связанных между собой тем. "
        "Обрати внимание на то, что уже можно оценить по фактам, "
        "и на действия, которые действительно зависят от тебя."
    )

    lines.append(
        "💭 Над чем подумать\n\n"
        "Какой конкретный шаг сейчас зависит от тебя "
        "и может сделать ситуацию понятнее?"
    )

    return "\n\n".join(
        lines
    ), chosen


def card_indices(chosen):
    indices = []

    for card in chosen:
        try:
            indices.append(
                CARDS.index(card)
            )

        except ValueError:
            return None

    return indices


def cards_from_json(cards_json):
    if not cards_json:
        return None

    try:
        indices = json.loads(
            cards_json
        )

        if (
            not isinstance(indices, list)
            or len(indices) != 3
        ):
            return None

        chosen = []

        for index in indices:
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= len(CARDS)
            ):
                return None

            chosen.append(
                CARDS[index]
            )

        if len(set(indices)) != 3:
            return None

        return chosen

    except Exception as exc:
        print(
            "Ошибка восстановления карт:",
            repr(exc),
            flush=True,
        )
        return None


def send_reading_result(
    chat_id,
    kind,
    topic,
    result,
    chosen,
):
    if (
        kind not in SPREADS
        or topic not in TOPICS.get(
            kind,
            {},
        )
        or not chosen
        or len(chosen) != 3
    ):
        print(
            "Некорректные данные для отправки расклада",
            flush=True,
        )
        return False

    positions = reading_positions(
        kind,
        topic,
    )

    images_sent = send_spread_images(
        chat_id,
        chosen,
        positions,
    )

    if not images_sent:
        print(
            "Не все изображения расклада отправлены",
            flush=True,
        )
        return False

    text_sent = send_long_message(
        chat_id,
        result,
    )

    if not text_sent:
        print(
            "Текст расклада не отправлен",
            flush=True,
        )
        return False

    return True


# =========================================================
# КАРТА / ВОПРОС ДНЯ
# =========================================================

def choose_day_card():
    return random.choice(
        CARDS
    )


def day_card_text(card):
    name, meaning, *_ = card

    return (
        "🔮 Твоя карта дня\n\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "💭 Вопрос дня:\n"
        "Как эта идея может проявиться "
        "в твоём сегодняшнем дне?\n\n"
        "✨ Таро здесь используется как "
        "развлекательная символическая практика, "
        "а не как точное предсказание."
    )


def question_text(card):
    name, meaning, *_ = card

    return (
        "❓ Вопрос дня\n\n"
        "Сформулируй свой вопрос про себя. "
        "Не обязательно писать его боту.\n\n"
        "Твоя карта:\n\n"
        f"{name}\n\n"
        f"{meaning}\n\n"
        "💭 Попробуй посмотреть на свой вопрос "
        "через идею этой карты.\n\n"
        "🔮 Это дополнительный ракурс для размышления, "
        "а не однозначный ответ или предсказание."
    )


def answer(call, text=None):
    try:
        bot.answer_callback_query(
            call.id,
            text=text,
        )
    except Exception:
        pass


# =========================================================
# АНКЕТА — ЛОГИКА
# =========================================================

def begin_profile(
    chat_id,
    user_id,
):
    name, age, _, _, _ = get_profile(
        user_id
    )

    if name and age:
        set_form_step(
            user_id,
            "profile_confirm",
        )

        bot.send_message(
            chat_id,
            "👤 Для персонализации расклада "
            "у меня сохранены данные:\n\n"
            f"Имя: {name}\n"
            f"Возраст: {age}\n\n"
            "Использовать их?",
            reply_markup=profile_keyboard(),
        )
        return

    set_form_step(
        user_id,
        "name",
    )

    bot.send_message(
        chat_id,
        "👤 Перед раскладом немного "
        "персонализируем его.\n\n"
        "Как тебя зовут?\n\n"
        "Напиши только имя.",
    )


def continue_after_main_profile(
    chat_id,
    user_id,
):
    kind, topic, period = get_pending_reading(
        user_id
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
            "Параметры расклада потеряны.\n\n"
            "Начни расклад заново.",
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
        ) = get_profile(
            user_id
        )

        if other_name and other_age:
            set_form_step(
                user_id,
                "other_confirm",
            )

            bot.send_message(
                chat_id,
                "💕 Для этого любовного расклада "
                "у меня сохранены данные второго человека:\n\n"
                f"Имя: {other_name}\n"
                f"Возраст: {other_age}\n\n"
                "Использовать их?",
                reply_markup=other_profile_keyboard(),
            )
            return

        set_form_step(
            user_id,
            "other_name",
        )

        bot.send_message(
            chat_id,
            "💕 Теперь укажи имя человека, "
            "о котором этот расклад.\n\n"
            "Напиши только имя.",
        )
        return

    finish_profile_and_process(
        chat_id,
        user_id,
    )


def finish_profile_and_process(
    chat_id,
    user_id,
):
    set_form_step(
        user_id,
        None,
    )

    kind, topic, period = get_pending_reading(
        user_id
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
            "Параметры расклада потеряны.\n\n"
            "Начни расклад заново.",
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

def activate_promo(
    user_id,
    code,
):
    normalized_code = (
        code.strip().upper()
    )

    if normalized_code != PROMO_CODE:
        return "invalid", 0

    with db() as conn:
        row = conn.execute("""
            INSERT INTO users (
                user_id,
                promo_code,
                promo_credits,
                created_at,
                last_seen
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
            return (
                "activated",
                row[0],
            )

        current = conn.execute("""
            UPDATE users
            SET
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
            RETURNING promo_credits
        """, (
            user_id,
        )).fetchone()

        return (
            "already",
            current[0] if current else 0,
        )


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
        """, (
            user_id,
        )).fetchone()

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
        """, (
            user_id,
        )).fetchone()

    if not row:
        return True

    return bool(
        row[0]
    )


def set_reminders_enabled(
    user_id,
    enabled,
):
    touch_user(
        user_id
    )

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                reminders_enabled = %s,
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            enabled,
            user_id,
        ))


def send_inactivity_reminders():
    cutoff = (
        datetime.now(TZ)
        - timedelta(
            days=REMINDER_AFTER_DAYS
        )
    )

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
            """, (
                cutoff,
            )).fetchall()

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
                """, (
                    user_id,
                    cutoff,
                )).fetchone()

            if not claimed:
                continue

            try:
                bot.send_message(
                    user_id,
                    "🔮 Заглянем в карты?\n\n"
                    "Твоя бесплатная Карта дня "
                    "ждёт тебя ✨",
                    reply_markup=reminder_message_keyboard(),
                )

            except Exception as exc:
                print(
                    "Не удалось отправить напоминание "
                    f"пользователю {user_id}: {repr(exc)}",
                    flush=True,
                )

                # Не отключаем напоминания навсегда
                # из-за одной временной ошибки Telegram.
                # Возвращаем состояние, чтобы система
                # могла попробовать позже.
                try:
                    with db() as conn:
                        conn.execute("""
                            UPDATE users
                            SET reminder_sent_at = NULL
                            WHERE user_id = %s
                              AND reminders_enabled = TRUE
                        """, (
                            user_id,
                        ))
                except Exception as restore_exc:
                    print(
                        "Не удалось восстановить "
                        "напоминание:",
                        repr(restore_exc),
                        flush=True,
                    )

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
        try:
            send_inactivity_reminders()

        except Exception as exc:
            print(
                "Ошибка reminder_worker:",
                repr(exc),
                flush=True,
            )

        time.sleep(
            REMINDER_CHECK_SECONDS
        )


# =========================================================
# INVOICE
# =========================================================

def make_invoice_payload(
    kind,
    topic,
    period,
    user_id,
):
    return (
        f"{kind}:"
        f"{topic}:"
        f"{period}:"
        f"{user_id}:"
        f"{uuid4().hex}"
    )


def invoice_details(
    payload,
    user_id,
):
    if not isinstance(
        payload,
        str,
    ):
        return None

    parts = payload.split(
        ":"
    )

    if len(parts) != 5:
        return None

    (
        kind,
        topic,
        period,
        payload_user_id,
        payment_nonce,
    ) = parts

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        return None

    if payload_user_id != str(
        user_id
    ):
        return None

    if not re.fullmatch(
        r"[0-9a-f]{32}",
        payment_nonce,
    ):
        return None

    return (
        kind,
        topic,
        period,
    )


# =========================================================
# КОНЕЦ ЧАСТИ 2/3
# =========================================================
# =========================================================
# ЧАСТЬ 3/3
# =========================================================


# =========================================================
# ОПЛАТА И СОХРАНЕНИЕ ПЛАТЕЖЕЙ
# =========================================================

def get_payment(charge_id):
    with db() as conn:
        row = conn.execute("""
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
        """, (
            charge_id,
        )).fetchone()

    return row


def save_payment(
    charge_id,
    user_id,
    kind,
    topic,
    period,
    result,
    chosen,
    amount,
):
    indices = card_indices(
        chosen
    )

    if not indices:
        raise ValueError(
            "Не удалось сохранить выпавшие карты"
        )

    cards_json = json.dumps(
        indices
    )

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
                %s, FALSE, %s, %s, now()
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
            result,
            amount,
            cards_json,
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
        """, (
            charge_id,
        ))


def send_saved_payment(
    chat_id,
    charge_id,
):
    row = get_payment(
        charge_id
    )

    if not row:
        return False

    (
        _,
        user_id,
        kind,
        topic,
        period,
        result,
        delivered,
        amount,
        cards_json,
    ) = row

    if delivered:
        return True

    if not valid_reading_params(
        kind,
        topic,
        period,
    ):
        print(
            "Платёж содержит некорректные "
            f"параметры: {charge_id}",
            flush=True,
        )
        return False

    chosen = cards_from_json(
        cards_json
    )

    if not chosen:
        print(
            "Не удалось восстановить карты "
            f"для платежа {charge_id}",
            flush=True,
        )
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


def send_invoice(
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
        bot.send_message(
            chat_id,
            "Не удалось подготовить оплату.\n\n"
            "Начни расклад заново.",
            reply_markup=main_keyboard(),
        )
        return False

    payload = make_invoice_payload(
        kind,
        topic,
        period,
        user_id,
    )

    try:
        bot.send_invoice(
            chat_id=chat_id,
            title=SPREADS[kind][0],
            description=(
                f"{topic_name(kind, topic)}\n"
                f"{period_name(period)}\n\n"
                "Персональный развлекательный "
                "расклад из 3 карт."
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
            "Ошибка отправки счёта:",
            repr(exc),
            flush=True,
        )

        bot.send_message(
            chat_id,
            "Не удалось создать счёт на оплату.\n\n"
            "Попробуй немного позже.",
            reply_markup=main_keyboard(),
        )

        return False


# =========================================================
# ОБРАБОТКА ВЫБРАННОГО РАСКЛАДА
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
            "Не удалось определить параметры расклада.\n\n"
            "Начни заново.",
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
                "🔮 Готовлю твой бесплатный расклад…"
            )

            try:
                result, chosen = spread(
                    kind,
                    topic,
                    period,
                    user_id=user_id,
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

                    bot.send_message(
                        chat_id,
                        "✨ Расклад готов.",
                        reply_markup=main_keyboard(),
                    )

                else:
                    restore_free_three(
                        user_id
                    )

                    bot.send_message(
                        chat_id,
                        "Не удалось полностью отправить расклад.\n\n"
                        "Бесплатная попытка сохранена. "
                        "Попробуй ещё раз.",
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
                    "Не удалось закончить расклад.\n\n"
                    "Бесплатная попытка сохранена. "
                    "Попробуй ещё раз немного позже.",
                    reply_markup=main_keyboard(),
                )

            return

    # Если есть промокредит — используем его
    # вместо оплаты Stars.
    promo_left = claim_promo_credit(
        user_id
    )

    if promo_left is not None:
        bot.send_message(
            chat_id,
            "🎁 Использую один бесплатный "
            "расклад по промокоду.\n\n"
            f"После этого останется: {promo_left}"
        )

        try:
            result, chosen = spread(
                kind,
                topic,
                period,
                user_id=user_id,
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

                bot.send_message(
                    chat_id,
                    "✨ Расклад готов.",
                    reply_markup=main_keyboard(),
                )

            else:
                restore_promo_credit(
                    user_id
                )

                bot.send_message(
                    chat_id,
                    "Не удалось полностью отправить расклад.\n\n"
                    "Промокредит возвращён. "
                    "Попробуй ещё раз.",
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
                "Не удалось закончить расклад.\n\n"
                "Промокредит возвращён. "
                "Попробуй немного позже.",
                reply_markup=main_keyboard(),
            )

        return

    # Остальные случаи — Telegram Stars.
    send_invoice(
        chat_id,
        user_id,
        kind,
        topic,
        period,
    )


# =========================================================
# START / УСЛОВИЯ
# =========================================================

def terms_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Принимаю",
            callback_data="terms_accept",
        )
    )

    return keyboard


def terms_text():
    return (
        "📜 Условия «Таро Оракул»\n\n"
        "🔮 Бот предназначен для развлекательных "
        "символических раскладов Таро.\n\n"
        "Бесплатно доступны Карта дня и Вопрос дня — "
        "по одному разу в день. Первый расклад "
        "«3 карты» доступен бесплатно один раз "
        "для аккаунта.\n\n"
        f"Платные расклады стоят {PRICE} Stars "
        "за один расклад.\n\n"
        "Результаты раскладов не являются точными "
        "предсказаниями и не заменяют медицинскую, "
        "юридическую, финансовую или иную "
        "профессиональную консультацию.\n\n"
        "Если возникла проблема с оплатой "
        "или получением расклада, используй "
        "команду /paysupport."
    )


def user_accepted_terms(
    user_id,
):
    with db() as conn:
        row = conn.execute("""
            SELECT terms_accepted
            FROM users
            WHERE user_id = %s
        """, (
            user_id,
        )).fetchone()

    return bool(
        row and row[0]
    )


def accept_terms(
    user_id,
):
    touch_user(
        user_id
    )

    with db() as conn:
        conn.execute("""
            UPDATE users
            SET
                terms_accepted = TRUE,
                last_seen = now(),
                reminder_sent_at = NULL
            WHERE user_id = %s
        """, (
            user_id,
        ))


@bot.message_handler(
    commands=["start"]
)
def start_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    touch_user(
        user_id
    )

    if not user_accepted_terms(
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
        "Карта дня и Вопрос дня доступны "
        "раз в день.\n"
        "Первый расклад «3 карты» — бесплатно.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=main_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "terms_accept"
)
def terms_accept_handler(call):
    answer(
        call
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    accept_terms(
        user_id
    )

    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=None,
        )
    except Exception:
        pass

    bot.send_message(
        chat_id,
        "✅ Условия приняты.\n\n"
        "Добро пожаловать в Таро Оракул 🔮",
        reply_markup=main_keyboard(),
    )


# =========================================================
# КАРТА ДНЯ
# =========================================================

def send_daily_card(
    chat_id,
    user_id,
):
    claimed = claim_free(
        user_id,
        "daily_card",
    )

    if not claimed:
        bot.send_message(
            chat_id,
            "🔮 Ты уже получил карту дня сегодня. "
            "Возвращайся завтра ✨",
            reply_markup=main_keyboard(),
        )
        return

    card = choose_day_card()

    try:
        sent = send_card_animation(
            chat_id,
            card,
            caption="🔮 Карта дня",
        )

        if not sent:
            restore_daily_claim(
                user_id,
                "daily_card",
            )

            bot.send_message(
                chat_id,
                "Не удалось отправить карту дня.\n\n"
                "Попытка сохранена. Попробуй ещё раз.",
                reply_markup=main_keyboard(),
            )
            return

        text_sent = send_long_message(
            chat_id,
            day_card_text(card),
            reply_markup=main_keyboard(),
        )

        if not text_sent:
            restore_daily_claim(
                user_id,
                "daily_card",
            )

    except Exception as exc:
        print(
            "Ошибка Карты дня:",
            repr(exc),
            flush=True,
        )

        restore_daily_claim(
            user_id,
            "daily_card",
        )

        bot.send_message(
            chat_id,
            "Не удалось получить карту дня.\n\n"
            "Попытка сохранена.",
            reply_markup=main_keyboard(),
        )


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


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reminder_get_card"
)
def reminder_card_handler(call):
    answer(
        call
    )

    touch_user(
        call.from_user.id
    )

    send_daily_card(
        call.message.chat.id,
        call.from_user.id,
    )


# =========================================================
# ВОПРОС ДНЯ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "❓ Вопрос дня"
)
def daily_question_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    touch_user(
        user_id
    )

    claimed = claim_free(
        user_id,
        "daily_question",
    )

    if not claimed:
        bot.send_message(
            chat_id,
            "❓ Ты уже получил Вопрос дня сегодня. "
            "Возвращайся завтра ✨",
            reply_markup=main_keyboard(),
        )
        return

    card = choose_day_card()

    try:
        sent = send_card_animation(
            chat_id,
            card,
            caption="❓ Вопрос дня",
        )

        if not sent:
            restore_daily_claim(
                user_id,
                "daily_question",
            )

            bot.send_message(
                chat_id,
                "Не удалось отправить карту.\n\n"
                "Попытка сохранена. Попробуй ещё раз.",
                reply_markup=main_keyboard(),
            )
            return

        text_sent = send_long_message(
            chat_id,
            question_text(card),
            reply_markup=main_keyboard(),
        )

        if not text_sent:
            restore_daily_claim(
                user_id,
                "daily_question",
            )

    except Exception as exc:
        print(
            "Ошибка Вопроса дня:",
            repr(exc),
            flush=True,
        )

        restore_daily_claim(
            user_id,
            "daily_question",
        )

        bot.send_message(
            chat_id,
            "Не удалось получить Вопрос дня.\n\n"
            "Попытка сохранена.",
            reply_markup=main_keyboard(),
        )


# =========================================================
# МЕНЮ РАСКЛАДОВ
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text == "✨ Сделать расклад"
)
def readings_menu_handler(message):
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
        call.data.startswith("reading_")
        and call.data
        not in (
            "reading_cancel",
            "reading_back_topic",
        )
)
def reading_kind_handler(call):
    answer(
        call
    )

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

    if kind not in SPREADS:
        bot.send_message(
            chat_id,
            "Неизвестный тип расклада.",
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
        chat_id,
        "🎯 Выбери тему расклада:",
        reply_markup=topics_keyboard(
            kind
        ),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("topic:")
)
def reading_topic_handler(call):
    answer(
        call
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    parts = call.data.split(
        ":",
        2,
    )

    if len(parts) != 3:
        return

    _, kind, topic = parts

    if (
        kind not in SPREADS
        or topic not in TOPICS.get(
            kind,
            {},
        )
    ):
        bot.send_message(
            chat_id,
            "Не удалось определить тему.\n\n"
            "Начни расклад заново.",
            reply_markup=main_keyboard(),
        )
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
def reading_period_handler(call):
    answer(
        call
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    period = call.data.split(
        ":",
        1,
    )[1]

    kind, topic, _ = get_pending_reading(
        user_id
    )

    if (
        kind not in SPREADS
        or topic not in TOPICS.get(
            kind,
            {},
        )
        or period not in PERIODS
    ):
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Параметры расклада потеряны.\n\n"
            "Начни заново.",
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
    answer(
        call
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    kind, _, _ = get_pending_reading(
        user_id
    )

    if kind not in SPREADS:
        clear_pending_reading(
            user_id
        )

        bot.send_message(
            chat_id,
            "Начни расклад заново.",
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
        chat_id,
        "🎯 Выбери тему расклада:",
        reply_markup=topics_keyboard(
            kind
        ),
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "reading_cancel"
)
def reading_cancel_handler(call):
    answer(
        call
    )

    clear_pending_reading(
        call.from_user.id
    )

    bot.send_message(
        call.message.chat.id,
        "❌ Расклад отменён.",
        reply_markup=main_keyboard(),
    )


# =========================================================
# АНКЕТА — CALLBACK
# =========================================================

@bot.callback_query_handler(
    func=lambda call:
        call.data == "profile_use"
)
def profile_use_handler(call):
    answer(
        call
    )

    user_id = call.from_user.id

    set_form_step(
        user_id,
        None,
    )

    continue_after_main_profile(
        call.message.chat.id,
        user_id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "profile_change"
)
def profile_change_handler(call):
    answer(
        call
    )

    set_form_step(
        call.from_user.id,
        "name",
    )

    bot.send_message(
        call.message.chat.id,
        "✏️ Напиши своё имя:",
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "other_use"
)
def other_use_handler(call):
    answer(
        call
    )

    user_id = call.from_user.id

    set_form_step(
        user_id,
        None,
    )

    finish_profile_and_process(
        call.message.chat.id,
        user_id,
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "other_change"
)
def other_change_handler(call):
    answer(
        call
    )

    set_form_step(
        call.from_user.id,
        "other_name",
    )

    bot.send_message(
        call.message.chat.id,
        "✏️ Напиши имя человека:",
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

    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "🎁 Чтобы активировать промокод, "
            "отправь его так:\n\n"
            "/promo КОД",
            reply_markup=main_keyboard(),
        )
        return

    status, credits = activate_promo(
        user_id,
        parts[1],
    )

    if status == "invalid":
        bot.send_message(
            message.chat.id,
            "❌ Такой промокод не найден.",
            reply_markup=main_keyboard(),
        )

    elif status == "activated":
        bot.send_message(
            message.chat.id,
            "🎁 Промокод активирован!\n\n"
            f"Тебе доступно бесплатных "
            f"платных раскладов: {credits}",
            reply_markup=main_keyboard(),
        )

    else:
        bot.send_message(
            message.chat.id,
            "ℹ️ Этот промокод уже был "
            "активирован на твоём аккаунте.\n\n"
            f"Осталось бесплатных раскладов: "
            f"{credits}",
            reply_markup=main_keyboard(),
        )


# =========================================================
# НАПОМИНАНИЯ — НАСТРОЙКИ
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

    enabled = get_reminders_enabled(
        user_id
    )

    if enabled:
        text = (
            "🔔 Напоминания включены.\n\n"
            f"Если ты не заходишь в бот "
            f"{REMINDER_AFTER_DAYS} дня, "
            "бот может ненавязчиво напомнить "
            "о бесплатной Карте дня."
        )

    else:
        text = (
            "🔕 Напоминания отключены.\n\n"
            "Ты можешь включить их снова "
            "в любое время."
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
    answer(
        call
    )

    set_reminders_enabled(
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
    answer(
        call
    )

    set_reminders_enabled(
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
        "развлекательных символических раскладов.\n\n"
        "✨ Карта дня и Вопрос дня — бесплатно "
        "раз в день.\n"
        "🔮 Первый расклад «3 карты» — бесплатно.\n"
        f"⭐ Платные расклады — {PRICE} Stars.\n\n"
        "Расклады не являются точными "
        "предсказаниями и не заменяют "
        "профессиональные консультации.\n\n"
        "Если возникла проблема с оплатой "
        "или результатом — /paysupport",
        reply_markup=main_keyboard(),
    )


# =========================================================
# SUPPORT
# =========================================================

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
        """, (
            user_id,
        ))

    bot.send_message(
        message.chat.id,
        "🛟 Поддержка по оплате\n\n"
        "Опиши проблему одним сообщением.\n\n"
        "Например: оплата прошла, "
        "но расклад не пришёл.",
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
        """, (
            user_id,
        ))

    return row[0]


def support_pending(
    user_id,
):
    with db() as conn:
        row = conn.execute("""
            SELECT support_pending
            FROM users
            WHERE user_id = %s
        """, (
            user_id,
        )).fetchone()

    return bool(
        row and row[0]
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

    if len(parts) < 3:
        bot.send_message(
            message.chat.id,
            "Формат:\n"
            "/reply ID_ОБРАЩЕНИЯ текст ответа"
        )
        return

    try:
        ticket_id = int(
            parts[1]
        )
    except ValueError:
        bot.send_message(
            message.chat.id,
            "ID обращения должен быть числом."
        )
        return

    reply_text = parts[2].strip()

    if not reply_text:
        bot.send_message(
            message.chat.id,
            "Текст ответа пуст."
        )
        return

    with db() as conn:
        row = conn.execute("""
            SELECT user_id
            FROM support_tickets
            WHERE id = %s
        """, (
            ticket_id,
        )).fetchone()

    if not row:
        bot.send_message(
            message.chat.id,
            "Обращение не найдено."
        )
        return

    target_user_id = row[0]

    try:
        delivered = send_long_message(
            target_user_id,
            "🛟 Ответ поддержки\n\n"
            + reply_text,
            reply_markup=main_keyboard(),
        )

        if delivered:
            bot.send_message(
                message.chat.id,
                "✅ Ответ отправлен."
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Не удалось отправить ответ."
            )

    except Exception as exc:
        print(
            "Ошибка ответа поддержки:",
            repr(exc),
            flush=True,
        )

        bot.send_message(
            message.chat.id,
            "❌ Не удалось отправить ответ."
        )


# =========================================================
# ТЕСТОВЫЕ РАСКЛАДЫ ВЛАДЕЛЬЦА
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

    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "Использование:\n"
            "/testreading love\n"
            "/testreading money\n"
            "/testreading three"
        )
        return

    kind = parts[1].strip().lower()

    if kind not in SPREADS:
        bot.send_message(
            message.chat.id,
            "Доступно: love, money, three"
        )
        return

    topic = next(
        iter(TOPICS[kind])
    )

    period = "near"

    bot.send_message(
        message.chat.id,
        "🧪 Тестовый расклад.\n"
        "Stars не списываются, "
        "бесплатная попытка не расходуется."
    )

    try:
        result, chosen = spread(
            kind,
            topic,
            period,
            user_id=message.from_user.id,
        )

        success = send_reading_result(
            message.chat.id,
            kind,
            topic,
            result,
            chosen,
        )

        print(
            f"Тестовый расклад отправлен: {success}",
            flush=True,
        )

        if not success:
            bot.send_message(
                message.chat.id,
                "⚠️ Тестовый расклад "
                "отправился не полностью."
            )

    except Exception as exc:
        print(
            "Ошибка /testreading:",
            repr(exc),
            flush=True,
        )

        bot.send_message(
            message.chat.id,
            "❌ Ошибка тестового расклада.\n\n"
            "Посмотри логи Render."
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

        if not details:
            bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=(
                    "Этот счёт больше недействителен. "
                    "Создай расклад заново."
                ),
            )
            return

        if (
            query.currency != "XTR"
            or query.total_amount != PRICE
        ):
            bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=(
                    "Сумма платежа не совпадает. "
                    "Создай счёт заново."
                ),
            )
            return

        bot.answer_pre_checkout_query(
            query.id,
            ok=True,
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

    payment = message.successful_payment

    if not payment:
        return

    charge_id = (
        payment.telegram_payment_charge_id
    )

    payload = payment.invoice_payload

    details = invoice_details(
        payload,
        user_id,
    )

    if not details:
        print(
            "Получена оплата с некорректным payload:",
            payload,
            flush=True,
        )

        bot.send_message(
            chat_id,
            "⭐ Оплата получена, но параметры "
            "расклада не удалось восстановить.\n\n"
            "Напиши /paysupport — платёж "
            "можно проверить по данным Telegram.",
            reply_markup=main_keyboard(),
        )
        return

    kind, topic, period = details

    existing = get_payment(
        charge_id
    )

    # Telegram может повторно доставить update.
    # Если платёж уже сохранён, ничего заново
    # не генерируем и не выбираем новые карты.
    if existing:
        if existing[1] != user_id:
            print(
                "Несовпадение user_id "
                f"для charge_id {charge_id}",
                flush=True,
            )
            return

        if existing[6]:
            print(
                "Повторный successful_payment "
                f"для уже доставленного {charge_id}",
                flush=True,
            )
            return

        delivered = send_saved_payment(
            chat_id,
            charge_id,
        )

        if delivered:
            clear_pending_reading(
                user_id
            )

            bot.send_message(
                chat_id,
                "✨ Оплаченный расклад доставлен.",
                reply_markup=main_keyboard(),
            )

        else:
            bot.send_message(
                chat_id,
                "⭐ Оплата сохранена, но расклад "
                "не удалось полностью доставить.\n\n"
                "Напиши /paysupport — повторно "
                "платить не нужно.",
                reply_markup=main_keyboard(),
            )

        return

    bot.send_message(
        chat_id,
        "⭐ Оплата получена.\n\n"
        "Готовлю твой расклад…"
    )

    try:
        # Карты выбираются один раз.
        # Именно эти карты затем сохраняются
        # вместе с результатом платежа.
        chosen = random.sample(
            CARDS,
            3,
        )

        result, chosen = spread(
            kind,
            topic,
            period,
            user_id=user_id,
            chosen=chosen,
        )

        created = save_payment(
            charge_id=charge_id,
            user_id=user_id,
            kind=kind,
            topic=topic,
            period=period,
            result=result,
            chosen=chosen,
            amount=payment.total_amount,
        )

        # Если между проверкой и INSERT
        # запись уже появилась, используем
        # сохранённую запись, а не генерируем
        # что-либо повторно.
        if not created:
            existing = get_payment(
                charge_id
            )

            if (
                existing
                and existing[1] == user_id
                and not existing[6]
            ):
                delivered = send_saved_payment(
                    chat_id,
                    charge_id,
                )

                if delivered:
                    clear_pending_reading(
                        user_id
                    )

                    bot.send_message(
                        chat_id,
                        "✨ Оплаченный расклад доставлен.",
                        reply_markup=main_keyboard(),
                    )

            return

        delivered = send_saved_payment(
            chat_id,
            charge_id,
        )

        if delivered:
            clear_pending_reading(
                user_id
            )

            bot.send_message(
                chat_id,
                "✨ Спасибо! Расклад готов.",
                reply_markup=main_keyboard(),
            )

        else:
            bot.send_message(
                chat_id,
                "⭐ Оплата сохранена, но расклад "
                "не удалось полностью доставить.\n\n"
                "Напиши /paysupport — повторно "
                "платить не нужно.",
                reply_markup=main_keyboard(),
            )

    except Exception as exc:
        print(
            "Ошибка после successful_payment:",
            repr(exc),
            flush=True,
        )

        # ВАЖНО:
        # здесь не предлагаем платить повторно,
        # потому что Telegram уже подтвердил оплату.
        bot.send_message(
            chat_id,
            "⭐ Оплата прошла, но при подготовке "
            "расклада произошла техническая ошибка.\n\n"
            "Не оплачивай расклад повторно. "
            "Напиши /paysupport.",
            reply_markup=main_keyboard(),
        )


# =========================================================
# ТЕКСТОВЫЕ СООБЩЕНИЯ:
# АНКЕТА + SUPPORT + НЕИЗВЕСТНЫЙ ВВОД
# =========================================================

def clean_person_name(value):
    if not isinstance(
        value,
        str,
    ):
        return None

    value = re.sub(
        r"\s+",
        " ",
        value.strip(),
    )

    if (
        len(value) < 2
        or len(value) > 40
    ):
        return None

    # Разрешаем русские и латинские буквы,
    # пробел, дефис и апостроф.
    if not re.fullmatch(
        r"[A-Za-zА-Яа-яЁё"
        r"\-'’ ]+",
        value,
    ):
        return None

    # Имя должно содержать хотя бы две буквы.
    letters = re.findall(
        r"[A-Za-zА-Яа-яЁё]",
        value,
    )

    if len(letters) < 2:
        return None

    return value


def parse_age(value):
    try:
        age = int(
            value.strip()
        )
    except (
        ValueError,
        TypeError,
        AttributeError,
    ):
        return None

    if age < 18 or age > 100:
        return None

    return age


@bot.message_handler(
    content_types=["text"]
)
def general_text_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Команды, которые не были обработаны
    # выше, не должны попадать в анкету.
    if (
        isinstance(message.text, str)
        and message.text.startswith("/")
    ):
        return

    touch_user(
        user_id
    )

    # -----------------------------
    # SUPPORT
    # -----------------------------

    if support_pending(
        user_id
    ):
        body = (
            message.text or ""
        ).strip()

        if not body:
            bot.send_message(
                chat_id,
                "Напиши описание проблемы текстом."
            )
            return

        if len(body) > 3000:
            bot.send_message(
                chat_id,
                "Сообщение слишком длинное.\n\n"
                "Пожалуйста, сократи его "
                "до 3000 символов."
            )
            return

        try:
            ticket_id = save_support_ticket(
                user_id,
                body,
            )

            bot.send_message(
                chat_id,
                "✅ Сообщение отправлено "
                "в поддержку.\n\n"
                f"Номер обращения: {ticket_id}",
                reply_markup=main_keyboard(),
            )

            if OWNER_ID:
                try:
                    send_long_message(
                        OWNER_ID,
                        "🛟 Новое обращение "
                        "в поддержку\n\n"
                        f"ID обращения: {ticket_id}\n"
                        f"User ID: {user_id}\n\n"
                        f"{body}\n\n"
                        "Ответить:\n"
                        f"/reply {ticket_id} текст",
                    )
                except Exception as exc:
                    print(
                        "Не удалось уведомить владельца:",
                        repr(exc),
                        flush=True,
                    )

        except Exception as exc:
            print(
                "Ошибка сохранения поддержки:",
                repr(exc),
                flush=True,
            )

            bot.send_message(
                chat_id,
                "Не удалось отправить сообщение "
                "в поддержку.\n\n"
                "Попробуй ещё раз немного позже.",
                reply_markup=main_keyboard(),
            )

        return

    # -----------------------------
    # АНКЕТА
    # -----------------------------

    (
        _,
        _,
        _,
        _,
        form_step,
    ) = get_profile(
        user_id
    )

    if form_step == "name":
        name = clean_person_name(
            message.text
        )

        if not name:
            bot.send_message(
                chat_id,
                "Напиши только имя.\n\n"
                "Можно использовать буквы, "
                "пробел или дефис."
            )
            return

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
            "Сколько тебе лет?\n"
            "Напиши возраст числом.",
        )
        return

    if form_step == "age":
        age = parse_age(
            message.text
        )

        if age is None:
            bot.send_message(
                chat_id,
                "Напиши возраст числом "
                "от 18 до 100."
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

        continue_after_main_profile(
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
                "Напиши только имя человека.\n\n"
                "Можно использовать буквы, "
                "пробел или дефис."
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
            "Сколько этому человеку лет?\n"
            "Напиши возраст числом.",
        )
        return

    if form_step == "other_age":
        age = parse_age(
            message.text
        )

        if age is None:
            bot.send_message(
                chat_id,
                "Напиши возраст числом "
                "от 18 до 100."
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

        finish_profile_and_process(
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
            "Используй кнопки под предыдущим "
            "сообщением или нажми «Отменить»."
        )
        return

    # -----------------------------
    # ПРОЧИЙ ТЕКСТ
    # -----------------------------

    bot.send_message(
        chat_id,
        "Выбери действие в меню 👇",
        reply_markup=main_keyboard(),
    )


# =========================================================
# ЗАПУСК
# =========================================================

def setup_webhook():
    if not WEBHOOK_BASE_URL:
        print(
            "RENDER_EXTERNAL_URL отсутствует. "
            "Webhook не установлен.",
            flush=True,
        )
        return

    webhook_url = (
        WEBHOOK_BASE_URL.rstrip("/")
        + WEBHOOK_PATH
    )

    try:
        bot.remove_webhook()

        time.sleep(
            0.5
        )

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
            f"Webhook установлен: {result}",
            flush=True,
        )

    except Exception as exc:
        print(
            "Ошибка установки webhook:",
            repr(exc),
            flush=True,
        )


def start_background_workers():
    update_thread = threading.Thread(
        target=telegram_update_worker,
        daemon=True,
        name="telegram-update-worker",
    )

    update_thread.start()

    reminder_thread = threading.Thread(
        target=reminder_worker,
        daemon=True,
        name="reminder-worker",
    )

    reminder_thread.start()


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
