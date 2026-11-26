
import os
import json
import time
import asyncio
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = "https://moiseenkoeldar2-del.github.io/shopbot/"
DATA_FILE = "registrations.json"
ONLINE_TIMEOUT = 300  # 5 минут активности = Онлайн

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

class RegStates(StatesGroup):
    waiting_nick = State()
    searching_player = State()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "nicks": {}, "login_status": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_data()

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Онлайн"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="♻️ Сбросить ник")],
            [KeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        ],
        resize_keyboard=True,
    )

def format_last_seen(ts: float) -> str:
    diff = int(time.time() - ts)
    if diff < ONLINE_TIMEOUT:
        return "🟢 Онлайн (сейчас)"
    mins = diff // 60
    if mins < 60:
        return f"⚫ Офлайн ({mins} мин. назад)"
    hours = mins // 60
    if hours < 24:
        return f"⚫ Офлайн ({hours} ч. назад)"
    days = hours // 24
    return f"⚫ Офлайн ({days} дн. назад)"

def update_activity(user_id: str, username: str = None, full_name: str = None):
    if user_id in db["users"]:
        db["users"][user_id]["last_seen"] = time.time()
        if username is not None:
            db["users"][user_id]["username"] = username
        if full_name is not None:
            db["users"][user_id]["full_name"] = full_name
        save_data(db)

def build_profile_text(uid: str, info: dict, is_own: bool = False) -> str:
    nick = info.get("nick", "Неизвестно")
    reg_date = info.get("reg_date", "Неизвестно")
    logins = info.get("logins", 1)
    status = format_last_seen(info.get("last_seen", 0))
    header = "👤 **Ваш профиль**" if is_own else f"🪪 **Профиль игрока {nick}**"
    lines = [
        header,
        "",
        f"🏷 Позывной: `{nick}`",
        f"📡 Статус: {status}",
        f"📅 Регистрация: {reg_date}",
        f"🔑 Успешных входов: {logins}",
    ]
    if is_own:
        lines.append(f"🆔 Ваш ID: `{uid}`")
    return "\n".join(lines)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = str(message.from_user.id)
    update_activity(uid, message.from_user.username, message.from_user.full_name)

    if uid in db["users"]:
        nick = db["users"][uid]["nick"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=f"{WEBAPP_URL}?nick={nick}"))]
        ])
        await message.answer(
            f"👋 С возвращением! Ваш позывной: `{nick}`.\n\n"
            f"Используйте кнопки меню ниже для просмотра игроков в сети, поиска профилей или запуска приложения.",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        await message.answer("Быстрый запуск магазина и кликера:", reply_markup=kb)
    else:
        await state.set_state(RegStates.waiting_nick)
        await message.answer(
            "🛸 **Добро пожаловать в DRONEPOINT AREX PRO!**\n\n"
            "Правило системы: **1 регистрация на человека**.\n"
            "✏️ Напишите в чат ваш желаемый позывной (от 3 до 16 символов, буквы/цифры/_):",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )

@router.message(F.text == "🟢 Онлайн")
async def show_online(message: Message):
    uid = str(message.from_user.id)
    update_activity(uid, message.from_user.username, message.from_user.full_name)

    if not db["users"]:
        return await message.answer("📭 В системе пока нет зарегистрированных игроков.", reply_markup=main_menu())

    now = time.time()
    online_list = []
    offline_list = []
    buttons = []

    for u_id, info in db["users"].items():
        nick = info.get("nick", "Без ника")
        last_seen = info.get("last_seen", 0)
        if now - last_seen < ONLINE_TIMEOUT:
            online_list.append(f"🟢 `{nick}` — в сети")
        else:
            offline_list.append(f"⚫ `{nick}` — {format_last_seen(last_seen).replace('⚫ Офлайн ', '')}")
        buttons.append([InlineKeyboardButton(text=f"🪪 Профиль: {nick}", callback_data=f"view_prof:{u_id}")])

    text_parts = [
        f"📡 **Мониторинг игроков (Всего: {len(db['users'])})**",
        f"🟢 В сети: **{len(online_list)}** | ⚫ Офлайн: **{len(offline_list)}**",
        "",
    ]
    if online_list:
        text_parts.append("**Сейчас онлайн:**")
        text_parts.extend(online_list)
        text_parts.append("")
    if offline_list:
        text_parts.append("**Не в сети:**")
        text_parts.extend(offline_list[:20])

    text_parts.append("\n👇 Нажмите на игрока ниже, чтобы открыть его профиль:")
    kb = InlineKeyboardMarkup(inline_keyboard=buttons[:15])
    await message.answer("\n".join(text_parts), reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("view_prof:"))
async def callback_view_profile(callback: CallbackQuery):
    target_uid = callback.data.split(":", 1)[1]
    update_activity(str(callback.from_user.id), callback.from_user.username, callback.from_user.full_name)

    info = db["users"].get(target_uid)
    if not info:
        return await callback.answer("Профиль не найден.", show_alert=True)

    is_own = (target_uid == str(callback.from_user.id))
    text = build_profile_text(target_uid, info, is_own=is_own)
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.message(F.text == "🔍 Найти игрока")
async def ask_search_player(message: Message, state: FSMContext):
    uid = str(message.from_user.id)
    update_activity(uid, message.from_user.username, message.from_user.full_name)
    await state.set_state(RegStates.searching_player)
    await message.answer("🔍 Введите позывной игрока, чей профиль хотите посмотреть:")

@router.message(RegStates.searching_player)
async def process_search_player(message: Message, state: FSMContext):
    query = message.text.strip()
    if query in {"🟢 Онлайн", "🔍 Найти игрока", "👤 Мой профиль", "♻️ Сбросить ник", "🚀 Открыть приложение"}:
        await state.clear()
        return

    await state.clear()
    found_uid = None
    for u_id, info in db["users"].items():
        if info.get("nick", "").lower() == query.lower():
            found_uid = u_id
            break

    if not found_uid:
        return await message.answer(
            f"❌ Игрок с позывным `{query}` не найден.",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )

    is_own = (found_uid == str(message.from_user.id))
    text = build_profile_text(found_uid, db["users"][found_uid], is_own=is_own)
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")

@router.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message, state: FSMContext):
    await state.clear()
    uid = str(message.from_user.id)
    update_activity(uid, message.from_user.username, message.from_user.full_name)

    if uid not in db["users"]:
        await state.set_state(RegStates.waiting_nick)
        return await message.answer(
            "⚠️ У вас ещё нет зарегистрированного профиля.\n✏️ Напишите желаемый позывной в чат:"
        )

    text = build_profile_text(uid, db["users"][uid], is_own=True)
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")

