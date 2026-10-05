import os
import json
import csv
import io
import threading
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
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

def export_orders_excel():
    """Menghasilkan file Excel (.xlsx) rapi dan berformat akuntansi resmi untuk owner/admin"""
    orders = load_orders()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Laundry"
    ws.views.sheetView[0].showGridLines = True

    # 1. Judul Banner Atas
    ws.merge_cells("A1:O1")
    title_cell = ws["A1"]
    title_cell.value = "REKAPITULASI PEMBUKUAN & PESANAN - FRESHCLEAN LAUNDRY"
    title_cell.font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    # Subtitle
    total_orders = len(orders)
    total_omset = sum(int(o.get("total_bayar", 0)) for o in orders.values() if isinstance(o.get("total_bayar"), (int, float)))
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M WIB")

    ws.merge_cells("A2:O2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Dicetak Otomatis pada: {now_str}  |  Total Pesanan: {total_orders} Nota  |  Total Omset: Rp {total_omset:,}"
    sub_cell.font = Font(name="Segoe UI", size=10, italic=True, color="1E293B")
    sub_cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 8

    # 2. Header Kolom
    headers = [
        "No.", "ID Nota", "Tanggal & Waktu", "Nama Pelanggan", "No. WhatsApp",
        "Layanan Laundry", "Estimasi", "Berat Riil", "Tagihan (Rp)",
        "Status Bayar", "Tahapan Cucian", "Metode Antar/Jemput",
        "Alamat / Titik GPS", "Catatan Khusus", "Rating ⭐"
    ]
    ws.row_dimensions[4].height = 28

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border_side = Side(border_style="thin", color="CBD5E1")
    header_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    for col_num, h_text in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_num)
        cell.value = h_text
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = header_border

    # 3. Data Baris
    cell_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0")
    )
    fill_white = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    fill_lunas = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    font_lunas = Font(name="Segoe UI", size=10, bold=True, color="166534")

    fill_pending = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    font_pending = Font(name="Segoe UI", size=10, bold=True, color="854D0E")

    fill_batal = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    font_batal = Font(name="Segoe UI", size=10, bold=True, color="991B1B")

    row_idx = 5
    sorted_orders = sorted(orders.values(), key=lambda x: x.get("waktu", ""), reverse=True)

    for idx, o in enumerate(sorted_orders, 1):
        ws.row_dimensions[row_idx].height = 22
        current_fill = fill_alt if idx % 2 == 0 else fill_white
        st_raw = o.get("status", "menunggu")
        st_label = STATUS_LIST.get(st_raw, st_raw)
        st_bayar = o.get("status_bayar", "Belum Lunas")
        tagihan_val = int(o.get("total_bayar", 0)) if str(o.get("total_bayar", 0)).isdigit() else 0
        rating_str = f"⭐ {o.get('rating')}/5" if o.get("rating") else "-"

        # Values
        vals = [
            (idx, Alignment(horizontal="center", vertical="center")),
            (o.get("order_id", "-"), Alignment(horizontal="center", vertical="center")),
            (o.get("waktu", "-"), Alignment(horizontal="center", vertical="center")),
            (o.get("nama", "-"), Alignment(horizontal="left", vertical="center")),
            (str(o.get("hp", "-")), Alignment(horizontal="center", vertical="center")),
            (o.get("layanan", o.get("produk", "-")), Alignment(horizontal="left", vertical="center")),
            (o.get("estimasi", "-"), Alignment(horizontal="center", vertical="center")),
            (o.get("berat_riil", "-") or "-", Alignment(horizontal="center", vertical="center")),
            (tagihan_val, Alignment(horizontal="right", vertical="center")),
            (st_bayar, Alignment(horizontal="center", vertical="center")),
            (st_label, Alignment(horizontal="center", vertical="center")),
            (o.get("metode", "-"), Alignment(horizontal="center", vertical="center")),
            (o.get("alamat", "-"), Alignment(horizontal="left", vertical="center")),
            (o.get("catatan", "-"), Alignment(horizontal="left", vertical="center")),
            (rating_str, Alignment(horizontal="center", vertical="center"))
        ]

        for col_idx, (val, align) in enumerate(vals, 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.value = val
            c.alignment = align
            c.border = cell_border
            c.fill = current_fill
            c.font = Font(name="Segoe UI", size=10)

            # Styling Kolom Tagihan
            if col_idx == 9:
                c.number_format = "#,##0"
                if tagihan_val > 0:
                    c.font = Font(name="Segoe UI", size=10, bold=True, color="1E3A8A")

            # Styling Status Bayar
            elif col_idx == 10:
                if st_bayar == "Lunas":
                    c.fill = fill_lunas
                    c.font = font_lunas
                else:
                    c.fill = fill_pending
                    c.font = font_pending

            # Styling Tahapan Cucian
            elif col_idx == 11:
                if st_raw == "selesai":
                    c.font = Font(name="Segoe UI", size=10, bold=True, color="166534")
                elif st_raw == "dibatalkan":
                    c.fill = fill_batal
                    c.font = font_batal

        row_idx += 1

    # 4. Baris Total Omset di Bawah
    if sorted_orders:
        ws.row_dimensions[row_idx].height = 26
        summary_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        top_thin = Side(style="thin", color="94A3B8")
        bot_double = Side(style="double", color="1E3A8A")
        total_border = Border(top=top_thin, bottom=bot_double, left=Side(style="thin", color="E2E8F0"), right=Side(style="thin", color="E2E8F0"))

        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=8)
        lbl_cell = ws.cell(row=row_idx, column=1)
        lbl_cell.value = "TOTAL KESELURUHAN OMSET TERCATAT (Rp)"
        lbl_cell.font = Font(name="Segoe UI", size=11, bold=True, color="0F172A")
        lbl_cell.alignment = Alignment(horizontal="right", vertical="center")
        
        for c_idx in range(1, 9):
            ws.cell(row=row_idx, column=c_idx).fill = summary_fill
            ws.cell(row=row_idx, column=c_idx).border = total_border

        # Kolom Total Formula
        sum_cell = ws.cell(row=row_idx, column=9)
        sum_cell.value = f"=SUM(I5:I{row_idx-1})"
        sum_cell.number_format = "#,##0"
        sum_cell.font = Font(name="Segoe UI", size=11, bold=True, color="1E3A8A")
        sum_cell.alignment = Alignment(horizontal="right", vertical="center")
        sum_cell.fill = summary_fill
        sum_cell.border = total_border

        for c_idx in range(10, 16):
            c_fill = ws.cell(row=row_idx, column=c_idx)
            c_fill.fill = summary_fill
            c_fill.border = total_border

    # 5. Otomatisasi Lebar Kolom
    col_min_widths = {
        1: 6,   # No
        2: 14,  # ID Nota
        3: 20,  # Waktu
        4: 22,  # Nama
        5: 18,  # WhatsApp
        6: 32,  # Layanan
        7: 15,  # Estimasi
        8: 14,  # Berat Riil
        9: 18,  # Tagihan
        10: 16, # Status Bayar
        11: 28, # Tahapan Cucian
        12: 24, # Metode
        13: 35, # Alamat
        14: 25, # Catatan
        15: 14  # Rating
    }

    for col_idx, min_w in col_min_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min_w

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
