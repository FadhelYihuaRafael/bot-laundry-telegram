import os
import sys
import re
import telebot
from dotenv import load_dotenv

# Konfigurasi console encoding agar aman di Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Muat file .env jika ada
load_dotenv()

# Token Bot
CUSTOMER_BOT_TOKEN = os.environ.get("CUSTOMER_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN", "").strip()

# Konfigurasi Admin & AI
ADMIN_PIN = os.environ.get("ADMIN_PIN", "freshclean88").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
PORT = int(os.environ.get("PORT", 10000))

# Path Data Penyimpanan
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")
CONFIG_FILE = os.path.join(BASE_DIR, "admin_config.json")

# Status Pengerjaan Laundry
STATUS_LIST = {
    "menunggu": "Menunggu Penjemputan / Konfirmasi",
    "dijemput": "Sedang Dijemput Kurir",
    "dicuci": "Sedang Dicuci & Dikeringkan",
    "setrika": "Sedang Disetrika & Dipacking Rapi",
    "siap": "Cucian Siap Diantar / Diambil",
    "selesai": "Pesanan Selesai (Diterima)",
    "dibatalkan": "Pesanan Dibatalkan"
}

STATUS_EMOJIS = {
    "menunggu": "⏳",
    "dijemput": "🛵",
    "dicuci": "🧼",
    "setrika": "♨️",
    "siap": "📦",
    "selesai": "✅",
    "dibatalkan": "❌"
}

# Inisialisasi Instance TeleBot
customer_bot = telebot.TeleBot(CUSTOMER_BOT_TOKEN) if CUSTOMER_BOT_TOKEN else None
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN) if ADMIN_BOT_TOKEN else None

def clean_markdown(text):
    """Menghapus karakter markdown yang sering membuat Telegram error jika tidak seimbang"""
    if not text:
        return ""
    # Hapus asterisks, underscores, dan backticks berlebih
    return text.replace("`", "'").replace("*", "").replace("_", "")

def safe_send(bot_instance, chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Mengirim pesan dengan fallback aman jika parsing entity Markdown gagal"""
    if not bot_instance or not chat_id:
        return None
    try:
        return bot_instance.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        # Fallback kirim plain text jika ada karakter Markdown yang rusak
        clean_text = clean_markdown(text)
        try:
            return bot_instance.send_message(chat_id, clean_text, reply_markup=reply_markup)
        except Exception as err2:
            print(f"[ERROR] Gagal kirim pesan ke {chat_id}: {err2}", flush=True)
            return None
