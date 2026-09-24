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


# =========================================================
# WEBHOOK
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

    if not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        abort(403)

    if not request.is_json:
        abort(415)

    update = types.Update.de_json(request.get_data(as_text=True))
    bot.process_new_updates([update])

    return "", 200


# =========================================================
# БАЗА
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
                INSERT INTO users (
                    user_id,
                    three_used
                )
                VALUES (%s, TRUE)

                ON CONFLICT (user_id)
                DO UPDATE SET three_used = TRUE
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
                    {field}
                )
                VALUES (%s, %s)

                ON CONFLICT (user_id)
                DO UPDATE SET {field} = EXCLUDED.{field}
                WHERE users.{field}
                    IS DISTINCT FROM EXCLUDED.{field}

                RETURNING user_id
            """, (
                user_id,
                today,
            )).fetchone()

        return row is not None


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
# РАСКЛАДЫ
# =========================================================

def spread(kind):
    title, positions = SPREADS[kind]

    chosen = random.sample(
        CARDS,
        3,
    )

    meaning_index = {
        "love": 2,
        "money": 3,
        "three": 1,
    }[kind]

    lines = [
        title,
        "━━━━━━━━━━━━━━",
        "Перед тобой три карты. "
        "Посмотри на каждую отдельно, а затем на их общую историю.",
    ]

    for number, position, card in zip(
        NUMBERS,
        positions,
        chosen,
    ):
        name = card[0]
        meaning = card[meaning_index]

        lines.append(
            f"{number} {position}\n\n"
            f"{name}\n\n"
            f"{meaning}"
        )

    names = [
        card[0]
        for card in chosen
    ]

    if kind == "love":
        connection = (
            "🔗 Как карты связаны\n\n"
            f"Связка {names[0]} → {names[1]} → {names[2]} "
            "предлагает посмотреть на отношения как на развивающуюся историю. "
            "Первая карта показывает фон ситуации, вторая — то, что особенно важно "
            "заметить сейчас, а третья — возможное направление развития.\n\n"
            "Главная идея этой комбинации — не пытаться предугадать чувства другого человека, "
            "а обратить внимание на общение, взаимность и реальные поступки."
        )

        conclusion = (
            "🔮 Общий итог\n\n"
            "Этот расклад не определяет судьбу отношений. "
            "Он предлагает посмотреть, какие чувства, ожидания и действия "
            "могут влиять на ситуацию сейчас.\n\n"
            "💭 Над чем подумать\n"
            "Что в этой ситуации ты действительно знаешь по поступкам человека, "
            "а что пока только предполагаешь?"
        )

    elif kind == "money":
        connection = (
            "🔗 Как карты связаны\n\n"
            f"Связка {names[0]} → {names[1]} → {names[2]} "
            "показывает три стороны одной финансовой ситуации: "
            "где ты находишься сейчас, какую возможность можно рассмотреть "
            "и какой фактор особенно важно не упустить.\n\n"
            "Полезно сопоставить символику карт с реальными цифрами, "
            "условиями и доступными ресурсами."
        )

        conclusion = (
            "🔮 Общий итог\n\n"
            "Карты могут подсказать новый ракурс, но финансовое решение "
            "лучше принимать на основе проверяемой информации, бюджета и оценки рисков.\n\n"
            "💭 Над чем подумать\n"
            "Какой один конкретный финансовый шаг ты можешь сделать сейчас, "
            "не подвергая себя неоправданному риску?\n\n"
            "⚠️ Это развлекательная символическая интерпретация, "
            "а не финансовая рекомендация."
        )

    else:
        connection = (
            "🔗 Как карты связаны\n\n"
            f"Связка {names[0]} → {names[1]} → {names[2]} "
            "создаёт последовательность из прошлого, настоящего "
            "и одного из возможных направлений будущего.\n\n"
            "Первая карта предлагает посмотреть на опыт, который уже повлиял на ситуацию. "
            "Вторая показывает тему, заслуживающую внимания сейчас. "
            "Третья не предсказывает неизбежное будущее, а предлагает подумать, "
            "куда ситуация может двигаться при текущих обстоятельствах."
        )

        conclusion = (
            "🔮 Общий итог\n\n"
            "Будущее не зафиксировано заранее. "
            "Твои решения, обстоятельства и действия других людей "
            "могут изменить дальнейшее развитие ситуации.\n\n"
            "💭 Над чем подумать\n"
            "Что из прошлого уже нельзя изменить, "
            "но какой выбор в настоящем всё ещё находится в твоих руках?"
        )

    lines.append(connection)
    lines.append(conclusion)

    return "\n\n".join(lines)


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
    bot.answer_callback_query(
        call.id,
        text=text,
    )


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
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
    bot.send_message(
        message.chat.id,
        f"Твой Telegram ID: {message.from_user.id}",
    )


# =========================================================
# УСЛОВИЯ
# =========================================================

@bot.message_handler(commands=["terms"])
def terms(message):
    bot.send_message(
        message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "Бесплатно:\n"
        "• Карта дня — один раз в день.\n"
        "• Вопрос дня — один раз в день.\n"
        "• Первый расклад «3 карты» — один раз на аккаунт.\n\n"
        "Платно:\n"
        f"• Любовь — {PRICE} Stars.\n"
        f"• Деньги — {PRICE} Stars.\n"
        f"• Последующие «3 карты» — {PRICE} Stars.\n\n"
        "Платный результат отправляется после подтверждения оплаты Telegram.\n\n"
        "Все расклады являются символической развлекательной интерпретацией "
        "и не являются точным предсказанием, медицинской, финансовой "
        "или юридической консультацией.\n\n"
        "Проблема с оплатой или результатом: /paysupport."
    )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

@bot.message_handler(
    commands=["support", "paysupport"]
)
def support(message):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id,
                support_pending
            )
            VALUES (%s, TRUE)

            ON CONFLICT (user_id)
            DO UPDATE SET support_pending = TRUE
        """, (
            message.from_user.id,
        ))

    bot.send_message(
        message.chat.id,
        "🛟 Опиши проблему одним сообщением.\n\n"
        "Не присылай пароль, токен или данные банковской карты.",
    )


