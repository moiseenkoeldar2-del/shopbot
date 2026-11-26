
import os
import json
import time
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PORT = int(os.getenv("PORT", 8000))
SELF_URL = os.getenv("RENDER_EXTERNAL_URL", "https://shopbot-2-412g.onrender.com")
WEBAPP_URL = "https://moiseenkoeldar2-del.github.io/shopbot/"
SUPPORT_CONTACT = "@eldar3275"
APP_VERSION = "3.1"
KYIV_TZ = ZoneInfo("Europe/Kyiv")
DATA_FILE = "registrations.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хранилище:
# users: {str(user_id): {"nick": str, "registered_at": float, "last_seen": float, "logins": int, "username": str, "version": str}}
# nicks: {nick_lower: str(user_id)}
# login_requests: {nick_lower: {"status": "pending"|"approved"|"denied", "ts": float}}
# search_mode: set(user_id)

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "nicks": {}}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

db = load_data()
login_requests = {}
search_mode = set()

def is_night_mode() -> bool:
    now_kyiv = datetime.now(KYIV_TZ)
    return 0 <= now_kyiv.hour < 7

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Онлайн"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="♻️ Сбросить ник")],
            [KeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
        ],
        resize_keyboard=True
    )

def format_time_ago(ts: float) -> str:
    diff = int(time.time() - ts)
    if diff < 300:
        return "🟢 Онлайн (сейчас)"
    mins = diff // 60
    if mins < 60:
        return f"⚫ Был(а) {mins} мин. назад"
    hours = mins // 60
    if hours < 24:
        return f"⚫ Был(а) {hours} ч. назад"
    days = hours // 24
    return f"⚫ Был(а) {days} дн. назад"

def format_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, KYIV_TZ).strftime("%d.%m.%Y %H:%M")

def update_activity(user_id: int, username: str = ""):
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid]["last_seen"] = time.time()
        if username:
            db["users"][uid]["username"] = username
        save_data(db)

def render_profile_card(uid: str, is_owner: bool = False) -> str:
    u = db["users"][uid]
    status_str = format_time_ago(u.get("last_seen", 0))
    reg_date = format_date(u.get("registered_at", time.time()))
    logins = u.get("logins", 0)
    uname = f" (@{u['username']})" if u.get("username") else ""
    header = "👤 **Ваш профиль**" if is_owner else f"🪪 **Профиль игрока {u['nick']}**"
    text = (
        f"{header}\n\n"
        f"🏷 Позывной: `{u['nick']}`{uname}\n"
        f"📡 Статус: {status_str}\n"
        f"📅 Регистрация: {reg_date}\n"
        f"🔐 Входов в приложение: {logins}\n"
        f"💬 Поддержка: {SUPPORT_CONTACT}"
    )
    return text