@router.message(F.text == "♻️ Сбросить ник")
@router.message(Command("resetник"))
@router.message(F.text.lower().startswith("/resetник"))
async def reset_nick(message: Message, state: FSMContext):
    await state.clear()
    uid = str(message.from_user.id)

    if uid in db["users"]:
        old_nick = db["users"][uid]["nick"]
        db["nicks"].pop(old_nick.lower(), None)
        db["login_status"].pop(old_nick.lower(), None)
        del db["users"][uid]
        save_data(db)
        await state.set_state(RegStates.waiting_nick)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен! Позывной `{old_nick}` отвязан.\n\n"
            f"✏️ Напишите новый позывной прямо сейчас:",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
    else:
        await state.set_state(RegStates.waiting_nick)
        await message.answer(
            "ℹ️ У вас нет привязанного позывного. Введите новый ник для регистрации:",
            reply_markup=main_menu(),
        )

@router.message(RegStates.waiting_nick)
async def register_nick_step(message: Message, state: FSMContext):
    uid = str(message.from_user.id)
    nick = message.text.strip()

    if nick in {"🟢 Онлайн", "🔍 Найти игрока", "👤 Мой профиль", "♻️ Сбросить ник", "🚀 Открыть приложение"}:
        return

    if uid in db["users"]:
        await state.clear()
        return await message.answer(
            f"⚠️ За вами уже закреплён позывной `{db['users'][uid]['nick']}` (правило: 1 регистрация на человека).",
            parse_mode="Markdown",
        )

    if not (3 <= len(nick) <= 16) or not all(c.isalnum() or c in "_-" for c in nick):
        return await message.answer(
            "❌ Неверный формат! Используйте от 3 до 16 символов (буквы, цифры, `_` или `-`). Попробуйте ещё раз:"
        )

    if nick.lower() in db["nicks"]:
        return await message.answer(f"⛔ Позывной `{nick}` уже занят другим игроком. Введите другой:", parse_mode="Markdown")

    db["users"][uid] = {
        "nick": nick,
        "reg_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "last_seen": time.time(),
        "logins": 0,
        "username": message.from_user.username,
        "full_name": message.from_user.full_name,
    }
    db["nicks"][nick.lower()] = uid
    save_data(db)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=f"{WEBAPP_URL}?nick={nick}"))]
    ])
    await message.answer(
        f"✅ Позывной `{nick}` успешно зарегистрирован!\n\n"
        f"Нажмите кнопку ниже, чтобы открыть приложение, введите свой ник и подтвердите вход здесь в боте.",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )
    await message.answer("👇 Вход в магазин и кликер:", reply_markup=kb)

