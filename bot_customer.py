import re
from datetime import datetime
from telebot import types
from config import customer_bot, admin_bot, safe_send, STATUS_LIST, STATUS_EMOJIS
from database import (
    load_admin_id, add_order, get_order, update_order, 
    get_orders_by_buyer, get_all_orders
)
from ai_helper import get_ai_reply

# State sementara pesanan pelanggan
user_order_drafts = {}
user_uploading_proof = {}

def customer_main_menu():
    """Menu tombol interaktif utama pelanggan"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_order = types.InlineKeyboardButton("🛵 Pesan Laundry (Jemput)", callback_data="order_now")
    btn_status = types.InlineKeyboardButton("🔍 Cek Status Cucian", callback_data="cek_pesanan")
    btn_tarif = types.InlineKeyboardButton("📋 Layanan & Tarif", callback_data="lihat_tarif")
    btn_info = types.InlineKeyboardButton("🏢 Info Outlet & Jam Buka", callback_data="info_toko")
    btn_bayar = types.InlineKeyboardButton("💳 Rekening & Cara Bayar", callback_data="info_bayar")
    btn_tanya = types.InlineKeyboardButton("💬 Tanya CS / AI Cerdas", callback_data="tanya_cs")
    
    markup.add(btn_order)
    markup.add(btn_status, btn_tarif)
    markup.add(btn_info, btn_bayar)
    markup.add(btn_tanya)
    return markup

def back_to_customer_menu():
    """Tombol kembali ke menu utama pelanggan"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_utama"))
    return markup

