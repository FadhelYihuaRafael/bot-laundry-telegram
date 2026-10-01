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

# API Key untuk Google Gemini AI (Opsional: jika diisi, bot bisa menjawab pertanyaan apapun secara cerdas tanpa batas)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# File untuk menyimpan ID Admin agar tidak hilang saat bot restart
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "admin_config.json")

# File untuk menyimpan semua data pesanan laundry
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

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
    """Menyimpan ID Admin ke file konfigurasi"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"admin_chat_id": admin_id}, f, indent=4)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan admin ID: {e}")
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
    """Menyimpan semua data pesanan laundry ke file JSON"""
    try:
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(orders_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan data pesanan: {e}", flush=True)

# Inisialisasi Bot & Admin Chat ID
bot = telebot.TeleBot(BOT_TOKEN)
ADMIN_CHAT_ID = load_admin_id()

# Muat data pesanan yang tersimpan
all_orders = load_orders()

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
            types.BotCommand("myid", "🆔 ID Telegram Saya"),
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
            order_list_text += f"• `{o.get('order_id')}` | {o.get('nama')} ({o.get('layanan')})\n  └ Status: _{st}_\n"
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
        "💡 *Tips Admin:*\n"
        "• Gunakan `/cekpesanan [ID_NOTA]` untuk melihat detail nota.\n"
        "• Klik tombol tahapan di notifikasi pesanan untuk memperbarui status cucian pelanggan.\n"
        "• 💬 *Tanya Asisten Cerdas:* Ketik `/tanya [pertanyaan]` atau langsung kirim pesan chat ke bot!"
    )

    bot.send_message(chat_id, admin_panel_text, parse_mode="Markdown")


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

        # Tombol aksi bagi Admin (WhatsApp + Update Tahapan Laundry)
        admin_markup = types.InlineKeyboardMarkup(row_width=1)
        clean_phone = "".join(filter(str.isdigit, order_data['hp']))
        if clean_phone.startswith("0"):
            clean_phone = "62" + clean_phone[1:]
        elif not clean_phone.startswith("62") and clean_phone:
            clean_phone = "62" + clean_phone

        if clean_phone:
            btn_wa_buyer = types.InlineKeyboardButton("💬 Chat Pelanggan via WhatsApp", url=f"https://wa.me/{clean_phone}")
            admin_markup.add(btn_wa_buyer)

        btn_st_cuci = types.InlineKeyboardButton("🧺 Tandai: Sedang Dicuci", callback_data=f"admin_status_{order_id}_dicuci")
        btn_st_setrika = types.InlineKeyboardButton("👔 Tandai: Sedang Disetrika & Packing", callback_data=f"admin_status_{order_id}_disetrika")
        btn_st_siap = types.InlineKeyboardButton("🛵 Tandai: Siap Diantar / Diambil", callback_data=f"admin_status_{order_id}_siap_antar")
        btn_st_selesai = types.InlineKeyboardButton("✅ Tandai: Cucian Selesai", callback_data=f"admin_status_{order_id}_selesai")
        btn_st_batal = types.InlineKeyboardButton("❌ Batalkan Pesanan", callback_data=f"admin_status_{order_id}_dibatalkan")
        admin_markup.add(btn_st_cuci, btn_st_setrika, btn_st_siap, btn_st_selesai, btn_st_batal)

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
                elif new_status == "selesai":
                    notif_msg += "🎉 Terima kasih banyak telah mempercayakan cucian Anda pada FreshClean Laundry! Semoga puas dengan layanan kami! ⭐⭐⭐⭐⭐"
                else:
                    notif_msg += "Pakaian Anda sedang kami proses dengan higienis dan teliti. Kami akan kabari kembali saat siap diantar."

                bot.send_message(
                    buyer_id,
                    notif_msg,
                    parse_mode="Markdown",
                    reply_markup=back_to_main_menu()
                )
                print(f"[INFO] Notifikasi update status {target_order_id} ({new_status}) terkirim ke pelanggan {buyer_id}", flush=True)
            except Exception as e:
                print(f"[ERROR] Gagal mengirim notifikasi status ke pelanggan {buyer_id}: {e}", flush=True)

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
    else:
        alamat_hint = "Masukkan *Alamat Lengkap Penjemputan* (Nama Jalan, No. Rumah/Kost/Kamar, RT/RW, Patokan):"

    msg = bot.send_message(
        chat_id,
        f"📍 *LANGKAH 3/4 - ALAMAT*\n"
        "─────────────────────────\n"
        f"{alamat_hint}",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    bot.register_next_step_handler(msg, step_input_alamat)

def step_input_alamat(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_orders.pop(chat_id, None)
        bot.send_message(chat_id, "Pesanan laundry dibatalkan.", reply_markup=persistent_menu_markup())
        bot.send_message(chat_id, "Kembali ke menu utama:", reply_markup=main_menu())
        return

    user_orders[chat_id]["alamat"] = message.text.strip()

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
    result_text = (
        "🔍 *STATUS PENGERJAAN CUCIAN*\n"
        "─────────────────────────\n"
        f"🆔 *No. Nota:* `{order_id}`\n"
        f"⏱️ *Waktu Order:* {order_rec['waktu']}\n\n"
        f"🧺 *Layanan:* {layanan_nama}\n"
        f"⚖️ *Estimasi:* {order_rec.get('estimasi', '-')}\n"
        f"👤 *Nama Pelanggan:* {order_rec['nama']}\n"
        f"📍 *Alamat:* {order_rec['alamat']}\n\n"
        f"📊 *Status Cucian:* *{status_label}*\n"
        "─────────────────────────\n"
        "Jika ada pertanyaan mengenai cucian Anda, silakan hubungi Admin / CS."
    )
    bot.send_message(chat_id, result_text, parse_mode="Markdown", reply_markup=back_to_main_menu())


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
            bot.reply_to(
                message,
                f"🔍 *Status Nota `{order_id}`*\n\n"
                f"🧺 Layanan: {layanan_nama}\n"
                f"📊 Status: *{status_label}*\n"
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
# ASISTEN PINTAR KHUSUS ADMIN (/tanya & CHAT LANGSUNG)
# ==========================================
def call_gemini_ai(query, admin_name):
    """Memanggil Google Gemini REST API jika GEMINI_API_KEY telah diatur"""
    if not GEMINI_API_KEY:
        return None
    try:
        total_orders = len(all_orders)
        active_orders = [o for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"]]
        sample_list = []
        for o in active_orders[:8]:
            sample_list.append(f"- Nota: {o.get('order_id')} | Pelanggan: {o.get('nama')} | HP: {o.get('hp')} | Paket: {o.get('layanan')} | Status: {o.get('status')}")
        sample_text = "\n".join(sample_list) if sample_list else "Tidak ada antrean cucian aktif."

        prompt_system = (
            f"Kamu adalah Asisten Pintar Pribadi untuk Pemilik/Admin FreshClean Laundry (bernama {admin_name}).\n"
            "Tugasmu membantu pemilik laundry mengelola bisnis, menganalisis data pesanan, memberikan tips operasional laundry (cara penanganan noda membandel, takaran deterjen, pemilihan parfum, SOP cuci/setrika), membuat draft pesan WhatsApp untuk pelanggan, atau memberikan strategi bisnis laundry.\n"
            "Jawablah dengan bahasa Indonesia yang ramah, profesional, ringkas, dan jelas menggunakan format Markdown Telegram (*bold*, _italic_, bullet points).\n\n"
            f"Data Usaha Laundry Saat Ini:\n"
            f"- Total seluruh nota tersimpan: {total_orders}\n"
            f"- Pesanan yang sedang aktif/berjalan: {len(active_orders)}\n"
            f"- Antrean Aktif Terkini:\n{sample_text}\n"
            "- Layanan & Tarif: Kiloan Reguler Rp 7.000/kg (2 Hari), Kilat Express Rp 10.000/kg (24 Jam), Super Express Rp 15.000/kg (6 Jam), Bed Cover Single Rp 20.000, Jumbo Rp 30.000, Cuci Sepatu Deep Clean Rp 25.000 - Rp 35.000.\n\n"
            f"Pertanyaan Pemilik/Admin:\n{query}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt_system}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
        }
        data_json = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_json, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidate = result.get("candidates", [])[0]
            answer = candidate.get("content", {}).get("parts", [])[0].get("text", "")
            return answer.strip()
    except Exception as e:
        print(f"[WARN] Gemini AI gagal dipanggil: {e}", flush=True)
        return None


def smart_local_assistant(query, admin_name):
    """Mesin asisten cerdas bawaan offline jika tanpa API Key Gemini"""
    q = query.lower()

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
        est_omset = selesai * 28000
        return (
            "💰 *RINGKASAN ESTIMASI PENDAPATAN & PESANAN*\n"
            "─────────────────────────\n"
            f"📦 Total Seluruh Nota Masuk : *{total} nota*\n"
            f"✅ Pesanan Selesai          : *{selesai} nota*\n"
            f"⏳ Pesanan Sedang Diproses  : *{aktif} nota*\n"
            f"💵 Estimasi Pendapatan      : *± Rp {est_omset:,}*\n"
            "─────────────────────────\n"
            "💡 _Estimasi dihitung berdasarkan rata-rata Rp 28.000/nota dari pesanan yang selesai._"
        )

    # 4. TIPS MENANGANI NODA MEMBANDEL
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
            "3. Kucek dengan air hangat sebelum dimasukkan ke mesin cuci."
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
    if "sepatu" in q:
        return (
            "👟 *SOP CUCI SEPATU DEEP CLEAN:*\n"
            "─────────────────────────\n"
            "• Gunakan sikat bulu kuda untuk upper material (kanvas/suede).\n"
            "• Gunakan sikat kaku untuk midsole & outsole.\n"
            "• Hindari mencelupkan sepatu langsung ke air banyak.\n"
            "• Jangan jemur sepatu di bawah terik matahari langsung agar outsole tidak menguning (_unyellowing_)."
        )

    # 5. TEMPLATE PESAN WHATSAPP
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
        else:
            return (
                "📝 *PILIHAN TEMPLATE CHAT WA:*\n"
                "1. Ketik: _'template penjemputan cucian'_\n"
                "2. Ketik: _'template rincian tagihan'_\n"
                "3. Ketik: _'template cucian siap antar'_\n"
                "4. Ketik: _'template permohonan maaf keterlambatan'_"
            )

    # 6. JAWABAN UMUM & MENU BANTUAN
    return (
        f"🤖 *Halo Bos {admin_name}!* Saya Asisten Cerdas FreshClean Laundry.\n\n"
        "Saya siap membantu operasional toko Anda. Coba tanyakan hal berikut:\n"
        "• _'Siapa saja yang cuciannya belum selesai?'_\n"
        "• _'Cari pesanan nama [Nama Pelanggan]'_\n"
        "• _'Berapa omset dan total pesanan saat ini?'_\n"
        "• _'Bagaimana cara menghilangkan noda minyak / darah / jamur?'_\n"
        "• _'Buatkan template chat WhatsApp konfirmasi penjemputan'_\n\n"
        "💡 *Tips AI:* Anda dapat menyetel `GEMINI_API_KEY` di pengaturan bot jika ingin saya menjawab pertanyaan bebas apapun dengan kecerdasan AI Google Gemini!"
    )


def process_admin_query(message, query):
    """Memproses pertanyaan admin dan mengirimkan balasan cerdas"""
    chat_id = message.chat.id
    admin_name = message.from_user.first_name or "Bos"

    try:
        bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass

    # 1. Coba via Gemini AI jika API Key ada
    answer = call_gemini_ai(query, admin_name)

    # 2. Jika tanpa API Key atau offline, gunakan asisten cerdas lokal
    if not answer:
        answer = smart_local_assistant(query, admin_name)

    bot.reply_to(message, answer, parse_mode="Markdown")


@bot.message_handler(commands=['tanya', 'ai', 'ask'])
def tanya_admin_command(message):
    """Perintah khusus admin untuk bertanya kepada Asisten Bot"""
    chat_id = message.chat.id
    if chat_id != ADMIN_CHAT_ID:
        bot.reply_to(
            message,
            "⛔ *Akses Ditolak!*\n"
            "Fitur asisten cerdas ini hanya dapat diakses oleh Pemilik / Admin Resmi FreshClean Laundry.",
            parse_mode="Markdown"
        )
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) >= 2:
        query = parts[1]
        process_admin_query(message, query)
    else:
        msg = bot.reply_to(
            message,
            "💬 *Halo Admin FreshClean!* 🤖\n\n"
            "Silakan ketik pertanyaan apa saja yang ingin Anda tanyakan ke Asisten Toko.\n"
            "Contoh:\n"
            "• _'Siapa saja yang cuciannya belum selesai?'_\n"
            "• _'Cari pesanan nama Fadhel'_\n"
            "• _'Bagaimana cara membersihkan noda oli di baju putih?'_\n"
            "• _'Berapa estimasi omset dan antrean saat ini?'_\n\n"
            "_(Ketik pertanyaan Anda sekarang)_",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, step_admin_tanya)


def step_admin_tanya(message):
    """Handler langkah berikutnya untuk pertanyaan admin"""
    if is_cancelled(message):
        bot.send_message(message.chat.id, "Sesi tanya jawab ditutup.", reply_markup=main_menu())
        return
    process_admin_query(message, message.text.strip())


@bot.message_handler(func=lambda msg: True, content_types=['text'])
def default_message_router(message):
    """Router pesan teks: Menjawab pertanyaan admin jika Admin yang chat, atau mengarahkan pelanggan"""
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # Jika pengirim adalah ADMIN dan tidak sedang mengisi form order, perlakukan sebagai pertanyaan ke Asisten
    if chat_id == ADMIN_CHAT_ID:
        process_admin_query(message, text)
        return

    # Jika pelanggan biasa mengirim teks acak, arahkan ke menu utama
    bot.send_message(
        chat_id,
        "Halo! 👋 Ada yang bisa kami bantu seputar cucian Anda di *FreshClean Laundry*?\n\n"
        "Silakan gunakan menu interaktif di bawah untuk melihat tarif, order jemput cucian, atau cek nota:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


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