@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext):
    uid = str(message.from_user.id)
    update_activity(uid, message.from_user.username, message.from_user.full_name)
    text = message.text.strip()

    if uid not in db["users"]:
        return await register_nick_step(message, state)

    # Быстрый просмотр профиля, если пользователь просто написал чей-то ник в чат
    for u_id, info in db["users"].items():
        if info.get("nick", "").lower() == text.lower():
            prof = build_profile_text(u_id, info, is_own=(u_id == uid))
            return await message.answer(prof, reply_markup=main_menu(), parse_mode="Markdown")

    await message.answer(
        "Выберите действие на клавиатуре ниже или напишите позывной игрока, чтобы открыть его профиль:",
        reply_markup=main_menu(),
    )

@router.callback_query(F.data.startswith("auth_yes:"))
async def auth_yes(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    uid = str(callback.from_user.id)
    update_activity(uid, callback.from_user.username, callback.from_user.full_name)

    if uid in db["users"]:
        db["users"][uid]["logins"] = db["users"][uid].get("logins", 0) + 1

    db["login_status"][nick.lower()] = {"status": "approved", "ts": time.time()}
    save_data(db)

    await callback.message.edit_text(
        f"✅ **Вход подтверждён!**\nАккаунт: `{nick}`\n\nВернитесь в приложение — доступ уже открыт.",
        parse_mode="Markdown",
    )
    await callback.answer("Вход разрешён!")

@router.callback_query(F.data.startswith("auth_no:"))
async def auth_no(callback: CallbackQuery):
    nick = callback.data.split(":", 1)[1]
    uid = str(callback.from_user.id)
    update_activity(uid, callback.from_user.username, callback.from_user.full_name)

    db["login_status"][nick.lower()] = {"status": "denied", "ts": time.time()}
    save_data(db)

    await callback.message.edit_text(
        f"❌ **Запрос на вход отклонён владельцем.**\nАккаунт: `{nick}`",
        parse_mode="Markdown",
    )
    await callback.answer("Запрос отклонён!", show_alert=True)

# --- HTTP API для связи с index.html ---
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

async def handle_options(request):
    return web.Response(headers=cors_headers())

async def handle_health(request):
    return web.json_response(
        {"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT", "users_count": len(db["users"])},
        headers=cors_headers(),
    )

async def handle_request_login(request):
    try:
        data = await request.json()
        nick = str(data.get("nickname", "")).strip()
        if not nick:
            return web.json_response({"ok": False, "error": "Укажите позывной"}, status=400, headers=cors_headers())

        owner_uid = db["nicks"].get(nick.lower())
        if not owner_uid:
            return web.json_response(
                {"ok": False, "error": "Позывной не зарегистрирован в боте"},
                status=404,
                headers=cors_headers(),
            )

        db["login_status"][nick.lower()] = {"status": "pending", "ts": time.time()}
        save_data(db)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"auth_yes:{nick}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"auth_no:{nick}"),
            ]
        ])
        await bot.send_message(
            chat_id=int(owner_uid),
            text=f"🔐 **Запрос на вход в аккаунт**\nПозывной: `{nick}`\n\nЭто вы пытаетесь зайти в аккаунт?",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return web.json_response({"ok": True, "status": "pending"}, headers=cors_headers())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500, headers=cors_headers())

async def handle_check_login(request):
    nick = request.query.get("nickname", "").strip().lower()
    if not nick:
        return web.json_response({"status": "none"}, headers=cors_headers())
    rec = db["login_status"].get(nick, {"status": "none"})
    if rec.get("status") == "approved":
        owner_uid = db["nicks"].get(nick)
        if owner_uid:
            update_activity(owner_uid)
    return web.json_response({"status": rec.get("status", "none")}, headers=cors_headers())

async def handle_ping(request):
    try:
        data = await request.json()
        nick = str(data.get("nickname", "")).strip().lower()
        uid = str(data.get("user_id", "")).strip()
        if nick and nick in db["nicks"]:
            update_activity(db["nicks"][nick])
        elif uid and uid in db["users"]:
            update_activity(uid)
        return web.json_response({"ok": True}, headers=cors_headers())
    except Exception:
        return web.json_response({"ok": False}, headers=cors_headers())

async def handle_reset_api(request):
    try:
        data = await request.json()
        nick = str(data.get("nickname", "")).strip().lower()
        uid = str(data.get("user_id", "")).strip()
        target_uid = db["nicks"].get(nick) or (uid if uid in db["users"] else None)
        if target_uid and target_uid in db["users"]:
            old_nick = db["users"][target_uid]["nick"]
            db["nicks"].pop(old_nick.lower(), None)
            db["login_status"].pop(old_nick.lower(), None)
            del db["users"][target_uid]
            save_data(db)
        return web.json_response({"ok": True}, headers=cors_headers())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500, headers=cors_headers())

async def start_services():
    dp.include_router(router)
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", handle_health)
    app.router.add_post("/api/request-login", handle_request_login)
    app.router.add_get("/api/check-login", handle_check_login)
    app.router.add_post("/api/ping", handle_ping)
    app.router.add_post("/api/reset", handle_reset_api)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_services())
