import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from telebot import types

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import customer_bot, admin_bot, PORT
from database import load_admin_id
from bot_customer import register_customer_handlers
from bot_admin import register_admin_handlers

def setup_telegram_commands():
    """Mendaftarkan menu tombol perintah resmi Telegram untuk kedua bot"""
    if customer_bot:
        try:
            customer_bot.set_my_commands([
                types.BotCommand("start", "🧺 Menu Utama FreshClean"),
                types.BotCommand("order", "🛵 Pesan Laundry (Jemput/Antar)"),
                types.BotCommand("status", "🔍 Cek Status Cucian & Tagihan"),
                types.BotCommand("tarif", "📋 Daftar Layanan & Tarif Lengkap"),
                types.BotCommand("lokasi", "🏢 Alamat Outlet & Jam Operasional"),
                types.BotCommand("bayar", "💳 Info Rekening & QRIS"),
                types.BotCommand("tanya", "💬 Konsultasi CS / AI Cerdas"),
                types.BotCommand("help", "📖 Panduan Penggunaan")
            ])
            print("✅ Perintah Telegram Bot Pelanggan berhasil didaftarkan.", flush=True)
        except Exception as e:
            print(f"[WARN] Gagal mendaftarkan commands Bot Pelanggan: {e}", flush=True)

    if admin_bot:
        try:
            admin_bot.set_my_commands([
                types.BotCommand("admin", "👑 Panel Kontrol & Dashboard Toko"),
                types.BotCommand("export", "📊 Unduh Rekap Excel (.xlsx)"),
                types.BotCommand("broadcast", "📢 Siaran Pesan Promo ke Pelanggan"),
                types.BotCommand("setadmin", "🔑 Daftarkan Akun Admin Utama")
            ])
            print("✅ Perintah Telegram Bot Admin berhasil didaftarkan.", flush=True)
        except Exception as e:
            print(f"[WARN] Gagal mendaftarkan commands Bot Admin: {e}", flush=True)


def start_cloud_health_server():
    """Web server mini agar bot dapat di-hosting 24/7 di layanan cloud seperti Render.com"""
    port_str = os.environ.get("PORT")
    if not port_str and not os.environ.get("RENDER"):
        return

    try:
        class HealthCheckHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"FreshClean Dual-Bot System (Customer + Admin) is Alive 24/7!")

            def log_message(self, format, *args):
                return

        port = int(port_str or 10000)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"🌐 Cloud Health-check server aktif di port {port}", flush=True)
    except Exception as e:
        print(f"ℹ️ Web server cloud tidak diaktifkan: {e}", flush=True)


def run_customer_bot():
    """Worker polling untuk Bot Pelanggan"""
    if not customer_bot:
        print("⚠️ Token Bot Pelanggan (CUSTOMER_BOT_TOKEN) belum diisi!", flush=True)
        return

    print("🚀 Bot Pelanggan aktif dan siap melayani pesanan...", flush=True)
    while True:
        try:
            customer_bot.infinity_polling(skip_pending=True, timeout=20)
        except Exception as e:
            print(f"[ERROR Bot Pelanggan] Terjadi kesalahan: {e}. Mengulang dalam 5 detik...", flush=True)
            time.sleep(5)


def run_admin_bot():
    """Worker polling untuk Bot Admin / Kasir"""
    if not admin_bot:
        print("⚠️ Token Bot Admin (ADMIN_BOT_TOKEN) belum diisi!", flush=True)
        return

    print("👑 Bot Admin aktif dan siap menerima notifikasi pesanan...", flush=True)
    while True:
        try:
            admin_bot.infinity_polling(skip_pending=True, timeout=20)
        except Exception as e:
            print(f"[ERROR Bot Admin] Terjadi kesalahan: {e}. Mengulang dalam 5 detik...", flush=True)
            time.sleep(5)


def main():
    print("==================================================", flush=True)
    print("✨ FRESHCLEAN LAUNDRY DUAL-BOT SYSTEM BERJALAN ✨", flush=True)
    print("==================================================", flush=True)

    # 1. Daftarkan handler untuk kedua bot
    if customer_bot:
        register_customer_handlers(customer_bot)
    if admin_bot:
        register_admin_handlers(admin_bot)

    # 2. Setup menu perintah resmi di Telegram
    setup_telegram_commands()

    # 3. Jalankan web server mini untuk Cloud (Render)
    start_cloud_health_server()

    # Info status
    admin_id = load_admin_id()
    if admin_id:
        print(f"🔔 Admin Chat ID terdaftar: {admin_id}", flush=True)
    else:
        print(f"⚠️ Belum ada Admin terdaftar. Kirim /setadmin dari Bot Admin untuk mendaftar.", flush=True)

    # 4. Jalankan kedua bot dalam thread terpisah
    t_customer = threading.Thread(target=run_customer_bot, daemon=True, name="CustomerBotThread")
    t_admin = threading.Thread(target=run_admin_bot, daemon=True, name="AdminBotThread")

    t_customer.start()
    t_admin.start()

    print("Tekan Ctrl + C di terminal untuk menghentikan kedua bot.", flush=True)
    print("==================================================", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Sistem Dual-Bot dihentikan oleh pengguna.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
