import asyncio
import json
import os
import logging
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://moiseenkoeldar2-del.github.io/shopbot/")
DB_FILE = "registrations.json"

if not BOT_TOKEN:
    logging.warning("BOT_TOKEN не задан в переменных окружения!")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()
router = Router()

# Загрузка и сохранение базы регистраций
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "nicks": {}}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_db()

# Статусы запросов на вход (по нику в нижнем регистре и по user_id)
login_status_by_nick = {}
login_status_by_id = {}


def get_webapp_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть ", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    if uid in db["users"]:
        nick = db["users"][uid]
        await message.answer(
            f"🛸 **DRONEPOINT AREX PRO — регистрации**\n\n"
            f"Ваш закреплённый позывной: `{nick}`\n"
            f"Правило: *1 регистрация на человека*.\n\n"
            f"Нажмите кнопку ниже, чтобы открыть терминал, или отправьте `/resetник`, если нужно сбросить привязку.",
            reply_markup=get_webapp_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "🛸 **Добро пожаловать в DRONEPOINT AREX PRO!**\n\n"
            "Для доступа к терминалу необходимо зарегистрировать уникальный позывной (*1 регистрация на человека*).\n\n"
            "✍️ **Напишите ваш желаемый ник прямо сюда в чат** (от 3 до 20 символов, буквы, цифры или `_`):",
            parse_mode="Markdown"
        )


@router.message(F.text.lower().startswith("/resetник") | F.text.lower().startswith("/resetnick"))
async def cmd_reset_nick(message: Message):
    uid = str(message.from_user.id)
    if uid in db["users"]:
        old_nick = db["users"].pop(uid)
        db["nicks"].pop(old_nick.lower(), None)
        login_status_by_nick.pop(old_nick.lower(), None)
        login_status_by_id.pop(uid, None)
        save_db(db)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен! Позывной `{old_nick}` отвязан.\n\n"
            f"✍️ Напишите новый желаемый ник в чат для повторной регистрации:",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "ℹ️ У вас нет активной привязки позывного. Лимит свободен.\n"
            "✍️ Напишите желаемый ник в чат, чтобы зарегистрироваться:"
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_nick_registration(message: Message):
    uid = str(message.from_user.id)
    raw_nick = message.text.strip()

    if uid in db["users"]:
        current_nick = db["users"][uid]
        await message.answer(
            f"⚠️ За вами уже закреплён позывной `{current_nick}` (действует правило: *1 регистрация на человека*).\n\n"
            f"Используйте его для входа в терминал или отправьте `/resetник` для сброса.",
            reply_markup=get_webapp_keyboard(),
            parse_mode="Markdown"
        )
        return

    if len(raw_nick) < 3 or len(raw_nick) > 20 or " " in raw_nick:
        await message.answer(
            "❌ Некорректный формат позывного. Используйте от 3 до 20 символов без пробелов.\nПопробуйте ещё раз:"
        )
        return

    nick_key = raw_nick.lower()
    if nick_key in db["nicks"] and db["nicks"][nick_key] != uid:
        await message.answer(
            f"⛔ Позывной `{raw_nick}` уже занят другим оператором. Придумайте другой:",
            parse_mode="Markdown"
        )
        return

    db["users"][uid] = raw_nick
    db["nicks"][nick_key] = uid
    save_db(db)

    await message.answer(
        f"✅ **Регистрация завершена!**\n\n"
        f"Ваш позывной: `{raw_nick}`\n"
        f"Telegram ID: `{uid}`\n\n"
        f"1️⃣ Откройте терминал по кнопке ниже.\n"
        f"2️⃣ Введите ваш ник и нажмите **«📨 Войти в аккаунт»**.\n"
        f"3️⃣ Подтвердите вход кнопкой **«✅ Да»** в этом чате.",
        reply_markup=get_webapp_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("auth_yes:"))