def cancel_order_markup():
    """Tombol batal saat proses order"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row(types.KeyboardButton("❌ Batal Pesan"), types.KeyboardButton("🚀 /start"))
    return markup

def is_cancelled(message):
    """Cek apakah pelanggan membatalkan pesanan"""
    text = (message.text or "").strip().lower()
    return text in ["❌ batal pesan", "batal", "cancel", "/batal", "/start"]

# ==========================================
# HANDLER COMMAND PELANGGAN
# ==========================================
def register_customer_handlers(bot):
    """Mendaftarkan semua handler pesan dan callback untuk Bot Pelanggan"""

    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        chat_id = message.chat.id
        first_name = message.from_user.first_name or "Pelanggan"
        
        welcome_text = (
            f"🧺 *SELAMAT DATANG DI FRESHCLEAN LAUNDRY!* ✨\n"
            f"─────────────────────────\n"
            f"Halo, Kak *{first_name}*! 👋\n"
            f"Solusi laundry higienis, wangi tahan lama, rapi, dan tepat waktu.\n\n"
            f"🌟 *Keunggulan Layanan Kami:*\n"
            f"• *1 Mesin 1 Pelanggan* (pakaian tidak dicampur)\n"
            f"• *Gratis Jemput & Antar* (radius 3 km, min. 4 kg)\n"
            f"• *Deterjen Premium & 4 Pilihan Aroma Mewah*\n"
            f"• *Garansi Cuci Ulang* jika kurang bersih!\n"
            f"─────────────────────────\n"
            f"Silakan pilih menu di bawah ini:"
        )
        safe_send(bot, chat_id, welcome_text, reply_markup=customer_main_menu())

    @bot.message_handler(commands=['help', 'bantuan'])
    def cmd_help(message):
        help_text = (
            "📖 *PANDUAN PENGGUNAAN BOT FRESHCLEAN:*\n"
            "─────────────────────────\n"
            "• `/order` : Memulai pesanan laundry baru\n"
            "• `/status [NO_NOTA]` : Mengecek status cucian & tagihan\n"
            "• `/tarif` : Melihat daftar harga & layanan lengkap\n"
            "• `/lokasi` : Info alamat outlet & jam operasional\n"
            "• `/bayar` : Nomor rekening BCA & QRIS pembayaran\n"
            "• `/tanya` : Konsultasi tips noda & pakaian dengan AI\n\n"
            "💡 _Anda juga bisa langsung mengetik pertanyaan bebas di chat ini._"
        )
        safe_send(bot, message.chat.id, help_text, reply_markup=back_to_customer_menu())

    @bot.message_handler(commands=['order', 'pesan'])
    def cmd_order(message):
        start_order_flow(message.chat.id, message.from_user)

    @bot.message_handler(commands=['status', 'cekpesanan'])
    def cmd_status(message):
        parts = message.text.strip().split()
        if len(parts) > 1:
            order_id = parts[1].upper()
            show_order_status(message.chat.id, order_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "🔍 *CEK STATUS CUCIAN*\n"
                "─────────────────────────\n"
                "Ketik nomor nota Anda (contoh: `LDR-1616`):",
                parse_mode="Markdown",
                reply_markup=cancel_order_markup()
            )
            bot.register_next_step_handler(msg, step_input_order_id_status)

    @bot.message_handler(commands=['tarif', 'harga', 'layanan'])
    def cmd_tarif(message):
        send_tarif_info(message.chat.id)

    @bot.message_handler(commands=['lokasi', 'outlet', 'jam'])
    def cmd_lokasi(message):
        send_outlet_info(message.chat.id)

    @bot.message_handler(commands=['bayar', 'rekening', 'qris'])
    def cmd_bayar(message):
        send_payment_info(message.chat.id)

    @bot.message_handler(commands=['tanya'])
    def cmd_tanya(message):
        msg = bot.send_message(
            message.chat.id,
            "💬 *TANYA ASISTEN FRESHCLEAN AI*\n"
            "─────────────────────────\n"
            "Silakan ketik pertanyaan Anda seputar laundry, jam operasional, atau tips noda pakaian:",
            parse_mode="Markdown",
            reply_markup=cancel_order_markup()
        )
        bot.register_next_step_handler(msg, step_user_ask_ai)

    # ==========================================
    # HANDLER CALLBACK INLINE TOMBOL
    # ==========================================
    @bot.callback_query_handler(func=lambda call: True)
    def handle_customer_callback(call):
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        data = call.data

        if data == "menu_utama":
            bot.answer_callback_query(call.id)
            welcome_text = (
                f"🧺 *MENU UTAMA FRESHCLEAN LAUNDRY* ✨\n"
                f"─────────────────────────\n"
                f"Silakan pilih layanan yang Anda perlukan di bawah ini:"
            )
            try:
                bot.edit_message_text(welcome_text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=customer_main_menu())
            except Exception:
                safe_send(bot, chat_id, welcome_text, reply_markup=customer_main_menu())

        elif data == "order_now":
            bot.answer_callback_query(call.id)
            start_order_flow(chat_id, call.from_user)

        elif data == "cek_pesanan":
            bot.answer_callback_query(call.id)
            # Tampilkan riwayat pesanan aktif jika ada
            user_orders = get_orders_by_buyer(chat_id)
            if user_orders:
                markup = types.InlineKeyboardMarkup(row_width=1)
                for o in sorted(user_orders, key=lambda x: x.get("waktu", ""), reverse=True)[:5]:
                    st_icon = STATUS_EMOJIS.get(o.get("status"), "📦")
                    btn_text = f"{st_icon} Nota {o.get('order_id')} ({o.get('layanan', 'Cucian')[:18]}...)"
                    markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"view_st_{o.get('order_id')}"))
                markup.add(types.InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_utama"))
                bot.send_message(chat_id, "🔍 *Pilih Nota Cucian Anda yang Ingin Dicek:*", parse_mode="Markdown", reply_markup=markup)
            else:
                msg = bot.send_message(
                    chat_id,
                    "🔍 *CEK STATUS CUCIAN*\n"
                    "─────────────────────────\n"
                    "Masukkan nomor nota cucian Anda (contoh: `LDR-1616`):",
                    parse_mode="Markdown",
                    reply_markup=cancel_order_markup()
                )
                bot.register_next_step_handler(msg, step_input_order_id_status)

        elif data.startswith("view_st_"):
            bot.answer_callback_query(call.id)
            order_id = data.replace("view_st_", "")
            show_order_status(chat_id, order_id)

        elif data == "lihat_tarif":
            bot.answer_callback_query(call.id)
            send_tarif_info(chat_id)

        elif data == "info_toko":
            bot.answer_callback_query(call.id)
            send_outlet_info(chat_id)

        elif data == "info_bayar":
            bot.answer_callback_query(call.id)
            send_payment_info(chat_id)

        elif data == "tanya_cs":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                chat_id,
                "💬 *TANYA ASISTEN FRESHCLEAN AI*\n"
                "─────────────────────────\n"
                "Ketik pertanyaan Anda sekarang seputar cucian, paket, atau jam operasional:",
                parse_mode="Markdown",
                reply_markup=cancel_order_markup()
            )
            bot.register_next_step_handler(msg, step_user_ask_ai)

        elif data.startswith("kirim_bukti_"):
            bot.answer_callback_query(call.id)
            order_id = data.replace("kirim_bukti_", "")
            user_uploading_proof[chat_id] = order_id
            msg = bot.send_message(
                chat_id,
                f"📸 *KIRIM BUKTI PEMBAYARAN NOTA `{order_id}`*\n"
                "─────────────────────────\n"
                "Silakan kirimkan foto struk / tangkapan layar transfer sekarang:\n"
                "_(Kirim sebagai gambar biasa)_",
                parse_mode="Markdown",
                reply_markup=cancel_order_markup()
            )
            bot.register_next_step_handler(msg, step_receive_payment_proof, order_id)

        elif data.startswith("rate_"):
            bot.answer_callback_query(call.id, "Terima kasih atas ulasannya! ⭐")
            # format: rate_{order_id}_{rating}
            parts = data.split("_")
            if len(parts) >= 3:
                order_id = parts[1]
                rating_val = parts[2]
                update_order(order_id, rating=rating_val)
                stars_text = "⭐" * int(rating_val)
                bot.edit_message_text(
                    f"🎉 *TERIMA KASIH ATAS ULASAN ANDA!* ✨\n\n"
                    f"Anda memberikan rating: {stars_text} ({rating_val}/5)\n"
                    f"Ulasan Anda sangat berarti untuk membantu kami menjaga kualitas layanan terbaik.",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="Markdown",
                    reply_markup=back_to_customer_menu()
                )
                # Notifikasi ke Bot Admin
                admin_id = load_admin_id()
                if admin_id and admin_bot:
                    safe_send(
                        admin_bot,
                        admin_id,
                        f"⭐ *ULASAN BARU DARI PELANGGAN!*\n"
                        f"• Nota: `{order_id}`\n"
                        f"• Rating: *{stars_text} ({rating_val}/5)*"
                    )

        # Pemilihan Layanan di Alur Order
        elif data.startswith("select_srv_"):
            bot.answer_callback_query(call.id)
            srv_code = data.replace("select_srv_", "")
            srv_map = {
                "reg": "Cuci Komplit Reguler (2 Hari)",
                "klt": "Cuci Komplit Kilat (1 Hari)",
                "exp": "Cuci Express Super (5 Jam)",
                "lipat": "Cuci Kering Lipat (Non-Setrika)",
                "setrika": "Setrika Uap Saja (Rapi & Wangi)",
                "bedcover": "Cuci Bed Cover / Selimut Tebal",
                "sepatu": "Cuci Sepatu Premium Sneakers"
            }
            layanan_pilihan = srv_map.get(srv_code, "Cuci Komplit Reguler")
            user_order_drafts[chat_id] = {"layanan": layanan_pilihan}

            # Lanjut ke Estimasi Berat / Pcs
            est_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            est_markup.row(types.KeyboardButton("1-3 Kg"), types.KeyboardButton("4-6 Kg"))
            est_markup.row(types.KeyboardButton("7-10 Kg"), types.KeyboardButton("Lebih dari 10 Kg"))
            est_markup.row(types.KeyboardButton("1 Pcs Bed Cover"), types.KeyboardButton("1 Pasang Sepatu"))
            est_markup.row(types.KeyboardButton("❌ Batal Pesan"))

            msg = bot.send_message(
                chat_id,
                f"✅ *Layanan Terpilih:* {layanan_pilihan}\n\n"
                f"⚖️ *LANGKAH 2/6 - PERKIRAAN JUMLAH/BERAT:*\n"
                f"Pilih atau ketik perkiraan berat cucian Anda:\n"
                f"_(Berat pasti akan ditimbang riil menggunakan timbangan digital saat tiba di outlet)_",
                parse_mode="Markdown",
                reply_markup=est_markup
            )
            bot.register_next_step_handler(msg, step_input_estimasi)

        # Konfirmasi Akhir Pesanan
        elif data == "confirm_order_final":
            bot.answer_callback_query(call.id)
            finalize_order(chat_id, call.message)

        elif data == "cancel_order_final":
            bot.answer_callback_query(call.id, "Pesanan dibatalkan")
            user_order_drafts.pop(chat_id, None)
            bot.edit_message_text(
                "❌ *Pemesanan laundry telah dibatalkan.*",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown",
                reply_markup=customer_main_menu()
            )

    # ==========================================
    # HANDLER FOTO LANGSUNG (BUKTI TRANSFER)
    # ==========================================
    @bot.message_handler(content_types=['photo'])
    def handle_customer_photo(message):
        chat_id = message.chat.id
        # Cek apakah sedang menunggu bukti untuk order tertentu
        pending_order_id = user_uploading_proof.get(chat_id)
        if not pending_order_id:
            # Cari pesanan aktif pengguna yang belum lunas
            active_orders = [
                o for o in get_orders_by_buyer(chat_id)
                if o.get("status") not in ["selesai", "dibatalkan"]
            ]
            if active_orders:
                latest = sorted(active_orders, key=lambda x: x.get("waktu", ""), reverse=True)[0]
                pending_order_id = latest.get("order_id")

        if pending_order_id:
            step_receive_payment_proof(message, pending_order_id)
        else:
            safe_send(
                bot,
                chat_id,
                "📸 Terima kasih telah mengirim gambar.\n"
                "Jika ini adalah bukti transfer pembayaran, silakan buat pesanan terlebih dahulu melalui menu *🛵 Pesan Laundry* (`/order`).",
                reply_markup=customer_main_menu()
            )

    # ==========================================
    # ROUTER PESAN TEKS BEBAS (AI ASISTEN)
    # ==========================================
    @bot.message_handler(func=lambda msg: True, content_types=['text'])
    def handle_customer_text(message):
        chat_id = message.chat.id
        text = (message.text or "").strip()
        first_name = message.from_user.first_name or "Pelanggan"

        # Cek jika pengguna mengetik nomor nota langsung (misal: LDR-1234)
        if re.match(r"^ldr-\d+$", text.lower()):
            show_order_status(chat_id, text.upper())
            return

        # Kirim aksi typing agar interaktif
        try:
            bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass

        ai_response = get_ai_reply(text, first_name, is_admin=False)
        safe_send(bot, chat_id, ai_response, reply_markup=customer_main_menu())


# ==========================================
# WIZARD PEMESANAN LAUNDRY INTERAKTIF
# ==========================================
def start_order_flow(chat_id, user_obj):
    """Langkah 1: Menampilkan pilihan layanan"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("👕 Cuci Komplit Reguler (2 Hari) - Rp 7.000/kg", callback_data="select_srv_reg"))
    markup.add(types.InlineKeyboardButton("⚡ Cuci Komplit Kilat (1 Hari) - Rp 10.000/kg", callback_data="select_srv_klt"))
    markup.add(types.InlineKeyboardButton("🚀 Cuci Express Super (5 Jam) - Rp 15.000/kg", callback_data="select_srv_exp"))
    markup.add(types.InlineKeyboardButton("🧺 Cuci Kering Lipat (Non-Setrika) - Rp 5.000/kg", callback_data="select_srv_lipat"))
    markup.add(types.InlineKeyboardButton("♨️ Setrika Uap Rapi & Wangi - Rp 4.000/kg", callback_data="select_srv_setrika"))
    markup.add(types.InlineKeyboardButton("🛏️ Cuci Bed Cover / Selimut - Mulai Rp 25.000", callback_data="select_srv_bedcover"))
    markup.add(types.InlineKeyboardButton("👟 Cuci Sepatu Sneakers - Mulai Rp 25.000", callback_data="select_srv_sepatu"))
    markup.add(types.InlineKeyboardButton("❌ Batal Pesan", callback_data="menu_utama"))

    user_order_drafts[chat_id] = {
        "buyer_chat_id": chat_id,
        "buyer_username": user_obj.username or user_obj.first_name or "Pelanggan"
    }

    safe_send(
        customer_bot,
        chat_id,
        "🛵 *FORMULIR PEMESANAN FRESHCLEAN LAUNDRY*\n"
        "─────────────────────────\n"
        "📍 *LANGKAH 1/6 - PILIH LAYANAN:*\n"
        "Silakan klik salah satu jenis layanan di bawah ini:",
        reply_markup=markup
    )

