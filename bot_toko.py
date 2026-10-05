import csv
import io
import json
import os
import random
import sys
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# Muat konfigurasi dari file .env lokal jika tersedia
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Konfigurasi encoding konsol agar aman di Windows
if sys.platform.startswith("win"):
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==========================================
# KONFIGURASI BOT & ADMIN
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8925512883:AAHvOTZmJ0i0WOgvmO6KGYfWqrbmCBuuQ-g")

# PIN Rahasia untuk mendaftarkan/mengubah akun Admin (Bisa diubah lewat env atau langsung di sini)
ADMIN_PIN = os.getenv("ADMIN_PIN", "freshclean88")

# API Key untuk Google Gemini AI (Terintegrasi resmi untuk kecerdasan AI Admin & Pelanggan)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6IF2W2zj9UGPaPSvzZmny0dcpzKGaldlgUdcwhfbd3r6A")

# File untuk menyimpan ID Admin agar tidak hilang saat bot restart
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "admin_config.json")

# File untuk menyimpan semua data pesanan laundry
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

# Lock untuk keamanan akses concurrent file JSON
orders_lock = threading.Lock()
config_lock = threading.Lock()

def load_admin_id():
    """Memuat ID Admin dari environment variable, file konfigurasi, atau fallback ID pemilik asli"""
    env_id = os.getenv("ADMIN_CHAT_ID")
    if env_id:
        try:
            return int(env_id)
        except ValueError:
            pass
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_chat_id", 1335564018)
        except Exception:
            return 1335564018
    return 1335564018

def save_admin_id(admin_id):
    """Menyimpan ID Admin ke file konfigurasi secara aman"""
    with config_lock:
        try:
            temp_file = CONFIG_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"admin_chat_id": admin_id}, f, indent=4)
            if os.path.exists(CONFIG_FILE):
                os.replace(temp_file, CONFIG_FILE)
            else:
                os.rename(temp_file, CONFIG_FILE)
            return True
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan admin ID: {e}", flush=True)
            return False

def load_orders():
    """Memuat semua data pesanan laundry dari file JSON"""
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_orders(orders_dict):
    """Menyimpan semua data pesanan laundry ke file JSON secara aman dan atomik"""
    with orders_lock:
        try:
            temp_file = ORDERS_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(orders_dict, f, indent=4, ensure_ascii=False)
            if os.path.exists(ORDERS_FILE):
                os.replace(temp_file, ORDERS_FILE)
            else:
                os.rename(temp_file, ORDERS_FILE)
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan data pesanan: {e}", flush=True)

# Inisialisasi Bot & Admin Chat ID
bot = telebot.TeleBot(BOT_TOKEN)
ADMIN_CHAT_ID = load_admin_id()

# Muat data pesanan yang tersimpan
all_orders = load_orders()

# Draft siaran pesan broadcast sementara
broadcast_draft = {}

# Status pengerjaan laundry yang valid
STATUS_LIST = {
    "menunggu": "⏳ Menunggu Penjemputan / Diterima di Outlet",
    "dicuci": "🧺 Sedang Dicuci & Dikeringkan",
    "disetrika": "👔 Sedang Disetrika & Packing Rapi",
    "siap_antar": "🛵 Selesai & Siap Diantar / Diambil",
    "selesai": "✅ Cucian Selesai & Diterima Pelanggan",
    "dibatalkan": "❌ Pesanan Dibatalkan"
}


# Tempat penyimpanan sementara sesi formulir pemesanan laundry
user_orders = {}


# ==========================================
# KEYBOARD / MENU INTERAKTIF
# ==========================================
def main_menu(is_admin=False):
    """Menu Utama Bot Laundry (dilengkapi tombol khusus admin jika yang membuka adalah Admin)"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_tarif = types.InlineKeyboardButton("🧺 Layanan & Tarif", callback_data="menu_tarif")
    btn_order = types.InlineKeyboardButton("🛵 Pesan Laundry / Jemput", callback_data="mulai_order")
    btn_cek_status = types.InlineKeyboardButton("🔍 Cek Status Cucian", callback_data="cek_status_pesanan")
    btn_promo = types.InlineKeyboardButton("✨ Keunggulan & Promo", callback_data="menu_keunggulan")
    btn_lokasi = types.InlineKeyboardButton("📍 Lokasi & Jam Buka", callback_data="menu_lokasi")
    btn_kontak = types.InlineKeyboardButton("📞 Hubungi Admin / CS", callback_data="menu_kontak")
    
    markup.add(btn_tarif, btn_order)
    markup.add(btn_cek_status, btn_promo)
    markup.add(btn_lokasi, btn_kontak)

    # Menu Khusus Eksklusif Pemilik / Admin Toko
    if is_admin:
        btn_admin = types.InlineKeyboardButton("👑 Panel Kontrol Admin", callback_data="buka_panel_admin")
        btn_tanya = types.InlineKeyboardButton("🤖 Tanya Asisten Cerdas", callback_data="buka_asisten_admin")
        markup.add(btn_admin, btn_tanya)

    return markup

def back_to_main_menu(is_admin=False):
    """Tombol kembali ke menu utama"""
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_utama")
    markup.add(btn_back)
    if is_admin:
        btn_admin = types.InlineKeyboardButton("👑 Panel Admin", callback_data="buka_panel_admin")
        markup.add(btn_admin)
    return markup

def cancel_order_markup():
    """Tombol batal saat proses pengisian data order"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn_cancel = types.KeyboardButton("❌ Batal Pesan")
    btn_home = types.KeyboardButton("🚀 /start")
    markup.row(btn_cancel, btn_home)
    return markup

def persistent_menu_markup(is_admin=False):
    """Keyboard menu tombol cepat di bagian bawah chat Telegram yang dipisahkan antara Admin dan User"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin:
        btn_start = types.KeyboardButton("🚀 /start")
        btn_admin = types.KeyboardButton("👑 /admin")
        btn_rekap = types.KeyboardButton("📊 /rekap")
        btn_tanya = types.KeyboardButton("💬 /tanya")
        markup.row(btn_start, btn_admin)
        markup.row(btn_rekap, btn_tanya)
    else:
        btn_start = types.KeyboardButton("🚀 /start")
        btn_order = types.KeyboardButton("🛵 Pesan Laundry")
        btn_tarif = types.KeyboardButton("🧺 Daftar Tarif")
        btn_status = types.KeyboardButton("🔍 Cek Status Cucian")
        markup.row(btn_start, btn_order)
        markup.row(btn_tarif, btn_status)
    return markup

def setup_bot_commands():
    """Mendaftarkan tombol menu perintah dan identitas bot (Nama & Deskripsi Laundry) ke Telegram"""
    try:
        # Atur Nama & Deskripsi Bot agar sesuai FreshClean Laundry
        try:
            bot.set_my_name(name="FreshClean Laundry Bot 🧺")
            bot.set_my_description(description="🧺 Selamat datang di FreshClean Laundry!\n\nLayanan cuci kiloan, satuan (bed cover, jas, selimut), sepatu, dan tas. Dilengkapi layanan antar-jemput cepat langsung ke rumah atau kost Anda!\n\nKlik START untuk melihat daftar tarif atau memesan.")
            bot.set_my_short_description(short_description="🧺 Bot resmi FreshClean Laundry. Cuci Kiloan, Satuan & Antar-Jemput Praktis!")
        except Exception:
            pass

        commands = [
            types.BotCommand("start", "🚀 Mulai / Menu Utama"),
            types.BotCommand("order", "🛵 Pesan Laundry / Jemput Cucian"),
            types.BotCommand("tarif", "🧺 Daftar Layanan & Tarif"),
            types.BotCommand("cekpesanan", "🔍 Cek Status Pengerjaan Cucian"),
            types.BotCommand("tanya", "🤖 Tanya Asisten Cerdas AI / CS"),
            types.BotCommand("myid", "🆔 ID Telegram Saya"),
            types.BotCommand("admin", "👑 Panel Kontrol Admin"),
            types.BotCommand("export", "📥 Unduh Rekap CSV (Admin)"),
            types.BotCommand("broadcast", "📢 Kirim Pengumuman (Admin)")
        ]
        bot.set_my_commands(commands)
        try:
            bot.set_chat_menu_button(menu_button=types.MenuButtonCommands(type="commands"))
        except Exception:
            pass
        print("[INFO] Identitas bot dan menu perintah Telegram berhasil didaftarkan.", flush=True)
    except Exception as e:
        print(f"[WARN] Gagal mendaftarkan menu perintah bot: {e}", flush=True)

def estimasi_berat_markup():
    """Pilihan cepat estimasi berat / jumlah cucian"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("👕 Sekitar 2 - 3 Kg", callback_data="estimasi_2-3 Kg")
    btn2 = types.InlineKeyboardButton("👕 Sekitar 4 - 6 Kg", callback_data="estimasi_4-6 Kg")
    btn3 = types.InlineKeyboardButton("👕 Di atas 7 Kg", callback_data="estimasi_Lebih dari 7 Kg")
    btn4 = types.InlineKeyboardButton("⚖️ Belum tahu (Timbang Kurir)", callback_data="estimasi_Ditimbang di tempat")
    btn_batal = types.InlineKeyboardButton("❌ Batal Pesan", callback_data="batalkan_order")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn_batal)
    return markup

def metode_layanan_markup():
    """Pilihan metode antar jemput atau drop ke outlet"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_jemput = types.InlineKeyboardButton("🛵 Antar-Jemput (Kurir jemput ke rumah/kost)", callback_data="metode_Antar-Jemput Kurir")
    btn_outlet = types.InlineKeyboardButton("🏪 Antar Sendiri ke Outlet Laundry", callback_data="metode_Antar Sendiri ke Outlet")
    btn_batal = types.InlineKeyboardButton("❌ Batal Pesan", callback_data="batalkan_order")
    markup.add(btn_jemput, btn_outlet, btn_batal)
    return markup


# ==========================================
# HANDLER COMMAND & TOMBOL CEPAT (/start, /order, /tarif, dll)
# ==========================================
@bot.message_handler(commands=['start', 'menu'])
@bot.message_handler(func=lambda msg: (msg.text or "").strip() in ["🚀 /start", "🧺 Menu Utama", "Menu Utama", "Mulai", "/start", "start"])
def send_welcome(message):
    user_name = message.from_user.first_name
    is_admin = (message.chat.id == ADMIN_CHAT_ID)

    if is_admin:
        welcome_text = (
            f"Halo, *{user_name}*! 👋 Selamat datang di *FreshClean Laundry* 🧺✨\n\n"
            "👑 *STATUS ANDA: PEMILIK / ADMIN UTAMA TOKO*\n"
            "─────────────────────────\n"
            "Bot siap membantu operasional toko Anda hari ini:\n"
            "• Terima & proses pesanan masuk\n"
            "• Pantau antrean & tahapan cucian (`/admin`)\n"
            "• Tanya Asisten Cerdas toko apa saja (`/tanya`)\n\n"
            "Silakan pilih menu khusus di bawah ini:"
        )
    else:
        welcome_text = (
            f"Halo, *{user_name}*! 👋 Selamat datang di *FreshClean Laundry* 🧺✨\n\n"
            "Solusi cucian bersih, wangi, higienis, dan rapi tanpa repot! "
            "Kami melayani cuci kiloan, satuan (bed cover, jas, selimut), sepatu, hingga *layanan antar-jemput langsung ke rumah/kost Anda*.\n\n"
            "Silakan pilih menu di bawah ini untuk melihat daftar tarif atau langsung pesan penjemputan cucian:\n\n"
            "💡 *Tips:* Anda bisa klik tombol menu di keyboard bawah layar kapan saja tanpa perlu mengetik!"
        )

    # Aktifkan tombol keyboard cepat di layar bawah sesuai role
    bot.send_message(
        message.chat.id,
        "✨ _Menu navigasi telah disesuaikan._",
        parse_mode="Markdown",
        reply_markup=persistent_menu_markup(is_admin=is_admin)
    )
    # Kirim menu utama interaktif
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode="Markdown", 
        reply_markup=main_menu(is_admin=is_admin)
    )

@bot.message_handler(commands=['order', 'pesan'])
@bot.message_handler(func=lambda msg: (msg.text or "").strip() in ["🛵 Pesan Laundry", "Pesan Laundry"])
def order_command(message):
    """Memulai pemesanan laundry"""
    start_order_process(message.chat.id, message.from_user.username)

@bot.message_handler(commands=['tarif', 'layanan'])
@bot.message_handler(func=lambda msg: (msg.text or "").strip() in ["🧺 Daftar Tarif", "Daftar Tarif", "Tarif"])
def tarif_command(message):
    """Melihat daftar tarif laundry"""
    send_tarif_message(message.chat.id)

@bot.message_handler(func=lambda msg: (msg.text or "").strip() in ["🔍 Cek Status Cucian", "Cek Status Cucian", "Cek Status"])
def status_quick_button(message):
    """Tombol cepat cek status cucian dari keyboard bawah"""
    msg = bot.send_message(
        message.chat.id,
        "🔍 *CEK STATUS PENGERJAAN CUCIAN*\n"
        "─────────────────────────\n"
        "Masukkan *Nomor Nota / ID Pesanan* Anda:\n"
        "Contoh: `LDR-1234`\n\n"
        "_(Ketik 'batal' atau klik '🚀 /start' untuk kembali)_",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, step_cek_status)

@bot.message_handler(commands=['myid'])
def show_my_id(message):
    """Menampilkan Telegram Chat ID pengguna"""
    chat_id = message.chat.id
    bot.reply_to(
        message, 
        f"🆔 ID Telegram Anda: `{chat_id}`\n\n"
        "Jika Anda pemilik laundry, Anda dapat mengetik `/setadmin` untuk mendaftarkan akun ini sebagai penerima pesanan masuk.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['setadmin'])
def set_admin_handler(message):
    """Mendaftarkan atau mengubah akun admin dengan proteksi PIN rahasia"""
    global ADMIN_CHAT_ID
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    parts = message.text.strip().split()

    # Cek apakah user menyertakan PIN rahasia
    if len(parts) < 2:
        bot.reply_to(
            message,
            "🔒 *AKSES DITOLAK: Perintah ini dilindungi PIN Rahasia!*\n\n"
            "Format yang benar:\n"
            "`/setadmin [PIN_RAHASIA]`\n\n"
            "Contoh: `/setadmin freshclean88`",
            parse_mode="Markdown"
        )
        if ADMIN_CHAT_ID and chat_id != ADMIN_CHAT_ID:
            try:
                bot.send_message(
                    ADMIN_CHAT_ID,
                    f"⚠️ *PERINGATAN KEAMANAN!*\n"
                    f"Seseorang mencoba menjalankan `/setadmin` tanpa PIN:\n"
                    f"• Nama: {user_name}\n"
                    f"• User ID: `{chat_id}`\n"
                    f"• Username: @{message.from_user.username or '-'}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        return

    input_pin = parts[1]
    if input_pin != ADMIN_PIN:
        bot.reply_to(
            message,
            "❌ *PIN SALAH!*\n"
            "Akses ditolak. Percobaan tidak sah ini telah dicatat sistem keamanan bot.",
            parse_mode="Markdown"
        )
        if ADMIN_CHAT_ID and chat_id != ADMIN_CHAT_ID:
            try:
                bot.send_message(
                    ADMIN_CHAT_ID,
                    f"🚨 *PERINGATAN KEAMANAN: PERCOBAAN AKSES ADMIN ILEGAL!*\n"
                    f"Seseorang memasukkan PIN yang salah pada `/setadmin`:\n"
                    f"• Nama: {user_name}\n"
                    f"• User ID: `{chat_id}`\n"
                    f"• Username: @{message.from_user.username or '-'}\n"
                    f"• PIN yang dicoba: `{input_pin}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        return

    # Jika PIN Benar
    ADMIN_CHAT_ID = chat_id
    save_admin_id(ADMIN_CHAT_ID)
    bot.reply_to(
        message,
        f"✅ *Autentikasi Admin Berhasil!*\n\n"
        f"Halo *{user_name}*, akun Telegram Anda (`{ADMIN_CHAT_ID}`) sekarang resmi terverifikasi sebagai *Admin FreshClean Laundry* 👑.\n\n"
        "Gunakan perintah `/admin` atau `/rekap` untuk membuka Panel Kontrol Admin!",
        parse_mode="Markdown"
    )
    print(f"[INFO] Admin Laundry berhasil diset ke Chat ID: {ADMIN_CHAT_ID} ({user_name})", flush=True)


def admin_panel_markup():
    """Menu tombol interaktif khusus Panel Kontrol Admin"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_export = types.InlineKeyboardButton("📥 Unduh Rekap CSV", callback_data="admin_export_csv")
    btn_filter = types.InlineKeyboardButton("📋 Filter Antrean", callback_data="admin_filter_antrean")
    btn_broadcast = types.InlineKeyboardButton("📢 Siaran Promo", callback_data="admin_start_broadcast")
    btn_refresh = types.InlineKeyboardButton("🔄 Refresh Panel", callback_data="buka_panel_admin")
    markup.add(btn_export, btn_filter)
    markup.add(btn_broadcast, btn_refresh)
    return markup