async def cb_auth_yes(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    uid = str(callback.from_user.id)
    nick_key = nick.lower()

    login_status_by_nick[nick_key] = "approved"
    login_status_by_id[uid] = "approved"

    await callback.message.edit_text(
        f"✅ **Вход подтверждён!**\n\n"
        f"Позывной: `{nick}`\n"
        f"Доступ в терминал открыт. Возвращайтесь в приложение!",
        parse_mode="Markdown"
    )
    await callback.answer("Вход разрешён!")


@router.callback_query(F.data.startswith("auth_no:"))
async def cb_auth_no(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    uid = str(callback.from_user.id)
    nick_key = nick.lower()

    login_status_by_nick[nick_key] = "denied"
    login_status_by_id[uid] = "denied"

    await callback.message.edit_text(
        f"❌ **Попытка входа отклонена!**\n\n"
        f"Доступ для позывного `{nick}` заблокирован.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход отклонен", show_alert=True)


dp.include_router(router)


# --- HTTP API для связи с GitHub Pages (index.html) ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

async def handle_options(request):
    return web.Response(status=204, headers=CORS_HEADERS)

async def api_health(request):
    return web.json_response(
        {"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT"},
        headers=CORS_HEADERS
    )

async def api_request_login(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400, headers=CORS_HEADERS)

    nickname = str(data.get("nickname", "")).strip()
    req_uid = str(data.get("user_id", "")).strip()

    if not nickname:
        return web.json_response({"ok": False, "error": "Укажите позывной"}, status=400, headers=CORS_HEADERS)

    nick_key = nickname.lower()
    target_uid = db["nicks"].get(nick_key)

    # Если ник не найден в базе по имени, пробуем найти по user_id из Telegram WebApp
    if not target_uid and req_uid in db["users"]:
        saved_nick = db["users"][req_uid]
        if saved_nick.lower() == nick_key:
            target_uid = req_uid

    if not target_uid:
        return web.json_response(
            {
                "ok": False,
                "error": "Позывной не зарегистрирован! Сначала напишите ник боту @DRONEPOINT_AREX_PRO_REGISTR_BOT"
            },
            headers=CORS_HEADERS
        )

    login_status_by_nick[nick_key] = "pending"
    login_status_by_id[str(target_uid)] = "pending"

    now_str = datetime.now().strftime("%H:%M:%S")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"auth_yes:{nickname}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"auth_no:{nickname}")
        ]
    ])

    try:
        if bot:
            await bot.send_message(
                chat_id=int(target_uid),
                text=(
                    f"🔐 **Запрос на вход в аккаунт**\n\n"
                    f"Позывной: `{nickname}`\n"
                    f"Время: `{now_str}`\n\n"
                    f"**Это вы пытаетесь зайти в аккаунт?**"
                ),
                reply_markup=kb,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения в ТГ: {e}")
        return web.json_response(
            {
                "ok": False,
                "error": "Бот не смог отправить сообщение. Откройте @DRONEPOINT_AREX_PRO_REGISTR_BOT и нажмите /start"
            },
            headers=CORS_HEADERS
        )

    return web.json_response({"ok": True, "status": "pending"}, headers=CORS_HEADERS)


async def api_check_login(request):
    nickname = request.query.get("nickname", "").strip().lower()
    req_uid = request.query.get("user_id", "").strip()

    status = "pending"
    if nickname and nickname in login_status_by_nick:
        status = login_status_by_nick[nickname]
    elif req_uid and req_uid in login_status_by_id:
        status = login_status_by_id[req_uid]

    return web.json_response({"ok": True, "status": status}, headers=CORS_HEADERS)


async def api_reset_nick(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    nickname = str(data.get("nickname", "")).strip().lower()
    req_uid = str(data.get("user_id", "")).strip()

    removed = False
    if nickname and nickname in db["nicks"]:
        uid = db["nicks"].pop(nickname)
        db["users"].pop(uid, None)
        login_status_by_nick.pop(nickname, None)
        login_status_by_id.pop(uid, None)
        removed = True

    if req_uid and req_uid in db["users"]:
        old_n = db["users"].pop(req_uid).lower()
        db["nicks"].pop(old_n, None)
        login_status_by_nick.pop(old_n, None)
        login_status_by_id.pop(req_uid, None)
        removed = True

    if removed:
        save_db(db)

    return web.json_response({"ok": True, "reset": True}, headers=CORS_HEADERS)


async def start_background_tasks(app):
    if bot:
        app["bot_task"] = asyncio.create_task(dp.start_polling(bot))

async def cleanup_background_tasks(app):
    if "bot_task" in app:
        app["bot_task"].cancel()
        try:
            await app["bot_task"]
        except asyncio.CancelledError:
            pass

def create_app():
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", api_health)
    app.router.add_post("/api/request-login", api_request_login)
    app.router.add_get("/api/check-login", api_check_login)
    app.router.add_post("/api/reset-nick", api_reset_nick)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    web.run_app(create_app(), host="0.0.0.0", port=port)
