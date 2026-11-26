
import os
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = "https://moiseenkoeldar2-del.github.io/shopbot/"
SELF_URL = "https://shopbot-2-412g.onrender.com"
DATA_FILE = "registrations.json"
APP_VERSION = "3.2"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "nick_to_id": {}, "login_status": {}}

def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

db = load_db()

def is_night_mode() -> bool:
    now = datetime.now(KYIV_TZ)
    return 0 <= now.hour < 7

def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Онлайн"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="♻️ Сбросить ник")],
            [KeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
        ],
        resize_keyboard=True
    )

def update_activity(user_id: int, username: str = ""):
    uid = str(user_id)
    now_ts = datetime.now(KYIV_TZ).timestamp()
    if uid not in db["users"]:
        db["users"][uid] = {
            "nickname": None,
            "username": username,
            "registered_at": None,
            "last_seen": now_ts,
            "logins": 0,
            "version": APP_VERSION
        }
    else:
        db["users"][uid]["last_seen"] = now_ts
        if username:
            db["users"][uid]["username"] = username
    save_db(db)

@router.message(CommandStart())
async def cmd_start(message: Message):
    if is_night_mode():
        await message.answer("🌙 Бот находится в ночном режиме (с 00:00 до 07:00 по Киеву). Возвращайтесь после 07:00!")
        return

    uid = str(message.from_user.id)
    update_activity(message.from_user.id, message.from_user.username or "")
    db["users"][uid]["version"] = APP_VERSION
    save_db(db)

    nick = db["users"][uid].get("nickname")
    if nick:
        await message.answer(
            f"✅ Система обновлена (v{APP_VERSION})!\n"
            f"Ваш закреплённый позывной: <b>{nick}</b>\n\n"
            f"Используйте меню ниже или откройте приложение.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"🛸 Добро пожаловать в <b>DRONEPOINT AREX PRO</b>!\n\n"
            f"Правило: <b>1 регистрация на человека</b>.\n"
            f"✏️ Напишите в чат желаемый позывной (от 3 до 16 символов), чтобы зарегистрироваться:",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )

@router.message(F.text.lower() == "/resetник")
@router.message(F.text == "♻️ Сбросить ник")
async def reset_nick(message: Message):
    if is_night_mode():
        await message.answer("🌙 Ночной режим (00:00 – 07:00). Попробуйте утром!")
        return

    uid = str(message.from_user.id)
    update_activity(message.from_user.id)
    user_data = db["users"].get(uid, {})
    old_nick = user_data.get("nickname")

    if old_nick:
        db["nick_to_id"].pop(old_nick.lower(), None)
        db["login_status"].pop(old_nick.lower(), None)
        db["users"][uid]["nickname"] = None
        save_db(db)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен (позывной <b>{old_nick}</b> отвязан).\n"
            f"✏️ Напишите новый позывной в чат для регистрации:",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer("ℹ️ У вас нет закреплённого позывного. Просто напишите желаемый ник в чат!", reply_markup=main_menu_kb())

@router.message(F.text == "🟢 Онлайн")
async def show_online(message: Message):
    if is_night_mode():
        await message.answer("🌙 Ночной режим (00:00 – 07:00).")
        return

    update_activity(message.from_user.id)
    now_ts = datetime.now(KYIV_TZ).timestamp()
    online_list = []
    offline_list = []
    buttons = []

    for uid, info in db["users"].items():
        nick = info.get("nickname")
        if not nick:
            continue
        diff = int(now_ts - info.get("last_seen", 0))
        if diff <= 300:
            online_list.append(f"🟢 <b>{nick}</b> — в сети")
        else:
            mins = max(1, diff // 60)
            ago = f"{mins} мин. назад" if mins < 60 else f"{mins // 60} ч. назад"
            offline_list.append(f"⚫ <b>{nick}</b> — {ago}")
        buttons.append([InlineKeyboardButton(text=f"👤 Профиль: {nick}", callback_data=f"prof:{nick}")])

    text = f"📊 <b>Мониторинг операторов</b>\n🟢 В сети: {len(online_list)} | ⚫ Офлайн: {len(offline_list)}\n\n"
    text += "\n".join(online_list + offline_list) if (online_list or offline_list) else "Пока нет зарегистрированных игроков."

    kb = InlineKeyboardMarkup(inline_keyboard=buttons[:15]) if buttons else None
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message):
    if is_night_mode():
        await message.answer("🌙 Ночной режим (00:00 – 07:00).")
        return

    uid = str(message.from_user.id)
    update_activity(message.from_user.id)
    info = db["users"].get(uid, {})
    nick = info.get("nickname") or "Не зарегистрирован"
    reg_at = info.get("registered_at") or "—"
    logins = info.get("logins", 0)

    await message.answer(
        f"👤 <b>Карточка оператора</b>\n"
        f"• Позывной: <b>{nick}</b>\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• Регистрация: {reg_at}\n"
        f"• Входов в систему: {logins}\n"
        f"• Поддержка: @eldar3275",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )

@router.message(F.text == "🔍 Найти игрока")
async def find_player_prompt(message: Message):
    if is_night_mode():
        await message.answer("🌙 Ночной режим (00:00 – 07:00).")
        return
    update_activity(message.from_user.id)
    await message.answer("🔍 Напишите в чат позывной игрока, профиль которого хотите посмотреть:")

