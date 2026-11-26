
import os
import json
import asyncio
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart, Command

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = "https://moiseenkoeldar2-del.github.io/shopbot/"
DB_FILE = "registrations.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Загрузка и сохранение базы регистраций (1 человек = 1 ник)
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
login_statuses = {}  # {str(user_id): {"status": "pending"|"approved"|"denied", "nickname": str}}


def get_webapp_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть терминал", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    if uid in db["users"]:
        nick = db["users"][uid]
        await message.answer(
            f"🛸 **DRONEPOINT AREX PRO — Бот регистрации**

"
            f"Ваш закреплённый позывной: `{nick}`
"
            f"Откройте терминал, введите этот ник и нажмите **«📨 Войти в аккаунт»** — я пришлю сюда запрос на подтверждение входа.

"
            f"♻️ Чтобы сбросить привязку (1 регистрация на человека), отправьте `/resetник`.",
            reply_markup=get_webapp_kb(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "🛸 **DRONEPOINT AREX PRO — Регистрация позывного**

"
            "⚠️ Действует правило: **1 регистрация на человека**.
"
            "✍️ **Напишите в ответ желаемый никнейм** (от 3 до 20 символов, буквы/цифры/_):",
            parse_mode="Markdown"
        )


@router.message(F.text.lower().startswith("/resetник"))
@router.message(Command("resetnick"))
async def cmd_reset_nick(message: Message):
    uid = str(message.from_user.id)
    if uid in db["users"]:
        old_nick = db["users"].pop(uid)
        db["nicks"].pop(old_nick.lower(), None)
        login_statuses.pop(uid, None)
        save_db(db)
        await message.answer(
            f"♻️ Лимит «1 регистрация на человека» сброшен! Позывной `{old_nick}` отвязан.

"
            f"✍️ Теперь вы можете отправить мне **новый никнейм** для регистрации.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("ℹ️ У вас нет активной регистрации. Просто напишите желаемый никнейм в этот чат.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_nick_registration(message: Message):
    uid = str(message.from_user.id)
    nick = message.text.strip()

    if uid in db["users"]:
        existing = db["users"][uid]
        await message.answer(
            f"⛔ **Сработало ограничение: 1 регистрация на человека.**
"
            f"За вами уже закреплён позывной `{existing}`.

"
            f"Откройте терминал и войдите под ним (или отправьте `/resetник` для сброса).",
            reply_markup=get_webapp_kb(),
            parse_mode="Markdown"
        )
        return

    if len(nick) < 3 or len(nick) > 20:
        await message.answer("⚠️ Длина ника должна быть от **3 до 20 символов**. Попробуйте ещё раз:", parse_mode="Markdown")
        return

    if nick.lower() in db["nicks"]:
        await message.answer("❌ Этот позывной уже занят другим оператором. Введите другой ник:")
        return

    db["users"][uid] = nick
    db["nicks"][nick.lower()] = uid
    save_db(db)

    await message.answer(
        f"✅ **Позывной `{nick}` успешно зарегистрирован!**

"
        f"Теперь перейдите в терминал, введите ваш ник `{nick}` и нажмите **«📨 Войти в аккаунт»** — я пришлю сюда кнопку подтверждения.",
        reply_markup=get_webapp_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("auth_yes:"))
async def cb_auth_yes(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    nick = callback.data.split(":", 1)[1]
    login_statuses[uid] = {"status": "approved", "nickname": nick}
    await callback.message.edit_text(
        f"✅ **Вход в аккаунт `{nick}` подтверждён!**
"
        f"Возвращайтесь в терминал — доступ открыт.",
        reply_markup=get_webapp_kb(),
        parse_mode="Markdown"
    )
    await callback.answer("Доступ разрешён")


@router.callback_query(F.data.startswith("auth_no:"))
async def cb_auth_no(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    nick = callback.data.split(":", 1)[1]
    login_statuses[uid] = {"status": "denied", "nickname": nick}
    await callback.message.edit_text(
        f"❌ **Попытка входа в аккаунт `{nick}` отклонена!**",
        parse_mode="Markdown"
    )
    await callback.answer("Вход заблокирован", show_alert=True)


# --- HTTP API для связи с index.html ---
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=200)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


async def api_health(request):
    return web.json_response({"status": "ok", "bot": "DRONEPOINT_AREX_PRO_REGISTR_BOT"})


async def api_request_login(request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    nick = str(data.get("nickname", "")).strip()

    if not nick:
        return web.json_response({"ok": False, "error": "empty_nick"})

    owner_uid = db["nicks"].get(nick.lower())
    if not owner_uid:
        return web.json_response({"ok": False, "error": "not_registered"})

    if uid and owner_uid != uid and uid in db["users"]:
        return web.json_response({"ok": False, "error": "wrong_owner"})

    target_uid = owner_uid
    real_nick = db["users"][target_uid]
    login_statuses[target_uid] = {"status": "pending", "nickname": real_nick}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"auth_yes:{real_nick}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"auth_no:{real_nick}")
        ]
    ])
    now_str = datetime.now().strftime("%H:%M:%S")
    try:
        await bot.send_message(
            chat_id=int(target_uid),
            text=(
                f"🔐 **Запрос на вход в терминал**
"
                f"Позывной: `{real_nick}`
"
                f"Время: `{now_str}`

"
                f"**Это вы пытаетесь зайти в аккаунт?**"
            ),
            reply_markup=kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        return web.json_response({"ok": False, "error": "tg_send_failed", "message": str(e)})

    return web.json_response({"ok": True, "target_uid": target_uid})


async def api_check_login(request):
    uid = str(request.query.get("user_id", "")).strip()
    if uid in login_statuses:
        return web.json_response(login_statuses[uid])
    for info in login_statuses.values():
        if info.get("status") in ("approved", "denied"):
            return web.json_response(info)
    return web.json_response({"status": "pending"})


async def api_reset_nick(request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if uid in db["users"]:
        old_nick = db["users"].pop(uid)
        db["nicks"].pop(old_nick.lower(), None)
        login_statuses.pop(uid, None)
        save_db(db)
    return web.json_response({"ok": True})


dp.include_router(router)


async def main():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", api_health)
    app.router.add_post("/api/request-login", api_request_login)
    app.router.add_get("/api/check-login", api_check_login)
    app.router.add_post("/api/reset-nick", api_reset_nick)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
