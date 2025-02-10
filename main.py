import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatType
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.sessions import StringSession
from pyrogram.errors import (
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PasswordHashInvalid
)
from telethon.errors import (
    ApiIdInvalidError, PhoneNumberInvalidError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    SessionPasswordNeededError, PasswordHashInvalidError
)
from config import API_ID, API_HASH, BOT_TOKEN

session_data = {}

logging.basicConfig(level=logging.INFO)

# 🛠️ बॉट स्टार्ट करने के लिए हैंडलर सेटअप
def setup_string_handler(app: Client):
    @app.on_message(filters.command(["pyro", "tele"]) & filters.private)
    async def session_setup(client, message: Message):
        platform = "Pyrogram" if message.command[0] == "pyro" else "Telethon"
        await handle_start(client, message, platform)

    @app.on_callback_query(filters.regex(r"^session_go_"))
    async def callback_query_go_handler(client, callback_query):
        await handle_callback_query(client, callback_query)

    @app.on_message(filters.text & filters.create(lambda _, __, message: message.chat.id in session_data))
    async def text_handler(client, message: Message):
        await handle_text(client, message)

async def handle_start(client, message, platform):
    session_type = "Telethon" if platform == "Telethon" else "Pyrogram"
    session_data[message.chat.id] = {"type": session_type}

    await message.reply(
        f"**Welcome to {session_type} Session Setup!**\n"
        "🔹 **यह एक सुरक्षित Session Generator है।**\n"
        "🔹 **हम आपकी कोई भी जानकारी सेव नहीं करते।**\n\n"
        "**⚠️ ध्यान दें:**\n"
        "1️⃣ **Session किसी के साथ शेयर न करें!**\n"
        "2️⃣ **OTP गलत डालने पर अकाउंट लॉक हो सकता है!**\n\n"
        "**➡️ शुरू करने के लिए 'Go' पर क्लिक करें!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Go", callback_data=f"session_go_{session_type.lower()}")],
            [InlineKeyboardButton("Close", callback_data="session_close")]
        ])
    )

async def handle_callback_query(client, callback_query):
    data = callback_query.data
    chat_id = callback_query.message.chat.id

    if data.startswith("session_go_"):
        session_type = data.split('_')[2]
        session_data[chat_id] = {"type": session_type}
        await callback_query.message.edit_text(
            "🔹 **अब अपना API ID भेजें:**\n(आप इसे [my.telegram.org](https://my.telegram.org) से प्राप्त कर सकते हैं)",
            parse_mode=ParseMode.HTML
        )
        session_data[chat_id]["stage"] = "api_id"

async def handle_text(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in session_data:
        return

    session = session_data[chat_id]
    stage = session.get("stage")

    if stage == "api_id":
        try:
            api_id = int(message.text)
            session["api_id"] = api_id
            session["stage"] = "api_hash"
            await message.reply("🔹 **अब अपना API Hash भेजें:**")
        except ValueError:
            await message.reply("❌ **Invalid API ID! कृपया सही संख्या दर्ज करें।**")

    elif stage == "api_hash":
        session["api_hash"] = message.text
        session["stage"] = "phone_number"
        await message.reply("📞 **अब अपना फ़ोन नंबर भेजें**\n(Format: `+91XXXXXXXXXX`)")

    elif stage == "phone_number":
        session["phone_number"] = message.text
        await send_otp(client, message)

    elif stage == "otp":
        otp = ''.join(filter(str.isdigit, message.text))
        session["otp"] = otp
        await validate_otp(client, message)

    elif stage == "2fa":
        session["password"] = message.text
        await validate_2fa(client, message)

async def send_otp(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    api_id = session["api_id"]
    api_hash = session["api_hash"]
    phone_number = session["phone_number"]
    telethon = session["type"] == "Telethon"

    if telethon:
        client_obj = TelegramClient(StringSession(), api_id, api_hash)
    else:
        client_obj = Client(":memory:", api_id, api_hash)

    await client_obj.connect()

    try:
        if telethon:
            code = await client_obj.send_code_request(phone_number)
        else:
            code = await client_obj.send_code(phone_number)
        
        session["client_obj"] = client_obj
        session["code"] = code
        session["stage"] = "otp"

        await message.reply("📩 **OTP भेज दिया गया है, कृपया उसे भेजें!**")
    except (ApiIdInvalid, ApiIdInvalidError):
        await message.reply("❌ **Invalid API ID/Hash!**")
    except (PhoneNumberInvalid, PhoneNumberInvalidError):
        await message.reply("❌ **Invalid Phone Number!**")

async def validate_otp(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    phone_number = session["phone_number"]
    otp = session["otp"]
    code = session["code"]
    telethon = session["type"] == "Telethon"

    try:
        if telethon:
            await client_obj.sign_in(phone_number, otp)
        else:
            await client_obj.sign_in(phone_number, code.phone_code_hash, otp)
        
        await generate_session(client, message)
    except (PhoneCodeInvalid, PhoneCodeInvalidError):
        await message.reply("❌ **Invalid OTP!**")
    except (PhoneCodeExpired, PhoneCodeExpiredError):
        await message.reply("❌ **OTP Expired!**")
    except (SessionPasswordNeeded, SessionPasswordNeededError):
        session["stage"] = "2fa"
        await message.reply("🔑 **2FA Enabled! कृपया अपना पासवर्ड भेजें।**")

async def validate_2fa(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    password = session["password"]
    telethon = session["type"] == "Telethon"

    try:
        if telethon:
            await client_obj.sign_in(password=password)
        else:
            await client_obj.check_password(password=password)

        await generate_session(client, message)
    except (PasswordHashInvalid, PasswordHashInvalidError):
        await message.reply("❌ **Invalid Password!**")

async def generate_session(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    telethon = session["type"] == "Telethon"

    if telethon:
        string_session = client_obj.session.save()
    else:
        string_session = await client_obj.export_session_string()

    saved_messages_peer = await client_obj.get_me()
    await client_obj.send_message(saved_messages_peer.id, f"🎉 **Session String:**\n\n`{string_session}`\n\n⚠️ **इसे किसी के साथ साझा न करें!**")

    await message.reply("✅ **Session आपकी 'Saved Messages' में भेज दिया गया है!**")

    await client_obj.disconnect()
    del session_data[chat_id]

# Pyrogram बॉट स्टार्ट करें
app = Client("sessionstring", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
setup_string_handler(app)
app.run()
