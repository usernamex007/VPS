import requests
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatType
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.sessions import StringSession
from pyrogram.errors import *
from telethon.errors import *
from asyncio.exceptions import TimeoutError
from config import API_ID, API_HASH, BOT_TOKEN

# Constants for timeouts
TIMEOUT_OTP = 600  # 10 minutes
TIMEOUT_2FA = 300  # 5 minutes

session_data = {}

def setup_string_handler(app: Client):
    @app.on_message(filters.command(["pyro", "tele"]) & filters.private)
    async def session_setup(client, message: Message):
        platform = "PyroGram" if message.command[0] == "pyro" else "Telethon"
        await start_session(client, message, platform)

    @app.on_callback_query(filters.regex(r"^session_(go|resume|close)_"))
    async def callback_handler(client, callback_query):
        await handle_callback_query(client, callback_query)

    @app.on_message(filters.text & filters.private)
    async def text_handler(client, message: Message):
        await handle_text(client, message)

async def start_session(client, message, platform):
    chat_id = message.chat.id
    session_data[chat_id] = {"type": platform, "stage": "start"}

    await message.reply(
        f"**Welcome to the {platform} Session Generator!**\n"
        "Follow the steps to generate your session string safely.\n\n"
        "**Click 'Go' to start!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Go", callback_data=f"session_go_{platform.lower()}")],
            [InlineKeyboardButton("Close", callback_data="session_close")]
        ])
    )

async def handle_callback_query(client, callback_query):
    chat_id = callback_query.message.chat.id
    data = callback_query.data.split("_")

    if data[1] == "close":
        await callback_query.message.edit_text("Session generation cancelled.")
        session_data.pop(chat_id, None)
        return

    if chat_id not in session_data:
        return

    session = session_data[chat_id]
    session_type = session["type"].lower()

    if data[1] in ["go", "resume"]:
        session["stage"] = "api_id"
        await callback_query.message.edit_text(
            "Please send your **API ID** (from my.telegram.org):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="session_close")]
            ])
        )

async def handle_text(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in session_data:
        return

    session = session_data[chat_id]
    stage = session["stage"]

    if stage == "api_id":
        try:
            session["api_id"] = int(message.text)
            session["stage"] = "api_hash"
            await message.reply("Now send your **API Hash**:")
        except ValueError:
            await message.reply("Invalid API ID! Please send a valid number.")

    elif stage == "api_hash":
        session["api_hash"] = message.text
        session["stage"] = "phone_number"
        await message.reply("Now send your **Phone Number** (with country code, e.g., +91xxxxxxxxxx):")

    elif stage == "phone_number":
        session["phone_number"] = message.text
        await message.reply("Sending OTP...")
        await send_otp(client, message)

    elif stage == "otp":
        otp = ''.join(filter(str.isdigit, message.text))
        if otp:
            session["otp"] = otp
            await validate_otp(client, message)
        else:
            await message.reply("Invalid OTP format! Please send only numbers.")

    elif stage == "2fa":
        session["password"] = message.text
        await validate_2fa(client, message)

async def send_otp(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    telethon = session["type"] == "Telethon"

    try:
        if telethon:
            client_obj = TelegramClient(StringSession(), session["api_id"], session["api_hash"])
        else:
            client_obj = Client(":memory:", session["api_id"], session["api_hash"])

        await client_obj.connect()
        session["client_obj"] = client_obj

        if telethon:
            session["code"] = await client_obj.send_code_request(session["phone_number"])
        else:
            session["code"] = await client_obj.send_code(session["phone_number"])

        session["stage"] = "otp"
        await message.reply("Please send the OTP you received on Telegram.")

    except (ApiIdInvalidError, PhoneNumberInvalidError) as e:
        await message.reply(f"Error: {str(e)}\n\nRestart the session generation.")
        session_data.pop(chat_id, None)

async def validate_otp(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    telethon = session["type"] == "Telethon"

    try:
        if telethon:
            await client_obj.sign_in(session["phone_number"], session["otp"])
        else:
            await client_obj.sign_in(session["phone_number"], session["code"].phone_code_hash, session["otp"])

        await generate_session(client, message)

    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        await message.reply("Invalid or expired OTP. Restart the session generation.")
        session_data.pop(chat_id, None)

    except SessionPasswordNeededError:
        session["stage"] = "2fa"
        await message.reply("Enter your 2FA password:")

async def validate_2fa(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    telethon = session["type"] == "Telethon"

    try:
        if telethon:
            await client_obj.sign_in(password=session["password"])
        else:
            await client_obj.check_password(session["password"])

        await generate_session(client, message)

    except PasswordHashInvalidError:
        await message.reply("Incorrect password. Restart the session generation.")
        session_data.pop(chat_id, None)

async def generate_session(client, message):
    chat_id = message.chat.id
    session = session_data[chat_id]
    client_obj = session["client_obj"]
    telethon = session["type"] == "Telethon"

    if telethon:
        session_string = client_obj.session.save()
    else:
        session_string = await client_obj.export_session_string()

    await client_obj.send_message("me", f"**Your {session['type']} Session:**\n\n`{session_string}`\n\nGenerated by @ItsSmartToolBot")
    await client_obj.disconnect()
    session_data.pop(chat_id, None)

    await message.reply("✅ Your session string has been saved in your 'Saved Messages'.")

# Initialize the Pyrogram Client
app = Client("sessionstring", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

setup_string_handler(app)
app.run()
