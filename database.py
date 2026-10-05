import os
import json
import csv
import io
import threading
from datetime import datetime
from config import ORDERS_FILE, CONFIG_FILE, STATUS_LIST

orders_lock = threading.Lock()
config_lock = threading.Lock()

def load_admin_id():
    """Memuat ID Admin dari environment atau file konfigurasi"""
    env_id = os.environ.get("ADMIN_CHAT_ID")
    if env_id and env_id.strip():
        try:
            return int(env_id.strip())
        except ValueError:
            pass

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_chat_id")
        except Exception:
            return None
    return None

def save_admin_id(admin_id):
    """Menyimpan ID Admin ke file konfigurasi secara aman dan atomik"""
    with config_lock:
        try:
            temp_file = CONFIG_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"admin_chat_id": int(admin_id)}, f, indent=4)
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
        except Exception as e:
            print(f"[ERROR] Gagal membaca {ORDERS_FILE}: {e}", flush=True)
            return {}
    return {}

def save_orders(orders_dict):
    """Menyimpan semua data pesanan laundry ke file JSON secara atomik"""
    with orders_lock:
        try:
            temp_file = ORDERS_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(orders_dict, f, indent=4, ensure_ascii=False)
            if os.path.exists(ORDERS_FILE):
                os.replace(temp_file, ORDERS_FILE)
            else:
                os.rename(temp_file, ORDERS_FILE)
            return True
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan data pesanan: {e}", flush=True)
            return False

def get_all_orders():
    """Mengambil seluruh data pesanan"""
    return load_orders()

def get_order(order_id):
    """Mengambil 1 pesanan berdasarkan ID nota"""
    orders = load_orders()
    return orders.get(order_id)

def add_order(order_id, order_data):
    """Menambahkan pesanan baru"""
    orders = load_orders()
    orders[order_id] = order_data
    save_orders(orders)
    return order_data

def update_order(order_id, **kwargs):
    """Memperbarui informasi pesanan"""
    orders = load_orders()
    if order_id in orders:
        orders[order_id].update(kwargs)
        save_orders(orders)
        return orders[order_id]
    return None

def get_orders_by_buyer(chat_id):
    """Mengambil daftar pesanan milik pelanggan tertentu"""
    orders = load_orders()
    return [o for o in orders.values() if o.get("buyer_chat_id") == chat_id]

def get_active_orders():
    """Mengambil semua pesanan yang belum selesai atau belum dibatalkan"""
    orders = load_orders()
    return [o for o in orders.values() if o.get("status") not in ["selesai", "dibatalkan"]]

def export_orders_csv():
    """Menghasilkan file CSV rekapitulasi seluruh pesanan"""
    orders = load_orders()
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header CSV
    writer.writerow([
        "ID Nota", "Waktu Order", "Nama Pelanggan", "No. WhatsApp/HP", 
        "Layanan", "Estimasi Berat/Pcs", "Berat Riil", "Total Tagihan (Rp)", 
        "Status Pembayaran", "Metode Antar/Jemput", "Alamat / GPS", 
        "Catatan Khusus", "Status Cucian", "Rating Pelanggan"
    ])
    
    for o in sorted(orders.values(), key=lambda x: x.get("waktu", ""), reverse=True):
        st_label = STATUS_LIST.get(o.get("status"), o.get("status", "-"))
        writer.writerow([
            o.get("order_id", "-"),
            o.get("waktu", "-"),
            o.get("nama", "-"),
            o.get("hp", "-"),
            o.get("layanan", o.get("produk", "-")),
            o.get("estimasi", "-"),
            o.get("berat_riil", "-"),
            o.get("total_bayar", 0),
            o.get("status_bayar", "Belum Lunas"),
            o.get("metode", "-"),
            o.get("alamat", "-"),
            o.get("catatan", "-"),
            st_label,
            f"{o.get('rating', '-')}/5" if o.get('rating') else "-"
        ])
    
    output.seek(0)
    return output.getvalue().encode("utf-8-sig")
