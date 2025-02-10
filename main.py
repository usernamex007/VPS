import asyncio
from pyrogram import Client, filters
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
from config import API_ID, API_HASH, BOT_TOKEN

# Dictionary to store session data
session_data = {}

app = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command(["start", "pyro", "tele"]) & filters.private)
async def start(client, message):
    command = message.command[0]
    chat_id = message.chat.id

    if command == "start":
        await message.reply("Welcome! Use /pyro for Pyrogram session or /tele for Telethon session.")
        return

    session_type = "Telethon" if command == "tele" else "Pyrogram"
    session_data[chat_id] = {"type": session_type}
    
    await message.reply(f"🔹 Generating {session_type} session...\nEnter your API ID:")

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    chat_id = message.chat.id
    if chat_id not in session_data:
        return

    session = session_data[chat_id]
    stage = session.get("stage", "api_id")

    if stage == "api_id":
        try:
            session["api_id"] = int(message.text)
            session["stage"] = "api_hash"
            await message.reply("Enter your API Hash:")
        except ValueError:
            await message.reply("Invalid API ID. Please enter a valid integer.")

    elif stage == "api_hash":
        session["api_hash"] = message.text
        session["stage"] = "phone_number"
        await message.reply("Enter your phone number (e.g., +91XXXXXXXXXX):")

    elif stage == "phone_number":
        session["phone_number"] = message.text
        await message.reply("Sending OTP...")
        await send_otp(client, message)

    elif stage == "otp":
        session["otp"] = message.text.replace(" ", "")
        await message.reply("Validating OTP...")
        await validate_otp(client, message)

    elif stage == "2fa":
        session["password"] = message.text
        await validate_2fa(client, message)

async def send_otp(client, message):
    session = session_data[message.chat.id]
    api_id, api_hash, phone_number = session["api_id"], session["api_hash"], session["phone_number"]
    is_telethon = session["type"] == "Telethon"

    client_obj = TelegramClient(StringSession(), api_id, api_hash) if is_telethon else Client(":memory:", api_id, api_hash)
    await client_obj.connect()

    try:
        if is_telethon:
            code = await client_obj.send_code_request(phone_number)
        else:
            code = await client_obj.send_code(phone_number)

        print(f"DEBUG: OTP Code Response = {code}")  # Debugging Line

        session["client_obj"] = client_obj
        session["code"] = code  # FIX: अब session में code स्टोर हो रहा है
        session["stage"] = "otp"

        await message.reply("Enter the OTP you received:")
    except (ApiIdInvalid, ApiIdInvalidError, PhoneNumberInvalid, PhoneNumberInvalidError):
        await message.reply("Invalid API ID or Phone Number. Please restart the process.")
        session_data.pop(message.chat.id, None)

async def validate_otp(client, message):
    session = session_data[message.chat.id]
    client_obj, phone_number, otp = session["client_obj"], session["phone_number"], session["otp"]
    is_telethon = session["type"] == "Telethon"

    try:
        if is_telethon:
            await client_obj.sign_in(phone_number, otp)
        else:
            await client_obj.sign_in(phone_number, session["code"].phone_code_hash, otp)
        await generate_session(client, message)
    except (PhoneCodeInvalid, PhoneCodeInvalidError, PhoneCodeExpired, PhoneCodeExpiredError):
        await message.reply("Invalid or expired OTP. Please restart the process.")
        session_data.pop(message.chat.id, None)
    except (SessionPasswordNeeded, SessionPasswordNeededError):
        session["stage"] = "2fa"
        await message.reply("2FA detected! Enter your password:")

async def validate_2fa(client, message):
    session = session_data[message.chat.id]
    client_obj, password = session["client_obj"], session["password"]
    is_telethon = session["type"] == "Telethon"

    try:
        if is_telethon:
            await client_obj.sign_in(password=password)
        else:
            await client_obj.check_password(password=password)
        await generate_session(client, message)
    except (PasswordHashInvalid, PasswordHashInvalidError):
        await message.reply("Incorrect password! Please restart the process.")
        session_data.pop(message.chat.id, None)

async def generate_session(client, message):
    session = session_data[message.chat.id]
    client_obj, is_telethon = session["client_obj"], session["type"] == "Telethon"

    string_session = client_obj.session.save() if is_telethon else await client_obj.export_session_string()
    await client_obj.send_message("me", f"Your {session['type']} session:\n\n`{string_session}`\n\nSave it securely!")
    await client_obj.disconnect()

    await message.reply("Session generated! Check your Saved Messages.")
    session_data.pop(message.chat.id, None)

app.run()