@router.message(Command("start"))
async def cmd_start(message: Message):
    if is_night_mode():
        return await message.answer(
            "🌙 **Бот находится в ночном режиме (с 00:00 до 07:00 по Киеву).**\n"
            "Приём регистраций и входов временно приостановлен. Возвращайтесь после 07:00!\n\n"
            f"💬 Поддержка: {SUPPORT_CONTACT}",
            parse_mode="Markdown"
        )

    uid = str(message.from_user.id)
    username = message.from_user.username or ""
    search_mode.discard(message.from_user.id)

    if uid in db["users"]:
        db["users"][uid]["version"] = APP_VERSION
        db["users"][uid]["last_seen"] = time.time()
        if username:
            db["users"][uid]["username"] = username
        save_data(db)
        nick = db["users"][uid]["nick"]
        await message.answer(
            f"✅ **Сессия обновлена (v{APP_VERSION})!**\n\n"
            f"Ваш закреплённый позывной: `{nick}`\n"
            f"Используйте меню кнопок ниже или запускайте приложение прямо отсюда.\n\n"
            f"💬 Поддержка: {SUPPORT_CONTACT}",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"🛸 **Добро пожаловать в DRONEPOINT AREX PRO SHOP!**\n\n"
            f"Для доступа к приложению необходимо зарегистрировать позывной.\n"
            f"⚠️ Правило: **строго 1 регистрация на человека**.\n\n"
            f"✍️ **Напишите в этот чат ваш желаемый позывной** (от 3 до 16 символов: буквы, цифры, `_`):",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

@router.message(F.text.lower().startswith("/resetник") | (F.text == "♻️ Сбросить ник"))
async def cmd_reset_nick(message: Message):
    if is_night_mode():
        return await message.answer("🌙 Ночной режим (00:00 – 07:00). Сброс доступен после 07:00.")

    uid = str(message.from_user.id)
    search_mode.discard(message.from_user.id)

    if uid in db["users"]:
        old_nick = db["users"][uid]["nick"]
        db["nicks"].pop(old_nick.lower(), None)
        db["users"].pop(uid, None)
        login_requests.pop(old_nick.lower(), None)
        save_data(db)
        await message.answer(
            f"♻️ **Лимит «1 регистрация на человека» сброшен!**\n"
            f"Позывной `{old_nick}` отвязан от вашего аккаунта.\n\n"
            f"✍️ Напишите новый желаемый позывной в чат для регистрации:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "ℹ️ У вас сейчас нет закреплённого позывного.\n✍️ Просто напишите желаемый ник в чат, чтобы зарегистрироваться!",
            reply_markup=get_main_keyboard()
        )

@router.message(F.text == "🟢 Онлайн")
async def cmd_online(message: Message):
    if is_night_mode():
        return await message.answer("🌙 Ночной режим (00:00 – 07:00). Мониторинг доступен после 07:00.")

    uid = str(message.from_user.id)
    if uid in db["users"] and db["users"][uid].get("version") != APP_VERSION:
        return await message.answer("🔄 Система обновилась! Пожалуйста, нажмите /start, чтобы обновить меню.")

    update_activity(message.from_user.id, message.from_user.username or "")
    search_mode.discard(message.from_user.id)

    if not db["users"]:
        return await message.answer("📭 В системе пока нет зарегистрированных игроков.", reply_markup=get_main_keyboard())

    now = time.time()
    online_list = []
    offline_list = []
    buttons = []

    sorted_users = sorted(db["users"].items(), key=lambda x: x[1].get("last_seen", 0), reverse=True)
    for target_uid, info in sorted_users:
        nick = info["nick"]
        is_on = (now - info.get("last_seen", 0)) < 300
        if is_on:
            online_list.append(f"• `{nick}` — 🟢 В сети")
        else:
            offline_list.append(f"• `{nick}` — {format_time_ago(info.get('last_seen', 0))}")
        buttons.append([InlineKeyboardButton(text=f"🪪 Профиль: {nick}", callback_data=f"view_prof:{target_uid}")])

    text = f"📡 **Мониторинг игроков (Всего: {len(sorted_users)})**\n\n"
    text += f"**🟢 Сейчас в сети ({len(online_list)}):**\n" + ("\n".join(online_list) if online_list else "Никого нет") + "\n\n"
    text += f"**⚫ Не в сети ({len(offline_list)}):**\n" + ("\n".join(offline_list[:15]) if offline_list else "Пусто")
    text += "\n\n👇 Нажмите на игрока ниже, чтобы открыть его профиль:"

    kb = InlineKeyboardMarkup(inline_keyboard=buttons[:20])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.message(F.text == "👤 Мой профиль")
async def cmd_my_profile(message: Message):
    if is_night_mode():
        return await message.answer("🌙 Ночной режим (00:00 – 07:00). Профиль доступен после 07:00.")

    uid = str(message.from_user.id)
    if uid in db["users"] and db["users"][uid].get("version") != APP_VERSION:
        return await message.answer("🔄 Система обновилась! Пожалуйста, нажмите /start, чтобы обновить меню.")

    search_mode.discard(message.from_user.id)
    if uid not in db["users"]:
        return await message.answer(
            "❌ Вы ещё не зарегистрированы.\n✍️ Напишите желаемый позывной в этот чат, чтобы создать профиль:",
            reply_markup=get_main_keyboard()
        )

    update_activity(message.from_user.id, message.from_user.username or "")
    await message.answer(render_profile_card(uid, is_owner=True), reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.message(F.text == "🔍 Найти игрока")
async def cmd_find_player(message: Message):
    if is_night_mode():
        return await message.answer("🌙 Ночной режим (00:00 – 07:00). Поиск доступен после 07:00.")

    uid = str(message.from_user.id)
    if uid in db["users"] and db["users"][uid].get("version") != APP_VERSION:
        return await message.answer("🔄 Система обновилась! Пожалуйста, нажмите /start, чтобы обновить меню.")

    update_activity(message.from_user.id, message.from_user.username or "")
    search_mode.add(message.from_user.id)
    await message.answer(
        "🔍 **Поиск профиля игрока**\n\nВведите точный позывной игрока, чей профиль хотите посмотреть:",
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("view_prof:"))
async def cb_view_profile(callback: CallbackQuery):
    if is_night_mode():
        return await callback.answer("🌙 Ночной режим (00:00 – 07:00)", show_alert=True)

    target_uid = callback.data.split(":", 1)[1]
    if target_uid not in db["users"]:
        return await callback.answer("Профиль не найден или сброшен.", show_alert=True)

    is_owner = (target_uid == str(callback.from_user.id))
    await callback.message.answer(render_profile_card(target_uid, is_owner=is_owner), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("login_yes:"))
async def cb_login_yes(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    nick_key = nick.lower()
    uid = str(callback.from_user.id)

    login_requests[nick_key] = {"status": "approved", "ts": time.time()}
    if uid in db["users"]:
        db["users"][uid]["last_seen"] = time.time()
        db["users"][uid]["logins"] = db["users"][uid].get("logins", 0) + 1
        save_data(db)

    await callback.message.edit_text(
        f"✅ **Вход в аккаунт `{nick}` подтверждён!**\nВернитесь в приложение — доступ открыт.",
        parse_mode="Markdown"
    )
    await callback.answer("Вход разрешён!")

@router.callback_query(F.data.startswith("login_no:"))
async def cb_login_no(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    nick_key = nick.lower()

    login_requests[nick_key] = {"status": "denied", "ts": time.time()}
    await callback.message.edit_text(
        f"⛔ **Запрос на вход в аккаунт `{nick}` отклонён.**\nПопытка чужого входа заблокирована.",
        parse_mode="Markdown"
    )
    await callback.answer("Запрос отклонён!", show_alert=True)

@router.message(F.text)
async def handle_text(message: Message):
    if is_night_mode():
        return await message.answer(
            "🌙 **Ночной режим (с 00:00 до 07:00 по Киеву).**\nБот временно отдыхает. Возвращайтесь после 07:00!",
            parse_mode="Markdown"
        )

    user_id = message.from_user.id
    uid = str(user_id)
    text = message.text.strip()
    username = message.from_user.username or ""

    # Режим поиска другого игрока
    if user_id in search_mode:
        search_mode.discard(user_id)
        target_uid = db["nicks"].get(text.lower())
        if not target_uid or target_uid not in db["users"]:
            return await message.answer(
                f"❌ Игрок с позывным `{text}` не найден в базе.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        return await message.answer(
            render_profile_card(target_uid, is_owner=(target_uid == uid)),
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

    # Проверка версии для уже зарегистрированных
    if uid in db["users"]:
        if db["users"][uid].get("version") != APP_VERSION:
            return await message.answer("🔄 Система обновилась! Нажмите /start, чтобы обновить меню кнопок.")
        update_activity(user_id, username)
        existing_nick = db["users"][uid]["nick"]
        return await message.answer(
            f"⚠️ За вами уже закреплён позывной `{existing_nick}` (правило: **1 регистрация на человека**).\n\n"
            f"• Чтобы открыть приложение, нажмите **«🚀 Открыть приложение»**.\n"
            f"• Чтобы сменить позывной, нажмите **«♻️ Сбросить ник»**.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

    # Регистрация нового позывного
    if len(text) < 3 or len(text) > 16 or " " in text:
        return await message.answer(
            "❌ Позывной должен быть от **3 до 16 символов** без пробелов.\nПопробуйте ещё раз:",
            parse_mode="Markdown"
        )

    nick_lower = text.lower()
    if nick_lower in db["nicks"]:
        return await message.answer(
            f"⛔ Позывной `{text}` уже занят другим игроком! Придумайте другой:",
            parse_mode="Markdown"
        )

    db["users"][uid] = {
        "nick": text,
        "registered_at": time.time(),
        "last_seen": time.time(),
        "logins": 0,
        "username": username,
        "version": APP_VERSION
    }
    db["nicks"][nick_lower] = uid
    save_data(db)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"🎉 **Регистрация успешно завершена!**\n\n"
        f"🏷 Ваш позывной: `{text}`\n"
        f"🔒 Привязка: 1 аккаунт на человека\n\n"
        f"Теперь откройте приложение, введите позывной `{text}` и подтвердите вход здесь в боте!",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await message.answer("Меню управления активировано 👇", reply_markup=get_main_keyboard())

# --- HTTP API для связи с приложением ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

async def handle_options(request):
    return web.Response(status=204, headers=CORS_HEADERS)

async def handle_health(request):
    return web.json_response(
        {"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT", "night_mode": is_night_mode()},
        headers=CORS_HEADERS
    )

async def handle_request_login(request):
    if is_night_mode():
        return web.json_response(
            {"ok": False, "error": "night_mode", "message": "Ночной режим (00:00 – 07:00). Вход доступен после 07:00."},
            headers=CORS_HEADERS
        )

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400, headers=CORS_HEADERS)

    nick = str(data.get("nickname", "")).strip()
    if not nick:
        return web.json_response({"ok": False, "error": "empty_nick"}, headers=CORS_HEADERS)

    nick_key = nick.lower()
    if nick_key == "/resetник":
        req_uid = str(data.get("user_id", ""))
        if req_uid in db["users"]:
            old_n = db["users"][req_uid]["nick"]
            db["nicks"].pop(old_n.lower(), None)
            db["users"].pop(req_uid, None)
            save_data(db)
        return web.json_response({"ok": True, "reset": True}, headers=CORS_HEADERS)

    owner_uid = db["nicks"].get(nick_key)
    if not owner_uid or owner_uid not in db["users"]:
        return web.json_response(
            {"ok": False, "error": "not_found", "message": "Позывной не найден. Сначала зарегистрируйтесь в боте!"},
            headers=CORS_HEADERS
        )

    real_nick = db["users"][owner_uid]["nick"]
    login_requests[nick_key] = {"status": "pending", "ts": time.time()}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"login_yes:{real_nick}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"login_no:{real_nick}")
        ]
    ])

    try:
        await bot.send_message(
            chat_id=int(owner_uid),
            text=f"🔐 **Запрос на вход в приложение**\n\nПозывной: `{real_nick}`\nЭто вы пытаетесь зайти в аккаунт?",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    except Exception:
        return web.json_response(
            {"ok": False, "error": "bot_blocked", "message": "Нажмите /start в боте @DRONEPOINT_AREX_PRO_REGISTR_BOT, чтобы получать уведомления!"},
            headers=CORS_HEADERS
        )

    return web.json_response({"ok": True, "status": "pending", "nickname": real_nick}, headers=CORS_HEADERS)

async def handle_check_login(request):
    if is_night_mode():
        return web.json_response({"status": "night_mode"}, headers=CORS_HEADERS)

    nick = request.query.get("nickname", "").strip().lower()
    req = login_requests.get(nick)
    if not req:
        return web.json_response({"status": "none"}, headers=CORS_HEADERS)
    return web.json_response({"status": req["status"]}, headers=CORS_HEADERS)

async def handle_ping(request):
    try:
        data = await request.json()
        nick = str(data.get("nickname", "")).strip().lower()
        owner_uid = db["nicks"].get(nick)
        if owner_uid and owner_uid in db["users"]:
            db["users"][owner_uid]["last_seen"] = time.time()
            save_data(db)
    except Exception:
        pass
    return web.json_response({"ok": True, "night_mode": is_night_mode()}, headers=CORS_HEADERS)

async def self_ping_loop():
    await asyncio.sleep(30)
    async with aiohttp.ClientSession() as session:
        while True:
            if not is_night_mode() and SELF_URL:
                try:
                    async with session.get(SELF_URL, timeout=10) as resp:
                        await resp.text()
                except Exception:
                    pass
            await asyncio.sleep(600)

async def main():
    dp.include_router(router)
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", handle_health)
    app.router.add_post("/api/request-login", handle_request_login)
    app.router.add_get("/api/check-login", handle_check_login)
    app.router.add_post("/api/ping", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    asyncio.create_task(self_ping_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
