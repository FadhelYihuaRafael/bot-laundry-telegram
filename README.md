# 🧺 FreshClean Laundry - Telegram Bot

Bot Telegram otomatis untuk layanan Laundry FreshClean, dilengkapi dengan fitur:
- Pemesanan laundry & penjemputan antar-jemput
- Cek tarif & jenis layanan
- Pelacakan nomor nota (status cucian)
- Panel kontrol khusus Admin
- Cloud health-check server (port 10000 / $PORT) untuk hosting 24/7 gratis

## 🚀 Cara Deploy 24 Jam Nonstop di Render.com (Gratis)

1. Buka [Render.com](https://render.com) dan login dengan akun **GitHub** Anda.
2. Klik tombol **New +** di pojok kanan atas, lalu pilih **Web Service**.
3. Pilih repository `FadhelYihuaRafael/bot-laundry-telegram`.
4. Render akan otomatis mendeteksi konfigurasi dari `render.yaml`.
5. Klik **Create Web Service**. Bot akan otomatis berjalan di cloud!

### ⏰ Menjaga Bot Tetap Aktif 24/7 (Anti-Sleep)
1. Salin link URL bot dari Render (contoh: `https://freshclean-bot.onrender.com`).
2. Buka [UptimeRobot.com](https://uptimerobot.com) (gratis).
3. Tambahkan Monitor baru:
   - **Monitor Type**: `HTTP(s)`
   - **URL**: Tempel link Render Anda
   - **Interval**: `Every 5 minutes`
4. Selesai! Bot akan aktif terus tanpa henti meskipun laptop dimatikan.