def generate_orders_csv():
    """Menghasilkan teks CSV dari seluruh riwayat data pesanan"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID Nota", "Waktu", "Nama Pelanggan", "No WhatsApp", "Username Telegram",
        "Paket Layanan", "Estimasi", "Berat Riil", "Total Tagihan (Rp)",
        "Status Pembayaran", "Status Cucian", "Rating", "Metode", "Alamat", "Catatan"
    ])
    for oid, o in all_orders.items():
        writer.writerow([
            oid,
            o.get("waktu", "-"),
            o.get("nama", "-"),
            o.get("hp", "-"),
            o.get("buyer_username", "-"),
            o.get("layanan", "-"),
            o.get("estimasi", "-"),
            o.get("berat_riil", "-"),
            o.get("total_bayar", "-"),
            o.get("status_bayar", "Belum Lunas"),
            STATUS_LIST.get(o.get("status", ""), o.get("status", "-")),
            f"{o.get('rating', '-')} Bintang" if o.get('rating') else "-",
            o.get("metode", "-"),
            o.get("alamat", "-"),
            o.get("catatan", "-")
        ])
    return output.getvalue()

def send_orders_csv(chat_id):
    """Mengirim file CSV rekap data transaksi ke Admin"""
    csv_text = generate_orders_csv()
    csv_bytes = io.BytesIO(csv_text.encode("utf-8-sig"))
    filename = f"Rekap_FreshClean_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    csv_bytes.name = filename
    total_nota = len(all_orders)
    total_omset = sum(int(o.get("total_bayar", 0)) for o in all_orders.values() if isinstance(o.get("total_bayar"), (int, float)))
    caption = (
        f"📊 *REKAP DATA TRANSAKSI FRESHCLEAN LAUNDRY*\n"
        f"─────────────────────────\n"
        f"• Total Seluruh Nota : *{total_nota} nota*\n"
        f"• Total Omset Tercatat: *Rp {total_omset:,}*\n\n"
        "💡 _File `.csv` ini di-encode dengan UTF-8 BOM sehingga dapat langsung dibuka rapi di Microsoft Excel atau Google Sheets tanpa teks berantakan._"
    )
    bot.send_document(chat_id, csv_bytes, caption=caption, parse_mode="Markdown")

@bot.message_handler(commands=['export', 'download', 'csv'])
def export_command(message):
    """Handler perintah /export untuk download laporan rekap CSV"""
    chat_id = message.chat.id
    if chat_id != ADMIN_CHAT_ID:
        bot.reply_to(message, "⛔ Perintah ini hanya dapat diakses oleh Admin Laundry.", parse_mode="Markdown")
        return
    send_orders_csv(chat_id)

@bot.message_handler(commands=['broadcast', 'siaran', 'promo'])
def broadcast_command(message):
    """Handler perintah /broadcast untuk mengirim pesan ke seluruh pelanggan"""
    chat_id = message.chat.id
    if chat_id != ADMIN_CHAT_ID:
        bot.reply_to(message, "⛔ Perintah ini hanya dapat diakses oleh Admin Laundry.", parse_mode="Markdown")
        return
    start_broadcast_prompt(chat_id)

@bot.message_handler(commands=['admin', 'rekap', 'panel'])
def admin_panel_handler(message):
    """Panel kontrol khusus admin untuk memantau status antrean cucian"""
    chat_id = message.chat.id
    if chat_id != ADMIN_CHAT_ID:
        bot.reply_to(
            message,
            "⛔ *Akses Ditolak!*\n"
            "Perintah ini hanya dapat diakses oleh Admin Resmi FreshClean Laundry.",
            parse_mode="Markdown"
        )
        return

    # Hitung statistik order
    total_orders = len(all_orders)
    menunggu_count = sum(1 for o in all_orders.values() if o.get("status") == "menunggu")
    dicuci_count = sum(1 for o in all_orders.values() if o.get("status") == "dicuci")
    disetrika_count = sum(1 for o in all_orders.values() if o.get("status") == "disetrika")
    siap_antar_count = sum(1 for o in all_orders.values() if o.get("status") == "siap_antar")
    selesai_count = sum(1 for o in all_orders.values() if o.get("status") == "selesai")

    # Ambil antrean pengerjaan terkini
    active_orders = [o for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"]]
    active_orders_sorted = sorted(active_orders, key=lambda x: x.get("waktu", ""), reverse=True)[:5]

    order_list_text = ""
    if active_orders_sorted:
        order_list_text = "\n📋 *Antrean Pengerjaan Terkini (Maks. 5):*\n"
        for o in active_orders_sorted:
            st = STATUS_LIST.get(o.get("status", ""), o.get("status", ""))
            tagihan = f" (Rp {o.get('total_bayar', 0):,})" if o.get('total_bayar') else ""
            order_list_text += f"• `{o.get('order_id')}` | {o.get('nama')} ({o.get('layanan')}){tagihan}\n  └ Status: _{st}_\n"
    else:
        order_list_text = "\n🎉 *Tidak ada antrean cucian aktif saat ini.*"

    admin_panel_text = (
        "👑 *PANEL KONTROL ADMIN - FRESHCLEAN LAUNDRY*\n"
        "─────────────────────────\n"
        f"📊 *Ringkasan Status Seluruh Cucian:*\n"
        f"• ⏳ Menunggu Jemput/Outlet : *{menunggu_count}*\n"
        f"• 🧺 Sedang Dicuci          : *{dicuci_count}*\n"
        f"• 👔 Sedang Disetrika       : *{disetrika_count}*\n"
        f"• 🛵 Siap Diantar / Diambil : *{siap_antar_count}*\n"
        f"• ✅ Selesai                : *{selesai_count}*\n"
        f"• 📦 Total Seluruh Nota     : *{total_orders}*\n"
        "─────────────────────────"
        f"{order_list_text}\n\n"
        "💡 *Menu Aksi Admin:*\n"
        "Pilih salah satu tombol di bawah untuk mengunduh laporan, memfilter antrean, atau menyiarkan promo:"
    )

    bot.send_message(chat_id, admin_panel_text, parse_mode="Markdown", reply_markup=admin_panel_markup())



# ==========================================
# HELPER TAMPILAN TARIF
# ==========================================
def get_tarif_text_and_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_p1 = types.InlineKeyboardButton("👕 Pesan Cuci Komplit Reguler (Rp 7.000/kg)", callback_data="order_paket_Cuci Komplit Reguler (2 Hari)")
    btn_p2 = types.InlineKeyboardButton("⚡ Pesan Cuci Kilat Express 1 Hari (Rp 10.000/kg)", callback_data="order_paket_Cuci Kilat Express 24 Jam")
    btn_p3 = types.InlineKeyboardButton("🚀 Pesan Super Express 6 Jam (Rp 15.000/kg)", callback_data="order_paket_Cuci Super Express 6 Jam")
    btn_p4 = types.InlineKeyboardButton("♨️ Pesan Cuci Kering / Setrika Saja", callback_data="order_paket_Cuci Kering / Setrika Saja")
    btn_p5 = types.InlineKeyboardButton("🛏️ Pesan Satuan (Bed Cover / Selimut / Jas)", callback_data="order_paket_Cuci Satuan (Bed Cover/Jas/Dll)")
    btn_p6 = types.InlineKeyboardButton("👟 Pesan Cuci Sepatu (Deep Clean)", callback_data="order_paket_Cuci Sepatu Deep Clean")
    btn_custom = types.InlineKeyboardButton("📝 Pesanan Lainnya / Campuran", callback_data="mulai_order")
    btn_back = types.InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_utama")
    
    markup.add(btn_p1, btn_p2, btn_p3, btn_p4, btn_p5, btn_p6, btn_custom, btn_back)

    tarif_text = (
        "🧺 *DAFTAR LAYANAN & TARIF FRESHCLEAN LAUNDRY*\n"
        "─────────────────────────\n\n"
        "✨ *1. CUCI KILOAN (Cuci + Kering + Setrika + Parfum Premium)*\n"
        "• *Reguler (2 Hari):* Rp 7.000 / kg\n"
        "• *Express (1 Hari / 24 Jam):* Rp 10.000 / kg\n"
        "• *Super Express (6 Jam Selesai):* Rp 15.000 / kg\n"
        "• *Setrika Uap Saja (2 Hari):* Rp 4.500 / kg\n"
        "• *Cuci Lipat (Tanpa Setrika):* Rp 5.000 / kg\n\n"
        "🛏️ *2. CUCI SATUAN & RUMAH TANGGA*\n"
        "• Bed Cover Single: Rp 20.000 / pcs\n"
        "• Bed Cover Double / Jumbo: Rp 30.000 / pcs\n"
        "• Selimut Tebal: Rp 18.000 / pcs\n"
        "• Jas / Blazer (Dry Clean): Rp 25.000 / pcs\n"
        "• Gorden / Karpet: Rp 15.000 - Rp 25.000 / m²\n\n"
        "👟 *3. LAUNDRY SEPATU & TAS*\n"
        "• Sneakers / Flat Shoes: Rp 25.000 / pasang\n"
        "• Deep Clean & Unyellowing: Rp 35.000 / pasang\n"
        "• Tas / Ransel: Rp 20.000 - Rp 35.000 / pcs\n\n"
        "─────────────────────────\n"
        "🛵 *Gratis Antar-Jemput* untuk area radius 3 km (min. 5 kg)!\n"
        "💡 *Pilih paket di bawah untuk langsung memesan / request penjemputan:*"
    )
    return tarif_text, markup

def send_tarif_message(chat_id):
    tarif_text, markup = get_tarif_text_and_markup()
    bot.send_message(chat_id, tarif_text, parse_mode="Markdown", reply_markup=markup)


# ==========================================
# HELPER OPERASIONAL LAUNDRY & ADMIN
# ==========================================
def step_admin_tanya(message):
    """Handler input pertanyaan khusus admin"""
    if is_cancelled(message):
        bot.send_message(message.chat.id, "Sesi tanya asisten ditutup.", reply_markup=persistent_menu_markup(is_admin=True))
        return
    process_query(message, message.text.strip(), is_admin=True)

def ask_billing_input(chat_id, order_id):
    """Meminta Admin memasukkan berat riil dan total tagihan untuk nota"""
    order = all_orders.get(order_id)
    if not order:
        bot.send_message(chat_id, f"⚠️ Nota {order_id} tidak ditemukan.")
        return
    msg = bot.send_message(
        chat_id,
        f"⚖️ *INPUT TIMBANGAN & TAGIHAN: `{order_id}`*\n"
        f"─────────────────────────\n"
        f"👤 Pelanggan: *{order.get('nama')}*\n"
        f"🧺 Layanan: *{order.get('layanan')}*\n\n"
        "Silakan ketik berat riil cucian & total tagihan (pisahkan dengan spasi):\n"
        "• Format: `[Berat_Kg] [Total_Rp]`\n"
        "• Contoh: `3.5 24500` (artinya 3.5 Kg, total Rp 24.500)\n"
        "• Atau cukup ketik beratnya saja: `3.5` (sistem otomatis menghitung tarif standar paketnya)\n\n"
        "_(Ketik 'batal' untuk membatalkan)_",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, lambda m: step_process_billing(m, order_id))

def step_process_billing(message, order_id):
    """Memproses input berat dan menerbitkan nota digital ke pelanggan"""
    chat_id = message.chat.id
    text = (message.text or "").strip()
    if is_cancelled(message):
        bot.send_message(chat_id, "Input tagihan dibatalkan.", reply_markup=persistent_menu_markup(is_admin=True))
        return

    order = all_orders.get(order_id)
    if not order:
        bot.send_message(chat_id, f"⚠️ Nota {order_id} tidak ditemukan.", reply_markup=persistent_menu_markup(is_admin=True))
        return

    parts = text.replace(",", ".").split()
    try:
        berat_val = float(parts[0])
        berat_str = f"{berat_val} Kg"
        if len(parts) >= 2:
            clean_digits = "".join(filter(str.isdigit, parts[1]))
            total_bayar = int(clean_digits) if clean_digits else int(berat_val * 7000)
        else:
            layanan_lower = order.get("layanan", "").lower()
            if "super express" in layanan_lower or "6 jam" in layanan_lower:
                rate = 15000
            elif "express" in layanan_lower or "24 jam" in layanan_lower:
                rate = 10000
            elif "lipat" in layanan_lower:
                rate = 5000
            elif "setrika" in layanan_lower:
                rate = 4500
            else:
                rate = 7000
            total_bayar = int(round(berat_val * rate))
    except Exception:
        msg = bot.send_message(
            chat_id,
            "⚠️ Format tidak valid. Silakan masukkan angka berat (contoh: `3.5`) atau dengan harga (contoh: `3.5 24500`):",
            parse_mode="Markdown",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, lambda m: step_process_billing(m, order_id))
        return

    order["berat_riil"] = berat_str
    order["total_bayar"] = total_bayar
    order["status_bayar"] = "Belum Lunas"
    save_orders(all_orders)

    bot.send_message(
        chat_id,
        f"✅ *Tagihan Nota `{order_id}` Berhasil Diterbitkan!*\n\n"
        f"• Pelanggan : *{order.get('nama')}*\n"
        f"• Berat Riil: *{berat_str}*\n"
        f"• Total Tagihan : *Rp {total_bayar:,}*\n"
        f"• Status Bayar : ⏳ Belum Lunas\n\n"
        "Rincian nota digital & instruksi pembayaran telah dikirimkan otomatis ke pelanggan.",
        parse_mode="Markdown",
        reply_markup=persistent_menu_markup(is_admin=True)
    )

    buyer_id = order.get("buyer_chat_id")
    if buyer_id:
        try:
            invoice_text = (
                "🧾 *NOTA RINCIAN & TAGIHAN CUCIAN*\n"
                "─────────────────────────\n"
                f"Halo Kak *{order.get('nama')}*! Cucian Anda telah selesai ditimbang di FreshClean Laundry:\n\n"
                f"🆔 *No. Nota:* `{order_id}`\n"
                f"🧺 *Layanan:* {order.get('layanan')}\n"
                f"⚖️ *Berat Riil Cucian:* *{berat_str}*\n"
                f"💵 *TOTAL TAGIHAN:* *Rp {total_bayar:,}*\n"
                f"📊 *Status Pembayaran:* ⏳ *Belum Lunas*\n"
                "─────────────────────────\n"
                "💳 *METODE PEMBAYARAN:*\n"
                "1. 📲 *QRIS:* Scan dari m-Banking BCA/Mandiri/GoPay/OVO/DANA/ShopeePay\n"
                "2. 🏦 *Transfer BCA:* `1234567890` a/n *FreshClean Laundry*\n"
                "3. 💵 *Tunai (COD):* Bayar tunai saat kurir mengantar cucian Anda\n\n"
                "Jika Anda transfer atau bayar via QRIS, silakan klik tombol *📸 Kirim Bukti Transfer* di bawah untuk upload foto bukti struk:"
            )
            inv_markup = types.InlineKeyboardMarkup(row_width=1)
            btn_proof = types.InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data=f"kirim_bukti_{order_id}")
            btn_menu = types.InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_utama")
            inv_markup.add(btn_proof, btn_menu)
            bot.send_message(buyer_id, invoice_text, parse_mode="Markdown", reply_markup=inv_markup)
        except Exception as e:
            print(f"[ERROR] Gagal mengirim tagihan ke pelanggan {buyer_id}: {e}", flush=True)

def prompt_upload_proof(chat_id, order_id):
    """Meminta pelanggan mengunggah foto bukti transfer"""
    order = all_orders.get(order_id)
    if not order:
        bot.send_message(chat_id, f"⚠️ Nota {order_id} tidak ditemukan.")
        return
    msg = bot.send_message(
        chat_id,
        f"📸 *KIRIM BUKTI PEMBAYARAN*\n"
        f"─────────────────────────\n"
        f"🆔 *No. Nota:* `{order_id}`\n"
        f"💵 *Total Tagihan:* *Rp {order.get('total_bayar', 0):,}*\n\n"
        "Silakan *kirim FOTO / SCREENSHOT bukti transfer* Anda ke chat ini sekarang:\n\n"
        "_(Ketik 'batal' untuk membatalkan)_",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, lambda m: step_receive_payment_proof(m, order_id))

def step_receive_payment_proof(message, order_id):
    """Menerima foto bukti pembayaran dan meneruskannya ke admin"""
    chat_id = message.chat.id
    if is_cancelled(message):
        bot.send_message(chat_id, "Pengiriman bukti transfer dibatalkan.", reply_markup=persistent_menu_markup())
        return

    order = all_orders.get(order_id)
    if not order:
        bot.send_message(chat_id, f"⚠️ Nota {order_id} tidak ditemukan.", reply_markup=persistent_menu_markup())
        return

    if not message.photo:
        msg = bot.send_message(
            chat_id,
            "⚠️ Anda belum mengirim foto. Mohon kirimkan gambar/foto screenshot bukti transfer:",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, lambda m: step_receive_payment_proof(m, order_id))
        return

    photo_id = message.photo[-1].file_id
    order["status_bayar"] = "Menunggu Verifikasi"
    save_orders(all_orders)

    bot.send_message(
        chat_id,
        f"✅ *Bukti Pembayaran Berhasil Dikirim!*\n\n"
        f"Terima kasih Kak *{order.get('nama')}*. Bukti transfer untuk nota `{order_id}` sedang diverifikasi oleh Admin FreshClean. "
        "Kami akan mengirimkan notifikasi saat pembayaran telah terkonfirmasi lunas. ✨",
        parse_mode="Markdown",
        reply_markup=persistent_menu_markup()
    )

    if ADMIN_CHAT_ID:
        try:
            admin_mk = types.InlineKeyboardMarkup(row_width=1)
            btn_verify = types.InlineKeyboardButton("✅ Konfirmasi Pembayaran Lunas", callback_data=f"admin_lunas_{order_id}")
            admin_mk.add(btn_verify)
            caption = (
                f"💳 *BUKTI PEMBAYARAN MASUK!* 📸\n"
                f"─────────────────────────\n"
                f"• No. Nota: `{order_id}`\n"
                f"• Pelanggan: *{order.get('nama')}* (@{order.get('buyer_username', '-')})\n"
                f"• Total Tagihan: *Rp {order.get('total_bayar', 0):,}*\n"
                f"• Status Bayar: *Menunggu Verifikasi*\n\n"
                "Silakan periksa mutasi rekening Anda, lalu klik tombol di bawah untuk verifikasi:"
            )
            bot.send_photo(ADMIN_CHAT_ID, photo_id, caption=caption, parse_mode="Markdown", reply_markup=admin_mk)
        except Exception as e:
            print(f"[ERROR] Gagal meneruskan foto bukti ke admin: {e}", flush=True)

def start_broadcast_prompt(chat_id):
    """Memulai proses broadcast pesan promo"""
    msg = bot.send_message(
        chat_id,
        "📢 *KIRIM SIARAN PROMO / PENGUMUMAN*\n"
        "─────────────────────────\n"
        "Ketik teks pesan promosi atau pengumuman yang ingin dikirimkan ke SEMUA pelanggan bot.\n\n"
        "_(Ketik 'batal' untuk membatalkan)_",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, step_receive_broadcast_draft)

def step_receive_broadcast_draft(message):
    """Menyimpan draft dan meminta konfirmasi sebelum siaran dikirim"""
    chat_id = message.chat.id
    if is_cancelled(message):
        bot.send_message(chat_id, "Siaran pesan dibatalkan.", reply_markup=persistent_menu_markup(is_admin=True))
        return

    text = message.text.strip()
    broadcast_draft[chat_id] = text

    preview = (
        "📢 *PREVIEW PESAN SIARAN:*\n"
        "─────────────────────────\n"
        f"{text}\n"
        "─────────────────────────\n"
        "Kirimkan pesan siaran ini ke seluruh pelanggan sekarang?"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_send = types.InlineKeyboardButton("🚀 Kirim Sekarang", callback_data="confirm_broadcast")
    btn_cancel = types.InlineKeyboardButton("❌ Batal", callback_data="cancel_broadcast")
    markup.add(btn_send, btn_cancel)

    bot.send_message(chat_id, preview, parse_mode="Markdown", reply_markup=markup)



# ==========================================
# HANDLER CALLBACK QUERY (Navigasi Tombol)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    global ADMIN_CHAT_ID
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # 1. Menu Utama
    if call.data == "menu_utama":
        is_adm = (chat_id == ADMIN_CHAT_ID)
        welcome_text = "Silakan pilih layanan yang Anda butuhkan di bawah ini:"
        bot.edit_message_text(
            welcome_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=main_menu(is_admin=is_adm)
        )

    # Handler tombol khusus admin dari menu utama
    elif call.data == "buka_panel_admin":
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "⛔ Khusus Admin Toko", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        admin_panel_handler(call.message)

    elif call.data == "buka_asisten_admin":
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "⛔ Khusus Admin Toko", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            chat_id,
            "💬 *Halo Admin FreshClean!* 🤖\n\n"
            "Ketik pertanyaan apa saja untuk Asisten Toko (misal: cari pelanggan, cek noda, omset, atau template WA):",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, step_admin_tanya)

    # 2. Menu Tarif & Layanan
    elif call.data == "menu_tarif":
        tarif_text, markup = get_tarif_text_and_markup()
        bot.edit_message_text(
            tarif_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # 3. Mulai Order dari Pilihan Paket Spesifik
    elif call.data.startswith("order_paket_"):
        paket_name = call.data.replace("order_paket_", "")
        user_orders[chat_id] = {
            "layanan": paket_name,
            "username": call.from_user.username or "-",
            "user_id": chat_id
        }
        
        bot.send_message(
            chat_id,
            f"🧺 Anda memilih: *{paket_name}*\n\n"
            "Berapa estimasi berat atau jumlah cucian Anda?\n"
            "_(Pilih tombol di bawah atau ketik langsung, misal: `5 kg` atau `1 bed cover`)_",
            parse_mode="Markdown",
            reply_markup=estimasi_berat_markup()
        )

    # 4. Handler Estimasi Berat dari Tombol Cepat
    elif call.data.startswith("estimasi_"):
        estimasi_val = call.data.replace("estimasi_", "")
        if chat_id not in user_orders:
            user_orders[chat_id] = {
                "layanan": "Cuci Reguler",
                "username": call.from_user.username or "-",
                "user_id": chat_id
            }
        user_orders[chat_id]["estimasi"] = estimasi_val

        bot.send_message(
            chat_id,
            f"⚖️ Estimasi Cucian: *{estimasi_val}*\n\n"
            "🛵 *Pilih Metode Penyerahan Cucian:*",
            parse_mode="Markdown",
            reply_markup=metode_layanan_markup()
        )

    # 5. Handler Metode Antar-Jemput vs Ke Outlet
    elif call.data.startswith("metode_"):
        metode_val = call.data.replace("metode_", "")
        if chat_id not in user_orders:
            bot.send_message(chat_id, "⚠️ Sesi pemesanan telah kedaluwarsa. Silakan mulai kembali dari menu utama.", reply_markup=main_menu())
            bot.answer_callback_query(call.id)
            return

        user_orders[chat_id]["metode"] = metode_val

        msg = bot.send_message(
            chat_id,
            f"🛵 Metode: *{metode_val}*\n\n"
            "👤 *LANGKAH 1/4 - IDENTITAS PELANGGAN*\n"
            "─────────────────────────\n"
            "Silakan masukkan *Nama Lengkap Anda*:\n\n"
            "_(Ketik 'batal' jika ingin membatalkan)_",
            parse_mode="Markdown",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, step_input_nama)

    # 6. Mulai Order Umum / Kustom
    elif call.data == "mulai_order":
        start_order_process(chat_id, call.from_user.username)

    # 7. Konfirmasi Order: Kirim ke Admin Laundry
    elif call.data == "konfirmasi_kirim_order":
        order_data = user_orders.get(chat_id)
        if not order_data:
            bot.send_message(chat_id, "⚠️ Sesi pemesanan telah selesai atau kedaluwarsa. Silakan buat pesanan baru dari menu utama.", reply_markup=main_menu())
            bot.answer_callback_query(call.id)
            return

        order_id = f"LDR-{random.randint(1000, 9999)}"
        waktu_sekarang = datetime.now().strftime("%d-%m-%Y %H:%M WIB")

        # 1. Pesan Konfirmasi untuk Pelanggan
        buyer_confirm_text = (
            "🎉 *PESANAN LAUNDRY BERHASIL DIBUAT!*\n"
            "─────────────────────────\n"
            f"🆔 *No. Nota / Pesanan:* `{order_id}`\n"
            f"⏱️ *Waktu Pemesanan:* {waktu_sekarang}\n\n"
            f"🧺 *Layanan:* {order_data.get('layanan', '-')}\n"
            f"⚖️ *Estimasi:* {order_data.get('estimasi', '-')}\n"
            f"🛵 *Metode:* {order_data.get('metode', 'Antar-Jemput')}\n"
            f"👤 *Nama:* {order_data['nama']}\n"
            f"📱 *WhatsApp:* {order_data['hp']}\n"
            f"📍 *Alamat / Lokasi:* {order_data['alamat']}\n"
            f"📝 *Catatan:* {order_data.get('catatan', '-')}\n\n"
            "─────────────────────────\n"
            "✨ *Status Saat Ini:* `⏳ Menunggu Penjemputan / Diterima`\n\n"
            "Terima kasih telah mempercayakan cucian Anda kepada *FreshClean Laundry*! 🧺\n"
            "Tim / Kurir kami akan segera menghubungi Anda melalui WhatsApp atau Telegram untuk konfirmasi penjemputan cucian."
        )
        bot.edit_message_text(
            buyer_confirm_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=back_to_main_menu()
        )

        # 2. Pesan Notifikasi untuk Admin Laundry
        admin_notif_text = (
            "🔔 *PESANAN LAUNDRY BARU MASUK!* 🔔\n"
            "─────────────────────────\n"
            f"🆔 *ID Nota:* `{order_id}`\n"
            f"⏱️ *Waktu:* {waktu_sekarang}\n\n"
            f"👤 *Pelanggan:* {order_data['nama']}\n"
            f"✈️ *Telegram:* @{order_data['username']} (ID: `{chat_id}`)\n"
            f"📱 *No. WhatsApp:* {order_data['hp']}\n\n"
            f"🧺 *Paket Layanan:* {order_data.get('layanan', '-')}\n"
            f"⚖️ *Estimasi Berat/Pcs:* {order_data.get('estimasi', '-')}\n"
            f"🛵 *Metode:* {order_data.get('metode', 'Antar-Jemput')}\n"
            f"📍 *Alamat Jemput/Kirim:*\n{order_data['alamat']}\n\n"
            f"📝 *Catatan Tambahan:* {order_data.get('catatan', '-')}\n"
            "─────────────────────────\n"
            "Silakan hubungi pelanggan atau perbarui status pengerjaan cucian di bawah:"
        )

        # Simpan pesanan ke database JSON
        all_orders[order_id] = {
            "order_id": order_id,
            "buyer_chat_id": chat_id,
            "buyer_username": order_data["username"],
            "nama": order_data["nama"],
            "hp": order_data["hp"],
            "layanan": order_data.get("layanan", "-"),
            "estimasi": order_data.get("estimasi", "-"),
            "metode": order_data.get("metode", "-"),
            "alamat": order_data["alamat"],
            "catatan": order_data.get("catatan", "-"),
            "waktu": waktu_sekarang,
            "status": "menunggu"
        }
        save_orders(all_orders)

        # Tombol aksi bagi Admin (WhatsApp + Input Tagihan + Update Tahapan Laundry)
        admin_markup = types.InlineKeyboardMarkup(row_width=1)
        clean_phone = "".join(filter(str.isdigit, order_data['hp']))
        if clean_phone.startswith("0"):
            clean_phone = "62" + clean_phone[1:]
        elif not clean_phone.startswith("62") and clean_phone:
            clean_phone = "62" + clean_phone

        if clean_phone:
            btn_wa_buyer = types.InlineKeyboardButton("💬 Chat Pelanggan via WhatsApp", url=f"https://wa.me/{clean_phone}")
            admin_markup.add(btn_wa_buyer)

        btn_bill = types.InlineKeyboardButton("⚖️ Input Berat Riil & Buat Tagihan", callback_data=f"admin_bill_{order_id}")
        btn_st_cuci = types.InlineKeyboardButton("🧺 Tandai: Sedang Dicuci", callback_data=f"admin_status_{order_id}_dicuci")
        btn_st_setrika = types.InlineKeyboardButton("👔 Tandai: Sedang Disetrika & Packing", callback_data=f"admin_status_{order_id}_disetrika")
        btn_st_siap = types.InlineKeyboardButton("🛵 Tandai: Siap Diantar / Diambil", callback_data=f"admin_status_{order_id}_siap_antar")
        btn_st_selesai = types.InlineKeyboardButton("✅ Tandai: Cucian Selesai", callback_data=f"admin_status_{order_id}_selesai")
        btn_st_batal = types.InlineKeyboardButton("❌ Batalkan Pesanan", callback_data=f"admin_status_{order_id}_dibatalkan")
        admin_markup.add(btn_bill, btn_st_cuci, btn_st_setrika, btn_st_siap, btn_st_selesai, btn_st_batal)

        # Kirim ke Admin jika ID admin sudah diset
        if ADMIN_CHAT_ID and ADMIN_CHAT_ID != 0:
            try:
                bot.send_message(ADMIN_CHAT_ID, admin_notif_text, parse_mode="Markdown", reply_markup=admin_markup)
                print(f"[INFO] Notifikasi laundry {order_id} berhasil dikirim ke Admin ({ADMIN_CHAT_ID})", flush=True)
            except Exception as e:
                print(f"[ERROR] Gagal mengirim notifikasi ke Admin ID {ADMIN_CHAT_ID}: {e}", flush=True)
        else:
            print(f"[PERINGATAN] Pesanan {order_id} masuk, tapi ADMIN_CHAT_ID belum diset! Ketik /setadmin di Telegram untuk mendaftarkan akun admin.", flush=True)

        # Bersihkan data sesi
        user_orders.pop(chat_id, None)

    # 8. Batalkan Order
    elif call.data == "batalkan_order":
        user_orders.pop(chat_id, None)
        bot.edit_message_text(
            "❌ Pemesanan laundry telah dibatalkan.\n\nSilakan pilih menu di bawah jika ingin menjelajahi layanan kami kembali:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=main_menu()
        )

    # 9. Cek Status Cucian (dipicu dari tombol menu)
    elif call.data == "cek_status_pesanan":
        msg = bot.send_message(
            chat_id,
            "🔍 *CEK STATUS PENGERJAAN CUCIAN*\n"
            "─────────────────────────\n"
            "Masukkan *Nomor Nota / ID Pesanan* Anda:\n"
            "Contoh: `LDR-1234`\n\n"
            "_(Ketik 'batal' untuk kembali ke menu)_",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, step_cek_status)

    # 10. Admin Update Status Laundry
    elif call.data.startswith("admin_status_"):
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Hanya Admin Laundry yang bisa mengubah status cucian.", show_alert=True)
            return

        # Format: admin_status_{order_id}_{new_status}
        parts = call.data.replace("admin_status_", "").rsplit("_", 1)
        if len(parts) != 2:
            bot.answer_callback_query(call.id, "Format status tidak valid.", show_alert=True)
            return

        target_order_id, new_status = parts[0], parts[1]

        if target_order_id not in all_orders:
            bot.answer_callback_query(call.id, f"Nota laundry {target_order_id} tidak ditemukan.", show_alert=True)
            return

        # Update status
        all_orders[target_order_id]["status"] = new_status
        save_orders(all_orders)

        status_label = STATUS_LIST.get(new_status, new_status)
        order_rec = all_orders[target_order_id]

        # Konfirmasi ke Admin
        bot.answer_callback_query(call.id, f"Status {target_order_id} diperbarui: {status_label}", show_alert=True)
        bot.send_message(
            chat_id,
            f"✅ Status cucian *{target_order_id}* milik *{order_rec['nama']}* berhasil diupdate ke:\n👉 *{status_label}*",
            parse_mode="Markdown"
        )

        # Kirim notifikasi update otomatis ke Pelanggan
        buyer_id = order_rec.get("buyer_chat_id")
        if buyer_id:
            try:
                notif_msg = (
                    "🧺 *UPDATE STATUS PENGERJAAN CUCIAN ANDA*\n"
                    "─────────────────────────\n"
                    f"Halo Kak *{order_rec['nama']}*, status cucian Anda diperbarui:\n\n"
                    f"🆔 *No. Nota:* `{target_order_id}`\n"
                    f"🧺 *Layanan:* {order_rec.get('layanan', '-')}\n\n"
                    f"📊 *Status Terkini:*\n👉 *{status_label}*\n"
                    "─────────────────────────\n"
                )
                if new_status == "siap_antar":
                    notif_msg += "🛵 Cucian Anda sudah bersih, wangi, rapi, dan siap diantar kurir atau diambil di outlet kami! ✨"
                    reply_mk = back_to_main_menu()
                elif new_status == "selesai":
                    notif_msg += (
                        "🎉 Terima kasih banyak telah mempercayakan cucian Anda pada FreshClean Laundry! Semoga puas dengan layanan kami! ✨\n\n"
                        "Bagaimana kepuasan Anda terhadap layanan cucian kami? Mohon berikan penilaian bintang di bawah:"
                    )
                    rating_markup = types.InlineKeyboardMarkup(row_width=3)
                    r5 = types.InlineKeyboardButton("⭐⭐⭐⭐⭐ (5)", callback_data=f"rate_{target_order_id}_5")
                    r4 = types.InlineKeyboardButton("⭐⭐⭐⭐ (4)", callback_data=f"rate_{target_order_id}_4")
                    r3 = types.InlineKeyboardButton("⭐⭐⭐ (3)", callback_data=f"rate_{target_order_id}_3")
                    r2 = types.InlineKeyboardButton("⭐⭐ (2)", callback_data=f"rate_{target_order_id}_2")
                    r1 = types.InlineKeyboardButton("⭐ (1)", callback_data=f"rate_{target_order_id}_1")
                    btn_home = types.InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_utama")
                    rating_markup.add(r5, r4)
                    rating_markup.add(r3, r2, r1)
                    rating_markup.add(btn_home)
                    reply_mk = rating_markup
                else:
                    notif_msg += "Pakaian Anda sedang kami proses dengan higienis dan teliti. Kami akan kabari kembali saat siap diantar."
                    reply_mk = back_to_main_menu()

                bot.send_message(
                    buyer_id,
                    notif_msg,
                    parse_mode="Markdown",
                    reply_markup=reply_mk
                )
                print(f"[INFO] Notifikasi update status {target_order_id} ({new_status}) terkirim ke pelanggan {buyer_id}", flush=True)
            except Exception as e:
                print(f"[ERROR] Gagal mengirim notifikasi status ke pelanggan {buyer_id}: {e}", flush=True)

    # 11. Handler Input Tagihan & Berat Riil oleh Admin
    elif call.data.startswith("admin_bill_"):
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        target_oid = call.data.replace("admin_bill_", "")
        bot.answer_callback_query(call.id)
        ask_billing_input(chat_id, target_oid)

    # 12. Handler Pelanggan Ingin Mengirim Bukti Transfer
    elif call.data.startswith("kirim_bukti_"):
        target_oid = call.data.replace("kirim_bukti_", "")
        bot.answer_callback_query(call.id)
        prompt_upload_proof(chat_id, target_oid)

    # 13. Handler Admin Verifikasi Pembayaran Lunas
    elif call.data.startswith("admin_lunas_"):
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        target_oid = call.data.replace("admin_lunas_", "")
        order = all_orders.get(target_oid)
        if not order:
            bot.answer_callback_query(call.id, "Nota tidak ditemukan.", show_alert=True)
            return
        order["status_bayar"] = "Lunas"
        save_orders(all_orders)
        bot.answer_callback_query(call.id, f"Nota {target_oid} diverifikasi Lunas!", show_alert=True)
        bot.send_message(
            chat_id,
            f"✅ Pembayaran untuk nota *{target_oid}* ({order.get('nama')}) resmi berstatus: *LUNAS* 💵✨",
            parse_mode="Markdown"
        )
        buyer_id = order.get("buyer_chat_id")
        if buyer_id:
            try:
                bot.send_message(
                    buyer_id,
                    f"🎉 *PEMBAYARAN DIVERIFIKASI & LUNAS!* 🧾\n"
                    f"─────────────────────────\n"
                    f"Halo Kak *{order.get('nama')}*, pembayaran untuk nota `{target_oid}` sebesar *Rp {order.get('total_bayar', 0):,}* "
                    "telah kami terima dan diverifikasi *LUNAS*. Terima kasih atas kepercayaan Anda! 🧺✨",
                    parse_mode="Markdown",
                    reply_markup=back_to_main_menu()
                )
            except Exception as e:
                print(f"[ERROR] Gagal mengirim notif lunas ke pelanggan {buyer_id}: {e}", flush=True)

    # 14. Handler Ulasan / Rating Bintang dari Pelanggan
    elif call.data.startswith("rate_"):
        parts = call.data.split("_")
        if len(parts) >= 3:
            target_oid = parts[1]
            score = parts[2]
            order = all_orders.get(target_oid)
            if order:
                order["rating"] = int(score)
                save_orders(all_orders)
                stars_visual = "⭐" * int(score)
                bot.answer_callback_query(call.id, f"Terima kasih atas ulasan {score} bintang Anda!")
                bot.edit_message_text(
                    f"⭐ *TERIMA KASIH ATAS PENILAIAN ANDA!*\n"
                    f"─────────────────────────\n"
                    f"Penilaian Anda: *{stars_visual}* ({score}/5 Bintang)\n\n"
                    "Ulasan Anda sangat berharga bagi kami untuk terus memberikan layanan laundry terbaik, bersih, dan higienis! 🧺✨",
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="Markdown",
                    reply_markup=back_to_main_menu()
                )
                if ADMIN_CHAT_ID:
                    try:
                        bot.send_message(
                            ADMIN_CHAT_ID,
                            f"🌟 *ULASAN BARU DARI PELANGGAN!*\n"
                            f"• No. Nota: `{target_oid}`\n"
                            f"• Pelanggan: *{order.get('nama')}*\n"
                            f"• Rating: *{stars_visual}* ({score}/5)",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

    # 15. Handler Download CSV dari Tombol Panel Admin
    elif call.data == "admin_export_csv":
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        bot.answer_callback_query(call.id, "Menyiapkan file CSV...")
        send_orders_csv(chat_id)

    # 16. Handler Filter Antrean Cucian
    elif call.data == "admin_filter_antrean":
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_f1 = types.InlineKeyboardButton("⏳ Menunggu Jemput", callback_data="filter_status_menunggu")
        btn_f2 = types.InlineKeyboardButton("🧺 Sedang Dicuci", callback_data="filter_status_dicuci")
        btn_f3 = types.InlineKeyboardButton("👔 Sedang Disetrika", callback_data="filter_status_disetrika")
        btn_f4 = types.InlineKeyboardButton("🛵 Siap Diantar", callback_data="filter_status_siap_antar")
        btn_f5 = types.InlineKeyboardButton("✅ Selesai", callback_data="filter_status_selesai")
        btn_f6 = types.InlineKeyboardButton("👑 Panel Admin", callback_data="buka_panel_admin")
        markup.add(btn_f1, btn_f2)
        markup.add(btn_f3, btn_f4)
        markup.add(btn_f5, btn_f6)
        bot.edit_message_text(
            "🔍 *PILIH FILTER STATUS ANTREAN CUCIAN:*\n"
            "Silakan pilih status yang ingin ditampilkan:",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif call.data.startswith("filter_status_"):
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        target_status = call.data.replace("filter_status_", "")
        status_label = STATUS_LIST.get(target_status, target_status)
        matching = [o for o in all_orders.values() if o.get("status") == target_status]
        matching_sorted = sorted(matching, key=lambda x: x.get("waktu", ""), reverse=True)

        res_text = f"📋 *ANTREAN STATUS: {status_label}*\n"
        res_text += f"Total: *{len(matching_sorted)} pesanan*\n─────────────────────────\n"
        if matching_sorted:
            for o in matching_sorted[:10]:
                tagihan_info = f" (Rp {o.get('total_bayar', 0):,})" if o.get('total_bayar') else ""
                res_text += f"• `{o.get('order_id')}` | *{o.get('nama')}*{tagihan_info}\n  └ {o.get('layanan')}\n  └ WA: `{o.get('hp')}`\n"
        else:
            res_text += "Tidak ada pesanan pada status ini."

        f_markup = types.InlineKeyboardMarkup(row_width=2)
        btn_f_back = types.InlineKeyboardButton("🔍 Filter Lain", callback_data="admin_filter_antrean")
        btn_f_panel = types.InlineKeyboardButton("👑 Panel Admin", callback_data="buka_panel_admin")
        f_markup.add(btn_f_back, btn_f_panel)

        bot.edit_message_text(res_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown", reply_markup=f_markup)

    # 17. Handler Broadcast Siaran Promo
    elif call.data == "admin_start_broadcast":
        if chat_id != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "Khusus Admin", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        start_broadcast_prompt(chat_id)

    elif call.data == "confirm_broadcast":
        if chat_id != ADMIN_CHAT_ID:
            return
        text_to_send = broadcast_draft.get(chat_id)
        if not text_to_send:
            bot.answer_callback_query(call.id, "Tidak ada draft siaran yang aktif.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Mengirim siaran ke pelanggan...")
        bot.send_message(chat_id, "⏳ *Sedang mengirim siaran pesan ke seluruh pelanggan...*", parse_mode="Markdown")

        unique_buyers = set(o.get("buyer_chat_id") for o in all_orders.values() if o.get("buyer_chat_id"))
        success_count = 0
        fail_count = 0

        for b_id in unique_buyers:
            try:
                bot.send_message(
                    b_id,
                    f"📢 *PENGUMUMAN FRESHCLEAN LAUNDRY*\n─────────────────────────\n{text_to_send}",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
                success_count += 1
            except Exception:
                fail_count += 1

        broadcast_draft.pop(chat_id, None)
        bot.send_message(
            chat_id,
            f"✅ *Siaran Pesan Selesai Terkirim!*\n"
            f"• Berhasil : *{success_count} pelanggan*\n"
            f"• Gagal : *{fail_count}*\n",
            parse_mode="Markdown",
            reply_markup=admin_panel_markup()
        )

    elif call.data == "cancel_broadcast":
        broadcast_draft.pop(chat_id, None)
        bot.answer_callback_query(call.id, "Siaran dibatalkan.")
        bot.edit_message_text(
            "❌ Pengiriman pesan siaran dibatalkan.",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=admin_panel_markup()
        )


    # 11. Keunggulan & Promo
    elif call.data == "menu_keunggulan":
        keunggulan_text = (
            "✨ *MENGAPA MEMILIH FRESHCLEAN LAUNDRY?*\n"
            "─────────────────────────\n\n"
            "🧺 *1 Mesin 1 Pelanggan*\n"
            "Pakaian Anda tidak pernah dicampur dengan pakaian orang lain demi kebersihan dan higienitas maksimal.\n\n"
            "🌸 *Parfum Premium Tahan Lama*\n"
            "Pilihan aroma mewah (Snappy, Sweet Lily, Ocean Fresh, Lavender) yang wangi segar berminggu-minggu.\n\n"
            "🧴 *Deterjen Ramah Serat Kain*\n"
            "Formula khusus menjaga warna pakaian tidak pudar dan kain tetap lembut.\n\n"
            "🛵 *Gratis Antar-Jemput*\n"
            "Cukup order via bot ini, kurir kami siap menjemput dan mengantar langsung ke depan pintu Anda!\n\n"
            "⏱️ *Tepat Waktu & Bergaransi*\n"
            "Garansi cuci ulang gratis jika kurang bersih atau belum wangi."
        )
        bot.edit_message_text(
            keunggulan_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=back_to_main_menu()
        )

    # 12. Lokasi Outlet & Jam Buka
    elif call.data == "menu_lokasi":
        lokasi_text = (
            "📍 *LOKASI OUTLET & JAM BUKA*\n"
            "─────────────────────────\n\n"
            "🏢 *Outlet FreshClean Laundry:*\n"
            "Jl. Melati Raya No. 45, Kecamatan Sukajadi, Kota Anda\n\n"
            "⏰ *Jam Operasional Penjemputan & Outlet:*\n"
            "• Senin - Sabtu : 07.30 - 21.00 WIB\n"
            "• Minggu & Libur: 08.00 - 20.00 WIB\n\n"
            "🛵 *Area Antar-Jemput:*\n"
            "Melayani seluruh area radius 10 km dari outlet kami.\n\n"
            "🗺️ *Google Maps:* [Klik di sini untuk rute ke outlet](https://maps.google.com)"
        )
        bot.edit_message_text(
            lokasi_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=back_to_main_menu()
        )

    # 13. Kontak Admin / Customer Service
    elif call.data == "menu_kontak":
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_wa = types.InlineKeyboardButton("💬 WhatsApp CS Laundry", url="https://wa.me/6281234567890")
        btn_tg_admin = types.InlineKeyboardButton("👤 Chat Telegram Admin", url="https://t.me/username_admin")
        btn_back = types.InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_utama")
        markup.add(btn_wa, btn_tg_admin, btn_back)

        kontak_text = (
            "📞 *LAYANAN PELANGGAN & BANTUAN*\n"
            "─────────────────────────\n\n"
            "Ada pertanyaan seputar noda membandel, request khusus, atau ingin cek kurir jemputan?\n\n"
            "• WhatsApp Admin: `0812-3456-7890`\n"
            "• Telegram CS: @username_admin\n"
            "• Jam Layanan CS: 08.00 - 21.00 WIB\n\n"
            "Silakan klik tombol di bawah untuk langsung terhubung:"
        )
        bot.edit_message_text(
            kontak_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    bot.answer_callback_query(call.id)


# ==========================================
# STEP-BY-STEP FORM PEMESANAN LAUNDRY
# ==========================================
def is_cancelled(message):
    """Cek apakah pelanggan ingin membatalkan pemesanan"""
    text = (message.text or "").strip().lower()
    return text in [
        "❌ batal pesan", "batal", "/batal", "cancel", "/cancel",
        "/start", "🚀 /start", "🧺 menu utama", "menu utama", "start"
    ]

def start_order_process(chat_id, username):
    """Memulai proses formulir pemesanan laundry"""
    user_orders[chat_id] = {
        "username": username or "-",
        "user_id": chat_id
    }
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton("👕 Cuci Komplit Reguler (Rp 7.000/kg)", callback_data="order_paket_Cuci Komplit Reguler")
    btn2 = types.InlineKeyboardButton("⚡ Cuci Kilat Express 24 Jam (Rp 10.000/kg)", callback_data="order_paket_Cuci Express 24 Jam")
    btn3 = types.InlineKeyboardButton("🚀 Super Express 6 Jam (Rp 15.000/kg)", callback_data="order_paket_Cuci Super Express 6 Jam")
    btn4 = types.InlineKeyboardButton("🛏️ Satuan / Bed Cover / Selimut / Jas", callback_data="order_paket_Satuan Bed Cover/Selimut")
    btn5 = types.InlineKeyboardButton("👟 Cuci Sepatu Deep Clean (Rp 30.000)", callback_data="order_paket_Cuci Sepatu Deep Clean")
    btn_batal = types.InlineKeyboardButton("❌ Batal Pesan", callback_data="batalkan_order")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn_batal)

    bot.send_message(
        chat_id,
        "🧺 *FORMULIR PEMESANAN LAUNDRY*\n"
        "─────────────────────────\n"
        "Silakan pilih jenis paket layanan yang Anda inginkan:",
        parse_mode="Markdown",
        reply_markup=markup
    )

def step_input_nama(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_orders.pop(chat_id, None)
        bot.send_message(chat_id, "Pesanan laundry dibatalkan.", reply_markup=persistent_menu_markup())
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    user_orders[chat_id]["nama"] = message.text.strip()

    msg = bot.send_message(
        chat_id,
        "📱 *LANGKAH 2/4 - NOMOR WHATSAPP*\n"
        "─────────────────────────\n"
        "Masukkan *Nomor WhatsApp / HP* aktif Anda untuk konfirmasi penjemputan & total timbangan:\n"
        "Contoh: `08123456789`",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, step_input_hp)

def step_input_hp(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_orders.pop(chat_id, None)
        bot.send_message(chat_id, "Pesanan laundry dibatalkan.", reply_markup=persistent_menu_markup())
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    user_orders[chat_id]["hp"] = message.text.strip()

    metode = user_orders[chat_id].get("metode", "")
    if "Outlet" in metode:
        alamat_hint = "Masukkan *Alamat Domisili / Kost Singkat* Anda (atau ketik `-` jika tidak perlu pengantaran balik):"
        step_markup = cancel_order_markup()
    else:
        alamat_hint = (
            "Masukkan *Alamat Lengkap Penjemputan* (Nama Jalan, No. Rumah/Kost/Kamar, RT/RW, Patokan).\n\n"
            "💡 *Tips Praktis:* Anda juga bisa langsung menekan tombol *📍 Kirim Titik Lokasi GPS* di bawah agar kurir tidak tersasar!"
        )
        step_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        btn_loc = types.KeyboardButton("📍 Kirim Titik Lokasi GPS Saya", request_location=True)
        btn_cancel = types.KeyboardButton("❌ Batal Pesan")
        btn_home = types.KeyboardButton("🚀 /start")
        step_markup.row(btn_loc)
        step_markup.row(btn_cancel, btn_home)

    msg = bot.send_message(
        chat_id,
        f"📍 *LANGKAH 3/4 - ALAMAT PENJEMPUTAN*\n"
        "─────────────────────────\n"
        f"{alamat_hint}",
        parse_mode="Markdown",
        reply_markup=step_markup
    )
    bot.register_next_step_handler(msg, step_input_alamat)

def step_input_alamat(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_orders.pop(chat_id, None)
        bot.send_message(chat_id, "Pesanan laundry dibatalkan.", reply_markup=persistent_menu_markup())
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        user_orders[chat_id]["alamat"] = f"📍 Titik GPS: {lat:.6f}, {lon:.6f} ([Buka Google Maps]({maps_link}))"
        user_orders[chat_id]["maps_link"] = maps_link
    else:
        user_orders[chat_id]["alamat"] = (message.text or "-").strip()

    msg = bot.send_message(
        chat_id,
        "📝 *LANGKAH 4/4 - CATATAN KHUSUS (Opsional)*\n"
        "─────────────────────────\n"
        "Apakah ada permintaan khusus untuk cucian Anda?\n"
        "Contoh:\n"
        "• _'Pisahkan baju putih dan pakaian warna luntur'_\n"
        "• _'Aroma parfum lavender'_\n"
        "• _'Tolong jemput jam 1 siang'_\n\n"
        "_(Ketik '-' jika tidak ada catatan khusus)_",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, step_input_catatan)

def step_input_catatan(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_orders.pop(chat_id, None)
        bot.send_message(chat_id, "Pesanan laundry dibatalkan.", reply_markup=persistent_menu_markup())
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    user_orders[chat_id]["catatan"] = message.text.strip()

    # Kembalikan reply keyboard menu cepat
    bot.send_message(chat_id, "Menyiapkan ringkasan pesanan...", reply_markup=persistent_menu_markup())

    # Tampilkan Ringkasan & Tombol Konfirmasi
    order = user_orders[chat_id]
    rekap_text = (
        "📋 *RINGKASAN PESANAN LAUNDRY*\n"
        "─────────────────────────\n"
        f"🧺 *Paket:* {order.get('layanan', 'Reguler')}\n"
        f"⚖️ *Estimasi:* {order.get('estimasi', 'Ditimbang saat dijemput')}\n"
        f"🛵 *Metode:* {order.get('metode', 'Antar-Jemput')}\n"
        f"👤 *Nama:* {order['nama']}\n"
        f"📱 *No. WhatsApp:* {order['hp']}\n"
        f"📍 *Alamat:* {order['alamat']}\n"
        f"📝 *Catatan Khusus:* {order['catatan']}\n"
        "─────────────────────────\n"
        "Apakah data pemesanan di atas sudah sesuai?"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_confirm = types.InlineKeyboardButton("✅ Ya, Konfirmasi & Jadwalkan Penjemputan", callback_data="konfirmasi_kirim_order")
    btn_cancel = types.InlineKeyboardButton("❌ Batalkan Pesanan", callback_data="batalkan_order")
    markup.add(btn_confirm, btn_cancel)

    bot.send_message(chat_id, rekap_text, parse_mode="Markdown", reply_markup=markup)


# ==========================================
# CEK STATUS CUCIAN
# ==========================================
def step_cek_status(message):
    """Handler saat pelanggan memasukkan nomor nota laundry untuk cek status"""
    chat_id = message.chat.id
    text = (message.text or "").strip()

    if text.lower() in ["batal", "/batal", "cancel", "/cancel", "/start", "🚀 /start", "menu", "menu utama", "start"]:
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    # Normalisasi input: bisa input nomor langsung atau prefix LDR-
    order_id = text.upper()
    if not order_id.startswith("LDR-") and not order_id.startswith("ORD-"):
        order_id = f"LDR-{order_id}"

    order_rec = all_orders.get(order_id)
    # Jika tidak ketemu, coba cek format ORD- jika ada data lama
    if not order_rec and order_id.startswith("LDR-"):
        alt_id = "ORD-" + order_id.replace("LDR-", "")
        if alt_id in all_orders:
            order_id = alt_id
            order_rec = all_orders.get(order_id)

    if not order_rec:
        msg = bot.send_message(
            chat_id,
            f"⚠️ Nota laundry dengan ID `{order_id}` tidak ditemukan di sistem kami.\n\n"
            "Pastikan Anda memasukkan nomor nota yang benar (contoh: `LDR-1234`).\n"
            "Silakan ketik ulang, atau klik tombol *🚀 /start* di bawah untuk kembali ke menu:",
            parse_mode="Markdown",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, step_cek_status)
        return

    status_label = STATUS_LIST.get(order_rec["status"], order_rec["status"])
    layanan_nama = order_rec.get("layanan") or order_rec.get("produk") or "-"
    
    billing_info = ""
    if order_rec.get("berat_riil"):
        billing_info += f"⚖️ *Berat Riil Cucian:* {order_rec['berat_riil']}\n"
    if order_rec.get("total_bayar"):
        billing_info += f"💵 *Total Tagihan:* Rp {order_rec['total_bayar']:,}\n"
        billing_info += f"💳 *Status Bayar:* *{order_rec.get('status_bayar', 'Belum Lunas')}*\n"
    if order_rec.get("rating"):
        billing_info += f"⭐ *Ulasan Anda:* {'⭐' * int(order_rec['rating'])} ({order_rec['rating']}/5)\n"

    result_text = (
        "🔍 *STATUS PENGERJAAN CUCIAN*\n"
        "─────────────────────────\n"
        f"🆔 *No. Nota:* `{order_id}`\n"
        f"⏱️ *Waktu Order:* {order_rec['waktu']}\n\n"
        f"🧺 *Layanan:* {layanan_nama}\n"
        f"⚖️ *Estimasi:* {order_rec.get('estimasi', '-')}\n"
        f"{billing_info}"
        f"👤 *Nama Pelanggan:* {order_rec['nama']}\n"
        f"📍 *Alamat:* {order_rec['alamat']}\n\n"
        f"📊 *Status Cucian:* *{status_label}*\n"
        "─────────────────────────\n"
        "Jika ada pertanyaan mengenai cucian Anda, silakan hubungi Admin / CS."
    )
    
    status_markup = types.InlineKeyboardMarkup()
    if order_rec.get("total_bayar") and order_rec.get("status_bayar") != "Lunas":
        btn_proof = types.InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data=f"kirim_bukti_{order_id}")
        status_markup.add(btn_proof)
    btn_back = types.InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_utama")
    status_markup.add(btn_back)

    bot.send_message(chat_id, result_text, parse_mode="Markdown", reply_markup=status_markup)


@bot.message_handler(commands=['cekpesanan', 'status'])
def cek_pesanan_command(message):
    """Perintah alternatif untuk cek status cucian via command"""
    parts = message.text.split()
    if len(parts) >= 2:
        order_id = parts[1].upper()
        if not order_id.startswith("LDR-") and not order_id.startswith("ORD-"):
            order_id = f"LDR-{order_id}"
        order_rec = all_orders.get(order_id)
        if order_rec:
            status_label = STATUS_LIST.get(order_rec["status"], order_rec["status"])
            layanan_nama = order_rec.get("layanan") or order_rec.get("produk") or "-"
            tagihan = f"\n💵 Tagihan: Rp {order_rec.get('total_bayar', 0):,} ({order_rec.get('status_bayar', 'Belum Lunas')})" if order_rec.get('total_bayar') else ""
            bot.reply_to(
                message,
                f"🔍 *Status Nota `{order_id}`*\n\n"
                f"🧺 Layanan: {layanan_nama}\n"
                f"📊 Status: *{status_label}*{tagihan}\n"
                f"⏱️ Waktu: {order_rec['waktu']}",
                parse_mode="Markdown"
            )

        else:
            bot.reply_to(message, f"⚠️ Nota laundry `{order_id}` tidak ditemukan.", parse_mode="Markdown")
    else:
        msg = bot.reply_to(
            message,
            "Masukkan *Nomor Nota Laundry* Anda (contoh: `LDR-1234`):",
            parse_mode="Markdown",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, step_cek_status)


# ==========================================
# ASISTEN PINTAR AI UNTUK ADMIN & PELANGGAN (/tanya & CHAT LANGSUNG)
# ==========================================
def call_gemini_ai(query, user_name, is_admin=False):
    """Memanggil Google Gemini REST API jika GEMINI_API_KEY telah diatur"""
    if not GEMINI_API_KEY:
        return None
    try:
        if is_admin:
            total_orders = len(all_orders)
            active_orders = [o for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"]]
            sample_list = []
            for o in active_orders[:8]:
                sample_list.append(f"- Nota: {o.get('order_id')} | Pelanggan: {o.get('nama')} | HP: {o.get('hp')} | Paket: {o.get('layanan')} | Status: {o.get('status')}")
            sample_text = "\n".join(sample_list) if sample_list else "Tidak ada antrean cucian aktif."

            prompt_system = (
                f"Kamu adalah Asisten AI Bisnis Khusus untuk Pemilik/Admin FreshClean Laundry (bernama {user_name}).\n"
                "Tugasmu membantu pemilik laundry menganalisis pesanan, menjawab pertanyaan operasional (penanganan noda, deterjen, parfum, SOP pengerjaan), membuat draft pesan WhatsApp untuk pelanggan, atau memberikan strategi bisnis laundry.\n"
                "Jawablah dengan bahasa Indonesia yang ramah, profesional, ringkas, dan jelas menggunakan format Markdown Telegram (*bold*, _italic_, bullet points).\n\n"
                f"Data Usaha Laundry Saat Ini:\n"
                f"- Total seluruh nota tersimpan: {total_orders}\n"
                f"- Pesanan yang sedang aktif/berjalan: {len(active_orders)}\n"
                f"- Antrean Aktif Terkini:\n{sample_text}\n"
                "- Layanan & Tarif: Kiloan Reguler Rp 7.000/kg (2 Hari), Kilat Express Rp 10.000/kg (24 Jam), Super Express Rp 15.000/kg (6 Jam), Bed Cover Single Rp 20.000, Jumbo Rp 30.000, Cuci Sepatu Deep Clean Rp 25.000 - Rp 35.000.\n\n"
                f"Pertanyaan Pemilik/Admin:\n{query}"
            )
        else:
            prompt_system = (
                f"Kamu adalah Asisten Cerdas & Customer Service (CS) Resmi FreshClean Laundry yang bertugas melayani pelanggan bernama {user_name}.\n"
                "Jawablah semua pertanyaan pelanggan dengan sangat ramah, hangat, sopan, membantu, solutif, dan informatif menggunakan bahasa Indonesia yang baik.\n"
                "Gunakan format Markdown Telegram (*bold*, _italic_, bullet points).\n\n"
                "Informasi Lengkap FreshClean Laundry:\n"
                "• Cuci Kiloan: Reguler Rp 7.000/kg (2 hari), Express 24 Jam Rp 10.000/kg (1 hari), Super Express 6 Jam Selesai Rp 15.000/kg, Cuci Kering Lipat Rp 5.000/kg, Setrika Uap Saja Rp 4.500/kg.\n"
                "• Cuci Satuan: Bed Cover Single Rp 20.000, Double/Jumbo Rp 30.000, Selimut Tebal Rp 18.000, Jas/Blazer Rp 25.000, Karpet/Gorden Rp 15.000-25.000/m².\n"
                "• Cuci Sepatu & Tas: Sneakers/Flat shoes Rp 25.000, Deep clean & unyellowing Rp 35.000, Tas/Ransel Rp 20.000-35.000.\n"
                "• Layanan Antar-Jemput: GRATIS untuk radius 3 km (minimal order 5 kg). Melayani antar-jemput hingga radius 10 km dari outlet.\n"
                "• Jam Operasional Outlet: Senin - Sabtu 07.30 - 21.00 WIB, Minggu & Libur 08.00 - 20.00 WIB.\n"
                "• Alamat Outlet: Jl. Melati Raya No. 45, Kecamatan Sukajadi.\n"
                "• Metode Pembayaran: QRIS (semua e-wallet / mobile banking), Transfer Bank BCA, atau Bayar Tunai (COD) saat kurir mengantar cucian.\n"
                "• Keunggulan Kami: 1 mesin 1 pelanggan (higienis dan tidak dicampur pakaian orang lain), deterjen ramah serat kain, 4 aroma parfum mewah tahan lama (Snappy, Sweet Lily, Ocean Fresh, Lavender), garansi cuci ulang gratis jika kurang bersih.\n"
                "• Cara Order: Pelanggan bisa klik tombol '🛵 Pesan Laundry' atau ketik /order.\n"
                "• Cek Cucian: Pelanggan bisa mengecek status cuciannya dengan mengetik /cekpesanan atau memasukkan nomor nota (misal LDR-1234).\n"
                "• Kamu juga sangat pintar menjawab tips seputar perawatan kain, bahan pakaian, atau tips menghilangkan noda rumahan jika pelanggan bertanya.\n"
                "• PENTING: Jaga kerahasiaan dan privasi data pelanggan lain (jangan berikan nomor HP atau alamat pelanggan lain).\n\n"
                f"Pertanyaan Pelanggan:\n{query}"
            )

        models_to_try = ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-flash-latest", "gemini-2.5-flash"]
        payload = {
            "contents": [{"parts": [{"text": prompt_system}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
        }
        data_json = json.dumps(payload).encode("utf-8")

        for model in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                req = urllib.request.Request(url, data=data_json, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=12) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidate = result.get("candidates", [])[0]
                    answer = candidate.get("content", {}).get("parts", [])[0].get("text", "")
                    if answer:
                        return answer.strip()
            except Exception:
                continue

        return None
    except Exception as e:
        print(f"[WARN] Gemini AI gagal dipanggil: {e}", flush=True)
        return None


def smart_local_assistant(query, user_name, is_admin=False):
    """Mesin pengetahuan cerdas bawaan untuk Admin dan Pelanggan"""
    q = query.lower()

    # ======================================
    # JIKA PENANYA ADALAH ADMIN TOKO
    # ======================================
    if is_admin:
        # 1. PENCARIAN PESANAN / PELANGGAN
        matched = []
        for oid, o in all_orders.items():
            o_name = o.get("nama", "").lower()
            o_hp = o.get("hp", "").lower()
            o_id = oid.lower()
            if (o_id in q or 
                (len(q) >= 3 and q in o_name) or 
                (len(q) >= 4 and q in o_hp) or
                any(w in o_name for w in q.split() if len(w) > 3)):
                matched.append(o)

        if ("cari" in q or "cek" in q or "nota" in q or "pelanggan" in q or "nama" in q) and matched:
            res = f"🔍 *Hasil Pencarian untuk:* _{query}_\n─────────────────────────\n"
            for o in matched[:5]:
                st = STATUS_LIST.get(o.get('status', ''), o.get('status', ''))
                res += (
                    f"🆔 *Nota:* `{o.get('order_id')}`\n"
                    f"👤 *Nama:* {o.get('nama')}\n"
                    f"📱 *WA:* `{o.get('hp')}`\n"
                    f"🧺 *Layanan:* {o.get('layanan')} ({o.get('estimasi', '-')})\n"
                    f"📍 *Alamat:* {o.get('alamat')}\n"
                    f"📊 *Status:* {st}\n"
                    f"⏱️ *Waktu:* {o.get('waktu')}\n"
                    "─────────────────────────\n"
                )
            return res

        # 2. STATUS ANTREAN & PESANAN AKTIF
        if any(k in q for k in ["antre", "antri", "belum selesai", "belum diambil", "belum diantar", "siapa saja", "siapa yang", "proses", "dicuci", "setrika"]):
            active = [o for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"]]
            if not active:
                return "🎉 *Alhamdulillah, semua cucian telah selesai!* Tidak ada cucian yang menumpuk di antrean saat ini."
            res = f"🧺 *Daftar Cucian yang Sedang Diproses ({len(active)} Pesanan):*\n─────────────────────────\n"
            for o in active[:10]:
                st = STATUS_LIST.get(o.get('status', ''), o.get('status', ''))
                res += f"• `{o.get('order_id')}` | *{o.get('nama')}*\n  └ {o.get('layanan')}\n  └ Status: _{st}_\n  └ WA: `{o.get('hp')}`\n"
            return res

        # 3. OMSET, PENDAPATAN & KEUANGAN
        if any(k in q for k in ["omset", "omzet", "pendapatan", "keuangan", "penghasilan", "penjualan", "laba", "untung", "uang", "laporan"]):
            total = len(all_orders)
            selesai = sum(1 for o in all_orders.values() if o.get("status") == "selesai")
            aktif = sum(1 for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"])
            real_omset = sum(int(o.get("total_bayar", 0)) for o in all_orders.values() if isinstance(o.get("total_bayar"), (int, float)))
            est_omset = real_omset if real_omset > 0 else (selesai * 28000)
            lunas_count = sum(1 for o in all_orders.values() if o.get("status_bayar") == "Lunas")
            return (
                "💰 *RINGKASAN ESTIMASI PENDAPATAN & PESANAN*\n"
                "─────────────────────────\n"
                f"📦 Total Seluruh Nota Masuk : *{total} nota*\n"
                f"✅ Pesanan Selesai          : *{selesai} nota*\n"
                f"⏳ Pesanan Sedang Diproses  : *{aktif} nota*\n"
                f"💳 Pembayaran Lunas         : *{lunas_count} nota*\n"
                f"💵 Total Omset Tercatat     : *Rp {est_omset:,}*\n"
                "─────────────────────────\n"
                "💡 _Gunakan tombol *📥 Unduh Rekap CSV* di Panel Admin atau ketik `/export` untuk download rekap pembukuan._"
            )


        # 4. TEMPLATE PESAN WHATSAPP UNTUK ADMIN
        if any(k in q for k in ["template", "pesan wa", "chat wa"]):
            if any(k in q for k in ["jemput", "ambil"]):
                return (
                    "📝 *TEMPLATE CHAT WA: KONFIRMASI PENJEMPUTAN*\n\n"
                    "```\nHalo Kak [Nama Pelanggan]! 👋\n"
                    "Kami dari FreshClean Laundry. Kurir kami sedang menuju ke lokasi Anda untuk penjemputan cucian (ID: [No. Nota]).\n"
                    "Mohon dipastikan pakaian kotor sudah siap ya Kak. Terima kasih! 🛵✨\n```"
                )
            elif any(k in q for k in ["tagihan", "total", "invoice", "bayar"]):
                return (
                    "📝 *TEMPLATE CHAT WA: RINCIAN TAGIHAN / TIMBANGAN*\n\n"
                    "```\nHalo Kak [Nama Pelanggan]! 🧺\n"
                    "Cucian Anda (Nota: [No. Nota]) sudah selesai ditimbang di outlet kami:\n"
                    "• Berat Riil : [Contoh: 4.5 Kg]\n"
                    "• Paket Layanan : Cuci Komplit Reguler\n"
                    "• Total Tagihan : Rp [Contoh: 31.500]\n\n"
                    "Pembayaran dapat ditransfer via QRIS / Rekening BCA: 123456789 a/n FreshClean.\n"
                    "Terima kasih Kak! ✨\n```"
                )
            elif any(k in q for k in ["selesai", "siap", "antar"]):
                return (
                    "📝 *TEMPLATE CHAT WA: CUCIAN SIAP DIANTAR*\n\n"
                    "```\nHalo Kak [Nama Pelanggan]! 🎉\n"
                    "Kabar gembira, cucian Anda (Nota: [No. Nota]) sudah bersih, wangi, rapi, dan siap diantar kurir ke alamat Anda.\n"
                    "Apakah Kakak ada di tempat sekarang? Terima kasih! 🛵🧺\n```"
                )

    # ======================================
    # JIKA PENANYA ADALAH PELANGGAN (USER)
    # ======================================
    else:
        # 1. PERTANYAAN TARIF / BIAYA
        if any(k in q for k in ["harga", "tarif", "biaya", "berapa per kg", "kiloan", "ongkos", "bayar berapa", "price", "list harga"]):
            return (
                "🧺 *DAFTAR TARIF FRESHCLEAN LAUNDRY*\n"
                "─────────────────────────\n"
                "✨ *Layanan Cuci Kiloan (Cuci + Kering + Setrika + Parfum):*\n"
                "• *Reguler (2 Hari):* Rp 7.000 / kg\n"
                "• *Kilat Express (24 Jam):* Rp 10.000 / kg\n"
                "• *Super Express (6 Jam Selesai):* Rp 15.000 / kg\n"
                "• *Cuci Lipat Saja:* Rp 5.000 / kg\n"
                "• *Setrika Uap Saja:* Rp 4.500 / kg\n\n"
                "🛏️ *Layanan Satuan:*\n"
                "• Bed Cover Single: Rp 20.000 | Jumbo: Rp 30.000\n"
                "• Selimut Tebal: Rp 18.000 | Jas: Rp 25.000\n"
                "• Cuci Sepatu Deep Clean: Rp 25.000 - Rp 35.000\n\n"
                "🛵 *Gratis Antar-Jemput* untuk area radius 3 km (min. 5 kg)!"
            )

        # 2. PERTANYAAN DURASI / BERAPA LAMA
        if any(k in q for k in ["berapa lama", "durasi", "kapan selesai", "express", "kilat", "cepat", "kapan jadi"]):
            return (
                "⏱️ *ESTIMASI WAKTU PENGERJAAN CUCIAN:*\n"
                "─────────────────────────\n"
                "• 🚀 *Super Express:* Selesai hanya dalam *6 Jam* (Rp 15.000/kg)\n"
                "• ⚡ *Kilat Express:* Selesai dalam *24 Jam / 1 Hari* (Rp 10.000/kg)\n"
                "• 👕 *Cuci Reguler:* Selesai dalam *2 Hari* (Rp 7.000/kg)\n"
                "• 🛏️ *Bed Cover / Satuan:* 2 - 3 Hari pengerjaan rapi & kering sempurna.\n"
                "• 👟 *Cuci Sepatu Deep Clean:* 2 - 3 Hari (dikeringkan tanpa merusak bahan)."
            )

        # 3. ANTAR-JEMPUT / RADIUS / ONGKIR
        if any(k in q for k in ["antar", "jemput", "kurir", "radius", "ongkir", "lokasi jemput", "bisa jemput", "free ongkir"]):
            return (
                "🛵 *LAYANAN ANTAR-JEMPUT CUCIAN:*\n"
                "─────────────────────────\n"
                "Ya, tentu bisa! Kurir kami siap menjemput dan mengantar cucian langsung ke rumah, kost, atau kantor Anda.\n\n"
                "• *Gratis Ongkir:* Radius sampai 3 km dari outlet kami (minimal cucian 5 kg).\n"
                "• *Jangkauan Layanan:* Melayani hingga radius 10 km dari outlet.\n\n"
                "Silakan klik tombol *🛵 Pesan Laundry* untuk mengisi alamat penjemputan!"
            )

        # 4. METODE PEMBAYARAN
        if any(k in q for k in ["bayar", "qris", "transfer", "cash", "tunai", "cod", "dana", "gopay", "bca"]):
            return (
                "💳 *METODE PEMBAYARAN FRESHCLEAN LAUNDRY:*\n"
                "─────────────────────────\n"
                "Kami menerima berbagai metode pembayaran praktis:\n\n"
                "1. 📲 *QRIS:* Scan dari semua aplikasi (BCA Mobile, Mandiri, GoPay, OVO, DANA, ShopeePay).\n"
                "2. 🏦 *Transfer Bank:* Bank BCA a/n FreshClean Laundry.\n"
                "3. 💵 *Tunai (COD):* Bayar langsung secara tunai saat kurir mengantar cucian bersih Anda."
            )

        # 5. JAM OPERASIONAL & LOKASI
        if any(k in q for k in ["buka", "tutup", "jam", "alamat", "lokasi", "outlet", "maps", "dimana", "daerah"]):
            return (
                "📍 *LOKASI & JAM OPERASIONAL FRESHCLEAN:*\n"
                "─────────────────────────\n"
                "🏢 *Outlet:* Jl. Melati Raya No. 45, Kecamatan Sukajadi, Kota Anda\n\n"
                "⏰ *Jam Buka & Operasional:*\n"
                "• Senin - Sabtu : 07.30 - 21.00 WIB\n"
                "• Minggu & Libur: 08.00 - 20.00 WIB\n\n"
                "Kurir penjemputan cucian beroperasi setiap hari selama jam buka outlet!"
            )

        # 6. CUCI SEPATU & BED COVER
        if any(k in q for k in ["sepatu", "sneakers", "tas", "bed cover", "selimut", "jas"]):
            return (
                "👟 *LAYANAN KHUSUS SEPATU, TAS & SATUAN:*\n"
                "─────────────────────────\n"
                "Kami melayani pencucian bahan khusus dengan perlakuan profesional:\n\n"
                "• 👟 *Sepatu Sneakers / Kanvas:* Rp 25.000 / pasang\n"
                "• 👟 *Deep Clean & Unyellowing Sepatu:* Rp 35.000 / pasang\n"
                "• 🎒 *Tas / Ransel:* Rp 20.000 - Rp 35.000 / pcs\n"
                "• 🛏️ *Bed Cover Single:* Rp 20.000 | *Double/Jumbo:* Rp 30.000\n"
                "• 👔 *Jas / Blazer:* Rp 25.000 / pcs"
            )

        # 7. CARA PESAN
        if any(k in q for k in ["cara pesan", "mau order", "gimana cara", "pesan laundry", "bisa cuci"]):
            return (
                "🛵 *CARA MUDAH MEMESAN LAUNDRY:*\n"
                "─────────────────────────\n"
                "1. Klik tombol *🛵 Pesan Laundry* di bawah atau ketik `/order`.\n"
                "2. Pilih paket layanan (Reguler, Express, Sepatu, dll).\n"
                "3. Masukkan nama, nomor WhatsApp, dan alamat penjemputan Anda.\n"
                "4. Kurir kami akan segera mengonfirmasi dan meluncur menjemput pakaian kotor Anda!"
            )

        # 8. CEK STATUS NOTA
        if any(k in q for k in ["cek nota", "cek status", "sudah jadi belum", "cucian saya", "lacak"]):
            return (
                "🔍 *CARA CEK STATUS PENGERJAAN CUCIAN:*\n"
                "─────────────────────────\n"
                "Ketik `/cekpesanan [Nomor_Nota]` (contoh: `/cekpesanan LDR-1234`), atau klik tombol *🔍 Cek Status Cucian* di menu utama.\n\n"
                "Sistem kami akan langsung menampilkan apakah cucian Anda sedang dicuci, disetrika, atau siap diantar!"
            )

    # ======================================
    # TIPS NODA (BERLAKU UNTUK ADMIN & PELANGGAN)
    # ======================================
    if "darah" in q:
        return (
            "🩸 *TIPS PENANGANAN NODA DARAH:*\n"
            "─────────────────────────\n"
            "1. *Gunakan AIR DINGIN* (Jangan air hangat/panas, karena protein darah akan mengunci ke serat kain).\n"
            "2. Oleskan sabun pencuci piring (Sunlight) atau Hidrogen Peroksida 3% langsung ke noda.\n"
            "3. Kucek perlahan hingga memudar, lalu cuci dengan deterjen biasa."
        )
    if any(k in q for k in ["minyak", "oli", "lemak", "kuah"]):
        return (
            "🛢️ *TIPS PENANGANAN NODA MINYAK / OLI:*\n"
            "─────────────────────────\n"
            "1. Taburkan bedak bayi atau tepung maizena di atas noda selama 15 menit untuk menyerap minyak.\n"
            "2. Oleskan sabun cuci piring pekat langsung tanpa air, diamkan 10 menit.\n"
            "3. Kucek dengan air hangat sebelum dicuci di mesin."
        )
    if any(k in q for k in ["tinta", "pulpen", "spidol"]):
        return (
            "🖊️ *TIPS PENANGANAN NODA TINTA:*\n"
            "─────────────────────────\n"
            "1. Beri alkohol 70% atau Hand Sanitizer pada kapas.\n"
            "2. Tepuk-tepuk noda dari luar ke arah dalam (jangan digosok agar tidak melebar).\n"
            "3. Serap dengan tisu kering, lalu cuci seperti biasa."
        )
    if any(k in q for k in ["jamur", "bintik hitam", "apek"]):
        return (
            "🍄 *TIPS PENANGANAN NODA JAMUR / BINTIK HITAM:*\n"
            "─────────────────────────\n"
            "1. Larutkan Citrun (asam sitrat) dan deterjen dalam air hangat.\n"
            "2. Rendam pakaian selama 30 - 45 menit.\n"
            "3. Kucek bagian yang berbintik, jamur akan rontok tanpa merusak warna pakaian."
        )
    if any(k in q for k in ["kunyit", "saus", "sambal", "makanan"]):
        return (
            "🍛 *TIPS PENANGANAN NODA KUNYIT / MAKANAN:*\n"
            "─────────────────────────\n"
            "1. Oleskan deterjen cair konsentrat langsung ke noda, kucek perlahan.\n"
            "2. *Jemur langsung di bawah terik sinar matahari* saat masih basah. Sinar UV alami sangat ampuh memecah pigmen kurkumin hingga hilang total!"
        )
    if "karat" in q:
        return (
            "⚙️ *TIPS PENANGANAN NODA KARAT:*\n"
            "─────────────────────────\n"
            "1. Beri perasan jeruk nipis dan taburan garam dapur pada noda karat.\n"
            "2. Jemur pakaian selama 15-20 menit, lalu sikat perlahan dan bilas air bersih."
        )

    # SALAM & RAMAH TAMAH
    if any(k in q for k in ["halo", "hai", "pagi", "siang", "sore", "malam", "assalamualaikum"]):
        return (
            f"Halo, Kak *{user_name}*! 👋 Ada yang bisa Asisten FreshClean Laundry bantu hari ini?\n\n"
            "Anda bisa menanyakan tarif, durasi cuci, promo antar-jemput, atau langsung memesan cucian!"
        )

    if any(k in q for k in ["terima kasih", "makasih", "thanks", "ok", "oke"]):
        return f"Sama-sama, Kak *{user_name}*! Senang bisa membantu Anda. Jika ada cucian kotor, FreshClean Laundry siap melayani dengan bersih dan wangi! 🧺✨"

    # DEFAULT FALLBACK
    if is_admin:
        return (
            f"🤖 *Halo Bos {user_name}!* Saya Asisten Toko FreshClean Laundry.\n\n"
            "Saya siap membantu operasional toko. Coba tanyakan hal berikut:\n"
            "• _'Siapa saja yang cuciannya belum selesai?'_\n"
            "• _'Cari pesanan nama Fadhel'_\n"
            "• _'Berapa omset dan total pesanan saat ini?'_\n"
            "• _'Bagaimana cara membersihkan noda minyak / darah / jamur?'_\n"
            "• _'Buatkan template chat WhatsApp konfirmasi penjemputan'_\n\n"
            "💡 *Tips:* Pasang `GEMINI_API_KEY` di pengaturan bot untuk kecerdasan AI Google Gemini tanpa batas!"
        )
    else:
        return (
            f"🤖 *Halo Kak {user_name}!* Selamat datang di layanan bantuan FreshClean Laundry.\n\n"
            "Silakan tanyakan apa saja seputar cucian Anda, misalnya:\n"
            "• _'Berapa harga cuci kiloan reguler & express?'_\n"
            "• _'Berapa lama proses cuci selesai?'_\n"
            "• _'Apakah bisa antar jemput ke rumah saya?'_\n"
            "• _'Berapa tarif cuci bed cover atau sepatu?'_\n"
            "• _'Bisa bayar pakai apa saja?'_\n\n"
            "Atau pilih tombol menu di bawah untuk langsung memesan layanan kami:"
        )


def process_query(message, query, is_admin=False):
    """Memproses pertanyaan dari Admin atau Pelanggan dan memberikan balasan cerdas"""
    chat_id = message.chat.id
    user_name = message.from_user.first_name or ("Bos" if is_admin else "Kakak")

    try:
        bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass

    # 1. Coba panggil Gemini AI jika API Key ada
    answer = call_gemini_ai(query, user_name, is_admin=is_admin)

    # 2. Jika tanpa API Key atau offline, gunakan mesin pengetahuan cerdas lokal
    if not answer:
        answer = smart_local_assistant(query, user_name, is_admin=is_admin)

    # Jika pelanggan yang bertanya, sertakan tombol aksi cepat di bawah jawaban
    markup = None
    if not is_admin:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_order = types.InlineKeyboardButton("🛵 Pesan Laundry", callback_data="mulai_order")
        btn_tarif = types.InlineKeyboardButton("🧺 Daftar Tarif", callback_data="menu_tarif")
        btn_menu = types.InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")
        markup.add(btn_order, btn_tarif)
        markup.add(btn_menu)

    # Kirim balasan dengan perlindungan error formatting Markdown (Fallback ke plain text jika entitas unclosed)
    try:
        bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=markup)
    except Exception as parse_err:
        try:
            bot.reply_to(message, answer, parse_mode=None, reply_markup=markup)
        except Exception as e:
            print(f"[ERROR] Gagal mengirim balasan: {e}", flush=True)


@bot.message_handler(commands=['tanya', 'ai', 'ask'])
def tanya_command(message):
    """Perintah untuk bertanya ke Asisten Bot (bisa diakses oleh Admin maupun Pelanggan)"""
    chat_id = message.chat.id
    is_admin = (chat_id == ADMIN_CHAT_ID)
    parts = message.text.strip().split(maxsplit=1)

    if len(parts) >= 2:
        query = parts[1]
        process_query(message, query, is_admin=is_admin)
    else:
        if is_admin:
            prompt_text = (
                "💬 *Halo Admin FreshClean!* 🤖\n\n"
                "Silakan ketik pertanyaan apa saja untuk Asisten Toko.\n"
                "Contoh:\n"
                "• _'Siapa saja yang cuciannya belum selesai?'_\n"
                "• _'Cari pesanan nama Fadhel'_\n"
                "• _'Bagaimana cara membersihkan noda oli di baju putih?'_\n"
                "• _'Berapa estimasi omset dan antrean saat ini?'_\n\n"
                "_(Ketik pertanyaan Anda sekarang)_"
            )
        else:
            prompt_text = (
                "💬 *Halo Kak! Ada yang bisa kami bantu?* 🤖✨\n\n"
                "Silakan ketik pertanyaan Anda seputar layanan FreshClean Laundry.\n"
                "Contoh pertanyaan:\n"
                "• _'Berapa harga cuci kiloan express?'_\n"
                "• _'Bisa antar jemput ke daerah Sukajadi?'_\n"
                "• _'Berapa lama proses cuci sepatu deep clean?'_\n"
                "• _'Bisa bayar pakai QRIS atau transfer?'_\n\n"
                "_(Ketik pertanyaan Anda sekarang)_"
            )

        msg = bot.reply_to(message, prompt_text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, step_user_tanya)


def step_user_tanya(message):
    """Handler langkah berikutnya untuk pertanyaan pengguna"""
    if is_cancelled(message):
        bot.send_message(message.chat.id, "Sesi tanya jawab ditutup.", reply_markup=main_menu())
        return
    is_admin = (message.chat.id == ADMIN_CHAT_ID)
    process_query(message, message.text.strip(), is_admin=is_admin)


@bot.message_handler(content_types=['photo'])
def handle_direct_photo(message):
    """Handler jika pengguna mengirim foto secara langsung (misal bukti struk transfer)"""
    chat_id = message.chat.id
    # Cari pesanan aktif pengguna yang belum lunas
    user_active_orders = [
        o for o in all_orders.values()
        if o.get("buyer_chat_id") == chat_id and o.get("status") not in ["selesai", "dibatalkan"]
    ]
    if user_active_orders:
        latest = sorted(user_active_orders, key=lambda x: x.get("waktu", ""), reverse=True)[0]
        step_receive_payment_proof(message, latest.get("order_id"))
    else:
        bot.reply_to(
            message,
            "📸 Terima kasih telah mengirimkan gambar.\n"
            "Jika ini adalah bukti transfer pembayaran, silakan buat pesanan terlebih dahulu melalui menu *🛵 Pesan Laundry* (`/order`).",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )


@bot.message_handler(func=lambda msg: True, content_types=['text'])
def default_message_router(message):
    """Router pesan teks: Menjawab semua pertanyaan pengguna (Admin & Pelanggan) secara cerdas"""
    chat_id = message.chat.id
    text = (message.text or "").strip()
    is_admin = (chat_id == ADMIN_CHAT_ID)

    # Proses pertanyaan secara otomatis dengan AI
    process_query(message, text, is_admin=is_admin)


def start_dummy_server():
    """Server web mini agar bot dapat di-hosting gratis di layanan cloud (seperti Render.com)"""
    # Hanya dijalankan di cloud server (Render otomatis menyediakan variabel PORT / RENDER)
    port_str = os.environ.get("PORT")
    if not port_str and not os.environ.get("RENDER"):
        return

    try:
        class HealthCheckHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"FreshClean Laundry Bot is Alive 24/7!")

            def log_message(self, format, *args):
                return

        port = int(port_str or 10000)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"🌐 Cloud Health-check server aktif di port {port}", flush=True)
    except Exception as e:
        print(f"ℹ️ Info: Web server cloud tidak diaktifkan ({e})", flush=True)


# ==========================================
# MENJALANKAN BOT
# ==========================================
if __name__ == "__main__":
    print(f"==================================================", flush=True)
    print(f"✨ FreshClean Laundry Bot sedang berjalan...", flush=True)
    
    # Jalankan server mini untuk platform cloud (Render, dll)
    start_dummy_server()

    # Daftarkan menu perintah resmi Telegram (/start, dll)
    setup_bot_commands()
    
    if ADMIN_CHAT_ID:
        print(f"🔔 Admin Chat ID terdaftar: {ADMIN_CHAT_ID}", flush=True)
    else:
        print(f"⚠️ Belum ada Admin terdaftar. Kirim /setadmin dari akun Telegram Anda untuk mendaftarkan akun admin.", flush=True)
    print(f"Tekan Ctrl + C di terminal untuk menghentikan bot.", flush=True)
    print(f"==================================================", flush=True)
    try:
        # skip_pending=True mencegah error query lama/kadaluarsa saat bot baru dinyalakan
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan: {e}", flush=True)
