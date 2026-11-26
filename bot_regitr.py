import os
import json
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

# Вставьте токен бота @DRONEPOINT_AREX_PRO_REGISTR_BOT
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬТЕ_СЮДА_ТОКЕН_БОТА")
PORT = int(os.getenv("PORT", 8080))
DB_FILE = "registrations.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хранилище статусов подтверждения входа в памяти: {user_id: "pending" | "approved" | "denied"}
login_statuses = {}


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- TELEGRAM ХЕНДЛЕРЫ ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот регистрации **DRONEPOINT AREX PRO**.

"
        "• Через меня приходит подтверждение входа в терминал.
"
        "• Команда `/resetник` — сбросить лимит «1 регистрация на человека».",
        parse_mode="Markdown"
    )


@router.message(F.text.lower().startswith("/resetник"))
async def cmd_reset_nick(message: Message):
    user_id = str(message.from_user.id)
    db = load_db()
    if user_id in db:
        old_nick = db.pop(user_id)
        save_db(db)
        login_statuses.pop(int(user_id), None)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен!
"
            f"Ник `{old_nick}` отвязан. Теперь вы можете зарегистрировать новый ник в терминале.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("ℹ️ У вас нет активного привязанного ника. Лимит свободен.")


@router.callback_query(F.data.startswith("login_yes:"))
async def on_login_yes(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    login_statuses[user_id] = "approved"

    await callback.message.edit_text(
        f"✅ Вход в аккаунт **{nickname}** подтверждён!
"
        f"Вернитесь в терминал — доступ уже открыт.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход подтверждён!")


@router.callback_query(F.data.startswith("login_no:"))
async def on_login_no(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    login_statuses[user_id] = "denied"

    await callback.message.edit_text(
        f"❌ Попытка входа в аккаунт **{nickname}** отклонена.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход отклонён", show_alert=True)


# --- HTTP API ДЛЯ СВЯЗИ С HTML-ТЕРМИНАЛОМ ---

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


async def handle_options(request: web.Request):
    return web.Response(headers=cors_headers())


async def api_check_nick(request: web.Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    nickname = str(data.get("nickname", "")).strip()

    if not nickname:
        return web.json_response({"ok": False, "error": "Введите ник"}, headers=cors_headers())

    db = load_db()
    # Проверяем, занят ли ник другим человеком
    for uid, reg_nick in db.items():
        if reg_nick.lower() == nickname.lower() and uid != user_id:
            return web.json_response({"ok": True, "available": False, "owner": uid}, headers=cors_headers())

    # Проверяем, зарегистрирован ли уже этот user_id
    existing_nick = db.get(user_id)
    return web.json_response(
        {"ok": True, "available": True, "existing_nick": existing_nick},
        headers=cors_headers()
    )


async def api_register(request: web.Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    nickname = str(data.get("nickname", "")).strip()

    if not user_id or not nickname:
        return web.json_response({"ok": False, "error": "Нет user_id или ника"}, headers=cors_headers())

    db = load_db()
    if user_id in db:
        return web.json_response(
            {"ok": False, "error": f"Лимит: 1 регистрация на человека (ваш ник: {db[user_id]})"},
            headers=cors_headers()
        )

    for reg_nick in db.values():
        if reg_nick.lower() == nickname.lower():
            return web.json_response({"ok": False, "error": "Этот ник уже занят"}, headers=cors_headers())

    db[user_id] = nickname
    save_db(db)
    return web.json_response({"ok": True, "nickname": nickname}, headers=cors_headers())


async def api_request_login(request: web.Request):
    data = await request.json()
    user_id = data.get("user_id")
    nickname = str(data.get("nickname", "")).strip()

    if not user_id or not nickname:
        return web.json_response({"ok": False, "error": "Откройте сайт через Telegram бота"}, headers=cors_headers())

    user_id = int(user_id)
    login_statuses[user_id] = "pending"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"login_yes:{nickname}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"login_no:{nickname}")
        ]
    ])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🔐 **Запрос на вход в терминал**
Ник: `{nickname}`

Это вы пытаетесь зайти в аккаунт?",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return web.json_response({"ok": True, "status": "pending"}, headers=cors_headers())
    except Exception as e:
        return web.json_response(
            {"ok": False, "error": "Сначала запустите бота @DRONEPOINT_AREX_PRO_REGISTR_BOT (/start)"},
            headers=cors_headers()
        )


async def api_check_login(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return web.json_response({"status": "none"}, headers=cors_headers())
    status = login_statuses.get(int(user_id), "none")
    return web.json_response({"status": status}, headers=cors_headers())


async def api_reset_nick(request: web.Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    db = load_db()
    if user_id in db:
        db.pop(user_id)
        save_db(db)
    if user_id.isdigit():
        login_statuses.pop(int(user_id), None)
    return web.json_response({"ok": True}, headers=cors_headers())


async def start_services():
    dp.include_router(router)

    app = web.Application()
    app.router.add_route("OPTIONS", "/api/{tail:.*}", handle_options)
    app.router.add_post("/api/check-nick", api_check_nick)
    app.router.add_post("/api/register", api_register)
    app.router.add_post("/api/request-login", api_request_login)
    app.router.add_get("/api/check-login", api_check_login)
    app.router.add_post("/api/reset-nick", api_reset_nick)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"API сервер запущен на порту {PORT}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_services())
