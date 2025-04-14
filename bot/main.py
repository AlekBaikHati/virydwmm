import logging
import os
from dotenv import load_dotenv  # Import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import asyncio
import threading
import nest_asyncio
import time  # Import time untuk menghitung uptime
import json
from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient, events
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from asyncio import Lock
from colorama import init, Fore, Style
from bot.utilities.http_server import run_http_server

# Muat variabel lingkungan dari .env
load_dotenv()

# Aktifkan logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Token bot Anda
TOKEN = os.getenv('API_TOKEN')  # Ambil dari .env

# Konfigurasi bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
LEBAR = int(os.getenv("LEBAR"))
TINGGI = int(os.getenv("TINGGI"))
DEFAULT_WATERMARK = os.getenv("DEFAULT_WATERMARK")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Mengakses CHANNEL_ID dari .env

# Cek variabel lingkungan
print("BOT_TOKEN:", BOT_TOKEN)
print("API_ID:", API_ID)

# Membaca caption dari file caption.txt
with open("bot/caption.txt", "r", encoding="utf-8") as file:
    PHOTO_CAPTION = file.read()

# Inisialisasi client bot
app = TelegramClient("my_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)  # Pastikan menggunakan bot_token

TEMP_DIR = "temp_photos"
os.makedirs(TEMP_DIR, exist_ok=True)

user_data = {}
user_locks = {}

def log(message, level="INFO"):
    colors = {
        "INFO": Fore.GREEN,
        "START": Fore.CYAN,
        "END": Fore.MAGENTA,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED
    }
    color = colors.get(level, Fore.WHITE)
    print(f"{color}[{level}] {message}{Style.RESET_ALL}")

# Tambahkan log saat bot pertama kali berjalan
log("「 ✦ BOT AKTIF ✦ 」", "START")

@app.on(events.NewMessage(pattern='/start'))
async def start(event):
    welcome_message = (
        "Selamat datang di Bot Penggabung Foto!\n\n"
        "Bot ini dapat membantu Anda menggabungkan dua foto menjadi satu.\n\n"
        "Berikut adalah perintah yang dapat Anda gunakan:\n"
        "/auto - Kirim dua foto secara berurutan, dan bot akan otomatis menggabungkannya.\n"
        "/manual - Kirim dua foto, lalu klik tombol 'GABUNG' untuk memulai proses penggabungan.\n"
        "/stop - Batalkan semua proses yang sedang berjalan.\n\n"
        "Silakan gunakan perintah di atas untuk mulai!\n"
        "Jika Anda memiliki pertanyaan lebih lanjut, jangan ragu untuk bertanya."
    )
    await event.respond(welcome_message)
    log(f"Pengguna {event.sender_id} memulai bot dengan perintah /start.", "INFO")

@app.on(events.NewMessage(pattern='/auto'))
async def set_auto_mode(event):
    user_id = event.sender_id
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['mode'] = 'auto'
    await event.respond("Mode diatur ke otomatis. Foto akan digabungkan setelah menerima dua foto.")
    log(f"Pengguna {user_id} mengatur mode ke otomatis.", "INFO")

@app.on(events.NewMessage(pattern='/manual'))
async def set_manual_mode(event):
    user_id = event.sender_id
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['mode'] = 'manual'
    await event.respond("Mode diatur ke manual. Anda harus mengklik tombol GABUNG untuk memproses foto.")
    log(f"User {user_id} set mode to manual.", "INFO")

@app.on(events.NewMessage(incoming=True))
async def photo_handler(event):
    if event.photo:  # Pastikan ini adalah foto
        user_id = event.sender_id
        if user_id not in user_locks:
            user_locks[user_id] = Lock()

        async with user_locks[user_id]:
            photo_path = os.path.join(TEMP_DIR, f"{user_id}_{event.photo.id}.jpg")
            await event.download_media(file=photo_path)
            log(f"Foto diterima dari pengguna {user_id} dan disimpan ke {photo_path}.", "INFO")

            if user_id not in user_data:
                user_data[user_id] = {'photos': [], 'mode': 'auto'}
            elif 'photos' not in user_data[user_id]:
                user_data[user_id]['photos'] = []

            user_data[user_id]['photos'].append(photo_path)

            # Jika mode otomatis, tunggu hingga dua foto diterima sebelum memproses
            if user_data[user_id]['mode'] == 'auto':
                if len(user_data[user_id]['photos']) == 2:
                    log("─── ⋆⋅☆MULAI☆⋅⋆ ──", "START")
                    await process_photos(event, user_id)
            elif user_data[user_id]['mode'] == 'manual':
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("GABUNG", callback_data="gabung")],
                    [InlineKeyboardButton("BATAL", callback_data="batal")]
                ])
                # Pastikan menggunakan metode yang benar untuk mengirim pesan
                await app.send_message(event.chat_id, "Foto diterima. Klik tombol GABUNG untuk melanjutkan.", reply_markup=keyboard)

