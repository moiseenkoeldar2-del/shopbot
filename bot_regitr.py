
import os
import json
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

# Токен берется из переменных окружения Koyeb (BOT_TOKEN)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬТЕ_ТОКЕН_ЕСЛИ_ЗАПУСКАЕТЕ_ЛОКАЛЬНО")
PORT = int(os.getenv("PORT", 8000))
DB_FILE = "registrations.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хранилище статусов подтверждения входа: {user_id: "pending" | "approved" | "denied"}
login_requests = {}


def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


registered_users = load_db()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    nick = registered_users.get(user_id)
    status_text = f"Ваш закреплённый ник: `{nick}`" if nick else "Ник ещё не зарегистрирован."
    await message.answer(
        f"🛸 **DRONEPOINT AREX PRO — Бот регистрации**

"
        f"{status_text}
"
        f"• Правило: **1 регистрация на человека**.
"
        f"• Чтобы сбросить лимит и отвязать ник, отправьте команду `/resetник`.",
        parse_mode="Markdown"
    )


@router.message(F.text.lower().startswith("/resetник") | F.text.lower().startswith("/resetnick"))
async def cmd_reset_nick(message: Message):
    user_id = str(message.from_user.id)
    if user_id in registered_users:
        old_nick = registered_users.pop(user_id)
        save_db(registered_users)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен!
"
            f"Позывной `{old_nick}` отвязан. Теперь вы можете зарегистрировать новый ник в терминале.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("ℹ️ У вас нет активной привязки ника. Лимит свободен.")


@router.callback_query(F.data.startswith("login_yes:"))
async def cb_login_yes(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = str(callback.from_user.id)

    # Проверяем правило 1 регистрация на человека
    existing_nick = registered_users.get(user_id)
    if existing_nick and existing_nick != nickname:
        login_requests[int(user_id)] = "denied"
        await callback.message.edit_text(
            f"⛔ Отказ: за вашим аккаунтом уже закреплён ник **{existing_nick}** (правило: 1 регистрация на человека).
"
            f"Отправьте `/resetник`, чтобы сбросить привязку.",
            parse_mode="Markdown"
        )
        return await callback.answer("Лимит 1 регистрация на человека", show_alert=True)

    registered_users[user_id] = nickname
    save_db(registered_users)
    login_requests[int(user_id)] = "approved"

    await callback.message.edit_text(
        f"✅ Вход в аккаунт **{nickname}** подтверждён!
Вернитесь в веб-терминал.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход подтверждён")


@router.callback_query(F.data.startswith("login_no:"))
async def cb_login_no(callback: CallbackQuery):
    nickname = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    login_requests[user_id] = "denied"

    await callback.message.edit_text(
        f"❌ Попытка входа в аккаунт **{nickname}** отклонена.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход отклонён", show_alert=True)


dp.include_router(router)


# --- HTTP API для связи с index.html ---
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


async def handle_options(request):
    return web.Response(status=204, headers=cors_headers())


async def handle_health(request):
    return web.Response(text="OK", status=200, headers=cors_headers())


async def handle_request_login(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        nickname = str(data.get("nickname", "")).strip()
        if not user_id or not nickname:
            return web.json_response({"ok": False, "error": "Не указан ID или ник"}, headers=cors_headers())

        existing = registered_users.get(str(user_id))
        if existing and existing != nickname:
            return web.json_response(
                {"ok": False, "error": f"За вами уже закреплён ник {existing}. Отправьте /resetник боту."},
                headers=cors_headers()
            )

        login_requests[user_id] = "pending"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"login_yes:{nickname}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"login_no:{nickname}")
            ]
        ])
        await bot.send_message(
            chat_id=user_id,
            text=f"🔐 **Запрос на вход в терминал DRONEPOINT**
Позывной: `{nickname}`

Это вы пытаетесь зайти в аккаунт?",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return web.json_response({"ok": True}, headers=cors_headers())
    except Exception as e:
        return web.json_response(
            {"ok": False, "error": "Откройте @DRONEPOINT_AREX_PRO_REGISTR_BOT и нажмите /start"},
            headers=cors_headers()
        )


async def handle_check_login(request):
    user_id = int(request.query.get("user_id", 0))
    status = login_requests.get(user_id, "pending")
    return web.json_response({"status": status}, headers=cors_headers())


async def handle_reset_nick(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id", ""))
        if user_id in registered_users:
            registered_users.pop(user_id)
            save_db(registered_users)
        return web.json_response({"ok": True}, headers=cors_headers())
    except Exception:
        return web.json_response({"ok": False}, headers=cors_headers())


async def main():
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", handle_health)
    app.router.add_post("/api/request-login", handle_request_login)
    app.router.add_get("/api/check-login", handle_check_login)
    app.router.add_post("/api/reset-nick", handle_reset_nick)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
