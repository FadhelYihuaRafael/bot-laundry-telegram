import io
import re
from datetime import datetime
from telebot import types
from config import admin_bot, customer_bot, safe_send, ADMIN_PIN, STATUS_LIST, STATUS_EMOJIS
from database import (
    load_admin_id, save_admin_id, get_order, update_order, 
    get_all_orders, get_active_orders, export_orders_csv, export_orders_excel
)
from ai_helper import get_ai_reply

# State draft admin
admin_broadcast_draft = {}
admin_billing_flow = {}

def admin_dashboard_markup():
    """Menu tombol interaktif utama Panel Kontrol Admin"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_active = types.InlineKeyboardButton("⏳ Pesanan Aktif", callback_data="admin_view_active")
    btn_find = types.InlineKeyboardButton("🔍 Cari Nota", callback_data="admin_find_order")
    btn_broadcast = types.InlineKeyboardButton("📢 Siaran Pesan Promo", callback_data="admin_start_broadcast")
    btn_export = types.InlineKeyboardButton("📊 Unduh Rekap Excel (.xlsx)", callback_data="admin_export_excel")
    btn_refresh = types.InlineKeyboardButton("🔄 Refresh Data", callback_data="admin_refresh_panel")
    
    markup.add(btn_active, btn_find)
    markup.add(btn_broadcast, btn_export)
    markup.add(btn_refresh)
    return markup

def back_to_admin_menu():
    """Tombol kembali ke panel admin"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin_panel_main"))
    return markup