async def process_photos(event, user_id):
    photos = user_data.get(user_id, {}).get('photos', [])
    if not photos:
        await event.respond("Tidak ada foto untuk digabungkan.")
        return

    processing_message = await event.respond("Foto sedang diproses...")
    log(f"Memproses foto untuk pengguna {user_id}.", "INFO")

    output_path = os.path.join(TEMP_DIR, f"{user_id}_output.jpg")
    merge_photos(photos, output_path)
    log(f"Foto digabungkan dan disimpan ke {output_path}.", "INFO")

    await app.send_file(CHANNEL_ID, output_path, caption=PHOTO_CAPTION)
    log(f"Foto dikirim ke channel {CHANNEL_ID}.", "INFO")

    success_message = await event.respond("Foto berhasil digabungkan!")
    log(f"Pesan sukses dikirim ke pengguna {user_id}.", "INFO")

    # Tunggu 5 detik sebelum menghapus pesan
    await asyncio.sleep(5)
    await app.delete_messages(event.chat_id, [processing_message.id, success_message.id])
    log(f"Pesan dihapus untuk pengguna {user_id}.", "INFO")

    for photo in photos:
        if os.path.exists(photo):
            os.remove(photo)
            log(f"Foto sementara {photo} dihapus.", "INFO")

    if os.path.exists(output_path):
        os.remove(output_path)
        log(f"Foto output {output_path} dihapus.", "INFO")
    
    log("─── ⋆⋅☆SELESAI☆⋅⋆ ──", "END")
    user_data[user_id]['photos'] = []

@app.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    if data == "gabung":
        await process_photos(event, user_id)
    elif data == "batal":
        photos = user_data.get(user_id, {}).get('photos', [])
        for photo in photos:
            if os.path.exists(photo):
                os.remove(photo)
                log(f"Deleted temporary photo {photo}.", "WARNING")
        await event.respond("Proses dibatalkan. Silakan kirim foto baru.")
        user_data[user_id]['photos'] = []
        log(f"Proses dibatalkan untuk pengguna {user_id}.", "WARNING")

def merge_photos(photo_paths, output_path, watermark=DEFAULT_WATERMARK):
    num_photos = len(photo_paths)
    individual_width = LEBAR // num_photos
    individual_height = TINGGI

    images = []

    for photo in photo_paths:
        img = Image.open(photo)
        aspect_ratio = img.width / img.height

        if aspect_ratio > 1:
            new_height = individual_height
            new_width = int(aspect_ratio * new_height)
        else:
            new_width = individual_width
            new_height = int(new_width / aspect_ratio)

        img = img.resize((new_width, new_height), Image.LANCZOS)

        if new_width < individual_width:
            scale_factor = individual_width / new_width
            img = img.resize((individual_width, int(new_height * scale_factor)), Image.LANCZOS)
            new_height = int(new_height * scale_factor)
        elif new_height < individual_height:
            scale_factor = individual_height / new_height
            img = img.resize((int(new_width * scale_factor), individual_height), Image.LANCZOS)
            new_width = int(new_width * scale_factor)

        left = max(0, (new_width - individual_width) / 2)
        top = max(0, (new_height - individual_height) / 2)
        right = left + individual_width
        bottom = top + individual_height

        img = img.crop((left, top, right, bottom))
        images.append(img)

    combined_image = Image.new('RGB', (LEBAR, TINGGI))

    x_offset = 0
    for img in images:
        combined_image.paste(img, (x_offset, 0))
        x_offset += img.width

    draw = ImageDraw.Draw(combined_image)

    # Menggunakan font dengan ukuran yang lebih besar
    try:
        font = ImageFont.truetype("arial.ttf", 160)  # Ganti ukuran font sesuai kebutuhan
    except IOError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), watermark, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = (LEBAR - text_width) / 2
    text_y = (TINGGI - text_height) / 2  # Posisikan teks di tengah vertikal
    draw.text((text_x, text_y), watermark, font=font, fill=(255, 255, 255, 128))

    combined_image.save(output_path, format='JPEG', quality=85)

