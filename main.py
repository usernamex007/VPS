import requests
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
    ApiIdInvalidError, PhoneNumberInvalidError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, SessionPasswordNeededError, PasswordHashInvalidError
)
from asyncio.exceptions import TimeoutError
from config import API_ID, API_HASH, BOT_TOKEN

# Timeout Constants
TIMEOUT_OTP = 600  # 10 minutes
TIMEOUT_2FA = 300  # 5 minutes

session_data = {}

def setup_string_handler(app: Client):
    @app.on_message(filters.command(["pyro", "tele"], prefixes=["/", "."]) & filters.private)
    async def session_setup(client, message: Message):
        platform = "PyroGram" if message.command[0] == "pyro" else "Telethon"
        await handle_start(client, message, platform)

    @app.on_callback_query(filters.regex(r"^session_"))
    async def callback_query_handler(client, callback_query):
        await handle_callback_query(client, callback_query)

    @app.on_message(filters.text & filters.create(lambda _, __, message: message.chat.id in session_data))
    async def text_handler(client, message: Message):
        await handle_text(client, message)

async def handle_start(client, message, platform):
    session_type = "Telethon" if platform == "Telethon" else "Pyrogram"
    session_data[message.chat.id] = {"type": session_type}
    await message.reply(
        f"Welcome to the {session_type} session setup!\n"
        "━━━━━━━━━━━━━━━━━\n"
        "This is a totally safe session string generator. We don't save any info that you will provide, so this is completely safe.\n\n"
        "Note: Don't send OTP directly. Otherwise, your account could be banned, or you may not be able to log in.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Go", callback_data=f"session_go_{session_type.lower()}"),
            InlineKeyboardButton("Close", callback_data="session_close")
        ]])
    )

async def handle_callback_query(client, callback_query):
    data = callback_query.data
    chat_id = callback_query.message.chat.id

    if data == "session_close":
        platform = session_data[chat_id]["type"].lower()
        await callback_query.message.edit_text(f"**Cancelled. You can start by sending /{platform}**")
        session_data.pop(chat_id, None)
        return

    if data.startswith("session_go_"):
        session_type = data.split('_')[2]
        await callback_query.message.edit_text(
            "<b>Send Your API ID</b>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Resume", callback_data=f"session_resume_{session_type}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.HTML
        )
        session_data[chat_id]["stage"] = "api_id"

    if data.startswith("session_resume_"):
        session_type = data.split('_')[2]
        await handle_start(client, callback_query.message, platform=session_type.capitalize())

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
            await message.reply(
                "<b>Send Your API Hash</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Resume", callback_data=f"session_resume_{session['type'].lower()}"),
                    InlineKeyboardButton("Close", callback_data="session_close")
                ]]),
                parse_mode=ParseMode.HTML
            )
            session["stage"] = "api_hash"
        except ValueError:
            await message.reply("Invalid API ID. Please enter a valid integer.")

    elif stage == "api_hash":
        session["api_hash"] = message.text
        await message.reply(
            "<b>Send Your Phone Number\n[Example: +880xxxxxxxxxx]</b>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Resume", callback_data=f"session_resume_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.HTML
        )
        session["stage"] = "phone_number"

    elif stage == "phone_number":
        session["phone_number"] = message.text
        otp_message = await message.reply("Sending OTP.....")
        await send_otp(client, message, otp_message)

    elif stage == "otp":
        session["otp"] = ''.join([char for char in message.text if char.isdigit()])
        otp_message = await message.reply("Validating OTP.....")
        await validate_otp(client, message, otp_message)

    elif stage == "2fa":
        session["password"] = message.text
        await validate_2fa(client, message)

async def send_otp(client, message, otp_message):
    session = session_data[message.chat.id]
    api_id, api_hash, phone_number = session["api_id"], session["api_hash"], session["phone_number"]
    telethon = session["type"] == "Telethon"

    client_obj = TelegramClient(StringSession(), api_id, api_hash) if telethon else Client(":memory:", api_id, api_hash)
    await client_obj.connect()

    try:
        session["client_obj"] = client_obj
        session["code"] = await client_obj.send_code_request(phone_number) if telethon else await client_obj.send_code(phone_number)
        session["stage"] = "otp"
        await message.reply("<b>Send The OTP as text. Example: 'AB5 CD0 EF3 GH7 IJ6'</b>")
    except Exception as e:
        await message.reply(f"Error: {e}")
        session_data.pop(message.chat.id, None)

async def validate_otp(client, message, otp_message):
    session = session_data[message.chat.id]
    client_obj, phone_number, otp, code = session["client_obj"], session["phone_number"], session["otp"], session["code"]
    telethon = session["type"] == "Telethon"

    try:
        await client_obj.sign_in(phone_number, otp) if telethon else await client_obj.sign_in(phone_number, code.phone_code_hash, otp)
        await generate_session(client, message)
    except Exception as e:
        await message.reply(f"Error: {e}")
        session_data.pop(message.chat.id, None)

async def generate_session(client, message):
    session = session_data[message.chat.id]
    client_obj = session["client_obj"]
    string_session = client_obj.session.save() if session["type"] == "Telethon" else await client_obj.export_session_string()

    await client_obj.send_message("me", f"**{session['type'].upper()} SESSION**:\n\n`{string_session}`")
    await client_obj.disconnect()
    await message.reply("<b>Session saved in your Saved Messages ✅</b>")
    session_data.pop(message.chat.id, None)

# Pyrogram Client
app = Client("sessionstring", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
setup_string_handler(app)
app.run()