def register_admin_handlers(bot):
    """Mendaftarkan seluruh handler pesan dan callback untuk Bot Admin"""

    # ==========================================
    # AUTHENTIKASI & SETUP ADMIN
    # ==========================================
    @bot.message_handler(commands=['setadmin'])
    def cmd_setadmin(message):
        chat_id = message.chat.id
        parts = message.text.strip().split()
        if len(parts) > 1 and parts[1] == ADMIN_PIN:
            save_admin_id(chat_id)
            safe_send(
                bot,
                chat_id,
                f"👑 *SELAMAT DATANG, OWNER/ADMIN!* 🎉\n"
                f"─────────────────────────\n"
                f"Chat ID `{chat_id}` berhasil didaftarkan sebagai Admin Utama FreshClean Laundry.\n"
                f"Semua notifikasi pesanan masuk dan bukti pembayaran akan otomatis dikirimkan ke bot ini.\n\n"
                f"Gunakan perintah `/admin` untuk membuka Dashboard Operasional.",
                reply_markup=admin_dashboard_markup()
            )
        else:
            safe_send(
                bot,
                chat_id,
                "⚠️ *PIN Admin Salah!*\nFormat: `/setadmin [PIN_RAHASIA]`",
                parse_mode="Markdown"
            )

    @bot.message_handler(commands=['start', 'admin', 'panel', 'dashboard'])
    def cmd_admin_panel(message):
        chat_id = message.chat.id
        current_admin = load_admin_id()

        # Otomatis daftarkan jika belum ada admin
        if not current_admin:
            save_admin_id(chat_id)
            current_admin = chat_id

        if chat_id != current_admin:
            safe_send(
                bot,
                chat_id,
                "⛔ *AKSES KHUSUS OWNER / ADMIN*\n"
                "Untuk mendaftarkan akun Telegram Anda sebagai admin, gunakan perintah:\n"
                "`/setadmin [PIN_RAHASIA]`"
            )
            return

        send_dashboard_view(chat_id)

    @bot.message_handler(commands=['export', 'excel'])
    def cmd_export(message):
        chat_id = message.chat.id
        if chat_id != load_admin_id():
            return
        send_excel_export(chat_id)

    @bot.message_handler(commands=['broadcast'])
    def cmd_broadcast(message):
        chat_id = message.chat.id
        if chat_id != load_admin_id():
            return
        start_broadcast_prompt(chat_id)

    # ==========================================
    # HANDLER CALLBACK PANEL ADMIN
    # ==========================================
    @bot.callback_query_handler(func=lambda call: True)
    def handle_admin_callback(call):
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        data = call.data
        admin_id = load_admin_id()

        if chat_id != admin_id:
            bot.answer_callback_query(call.id, "Akses khusus admin.", show_alert=True)
            return

        if data in ["admin_panel_main", "admin_refresh_panel"]:
            bot.answer_callback_query(call.id, "Dashboard diperbarui")
            send_dashboard_view(chat_id, edit_message_id=msg_id)

        elif data == "admin_view_active":
            bot.answer_callback_query(call.id)
            active_orders = get_active_orders()
            if not active_orders:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 Kembali ke Panel", callback_data="admin_panel_main"))
                bot.edit_message_text(
                    "🎉 *TIDAK ADA ANTRIAN PESANAN AKTIF*\nSemua cucian telah selesai diproses atau belum ada pesanan baru.",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
                return

            markup = types.InlineKeyboardMarkup(row_width=1)
            for o in sorted(active_orders, key=lambda x: x.get("waktu", ""), reverse=True)[:10]:
                st_icon = STATUS_EMOJIS.get(o.get("status"), "📦")
                tagihan = f" (Rp {o.get('total_bayar', 0):,})" if o.get("total_bayar") else ""
                btn_text = f"{st_icon} {o.get('order_id')} | {o.get('nama')} - {o.get('layanan', 'Cucian')[:15]}...{tagihan}"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin_detail_{o.get('order_id')}"))
            markup.add(types.InlineKeyboardButton("🔙 Kembali ke Panel", callback_data="admin_panel_main"))

            bot.edit_message_text(
                f"📋 *DAFTAR PESANAN AKTIF ({len(active_orders)} NOTA)*\n"
                f"Klik nota di bawah untuk mengubah status atau membuat tagihan:",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown",
                reply_markup=markup
            )

        elif data.startswith("admin_detail_"):
            bot.answer_callback_query(call.id)
            order_id = data.replace("admin_detail_", "")
            show_admin_order_card(chat_id, order_id, edit_message_id=msg_id)

        elif data == "admin_find_order":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                chat_id,
                "🔍 *CARI NOTA LAUNDRY*\nKetik nomor nota yang dicari (contoh: `LDR-1616`):",
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, step_admin_search_order)

        elif data in ["admin_export_excel", "admin_export_csv"]:
            bot.answer_callback_query(call.id, "Mempersiapkan file Excel...")
            send_excel_export(chat_id)

        elif data == "admin_start_broadcast":
            bot.answer_callback_query(call.id)
            start_broadcast_prompt(chat_id)

        elif data == "confirm_broadcast":
            bot.answer_callback_query(call.id, "Mengirim siaran...")
            text_to_send = admin_broadcast_draft.get(chat_id)
            if not text_to_send:
                safe_send(bot, chat_id, "Draft siaran tidak ditemukan.", reply_markup=admin_dashboard_markup())
                return

            all_orders = get_all_orders()
            unique_buyers = set(o.get("buyer_chat_id") for o in all_orders.values() if o.get("buyer_chat_id"))
            success_count = 0
            fail_count = 0

            bot.send_message(chat_id, "⏳ *Sedang mengirim siaran pesan ke seluruh pelanggan...*", parse_mode="Markdown")

            for b_id in unique_buyers:
                try:
                    if customer_bot:
                        customer_bot.send_message(
                            b_id,
                            f"📢 *PENGUMUMAN DARI FRESHCLEAN LAUNDRY*\n─────────────────────────\n{text_to_send}",
                            parse_mode="Markdown"
                        )
                        success_count += 1
                except Exception:
                    fail_count += 1

            admin_broadcast_draft.pop(chat_id, None)
            safe_send(
                bot,
                chat_id,
                f"✅ *SIARAN PESAN SELESAI TERKIRIM!*\n"
                f"• Berhasil : *{success_count} pelanggan*\n"
                f"• Gagal : *{fail_count}*\n",
                reply_markup=admin_dashboard_markup()
            )

        elif data == "cancel_broadcast":
            admin_broadcast_draft.pop(chat_id, None)
            bot.answer_callback_query(call.id, "Siaran dibatalkan")
            bot.edit_message_text("❌ Pengiriman pesan siaran dibatalkan.", chat_id=chat_id, message_id=msg_id, reply_markup=admin_dashboard_markup())

        # Handler Update Status Cucian
        elif data.startswith("admin_st_"):
            # format: admin_st_{status}_{order_id}
            parts = data.split("_")
            if len(parts) >= 4:
                new_status = parts[2]
                order_id = parts[3]
                process_status_change(bot, call, order_id, new_status, msg_id)

        # Handler Input Tagihan & Berat Riil
        elif data.startswith("admin_bill_"):
            bot.answer_callback_query(call.id)
            order_id = data.replace("admin_bill_", "")
            order_rec = get_order(order_id)
            if not order_rec:
                bot.send_message(chat_id, f"Nota `{order_id}` tidak ditemukan.", parse_mode="Markdown")
                return

            admin_billing_flow[chat_id] = {"order_id": order_id}
            msg = bot.send_message(
                chat_id,
                f"⚖️ *INPUT TIMBANGAN RIIL NOTA `{order_id}`*\n"
                f"Pelanggan: *{order_rec.get('nama')}*\n"
                f"Layanan: {order_rec.get('layanan')}\n\n"
                f"Masukkan berat riil timbangan (contoh: `3.5 kg` atau `2 pcs`):",
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, step_admin_input_berat)

        # Handler Verifikasi Bukti Pembayaran
        elif data.startswith("admin_verify_pay_"):
            order_id = data.replace("admin_verify_pay_", "")
            bot.answer_callback_query(call.id, "Pembayaran diverifikasi Lunas!")
            update_order(order_id, status_bayar="Lunas")
            order_rec = get_order(order_id)

            bot.edit_message_caption(
                f"✅ *PEMBAYARAN NOTA `{order_id}` DIVERIFIKASI LUNAS!*\n"
                f"Pelanggan: {order_rec.get('nama')}\n"
                f"Status: *LUNAS*",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown"
            )

            # Notifikasi ke Pelanggan di Bot Pelanggan
            buyer_id = order_rec.get("buyer_chat_id")
            if buyer_id and customer_bot:
                safe_send(
                    customer_bot,
                    buyer_id,
                    f"🎉 *PEMBAYARAN DITERIMA & LUNAS!* ✨\n"
                    f"─────────────────────────\n"
                    f"Terima kasih Kak *{order_rec.get('nama')}*, bukti transfer pembayaran untuk nota `{order_id}` telah kami verifikasi *LUNAS*.\n"
                    f"Cucian Anda akan segera kami selesaikan dan antar dengan rapi & wangi! 🧺🌸"
                )

        elif data.startswith("admin_reject_pay_"):
            order_id = data.replace("admin_reject_pay_", "")
            bot.answer_callback_query(call.id, "Bukti pembayaran ditolak.")
            order_rec = get_order(order_id)

            bot.edit_message_caption(
                f"❌ *BUKTI PEMBAYARAN NOTA `{order_id}` DITOLAK!*\n"
                f"Pelanggan: {order_rec.get('nama')}",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown"
            )

            buyer_id = order_rec.get("buyer_chat_id")
            if buyer_id and customer_bot:
                safe_send(
                    customer_bot,
                    buyer_id,
                    f"⚠️ *BUKTI TRANSFER BELUM TERVERIFIKASI*\n"
                    f"─────────────────────────\n"
                    f"Mohon maaf Kak, bukti transfer untuk nota `{order_id}` belum dapat kami verifikasi karena gambar kurang jelas atau dana belum masuk.\n"
                    f"Silakan kirimkan kembali bukti transfer yang jelas atau hubungi Admin kami."
                )

    # ==========================================
    # ROUTER TEKS BEBAS ADMIN (AI ASISTEN OPERASIONAL)
    # ==========================================
    @bot.message_handler(func=lambda msg: True, content_types=['text'])
    def handle_admin_text(message):
        chat_id = message.chat.id
        if chat_id != load_admin_id():
            return

        text = (message.text or "").strip()
        first_name = message.from_user.first_name or "Admin"

        # Cek jika admin mengetik nota langsung
        if re.match(r"^ldr-\d+$", text.lower()):
            show_admin_order_card(chat_id, text.upper())
            return

        try:
            bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass

        ai_reply = get_ai_reply(text, first_name, is_admin=True)
        safe_send(bot, chat_id, ai_reply, reply_markup=admin_dashboard_markup())


