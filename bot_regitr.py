
import os
import json
import asyncio
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
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", 8000))
WEBAPP_URL = "https://moiseenkoeldar2-del.github.io/shopbot/"
DB_FILE = "registrations.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "login_requests": {}}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("DB save error:", e)

db = load_db()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    nick = db["users"].get(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть терминал", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    if nick:
        text = (
            "🛸 **DRONEPOINT AREX PRO — Бот регистрации**\n\n"
            f"✅ Ваш позывной: `{nick}`\n"
            "ℹ️ Действует правило: *1 регистрация на человека*.\n"
            "♻️ Для сброса лимита отправьте команду `/resetник`"
        )
    else:
        text = (
            "🛸 **DRONEPOINT AREX PRO — Бот регистрации**\n\n"
            "Добро пожаловать! Откройте терминал ниже или отправьте желаемый позывной (от 3 до 16 символов) прямо сюда для регистрации.\n"
            "♻️ Сброс привязки: `/resetник`"
        )
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.message(F.text.lower().startswith("/resetник") | F.text.lower().startswith("/resetnick"))
async def cmd_reset_nick(message: Message):
    user_id = str(message.from_user.id)
    if user_id in db["users"]:
        old_nick = db["users"].pop(user_id)
        db["login_requests"].pop(user_id, None)
        save_db(db)
        await message.answer(
            "♻️ Лимит «1 регистрация на человека» сброшен!\n"
            f"Позывной `{old_nick}` отвязан. Теперь вы можете зарегистрировать новый ник.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("ℹ️ У вас нет активной привязки позывного. Лимит свободен.")

@router.message(F.text & ~F.text.startswith("/"))
async def register_via_chat(message: Message):
    user_id = str(message.from_user.id)
    raw_nick = message.text.strip()

    if user_id in db["users"]:
        existing = db["users"][user_id]
        await message.answer(
            "⛔ Лимит: **1 регистрация на человека**.\n"
            f"За вами уже закреплён позывной `{existing}`.\n"
            "Чтобы сменить его, введите `/resetник`.",
            parse_mode="Markdown"
        )
        return

    if not (3 <= len(raw_nick) <= 16):
        await message.answer("⚠️ Позывной должен содержать от 3 до 16 символов.")
        return

    if any(n.lower() == raw_nick.lower() for n in db["users"].values()):
        await message.answer(f"❌ Позывной `{raw_nick}` уже занят другим оператором.", parse_mode="Markdown")
        return

    db["users"][user_id] = raw_nick
    save_db(db)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Войти в терминал", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"✅ Позывной `{raw_nick}` успешно зарегистрирован за вашим Telegram ID!\n"
        "Теперь вы можете войти в терминал.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("login_yes:"))
async def cb_login_yes(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = str(callback.from_user.id)
    db["login_requests"][user_id] = "approved"
    if user_id not in db["users"]:
        db["users"][user_id] = nickname
    save_db(db)
    await callback.message.edit_text(
        f"✅ Вход в аккаунт `{nickname}` подтверждён!\nВернитесь в терминал WebApp.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход разрешён")

@router.callback_query(F.data.startswith("login_no:"))
async def cb_login_no(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = str(callback.from_user.id)
    db["login_requests"][user_id] = "denied"
    save_db(db)
    await callback.message.edit_text(
        f"❌ Попытка входа в аккаунт `{nickname}` отклонена.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход отклонён", show_alert=True)

dp.include_router(router)

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

async def handle_options(request):
    return web.Response(status=204, headers=cors_headers())

async def handle_health(request):
    return web.json_response({"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT"}, headers=cors_headers())

async def handle_request_login(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id", "")).strip()
        nickname = str(data.get("nickname", "")).strip()
        if not user_id or not nickname:
            return web.json_response({"ok": False, "error": "missing_params"}, status=400, headers=cors_headers())

        bound_nick = db["users"].get(user_id)
        if bound_nick and bound_nick.lower() != nickname.lower():
            return web.json_response(
                {"ok": False, "error": "limit_reached", "bound_nick": bound_nick},
                headers=cors_headers()
            )

        db["login_requests"][user_id] = "pending"
        save_db(db)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"login_yes:{nickname}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"login_no:{nickname}"),
            ]
        ])
        now_str = datetime.now().strftime("%H:%M:%S")
        await bot.send_message(
            chat_id=int(user_id),
            text=(
                "🔐 **Запрос на вход в терминал**\n"
                f"👤 Позывной: `{nickname}`\n"
                f"🕒 Время: `{now_str}`\n\n"
                "Это вы пытаетесь зайти в аккаунт?"
            ),
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return web.json_response({"ok": True, "status": "pending"}, headers=cors_headers())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500, headers=cors_headers())

async def handle_check_login(request):
    user_id = str(request.query.get("user_id", "")).strip()
    status = db["login_requests"].get(user_id, "none")
    bound_nick = db["users"].get(user_id, "")
    return web.json_response({"ok": True, "status": status, "bound_nick": bound_nick}, headers=cors_headers())

async def handle_reset_api(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id", "")).strip()
        if user_id in db["users"]:
            db["users"].pop(user_id, None)
        db["login_requests"].pop(user_id, None)
        save_db(db)
        return web.json_response({"ok": True}, headers=cors_headers())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500, headers=cors_headers())

async def start_web_server():
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", handle_health)
    app.router.add_post("/api/request-login", handle_request_login)
    app.router.add_get("/api/check-login", handle_check_login)
    app.router.add_post("/api/reset", handle_reset_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"HTTP API server started on port {PORT}")

async def main():
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