def step_input_estimasi(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    user_order_drafts[chat_id]["estimasi"] = message.text.strip()

    # Langkah 3: Metode Antar / Jemput
    mtd_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    mtd_markup.row(types.KeyboardButton("🛵 Dijemput Kurir ke Rumah / Kost"), types.KeyboardButton("🏢 Antar Sendiri ke Outlet"))
    mtd_markup.row(types.KeyboardButton("❌ Batal Pesan"))

    msg = customer_bot.send_message(
        chat_id,
        "🛵 *LANGKAH 3/6 - METODE ANTAR-JEMPUT:*\n"
        "Apakah cucian ingin dijemput kurir kami atau Anda antar sendiri ke outlet?",
        parse_mode="Markdown",
        reply_markup=mtd_markup
    )
    customer_bot.register_next_step_handler(msg, step_input_metode)

def step_input_metode(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    user_order_drafts[chat_id]["metode"] = message.text.strip()

    msg = customer_bot.send_message(
        chat_id,
        "👤 *LANGKAH 4/6 - NAMA LENGKAP:*\n"
        "Masukkan nama pemesan / pemilik cucian:",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    customer_bot.register_next_step_handler(msg, step_input_nama)

def step_input_nama(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    user_order_drafts[chat_id]["nama"] = message.text.strip()

    msg = customer_bot.send_message(
        chat_id,
        "📞 *LANGKAH 5/6 - NOMOR WHATSAPP:*\n"
        "Masukkan nomor WhatsApp aktif Anda (contoh: `081234567890`):",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    customer_bot.register_next_step_handler(msg, step_input_hp)

def step_input_hp(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    hp = message.text.strip()
    user_order_drafts[chat_id]["hp"] = hp

    # Langkah 6: Alamat & GPS
    loc_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    loc_markup.row(types.KeyboardButton("📍 Kirim Titik Lokasi GPS Saya", request_location=True))
    loc_markup.row(types.KeyboardButton("❌ Batal Pesan"))

    msg = customer_bot.send_message(
        chat_id,
        "📍 *LANGKAH 6/6 - ALAMAT PENJEMPUTAN:*\n"
        "Ketik alamat lengkap (Nama Jalan, No. Rumah/Kost/Kamar, Patokan)\n\n"
        "💡 *Tips:* Anda juga bisa langsung menekan tombol *📍 Kirim Titik Lokasi GPS Saya* di bawah agar kurir tidak tersasar!",
        parse_mode="Markdown",
        reply_markup=loc_markup
    )
    customer_bot.register_next_step_handler(msg, step_input_alamat)

def step_input_alamat(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        user_order_drafts[chat_id]["alamat"] = f"📍 Titik GPS: {lat:.6f}, {lon:.6f}"
        user_order_drafts[chat_id]["maps_link"] = maps_link
    else:
        user_order_drafts[chat_id]["alamat"] = (message.text or "-").strip()
        user_order_drafts[chat_id]["maps_link"] = ""

    # Catatan Tambahan
    msg = customer_bot.send_message(
        chat_id,
        "📝 *CATATAN TAMBAHAN (OPSIONAL):*\n"
        "Tulis instruksi khusus (misal: *Pilihan aroma Snappy*, *ada noda kopi di kemeja putih*), atau ketik `-` jika tidak ada:",
        parse_mode="Markdown",
        reply_markup=cancel_order_markup()
    )
    customer_bot.register_next_step_handler(msg, step_input_catatan)

def step_input_catatan(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        user_order_drafts.pop(chat_id, None)
        safe_send(customer_bot, chat_id, "Pemesanan dibatalkan.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    user_order_drafts[chat_id]["catatan"] = (message.text or "-").strip()

    # Tampilkan Ringkasan Konfirmasi
    draft = user_order_drafts[chat_id]
    summary_text = (
        "📋 *RINGKASAN PESANAN ANDA*\n"
        "─────────────────────────\n"
        f"🧺 *Layanan:* {draft.get('layanan')}\n"
        f"⚖️ *Perkiraan:* {draft.get('estimasi')}\n"
        f"🛵 *Metode:* {draft.get('metode')}\n"
        f"👤 *Nama:* {draft.get('nama')}\n"
        f"📞 *WhatsApp:* {draft.get('hp')}\n"
        f"📍 *Alamat:* {draft.get('alamat')}\n"
        f"📝 *Catatan:* {draft.get('catatan')}\n"
        "─────────────────────────\n"
        "Apakah data di atas sudah benar?"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Konfirmasi Pesan", callback_data="confirm_order_final"),
        types.InlineKeyboardButton("❌ Batal", callback_data="cancel_order_final")
    )

    safe_send(customer_bot, chat_id, "Menyimpan data...", reply_markup=types.ReplyKeyboardRemove())
    safe_send(customer_bot, chat_id, summary_text, reply_markup=markup)

def finalize_order(chat_id, message):
    """Menyimpan pesanan dan mengirimkan notifikasi ke Pelanggan dan Admin"""
    draft = user_order_drafts.get(chat_id)
    if not draft:
        safe_send(customer_bot, chat_id, "Terjadi kesalahan. Silakan ulangi pemesanan dengan /order.", reply_markup=customer_main_menu())
        return

    # Buat Order ID Unik (contoh: LDR-4821)
    timestamp_str = datetime.now().strftime("%d-%m-%Y %H:%M WIB")
    import random
    order_id = f"LDR-{random.randint(1000, 9999)}"

    order_record = {
        "order_id": order_id,
        "buyer_chat_id": chat_id,
        "buyer_username": draft.get("buyer_username", "-"),
        "nama": draft.get("nama", "-"),
        "hp": draft.get("hp", "-"),
        "layanan": draft.get("layanan", "-"),
        "estimasi": draft.get("estimasi", "-"),
        "metode": draft.get("metode", "-"),
        "alamat": draft.get("alamat", "-"),
        "maps_link": draft.get("maps_link", ""),
        "catatan": draft.get("catatan", "-"),
        "waktu": timestamp_str,
        "status": "menunggu",
        "total_bayar": 0,
        "status_bayar": "Belum Lunas",
        "berat_riil": ""
    }

    # Simpan ke database
    add_order(order_id, order_record)
    user_order_drafts.pop(chat_id, None)

    # 1. Kirim Nota ke Pelanggan
    nota_pelanggan = (
        f"🎉 *PESANAN LAUNDRY BERHASIL DIBUAT!* ✨\n"
        f"─────────────────────────\n"
        f"📄 *Nomor Nota:* `{order_id}`\n"
        f"⏱️ *Waktu Order:* {timestamp_str}\n\n"
        f"🧺 *Layanan:* {order_record['layanan']}\n"
        f"⚖️ *Perkiraan:* {order_record['estimasi']}\n"
        f"🛵 *Metode:* {order_record['metode']}\n"
        f"📍 *Alamat:* {order_record['alamat']}\n"
        f"📊 *Status:* *Menunggu Penjemputan / Konfirmasi Kurir*\n"
        f"─────────────────────────\n"
        f"💡 _Simpan nomor nota Anda. Gunakan menu *🔍 Cek Status Cucian* atau ketik `/status {order_id}` untuk memantau cucian._"
    )
    safe_send(customer_bot, chat_id, nota_pelanggan, reply_markup=customer_main_menu())

    # 2. Kirim Notifikasi Real-Time ke BOT ADMIN
    admin_id = load_admin_id()
    if admin_id and admin_bot:
        hp_clean = re.sub(r"[^\d]", "", order_record['hp'])
        if hp_clean.startswith("0"):
            hp_wa = "62" + hp_clean[1:]
        else:
            hp_wa = hp_clean
        wa_link = f"https://wa.me/{hp_wa}?text=Halo%20Kak%20{order_record['nama']},%20kurir%20FreshClean%20Laundry%20akan%20segera%20menjemput%20cucian%20Anda%20(Nota%20{order_id})."

        admin_notif = (
            f"🔔 *PESANAN LAUNDRY BARU MASUK!* 🧺\n"
            f"─────────────────────────\n"
            f"📄 *No. Nota:* `{order_id}`\n"
            f"⏱️ *Waktu:* {timestamp_str}\n\n"
            f"👤 *Pelanggan:* {order_record['nama']} (@{order_record['buyer_username']})\n"
            f"📞 *WhatsApp:* `{order_record['hp']}`\n"
            f"🧺 *Layanan:* {order_record['layanan']}\n"
            f"⚖️ *Estimasi:* {order_record['estimasi']}\n"
            f"🛵 *Metode:* {order_record['metode']}\n"
            f"📍 *Alamat:* {order_record['alamat']}\n"
            f"📝 *Catatan:* {order_record['catatan']}\n"
            f"─────────────────────────\n"
            f"Silakan hubungi pelanggan atau atur tahapan pengerjaan:"
        )

        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        btn_wa = types.InlineKeyboardButton("📞 Hubungi WhatsApp", url=wa_link)
        btn_bill = types.InlineKeyboardButton("⚖️ Input Berat & Tagihan", callback_data=f"admin_bill_{order_id}")
        btn_st_cuci = types.InlineKeyboardButton("🧼 Dicuci", callback_data=f"admin_st_dicuci_{order_id}")
        btn_st_setrika = types.InlineKeyboardButton("♨️ Disetrika", callback_data=f"admin_st_setrika_{order_id}")
        btn_st_siap = types.InlineKeyboardButton("📦 Siap Antar", callback_data=f"admin_st_siap_{order_id}")
        btn_st_selesai = types.InlineKeyboardButton("✅ Selesai", callback_data=f"admin_st_selesai_{order_id}")

        if order_record.get("maps_link"):
            btn_maps = types.InlineKeyboardButton("📍 Buka Google Maps", url=order_record["maps_link"])
            admin_markup.add(btn_wa, btn_maps)
        else:
            admin_markup.add(btn_wa)

        admin_markup.add(btn_bill)
        admin_markup.add(btn_st_cuci, btn_st_setrika)
        admin_markup.add(btn_st_siap, btn_st_selesai)

        safe_send(admin_bot, admin_id, admin_notif, reply_markup=admin_markup)


# ==========================================
# STATUS PESANAN & BUKTI TRANSFER
# ==========================================
def show_order_status(chat_id, order_id):
    """Menampilkan rincian status cucian kepada pelanggan"""
    order_rec = get_order(order_id)
    if not order_rec:
        safe_send(customer_bot, chat_id, f"⚠️ Nomor nota `{order_id}` tidak ditemukan dalam sistem.", reply_markup=back_to_customer_menu())
        return

    st_label = STATUS_LIST.get(order_rec.get("status"), order_rec.get("status", "-"))
    st_icon = STATUS_EMOJIS.get(order_rec.get("status"), "📊")

    billing_text = ""
    if order_rec.get("berat_riil"):
        billing_text += f"⚖️ *Berat Riil Cucian:* {order_rec['berat_riil']}\n"
    if order_rec.get("total_bayar"):
        billing_text += f"💵 *Total Tagihan:* Rp {order_rec['total_bayar']:,}\n"
        billing_text += f"💳 *Status Pembayaran:* *{order_rec.get('status_bayar', 'Belum Lunas')}*\n"
    if order_rec.get("rating"):
        billing_text += f"⭐ *Ulasan Anda:* {'⭐' * int(order_rec['rating'])} ({order_rec['rating']}/5)\n"

    status_card = (
        f"🔍 *STATUS PENGERJAAN CUCIAN*\n"
        f"─────────────────────────\n"
        f"📄 *Nomor Nota:* `{order_id}`\n"
        f"⏱️ *Waktu Order:* {order_rec.get('waktu', '-')}\n\n"
        f"🧺 *Layanan:* {order_rec.get('layanan', '-')}\n"
        f"{billing_text}\n"
        f"{st_icon} *Status Terkini:* *{st_label}*\n"
        f"📍 *Alamat:* {order_rec.get('alamat', '-')}\n"
        f"─────────────────────────\n"
        f"Jika butuh bantuan, silakan gunakan menu Tanya CS."
    )

    markup = types.InlineKeyboardMarkup()
    if order_rec.get("total_bayar") and order_rec.get("status_bayar") != "Lunas":
        markup.add(types.InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data=f"kirim_bukti_{order_id}"))
    markup.add(types.InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_utama"))

    safe_send(customer_bot, chat_id, status_card, reply_markup=markup)

def step_input_order_id_status(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Silakan pilih menu:", reply_markup=customer_main_menu())
        return

    order_id = message.text.strip().upper()
    show_order_status(chat_id, order_id)

def step_receive_payment_proof(message, order_id):
    """Menerima foto bukti transfer dari pelanggan dan meneruskannya ke Bot Admin"""
    chat_id = message.chat.id
    user_uploading_proof.pop(chat_id, None)

    if not message.photo:
        safe_send(customer_bot, chat_id, "⚠️ Harap kirimkan gambar/foto bukti transfer yang jelas.", reply_markup=back_to_customer_menu())
        return

    file_id = message.photo[-1].file_id
    order_rec = get_order(order_id)
    buyer_name = order_rec.get("nama") if order_rec else "Pelanggan"

    # Konfirmasi ke Pelanggan
    safe_send(
        customer_bot,
        chat_id,
        f"✅ *BUKTI TRANSFER DITERIMA!*\n"
        f"─────────────────────────\n"
        f"Bukti pembayaran untuk nota `{order_id}` telah kami terima dan langsung diteruskan ke Kasir.\n"
        f"Status tagihan akan otomatis terupdate setelah diverifikasi. Terima kasih! 🙏",
        reply_markup=customer_main_menu()
    )

    # Kirim ke BOT ADMIN
    admin_id = load_admin_id()
    if admin_id and admin_bot:
        caption = (
            f"📸 *BUKTI TRANSFER PEMBAYARAN MASUK!*\n"
            f"─────────────────────────\n"
            f"📄 *No. Nota:* `{order_id}`\n"
            f"👤 *Pelanggan:* {buyer_name}\n"
            f"💵 *Tagihan:* Rp {order_rec.get('total_bayar', 0):,} ({order_rec.get('status_bayar', 'Belum Lunas')})\n"
            f"─────────────────────────\n"
            f"Silakan verifikasi bukti transfer berikut:"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_approve = types.InlineKeyboardButton("✅ Verifikasi LUNAS", callback_data=f"admin_verify_pay_{order_id}")
        btn_reject = types.InlineKeyboardButton("❌ Tolak Bukti", callback_data=f"admin_reject_pay_{order_id}")
        markup.add(btn_approve, btn_reject)

        try:
            admin_bot.send_photo(admin_id, file_id, caption=caption, parse_mode="Markdown", reply_markup=markup)
        except Exception as e:
            print(f"[ERROR] Gagal kirim foto bukti ke admin: {e}", flush=True)

def step_user_ask_ai(message):
    chat_id = message.chat.id
    if is_cancelled(message):
        safe_send(customer_bot, chat_id, "Sesi tanya jawab ditutup.", reply_markup=types.ReplyKeyboardRemove())
        safe_send(customer_bot, chat_id, "Kembali ke menu utama:", reply_markup=customer_main_menu())
        return

    text = message.text.strip()
    first_name = message.from_user.first_name or "Pelanggan"
    safe_send(customer_bot, chat_id, "Sedang menjawab...", reply_markup=types.ReplyKeyboardRemove())
    
    reply = get_ai_reply(text, first_name, is_admin=False)
    safe_send(customer_bot, chat_id, reply, reply_markup=customer_main_menu())

# ==========================================
# INFORMASI STATIC
# ==========================================
def send_tarif_info(chat_id):
    tarif_text = (
        "🧺 *DAFTAR LAYANAN & TARIF FRESHCLEAN:* 🏷️\n"
        "─────────────────────────\n"
        "👕 *KILOGRAMAN (Pakaian Sehari-hari):*\n"
        "• *Cuci Komplit Reguler* (2 Hari) : Rp 7.000 / kg\n"
        "• *Cuci Komplit Kilat* (1 Hari)   : Rp 10.000 / kg\n"
        "• *Cuci Express Super* (5 Jam)    : Rp 15.000 / kg\n"
        "• *Cuci Kering Lipat* (Tanpa Setrika) : Rp 5.000 / kg\n"
        "• *Setrika Uap Wangi Rapi*        : Rp 4.000 / kg\n\n"
        "🛏️ *SATUAN (Bed Cover & Perlengkapan):*\n"
        "• Bed Cover Single / Sedang : Rp 25.000\n"
        "• Bed Cover King / Jumbo    : Rp 35.000\n"
        "• Selimut Tebal / Sprei Set : Rp 15.000 - Rp 20.000\n"
        "• Cuci Sepatu Sneakers      : Rp 25.000 - Rp 40.000\n"
        "─────────────────────────\n"
        "🛵 *Gratis Ongkir Penjemputan* untuk radius 3 km (min. 4 kg)!\n"
        "Klik *🛵 Pesan Laundry* untuk memesan kurir sekarang."
    )
    safe_send(customer_bot, chat_id, tarif_text, reply_markup=back_to_customer_menu())

def send_outlet_info(chat_id):
    info_text = (
        "🏢 *INFO OUTLET & JAM OPERASIONAL* 📍\n"
        "─────────────────────────\n"
        "🏠 *Alamat Outlet:*\n"
        "Jl. Melati Raya No. 45, Kecamatan Sukajadi, Kota Anda\n\n"
        "⏰ *Jam Operasional:*\n"
        "• Senin - Sabtu : 07.30 - 21.00 WIB\n"
        "• Minggu & Libur: 08.00 - 20.00 WIB\n\n"
        "🛵 *Jangkauan Kurir Jemput-Antar:*\n"
        "Radius hingga 7 km dari outlet kami.\n\n"
        "☎️ *Kontak Customer Service:* 0812-3456-7890"
    )
    safe_send(customer_bot, chat_id, info_text, reply_markup=back_to_customer_menu())

def send_payment_info(chat_id):
    pay_text = (
        "💳 *REKENING & CARA PEMBAYARAN* 💵\n"
        "─────────────────────────\n"
        "Kami menyediakan berbagai opsi pembayaran yang mudah:\n\n"
        "1. *QRIS (Semua Pembayaran Digital):*\n"
        "   Mendukung GoPay, OVO, ShopeePay, DANA, LinkAja, dan semua Mobile Banking.\n\n"
        "2. *Transfer Bank BCA:*\n"
        "   • No. Rekening: `8735091234`\n"
        "   • Atas Nama   : *FreshClean Laundry*\n\n"
        "3. *Bayar Tunai (COD):*\n"
        "   Bayar langsung ke kurir saat cucian Anda diantar.\n"
        "─────────────────────────\n"
        "📸 Bukti transfer dapat langsung Anda kirimkan ke chat bot ini."
    )
    safe_send(customer_bot, chat_id, pay_text, reply_markup=back_to_customer_menu())
