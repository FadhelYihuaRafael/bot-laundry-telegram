import json
import urllib.request
import urllib.error
from config import GEMINI_API_KEY
from database import get_all_orders

def call_gemini_ai(query, user_name, is_admin=False):
    """Menghubungi API Google Gemini AI untuk menjawab pertanyaan secara kontekstual"""
    if not GEMINI_API_KEY:
        return None

    try:
        all_orders = get_all_orders()
        if is_admin:
            total_orders = len(all_orders)
            selesai = sum(1 for o in all_orders.values() if o.get("status") == "selesai")
            aktif = sum(1 for o in all_orders.values() if o.get("status") not in ["selesai", "dibatalkan"])
            prompt_system = (
                f"Kamu adalah AI Asisten Operasional & Bisnis untuk Owner/Admin FreshClean Laundry.\n"
                f"Nama Admin: {user_name}.\n"
                f"Data Toko Terkini: Total Nota: {total_orders}, Pesanan Aktif: {aktif}, Pesanan Selesai: {selesai}.\n"
                f"Tugasmu: Bantu admin membuat template pesan WhatsApp yang sopan & ramah ke pelanggan, "
                f"berikan saran manajemen laundry, tips mengatasi komplain cucian, atau analisis singkat.\n"
                f"Gaya bicara: Sopan, profesional, solutif, gunakan emoji yang relevan.\n\n"
                f"Pertanyaan/Perintah Admin:\n{query}"
            )
        else:
            prompt_system = (
                f"Kamu adalah 'FreshClean AI Assistant', asisten customer service cerdas dan ramah dari FreshClean Laundry.\n"
                f"Kamu sedang berbicara dengan pelanggan bernama {user_name}.\n"
                f"Informasi Toko FreshClean Laundry:\n"
                f"• Lokasi: Jl. Melati Raya No. 45, Sukajadi.\n"
                f"• Jam Operasional: Setiap hari 07.30 - 21.00 WIB (Minggu/Libur: 08.00 - 20.00 WIB).\n"
                f"• Layanan & Tarif: Cuci Komplit Reguler 2 Hari (Rp 7.000/kg), Cuci Komplit Kilat 1 Hari (Rp 10.000/kg), "
                f"Express 5 Jam (Rp 15.000/kg), Cuci Kering Lipat (Rp 5.000/kg), Setrika Uap (Rp 4.000/kg), "
                f"Bed Cover (Rp 25.000 - Rp 35.000), Sepatu (Rp 25.000 - Rp 45.000).\n"
                f"• Fasilitas: Gratis jemput-antar radius 3 km (min. 4 kg).\n"
                f"• Metode Pembayaran: QRIS (GoPay/OVO/ShopeePay/BCA), Transfer Bank BCA 8735091234, atau Tunai COD.\n"
                f"• Keunggulan: 1 mesin 1 pelanggan (higienis tidak dicampur), deterjen ramah serat kain, 4 aroma parfum (Snappy, Sweet Lily, Ocean Fresh, Lavender), garansi cuci ulang jika kurang bersih.\n"
                f"• Jawablah pertanyaan seputar perawatan pakaian, tips noda, jam operasional, atau cara order secara ramah, sopan, dan jelas.\n\n"
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
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_body = response.read().decode("utf-8")
                    parsed = json.loads(res_body)
                    candidates = parsed.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
            except Exception:
                continue

    except Exception as e:
        print(f"[AI] Error menghubungi Gemini: {e}", flush=True)

    return None


def smart_local_assistant(query, user_name, is_admin=False):
    """Asisten pintar berbasis aturan lokal saat internet lambat atau API AI tidak tersedia"""
    q = query.lower()
    all_orders = get_all_orders()

    if is_admin:
        # Analisis Cepat untuk Admin
        if any(k in q for k in ["omset", "pendapatan", "keuangan", "rekap"]):
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
                "💡 _Gunakan menu `/export` untuk mengunduh rekap CSV pembukuan lengkap._"
            )

        # Template Pesan WhatsApp
        if any(k in q for k in ["template", "pesan wa", "chat wa"]):
            if any(k in q for k in ["jemput", "ambil"]):
                return (
                    "📝 *TEMPLATE CHAT WA: KURIR MENUJU LOKASI*\n"
                    "─────────────────────────\n"
                    "Halo Kak [Nama Pelanggan]! 👋\n"
                    "Kurir FreshClean Laundry saat ini sedang dalam perjalanan menuju alamat Kakak untuk penjemputan cucian.\n\n"
                    "Mohon pastikan pakaian sudah siap ya Kak. Terima kasih banyak! 🙏✨"
                )
            elif any(k in q for k in ["selesai", "siap"]):
                return (
                    "📝 *TEMPLATE CHAT WA: CUCIAN SELESAI*\n"
                    "─────────────────────────\n"
                    "Halo Kak [Nama Pelanggan]! ✨\n"
                    "Kabar gembira! Cucian Kakak dengan nota *[No. Nota]* sudah selesai, wangi, dan rapi dipacking.\n\n"
                    "Apakah mau diantar sekarang atau diambil sendiri ke outlet? Mohon konfirmasinya ya Kak. Terima kasih! 🧺🌸"
                )

        return (
            "👑 *PANDUAN OPERASIONAL ADMIN FRESHCLEAN:*\n"
            "─────────────────────────\n"
            "• `/admin` : Membuka dashboard utama toko & antrean pesanan\n"
            "• `/export`: Mengunduh rekapitulasi data pesanan ke file CSV Excel\n"
            "• `/broadcast`: Kirim pesan siaran promo serentak ke semua pelanggan\n"
            "• Anda juga bisa meminta saya membuatkan *template chat WA* ke pelanggan!"
        )

    else:
        # Jawaban Pintar untuk Pelanggan
        if any(k in q for k in ["jam", "buka", "tutup", "operasional"]):
            return (
                "📍 *LOKASI & JAM OPERASIONAL FRESHCLEAN:*\n"
                "─────────────────────────\n"
                "🏢 *Outlet:* Jl. Melati Raya No. 45, Kecamatan Sukajadi\n\n"
                "⏰ *Jam Buka:*\n"
                "• Senin - Sabtu : 07.30 - 21.00 WIB\n"
                "• Minggu & Libur: 08.00 - 20.00 WIB\n\n"
                "🛵 Kurir penjemputan cucian beroperasi setiap hari selama jam buka outlet!"
            )

        if any(k in q for k in ["harga", "tarif", "biaya", "paket"]):
            return (
                "🧺 *DAFTAR TARIF FRESHCLEAN LAUNDRY:*\n"
                "─────────────────────────\n"
                "• Cuci Komplit Reguler (2 Hari) : *Rp 7.000 / kg*\n"
                "• Cuci Komplit Kilat (1 Hari)   : *Rp 10.000 / kg*\n"
                "• Cuci Express Super (5 Jam)    : *Rp 15.000 / kg*\n"
                "• Cuci Kering Lipat (Non-Setrika): *Rp 5.000 / kg*\n"
                "• Setrika Uap Rapi Wangi        : *Rp 4.000 / kg*\n"
                "• Cuci Bed Cover / Selimut      : *Mulai Rp 25.000*\n"
                "• Cuci Sepatu Sneakers / Kulit  : *Mulai Rp 25.000*\n\n"
                "🛵 *Gratis Ongkir Penjemputan* untuk radius 3 km (min. 4 kg)!"
            )

        if any(k in q for k in ["bayar", "rekening", "transfer", "qris", "bca"]):
            return (
                "💳 *METODE PEMBAYARAN FRESHCLEAN:*\n"
                "─────────────────────────\n"
                "1. *QRIS*: Scan semua e-wallet (GoPay, OVO, ShopeePay, DANA) & Mobile Banking.\n"
                "2. *Transfer Bank BCA*: `8735091234` a/n FreshClean Laundry.\n"
                "3. *Bayar Tunai (COD)*: Bayar langsung ke kurir saat cucian diantar.\n\n"
                "📸 Bukti transfer bisa langsung dikirimkan lewat bot ini."
            )

        if any(k in q for k in ["noda", "luntur", "minyak", "tinta"]):
            return (
                "💡 *TIPS PERAWATAN NODA DARI FRESHCLEAN:*\n"
                "─────────────────────────\n"
                "• *Noda Minyak*: Berikan sedikit sabun pencuci piring cair pada noda kering sebelum dicuci.\n"
                "• *Noda Tinta*: Bersihkan perlahan dengan kapas yang dibasahi alkohol atau hand sanitizer.\n"
                "• *Pakaian Luntur*: Selalu pisahkan pakaian putih dari pakaian berwarna pekat.\n\n"
                "Di FreshClean, cucian Anda dicuci *1 mesin 1 pelanggan* sehingga aman dan higienis!"
            )

        return (
            f"Halo Kak {user_name}! 👋\n"
            "Saya adalah asisten FreshClean Laundry. Ada yang bisa kami bantu seputar cucian Anda?\n\n"
            "Gunakan tombol menu di bawah untuk *🛵 Pesan Laundry*, *🔍 Cek Status Cucian*, atau *📋 Daftar Tarif*."
        )


def get_ai_reply(query, user_name, is_admin=False):
    """Mendapatkan jawaban terbaik dari Gemini AI dengan fallback cerdas lokal"""
    gemini_resp = call_gemini_ai(query, user_name, is_admin=is_admin)
    if gemini_resp:
        return gemini_resp
    return smart_local_assistant(query, user_name, is_admin=is_admin)
