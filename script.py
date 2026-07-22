import asyncio
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified, RPCError
from aiohttp import web

# =============================================================
# 🔑 ВАШІ ОФІЦІЙНІ ДАНІ
# =============================================================
API_ID = 27422206
API_HASH = "37295c82175268557acfd8f8f0c5a7e4"
BOT_TOKEN = "8760890214:AAGs0vvMOcPtvASd99RANhOdJm_eutXUWKU"
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Використовуємо нове ім'я сесії v2, щоб уникнути конфліктів авторизації
app = Client(
    "downloader_render_v2",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_links = {}


# --- ВЕБ-СЕРВЕР ДЛЯ BINDING ПОРТУ НА RENDER ---
async def handle_ping(request):
    return web.Response(text="Bot is online and running!")


async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 Веб-сервер піднято на порту {port}")


# --- АСИНХРОННЕ ЗАВАНТАЖЕННЯ ЧЕРЕЗ CLI YT-DLP ---
async def download_media(url: str, output_template: str, fmt: str) -> bool:
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "-o", output_template,
        "--no-warnings",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        url
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logging.error(f"Помилка yt-dlp: {stderr.decode()}")
        return False
    return True


# --- ОБРОБНИКИ КОМАНД TELEGRAM ---

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "Привіт! 📥 Я готовий завантажувати відео з **YouTube, TikTok, Instagram**.\n\n"
        "Надішли мені посилання на відео!"
    )


@app.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_url(client: Client, message: Message):
    url = message.text.strip()
    user_links[message.from_user.id] = url

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Максимальна (1080p/4K)", callback_data="q_max"),
            InlineKeyboardButton("🎬 HD (720p)", callback_data="q_720")
        ],
        [
            InlineKeyboardButton("📱 SD (480p)", callback_data="q_480"),
            InlineKeyboardButton("🎵 Тільки MP3", callback_data="q_mp3")
        ]
    ])
    await message.reply_text("Обери якість для завантаження:", reply_markup=keyboard)


@app.on_callback_query(filters.regex(r"^q_"))
async def process_quality(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    url = user_links.get(user_id)

    if not url:
        try:
            await callback.message.edit_text("❌ Посилання застаріло. Надішли його ще раз.")
        except MessageNotModified:
            pass
        return

    quality_code = callback.data.split("_")[1]

    if quality_code == "max":
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        label = "Максимальна"
        ext = "mp4"
    elif quality_code == "720":
        fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        label = "720p"
        ext = "mp4"
    elif quality_code == "480":
        fmt = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
        label = "480p"
        ext = "mp4"
    else:
        fmt = "bestaudio/best"
        label = "MP3"
        ext = "mp3"

    try:
        status_msg = await callback.message.edit_text(f"⏳ Завантажую ({label})... Зачекай.")
    except MessageNotModified:
        status_msg = callback.message

    filename_base = f"file_{user_id}_{callback.message.id}"
    output_template = f"{filename_base}.%(ext)s"

    try:
        success = await download_media(url, output_template, fmt)

        # Шукаємо завантажений файл
        downloaded_file = None
        for f in os.listdir("."):
            if f.startswith(filename_base):
                downloaded_file = f
                break

        if success and downloaded_file and os.path.exists(downloaded_file):
            size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)

            if size_mb > 2000:  # Ліміт Telegram 2 ГБ
                await status_msg.edit_text("❌ Файл занадто великий для відправки в Telegram (> 2GB).")
                os.remove(downloaded_file)
                return

            try:
                await status_msg.edit_text(f"📤 Відправляю у чат ({size_mb:.1f} МБ)...")
            except MessageNotModified:
                pass

            if downloaded_file.endswith(".mp3") or quality_code == "mp3":
                await client.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=downloaded_file,
                    caption=f"✅ Завантажено у якості: {label}"
                )
            else:
                await client.send_video(
                    chat_id=callback.message.chat.id,
                    video=downloaded_file,
                    caption=f"✅ Завантажено у якості: {label}"
                )

            await status_msg.delete()
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
        else:
            try:
                await status_msg.edit_text("❌ Помилка завантаження. Перевірте посилання або спробуйте іншу якість.")
            except MessageNotModified:
                pass

    except RPCError as e:
        logging.error(f"Помилка Telegram API: {e}")
    except Exception as e:
        logging.error(f"Загальна помилка: {e}")
        try:
            await status_msg.edit_text(f"❌ Виникла помилка: {e}")
        except MessageNotModified:
            pass
    finally:
        # Прибирання залишків файлів
        for f in os.listdir("."):
            if f.startswith(filename_base) and os.path.exists(f):
                os.remove(f)


async def main():
    await start_web_server()
    await app.start()
    logging.info("🚀 Бот повністю запущений і готовий до роботи!")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())