# ==========================================
# FUNGSI HELPER PANEL ADMIN
# ==========================================
def send_dashboard_view(chat_id, edit_message_id=None):
    """Menampilkan ringkasan statistik dan menu utama admin"""
    orders = get_all_orders()
    total = len(orders)
    selesai = sum(1 for o in orders.values() if o.get("status") == "selesai")
    aktif = sum(1 for o in orders.values() if o.get("status") not in ["selesai", "dibatalkan"])
    lunas = sum(1 for o in orders.values() if o.get("status_bayar") == "Lunas")
    
    real_omset = sum(
        int(o.get("total_bayar", 0)) for o in orders.values() 
        if isinstance(o.get("total_bayar"), (int, float))
    )

    dashboard_text = (
        "👑 *PANEL KONTROL OPERASIONAL FRESHCLEAN* 📊\n"
        "─────────────────────────\n"
        f"📦 *Total Seluruh Nota*    : `{total}` pesanan\n"
        f"⏳ *Pesanan Aktif Berjalan*: `{aktif}` antrean\n"
        f"✅ *Pesanan Selesai*       : `{selesai}` pesanan\n"
        f"💳 *Pembayaran Lunas*      : `{lunas}` nota\n"
        f"💵 *Total Omset Tercatat*  : *Rp {real_omset:,}*\n"
        "─────────────────────────\n"
        "Pilih tindakan cepat di bawah:"
    )

    markup = admin_dashboard_markup()
    if edit_message_id:
        try:
            admin_bot.edit_message_text(dashboard_text, chat_id=chat_id, message_id=edit_message_id, parse_mode="Markdown", reply_markup=markup)
            return
        except Exception:
            pass
    safe_send(admin_bot, chat_id, dashboard_text, reply_markup=markup)