async def main() -> None:
    # Mulai server HTTP di thread terpisah
    threading.Thread(target=run_http_server).start()

##app.add_event_handler(start, events.NewMessage(pattern='/start'))
##app.add_event_handler(set_auto_mode, events.NewMessage(pattern='/auto'))
##app.add_event_handler(set_manual_mode, events.NewMessage(pattern='/manual'))
##app.add_event_handler(photo_handler, events.NewMessage(incoming=True))
##app.add_event_handler(callback_handler, events.CallbackQuery)

    await app.start()  # Memulai bot
    await app.run_until_disconnected()  # Menjalankan bot Telegram

if __name__ == "__main__":
    loop = asyncio.get_event_loop()  # Mendapatkan event loop yang sudah ada
    try:
        loop.run_until_complete(main())  # Menjalankan fungsi main di dalam event loop yang ada
    except KeyboardInterrupt:
        print("Bot dihentikan dengan baik.")
@app.on_message(filters.photo)
async def photo_handler(client, message):
    user_id = message.from_user.id
    if user_id not in user_locks:
        user_locks[user_id] = Lock()

    async with user_locks[user_id]:
        photo_path = os.path.join(TEMP_DIR, f"{user_id}_{message.photo.file_id}.jpg")
        await message.download(file_name=photo_path)

        if user_id not in user_data:
            user_data[user_id] = {'photos': [], 'mode': 'auto'}
        
        user_data[user_id]['photos'].append(photo_path)

        if user_data[user_id]['mode'] == 'auto' and len(user_data[user_id]['photos']) == 2:
            await process_photos(message, user_id)
        elif user_data[user_id]['mode'] == 'manual':
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("GABUNG", callback_data="gabung")],
                [InlineKeyboardButton("BATAL", callback_data="batal")]
            ])
            await message.reply("Foto diterima. Klik tombol GABUNG untuk melanjutkan.", reply_markup=keyboard)

async def process_photos(message, user_id):
    photos = user_data[user_id]['photos']
    output_path = os.path.join(TEMP_DIR, f"{user_id}_output.jpg")
    merge_photos(photos, output_path)

    await app.send_photo(chat_id=CHANNEL_ID, photo=output_path, caption=DEFAULT_WATERMARK)
    await message.reply("Foto berhasil digabungkan!")

    # Hapus foto sementara
    for photo in photos:
        if os.path.exists(photo):
            os.remove(photo)
    user_data[user_id]['photos'] = []

def merge_photos(photo_paths, output_path):
    # Implementasi penggabungan foto
    images = [Image.open(photo) for photo in photo_paths]
    combined_image = Image.new('RGB', (LEBAR, TINGGI))

    x_offset = 0
    for img in images:
        combined_image.paste(img, (x_offset, 0))
        x_offset += img.width

    combined_image.save(output_path)

async def main():
    # Mulai server HTTP di thread terpisah
    asyncio.create_task(run_http_server())

    # Jalankan bot
    await app.start()
    await app.idle()  # Menunggu hingga bot dihentikan

if __name__ == "__main__":
    asyncio.run(main())