@router.callback_query(F.data.startswith("prof:"))
async def view_other_profile(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    target_uid = db["nick_to_id"].get(nick.lower())
    if not target_uid or target_uid not in db["users"]:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    info = db["users"][target_uid]
    now_ts = datetime.now(KYIV_TZ).timestamp()
    is_on = (now_ts - info.get("last_seen", 0)) <= 300
    status_str = "🟢 В сети" if is_on else "⚫ Не в сети"

    await callback.message.answer(
        f"🪪 <b>Профиль игрока {info.get('nickname')}</b>\n"
        f"• Статус: {status_str}\n"
        f"• Дата регистрации: {info.get('registered_at') or '—'}\n"
        f"• Успешных входов: {info.get('logins', 0)}",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("login_yes:"))
async def approve_login(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    db["login_status"][nick.lower()] = "approved"
    uid = str(callback.from_user.id)
    if uid in db["users"]:
        db["users"][uid]["logins"] = db["users"][uid].get("logins", 0) + 1
    save_db(db)
    await callback.message.edit_text(f"✅ Вход в аккаунт <b>{nick}</b> подтверждён!", parse_mode="HTML")
    await callback.answer("Доступ открыт")

@router.callback_query(F.data.startswith("login_no:"))
async def deny_login(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    db["login_status"][nick.lower()] = "denied"
    save_db(db)
    await callback.message.edit_text(f"⛔ Запрос на вход в аккаунт <b>{nick}</b> отклонён.", parse_mode="HTML")
    await callback.answer("Вход отклонён", show_alert=True)

@router.message(F.text)
async def handle_text(message: Message):
    if is_night_mode():
        await message.answer("🌙 Бот на ночном перерыве с 00:00 до 07:00 по Киеву.")
        return

    uid = str(message.from_user.id)
    update_activity(message.from_user.id, message.from_user.username or "")

    if db["users"].get(uid, {}).get("version") != APP_VERSION:
        await message.answer("🔄 Система обновилась! Пожалуйста, нажмите /start для обновления меню.")
        return

    text = message.text.strip()
    existing_nick = db["users"][uid].get("nickname")

    if existing_nick:
        target_uid = db["nick_to_id"].get(text.lower())
        if target_uid and target_uid in db["users"]:
            info = db["users"][target_uid]
            now_ts = datetime.now(KYIV_TZ).timestamp()
            status_str = "🟢 В сети" if (now_ts - info.get("last_seen", 0)) <= 300 else "⚫ Офлайн"
            await message.answer(
                f"🪪 <b>Профиль игрока {info.get('nickname')}</b>\n"
                f"• Статус: {status_str}\n"
                f"• Регистрация: {info.get('registered_at') or '—'}\n"
                f"• Входов: {info.get('logins', 0)}",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"ℹ️ За вами уже закреплён позывной <b>{existing_nick}</b> (1 регистрация на человека).\n"
                f"Если хотите сменить его — нажмите <b>♻️ Сбросить ник</b>.",
                reply_markup=main_menu_kb(),
                parse_mode="HTML"
            )
        return

    if len(text) < 3 or len(text) > 16 or text.startswith("/"):
        await message.answer("⚠️ Позывной должен содержать от 3 до 16 символов и не начинаться с /.")
        return

    if text.lower() in db["nick_to_id"]:
        await message.answer("❌ Этот позывной уже занят другим игроком! Придумайте другой.")
        return

    now_str = datetime.now(KYIV_TZ).strftime("%d.%m.%Y %H:%M")
    db["users"][uid]["nickname"] = text
    db["users"][uid]["registered_at"] = now_str
    db["nick_to_id"][text.lower()] = uid
    save_db(db)

    await message.answer(
        f"✅ Позывной <b>{text}</b> успешно зарегистрирован!\n"
        f"Теперь откройте приложение, введите этот ник и подтвердите вход в боте.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )

# HTTP API ДЛЯ ПРИЛОЖЕНИЯ
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

async def handle_options(request):
    return web.Response(headers=cors_headers())

async def health_check(request):
    return web.json_response(
        {"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT", "night_mode": is_night_mode()},
        headers=cors_headers()
    )

async def api_request_login(request):
    if is_night_mode():
        return web.json_response({"status": "night_mode"}, headers=cors_headers())

    data = await request.json()
    nick = (data.get("nickname") or "").strip()
    owner_uid = db["nick_to_id"].get(nick.lower())

    if not owner_uid:
        return web.json_response({"status": "not_found"}, headers=cors_headers())

    db["login_status"][nick.lower()] = "pending"
    save_db(db)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"login_yes:{nick}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"login_no:{nick}")
        ]
    ])
    try:
        await bot.send_message(
            chat_id=int(owner_uid),
            text=f"🔐 <b>Запрос на вход в приложение</b>\nПозывной: <b>{nick}</b>\n\nЭто вы пытаетесь зайти в аккаунт?",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        pass

    return web.json_response({"status": "pending"}, headers=cors_headers())

async def api_check_login(request):
    nick = (request.query.get("nickname") or "").strip().lower()
    st = db["login_status"].get(nick, "pending")
    return web.json_response({"status": st}, headers=cors_headers())

async def self_ping_loop():
    import aiohttp
    while True:
        await asyncio.sleep(600)
        if not is_night_mode():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(SELF_URL) as resp:
                        await resp.text()
            except Exception:
                pass

async def main():
    dp.include_router(router)
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", health_check)
    app.router.add_post("/api/request-login", api_request_login)
    app.router.add_get("/api/check-login", api_check_login)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    asyncio.create_task(self_ping_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