def show_admin_order_card(chat_id, order_id, edit_message_id=None):
    """Menampilkan kartu detail nota dengan tombol operasional admin lengkap"""
    order_rec = get_order(order_id)
    if not order_rec:
        safe_send(admin_bot, chat_id, f"⚠️ Nota `{order_id}` tidak ditemukan.", reply_markup=back_to_admin_menu())
        return

    st_label = STATUS_LIST.get(order_rec.get("status"), order_rec.get("status", "-"))
    st_icon = STATUS_EMOJIS.get(order_rec.get("status"), "📊")

    billing_info = ""
    if order_rec.get("berat_riil"):
        billing_info += f"⚖️ *Berat Riil:* {order_rec['berat_riil']}\n"
    if order_rec.get("total_bayar"):
        billing_info += f"💵 *Tagihan:* Rp {order_rec['total_bayar']:,}\n"
        billing_info += f"💳 *Status Bayar:* *{order_rec.get('status_bayar', 'Belum Lunas')}*\n"
    if order_rec.get("rating"):
        billing_info += f"⭐ *Ulasan Pelanggan ({order_rec.get('nama', 'Pelanggan')}):* {'⭐' * int(order_rec['rating'])} ({order_rec['rating']}/5)\n"

    # Link WhatsApp Pelanggan
    hp_clean = re.sub(r"[^\d]", "", order_rec.get("hp", ""))
    if hp_clean.startswith("0"):
        hp_wa = "62" + hp_clean[1:]
    else:
        hp_wa = hp_clean
    wa_link = f"https://wa.me/{hp_wa}?text=Halo%20Kak%20{order_rec.get('nama')},%20konfirmasi%20dari%20FreshClean%20Laundry%20terkait%20nota%20{order_id}."

    card_text = (
        f"📄 *DETAIL NOTA LAUNDRY: `{order_id}`*\n"
        f"─────────────────────────\n"
        f"⏱️ *Waktu:* {order_rec.get('waktu')}\n"
        f"👤 *Nama:* {order_rec.get('nama')} (@{order_rec.get('buyer_username')})\n"
        f"📞 *WhatsApp:* `{order_rec.get('hp')}`\n"
        f"🧺 *Layanan:* {order_rec.get('layanan')}\n"
        f"⚖️ *Estimasi:* {order_rec.get('estimasi')}\n"
        f"🛵 *Metode:* {order_rec.get('metode')}\n"
        f"📍 *Alamat:* {order_rec.get('alamat')}\n"
        f"📝 *Catatan:* {order_rec.get('catatan')}\n"
        f"{billing_info}"
        f"─────────────────────────\n"
        f"{st_icon} *Status Saat Ini:* *{st_label}*\n"
        f"─────────────────────────\n"
        f"Klik tombol di bawah untuk memperbarui status atau buat tagihan:"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_wa = types.InlineKeyboardButton("📞 Hubungi WhatsApp", url=wa_link)
    btn_bill = types.InlineKeyboardButton("⚖️ Input Berat & Tagihan", callback_data=f"admin_bill_{order_id}")
    btn_st_cuci = types.InlineKeyboardButton("🧼 Dicuci", callback_data=f"admin_st_dicuci_{order_id}")
    btn_st_setrika = types.InlineKeyboardButton("♨️ Disetrika", callback_data=f"admin_st_setrika_{order_id}")
    btn_st_siap = types.InlineKeyboardButton("📦 Siap Antar", callback_data=f"admin_st_siap_{order_id}")
    btn_st_selesai = types.InlineKeyboardButton("✅ Selesai", callback_data=f"admin_st_selesai_{order_id}")
    btn_st_batal = types.InlineKeyboardButton("❌ Batalkan", callback_data=f"admin_st_dibatalkan_{order_id}")
    btn_back = types.InlineKeyboardButton("🔙 Panel Utama", callback_data="admin_panel_main")

    if order_rec.get("maps_link"):
        markup.add(btn_wa, types.InlineKeyboardButton("📍 Buka Maps", url=order_rec["maps_link"]))
    else:
        markup.add(btn_wa)

    markup.add(btn_bill)
    markup.add(btn_st_cuci, btn_st_setrika)
    markup.add(btn_st_siap, btn_st_selesai)
    markup.add(btn_st_batal, btn_back)

    if edit_message_id:
        try:
            admin_bot.edit_message_text(card_text, chat_id=chat_id, message_id=edit_message_id, parse_mode="Markdown", reply_markup=markup)
            return
        except Exception:
            pass
    safe_send(admin_bot, chat_id, card_text, reply_markup=markup)

def process_status_change(bot, call, order_id, new_status, msg_id):
    """Memperbarui status pengerjaan dan mengirim notifikasi otomatis ke Pelanggan"""
    chat_id = call.message.chat.id
    order_rec = get_order(order_id)
    if not order_rec:
        bot.answer_callback_query(call.id, "Pesanan tidak ditemukan.")
        return

    update_order(order_id, status=new_status)
    st_label = STATUS_LIST.get(new_status, new_status)
    bot.answer_callback_query(call.id, f"Status diubah: {st_label}")

    # 1. Kirim Notifikasi ke PELANGGAN di Bot Pelanggan
    buyer_chat_id = order_rec.get("buyer_chat_id")
    if buyer_chat_id and customer_bot:
        notif_msg = (
            f"🔔 *PEMBARUAN STATUS CUCIAN ANDA* 🧺\n"
            f"─────────────────────────\n"
            f"📄 *No. Nota:* `{order_id}`\n"
            f"🧺 *Layanan:* {order_rec.get('layanan')}\n\n"
            f"📊 *Status Terkini:* *{st_label}*\n"
            f"─────────────────────────\n"
        )
        reply_markup = None

        if new_status == "dicuci":
            notif_msg += "Pakaian Anda saat ini sedang dalam proses pencucian higienis dengan deterjen premium ramah kain. 🧼"
        elif new_status == "setrika":
            notif_msg += "Pakaian Anda telah selesai dicuci dan saat ini sedang disetrika uap rapi serta disemprot parfum mewah pilihan. ♨️"
        elif new_status == "siap":
            notif_msg += "Cucian Anda sudah selesai dipacking rapi dan wangi! Siap untuk diantar kurir atau diambil di outlet. 📦"
        elif new_status == "selesai":
            notif_msg += (
                "🎉 *Pesanan laundry Anda telah selesai dan diterima!* Terima kasih banyak telah mempercayakan cucian Anda pada FreshClean Laundry! ✨\n\n"
                "Bagaimana pengalaman layanan kami? Mohon berikan ulasan bintang di bawah ini:"
            )
            # Tombol Rating untuk Pelanggan
            rate_mk = types.InlineKeyboardMarkup(row_width=5)
            rate_mk.add(
                types.InlineKeyboardButton("⭐ 1", callback_data=f"rate_{order_id}_1"),
                types.InlineKeyboardButton("⭐ 2", callback_data=f"rate_{order_id}_2"),
                types.InlineKeyboardButton("⭐ 3", callback_data=f"rate_{order_id}_3"),
                types.InlineKeyboardButton("⭐ 4", callback_data=f"rate_{order_id}_4"),
                types.InlineKeyboardButton("⭐ 5", callback_data=f"rate_{order_id}_5")
            )
            reply_markup = rate_mk
        elif new_status == "dibatalkan":
            notif_msg += "Pesanan ini telah dibatalkan. Jika ada pertanyaan silakan hubungi Admin kami."

        safe_send(customer_bot, buyer_chat_id, notif_msg, reply_markup=reply_markup)

    # 2. Refresh Tampilan Kartu Admin
    show_admin_order_card(chat_id, order_id, edit_message_id=msg_id)

def step_admin_input_berat(message):
    chat_id = message.chat.id
    berat_text = message.text.strip()
    flow = admin_billing_flow.get(chat_id)
    if not flow:
        return

    flow["berat_riil"] = berat_text
    msg = admin_bot.send_message(
        chat_id,
        f"⚖️ Berat riil: *{berat_text}*\n\n"
        f"💵 *Masukkan Total Tagihan Pembayaran (Rp)*:\n"
        f"_(Cukup ketik angka saja, contoh: `28000` atau `35000`)_",
        parse_mode="Markdown"
    )
    admin_bot.register_next_step_handler(msg, step_admin_input_tagihan)

def step_admin_input_tagihan(message):
    chat_id = message.chat.id
    flow = admin_billing_flow.pop(chat_id, None)
    if not flow:
        return

    order_id = flow["order_id"]
    berat_riil = flow["berat_riil"]
    
    # Ambil angka saja
    digits_only = re.sub(r"[^\d]", "", message.text.strip())
    try:
        total_bayar = int(digits_only)
    except ValueError:
        total_bayar = 0

    # Simpan ke Database
    update_order(order_id, berat_riil=berat_riil, total_bayar=total_bayar)
    order_rec = get_order(order_id)

    safe_send(
        admin_bot,
        chat_id,
        f"✅ *TAGIHAN NOTA `{order_id}` BERHASIL DIBUAT!*\n"
        f"• Berat Riil : *{berat_riil}*\n"
        f"• Total Tagihan : *Rp {total_bayar:,}*\n\n"
        f"Notifikasi tagihan resmi telah otomatis dikirimkan ke Pelanggan.",
        reply_markup=admin_dashboard_markup()
    )

    # Kirimkan Tagihan ke BOT PELANGGAN
    buyer_id = order_rec.get("buyer_chat_id")
    if buyer_id and customer_bot:
        billing_client_card = (
            f"🔔 *TAGIHAN LAUNDRY ANDA SUDAH TERBIT* 🧾\n"
            f"─────────────────────────\n"
            f"📄 *Nomor Nota:* `{order_id}`\n"
            f"🧺 *Layanan:* {order_rec.get('layanan')}\n"
            f"⚖️ *Berat Riil Cucian:* *{berat_riil}*\n"
            f"💵 *Total Tagihan:* *Rp {total_bayar:,}*\n"
            f"💳 *Status Pembayaran:* *Belum Lunas*\n"
            f"─────────────────────────\n"
            f"Silakan lakukan pembayaran melalui:\n"
            f"• *BCA*: `8735091234` a/n FreshClean Laundry\n"
            f"• *QRIS*: Scan QRIS di menu rekening\n"
            f"• *COD*: Bayar tunai ke kurir saat cucian diantar\n\n"
            f"Setelah transfer, klik tombol *📸 Kirim Bukti Transfer* di bawah untuk verifikasi otomatis:"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data=f"kirim_bukti_{order_id}"))
        markup.add(types.InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_utama"))

        safe_send(customer_bot, buyer_id, billing_client_card, reply_markup=markup)

def step_admin_search_order(message):
    chat_id = message.chat.id
    order_id = message.text.strip().upper()
    show_admin_order_card(chat_id, order_id)

def send_excel_export(chat_id):
    """Menghasilkan dan mengirimkan file Excel (.xlsx) rapi dan profesional ke chat admin"""
    try:
        try:
            admin_bot.send_chat_action(chat_id, "upload_document")
        except Exception:
            pass

        excel_bytes = export_orders_excel()
        doc = io.BytesIO(excel_bytes)
        filename = f"rekap_laundry_freshclean_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        doc.name = filename

        all_orders = get_all_orders()
        total = len(all_orders)
        selesai = sum(1 for o in all_orders.values() if o.get("status") == "selesai")
        real_omset = sum(int(o.get("total_bayar", 0)) for o in all_orders.values() if isinstance(o.get("total_bayar"), (int, float)))

        caption = (
            "📊 *REKAPITULASI PEMBUKUAN RESMI FRESHCLEAN* 🧺\n"
            "─────────────────────────\n"
            f"📁 *Format File:* Microsoft Excel (`.xlsx`)\n"
            f"📦 *Total Nota:* `{total}` pesanan\n"
            f"✅ *Pesanan Selesai:* `{selesai}` pesanan\n"
            f"💵 *Total Omset Tercatat:* *Rp {real_omset:,}*\n"
            "─────────────────────────\n"
            "✨ *Tampilan Sudah Diformat Rapi:*\n"
            "• Banner Judul & Info Tanggal Cetak\n"
            "• Header Biru dengan Garis Tabel Lengkap\n"
            "• Kolom Lebar Otomatis (Tidak Terpotong)\n"
            "• Warna Status Pembayaran (Hijau = Lunas, Kuning = Belum Lunas)\n"
            "• Format Angka Rupiah & Rumus Total Otomatis"
        )

        admin_bot.send_document(
            chat_id,
            doc,
            caption=caption,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[ERROR] Gagal export Excel: {e}, mencoba fallback CSV...", flush=True)
        # Fallback ke CSV jika ada kendala
        try:
            csv_bytes = export_orders_csv()
            doc = io.BytesIO(csv_bytes)
            doc.name = f"rekap_laundry_freshclean_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            admin_bot.send_document(
                chat_id,
                doc,
                caption="📥 *Rekapitulasi Pembukuan Laundry (Format CSV)*",
                parse_mode="Markdown"
            )
        except Exception as e2:
            safe_send(admin_bot, chat_id, f"⚠️ Gagal mengekspor data: {e2}")

def start_broadcast_prompt(chat_id):
    """Memulai alur siaran pesan promo"""
    msg = admin_bot.send_message(
        chat_id,
        "📢 *SIARAN PESAN PROMO KE SELURUH PELANGGAN*\n"
        "─────────────────────────\n"
        "Ketik teks pengumuman/promo yang ingin disiarkan ke semua pelanggan yang pernah order:",
        parse_mode="Markdown"
    )
    admin_bot.register_next_step_handler(msg, step_admin_input_broadcast)

def step_admin_input_broadcast(message):
    chat_id = message.chat.id
    text_to_broadcast = message.text.strip()
    admin_broadcast_draft[chat_id] = text_to_broadcast

    preview_text = (
        "📢 *PRATINJAU SIARAN PESAN PROMO:*\n"
        "─────────────────────────\n"
        f"{text_to_broadcast}\n"
        "─────────────────────────\n"
        "Apakah Anda yakin ingin mengirim pesan di atas ke seluruh pelanggan?"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 Kirim Sekarang", callback_data="confirm_broadcast"),
        types.InlineKeyboardButton("❌ Batal", callback_data="cancel_broadcast")
    )
    safe_send(admin_bot, chat_id, preview_text, reply_markup=markup)
