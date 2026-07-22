import asyncio
# 🛠 Патч для сумісності з новішими версіями Python (3.12+)
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified
from yt_dlp import YoutubeDL
from aiohttp import web

# =============================================================
# 🔑 ВАШІ ОФІЦІЙНІ ДАНІ
# =============================================================
API_ID = 27422206
API_HASH = "37295c82175268557acfd8f8f0c5a7e4"
BOT_TOKEN = "8760890214:AAGs0vvMOcPtvASd99RANhOdJm_eutXUWKU"
# =============================================================

logging.basicConfig(level=logging.INFO)

app = Client(
    "unlimited_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_links = {}

# --- ВЕБ-СЕРВЕР ДЛЯ BINDING ПОРТУ НА RENDER ---
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    
    # Render передає свій порт у змінну PORT (за замовчуванням 10000)
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Веб-сервер успішно піднято на порту {port}")

def download_video_sync(url: str, output_path: str, quality_format: str) -> str:
    ydl_opts = {
        'format': quality_format,
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "Привіт! 📥 Я бот для завантаження відео з **YouTube, TikTok та Instagram**.\n\n"
        "Надішли мені посилання на відео, щоб розпочати."
    )

@app.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_url_message(client: Client, message: Message):
    url = message.text.strip()
    user_links[message.from_user.id] = url

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Максимальна (1080p / 4K)", callback_data="q_max"),
            InlineKeyboardButton("🎬 HD (720p)", callback_data="q_720")
        ],
        [
            InlineKeyboardButton("📱 SD (480p)", callback_data="q_480"),
            InlineKeyboardButton("🎵 Тільки Аудіо (MP3)", callback_data="q_mp3")
        ]
    ])
    await message.reply_text("Обери бажану якість завантаження:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^q_"))
async def process_quality_selection(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    url = user_links.get(user_id)

    if not url:
        try:
            await callback.message.edit_text("❌ Помилка: Посилання застаріло. Надішли його ще раз.")
        except MessageNotModified:
            pass
        return

    quality_code = callback.data.split("_")[1]

    if quality_code == "max":
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        quality_label = "Максимальна"
        ext = "mp4"
    elif quality_code == "720":
        fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        quality_label = "720p"
        ext = "mp4"
    elif quality_code == "480":
        fmt = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
        quality_label = "480p"
        ext = "mp4"
    else:
        fmt = "bestaudio/best"
        quality_label = "MP3 Аудіо"
        ext = "mp3"

    status_msg = await callback.message.edit_text(f"⏳ Завантажую ({quality_label})... Зачекай трохи.")
    file_path = f"download_{user_id}_{callback.message.id}.{ext}"

    try:
        await asyncio.to_thread(download_video_sync, url, file_path, fmt)

        if os.path.exists(file_path):
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            try:
                await status_msg.edit_text(f"📤 Відправляю у Telegram ({file_size_mb:.1f} МБ)...")
            except MessageNotModified:
                pass

            if ext == "mp3":
                await client.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=file_path,
                    caption=f"✅ Завантажено у якості: {quality_label}"
                )
            else:
                await client.send_video(
                    chat_id=callback.message.chat.id,
                    video=file_path,
                    caption=f"✅ Завантажено у якості: {quality_label}"
                )
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Не вдалося зберегти файл.")

    except Exception as e:
        logging.error(f"Помилка: {e}")
        try:
            await status_msg.edit_text(f"❌ Помилка при завантаженні: {e}")
        except MessageNotModified:
            pass

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def main():
    await start_web_server()
    await app.start()
    logging.info("Бот успішно запущений!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