@bot.message_handler(commands=["reply"])
def reply_to_ticket(message):
    if message.from_user.id != OWNER_ID:
        return

    parts = message.text.split(
        maxsplit=2
    )

    if (
        len(parts) < 3
        or not parts[1].isdigit()
    ):
        bot.send_message(
            message.chat.id,
            "Формат: /reply НОМЕР_ОБРАЩЕНИЯ ответ",
        )
        return

    ticket_id = int(parts[1])

    with db() as conn:
        row = conn.execute(
            "SELECT user_id "
            "FROM support_tickets "
            "WHERE id = %s",
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
# КАРТА ДНЯ
# =========================================================

@bot.message_handler(
    func=lambda m: m.text == "🔮 Карта дня"
)
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


# =========================================================
# ВОПРОС ДНЯ
# =========================================================

@bot.message_handler(
    func=lambda m: m.text == "❓ Вопрос дня"
)
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

@bot.message_handler(
    func=lambda m: m.text == "✨ Сделать расклад"
)
def reading(message):

    bot.send_message(
        message.chat.id,
        "✨ Выбери расклад:\n\n"
        f"💕 Любовь — подробный расклад из 3 карт "
        f"о чувствах и развитии ситуации · {PRICE} ⭐\n\n"
        f"💰 Деньги — текущая ситуация, возможность "
        f"и важный фактор · {PRICE} ⭐\n\n"
        "🔮 3 карты — прошлое, настоящее "
        "и возможное будущее.\n"
        f"Первый раз бесплатно, затем {PRICE} ⭐.",
        reply_markup=readings_keyboard(),
    )


@bot.message_handler(
    func=lambda m: m.text == "ℹ️ О боте"
)
def about(message):

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
# ОПЛАТА
# =========================================================

def send_invoice(
    chat_id,
    user_id,
    kind,
):
    title = SPREADS[kind][0]

    payload = (
        f"{kind}:"
        f"{user_id}:"
        f"{uuid4().hex}"
    )

    bot.send_invoice(
        chat_id,
        title,
        "Подробный символический расклад Таро из трёх карт.",
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


def offer_payment(
    chat_id,
    user_id,
    kind,
):
    if not OWNER_ID:
        bot.send_message(
            chat_id,
            "Оплата пока настраивается. Попробуй позже.",
        )
        return

    with db() as conn:
        row = conn.execute(
            "SELECT terms_accepted "
            "FROM users "
            "WHERE user_id = %s",
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
            f"⭐ Стоимость расклада — {PRICE} Stars.\n\n"
            "Ты получишь подробную интерпретацию трёх карт, "
            "их взаимосвязь, общий итог и вопрос для размышления.\n\n"
            "После успешной оплаты результат придёт автоматически.",
            reply_markup=keyboard,
        )

        return

    send_invoice(
        chat_id,
        user_id,
        kind,
    )


# =========================================================
# ВЫБОР РАСКЛАДА
# =========================================================

@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("reading_")
)
def reading_callback(call):

    kind = call.data.removeprefix(
        "reading_"
    )

    if kind not in SPREADS:
        answer(
            call,
            "Расклад не найден",
        )
        return

    if kind == "three":

        if claim_free(
            call.from_user.id,
            "three_used",
        ):
            answer(call)

            bot.send_message(
                call.message.chat.id,
                "🎁 Это твой первый расклад «3 карты», "
                "поэтому он бесплатный.",
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
# СОГЛАСИЕ С УСЛОВИЯМИ
# =========================================================

@bot.callback_query_handler(
    func=lambda c:
    c.data == "show_terms"
)
def show_terms(call):

    answer(call)

    bot.send_message(
        call.message.chat.id,
        "📖 Условия Таро Оракул\n\n"
        "Карта дня и Вопрос дня доступны бесплатно раз в день.\n"
        "Первый расклад «3 карты» бесплатный.\n\n"
        f"Платные расклады стоят {PRICE} Stars.\n\n"
        "Все расклады являются развлекательной "
        "символической интерпретацией.\n\n"
        "Проблемы с оплатой: /paysupport."
    )


@bot.callback_query_handler(
    func=lambda c:
    c.data
    and c.data.startswith("agree_")
)
def agree(call):

    kind = call.data.removeprefix(
        "agree_"
    )

    if kind not in SPREADS:
        answer(
            call,
            "Неизвестный расклад",
        )
        return

    with db() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id,
                terms_accepted
            )
            VALUES (%s, TRUE)

            ON CONFLICT (user_id)
            DO UPDATE SET terms_accepted = TRUE
        """, (
            call.from_user.id,
        ))

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

def invoice_details(
    payload,
    user_id,
):
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
                "FROM users "
                "WHERE user_id = %s",
                (
                    query.from_user.id,
                ),
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
                "Не удалось проверить оплату. "
                "Попробуй позже."
            ),
        )


# =========================================================
# УСПЕШНАЯ ОПЛАТА
# =========================================================

@bot.message_handler(
    content_types=[
        "successful_payment"
    ]
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
            "Платёж получен, но результат "
            "требует проверки.\n\n"
            "Напиши /paysupport.",
        )
        return

    charge_id = (
        payment.telegram_payment_charge_id
    )

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
            "SELECT "
            "user_id, result, delivered "
            "FROM payments "
            "WHERE charge_id = %s",
            (charge_id,),
        ).fetchone()

    if not row:
        bot.send_message(
            message.chat.id,
            "Платёж получен, но возникла "
            "ошибка выдачи.\n\n"
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
        "🔮 Твой расклад готов.",
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
# ПРОЧИЕ СООБЩЕНИЯ / SUPPORT
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
            (
                message.from_user.id,
            ),
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
            (
                message.from_user.id,
            ),
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
                f"Пользователь: "
                f"{message.from_user.id}\n\n"
                f"{message.text[:3500]}\n\n"
                f"Ответить:\n"
                f"/reply {ticket} текст",
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

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000,
            )
        ),
    )
