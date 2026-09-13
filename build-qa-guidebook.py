#!/usr/bin/env python3
"""
WIM Fleetbase — QA Testing Guidebook PDF
Brand: WIM (PT Wahana Inti Mas) / SanQua Group
"""

import os, sys
from fpdf import FPDF

FONT_PATH = '/Library/Fonts/Arial Unicode.ttf'
if not os.path.exists(FONT_PATH):
    FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

BLUE      = (41, 55, 128)
GREEN     = (11, 135, 67)
PALE_BLUE = (165, 198, 233)
RED       = (237, 34, 36)
WHITE     = (255, 255, 255)
DARK      = (26, 26, 46)
GRAY      = (102, 102, 102)

CW = 186  # content width: 210 - 12 - 12

class WIMGuidePDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(auto=True, margin=18)
        self.add_font('U', '', FONT_PATH)
        self.add_font('U', 'B', FONT_PATH)
        self.add_font('U', 'I', FONT_PATH)
        self.add_font('U', 'BI', FONT_PATH)
        self.set_margins(12, 15, 12)
        self.m_lm = 12
        self.m_cw = 186

    def header(self):
        if self.page_no() > 1:
            self.set_font('U', 'I', 6)
            self.set_text_color(*GRAY)
            self.cell(0, 4, 'WIM Fleetbase | QA Testing Guidebook', align='L')
            self.cell(0, 4, f'Page {self.page_no()}', align='R', new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*PALE_BLUE)
            self.line(12, self.get_y(), 198, self.get_y())
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font('U', 'I', 6)
        self.set_text_color(*GRAY)
        self.cell(0, 4, 'PT Wahana Inti Mas — SanQua Group', align='C')

    def cover_page(self):
        self.add_page()
        self.set_fill_color(*BLUE)
        self.rect(0, 0, 210, 297, 'F')
        self.set_fill_color(*GREEN)
        self.rect(0, 0, 210, 4, 'F')
        self.set_y(45)
        self.set_font('U', 'B', 28)
        self.set_text_color(*WHITE)
        self.cell(0, 14, 'WIM Fleetbase', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 14, 'QA Testing Guidebook', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        self.set_draw_color(*GREEN)
        self.set_line_width(1)
        self.line(60, self.get_y(), 150, self.get_y())
        self.ln(8)
        self.set_font('U', '', 14)
        self.set_text_color(*PALE_BLUE)
        self.cell(0, 8, 'PT Wahana Inti Mas', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font('U', '', 10)
        self.cell(0, 6, 'SanQua Group -- Distribution Operations', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font('U', 'I', 9)
        self.cell(0, 6, 'September 2026', align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*GREEN)
        self.rect(0, 285, 210, 12, 'F')
        self.set_font('U', 'I', 7)
        self.set_text_color(*WHITE)
        self.set_y(288)
        self.cell(0, 4, 'Prepared by Hermes Agent -- Seraphine', align='C')

    def st(self, num, title):
        label = f'  {num}. {title}' if num else f'  {title}'
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font('U', 'B', 13)
        self.cell(0, 8, label, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def sb(self, title):
        self.set_font('U', 'B', 10)
        self.set_text_color(*GREEN)
        self.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def bd(self, text):
        self.set_font('U', '', 9)
        self.set_text_color(*DARK)
        self.multi_cell(0, 4.5, text)
        self.ln(1)

    def bu(self, text, indent=8):
        self.set_font('U', '', 9)
        self.set_text_color(*DARK)
        self.set_x(self.l_margin + indent)
        self.multi_cell(0, 4.5, '- ' + text)
        self.ln(0.5)

    def kv(self, key, value):
        self.set_font('U', 'B', 9)
        self.set_text_color(*BLUE)
        self.cell(45, 5, key)
        self.set_font('U', '', 9)
        self.set_text_color(*DARK)
        self.cell(0, 5, str(value), new_x="LMARGIN", new_y="NEXT")
        self.ln(0.3)

    def step(self, num, text):
        self.set_font('U', 'B', 9)
        self.set_text_color(*BLUE)
        prefix = f'{num}. '
        self.set_x(self.l_margin)
        w = self.get_string_width(prefix)
        self.cell(w, 4.5, prefix)
        self.set_font('U', '', 9)
        self.set_text_color(*DARK)
        self.multi_cell(0, 4.5, text)
        self.ln(0.8)

    def code(self, text):
        self.set_font('U', '', 7)
        self.set_text_color(*DARK)
        self.set_x(self.l_margin + 4)
        self.multi_cell(self.m_cw - 8, 4, text)
        self.ln(0.5)

    def ibox(self, text):
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font('U', 'B', 9)
        self.cell(0, 6, '  [INFO]', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_x(self.l_margin)
        self.set_fill_color(235, 240, 255)
        self.set_text_color(*DARK)
        self.set_font('U', '', 9)
        y0 = self.get_y()
        self.multi_cell(0, 4.5, text)
        y1 = self.get_y()
        self.set_fill_color(200, 215, 255)
        self.rect(self.l_margin, y0, 2, y1 - y0, 'F')
        self.ln(2)

    def tbox(self, text):
        self.set_fill_color(*GREEN)
        self.set_text_color(*WHITE)
        self.set_font('U', 'B', 9)
        self.cell(0, 6, '  [TIP]', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_x(self.l_margin)
        self.set_fill_color(230, 245, 235)
        self.set_text_color(*DARK)
        self.set_font('U', '', 9)
        y0 = self.get_y()
        self.multi_cell(0, 4.5, text)
        y1 = self.get_y()
        self.set_fill_color(200, 235, 210)
        self.rect(self.l_margin, y0, 2, y1 - y0, 'F')
        self.ln(2)

    def wbox(self, text):
        self.set_fill_color(*RED)
        self.set_text_color(*WHITE)
        self.set_font('U', 'B', 9)
        self.cell(0, 6, '  [PERHATIAN]', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_x(self.l_margin)
        self.set_fill_color(255, 235, 235)
        self.set_text_color(180, 50, 50)
        self.set_font('U', '', 9)
        y0 = self.get_y()
        self.multi_cell(0, 4.5, text)
        y1 = self.get_y()
        self.set_fill_color(255, 200, 200)
        self.rect(self.l_margin, y0, 2, y1 - y0, 'F')
        self.ln(2)

    def chk(self, items):
        for item in items:
            self.set_font('U', '', 9)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 6)
            self.multi_cell(0, 4.5, '[ ] ' + item)
            self.ln(0.2)
        self.ln(1)

    def tbl(self, headers, data, col_widths, align=None):
        if align is None:
            align = ['C'] * len(headers)
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font('U', 'B', 7.5)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 6, h, border=1, fill=True, align='C')
        self.ln()
        for r, row in enumerate(data):
            bg = PALE_BLUE if r % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font('U', '', 7.5)
            for i, c in enumerate(row):
                self.cell(col_widths[i], 5.5, str(c), border=1, fill=True, align=align[i])
            self.ln()
        self.ln(2)


def build_pdf():
    pdf = WIMGuidePDF()

    # ══════════════════════════════════════════════
    # COVER PAGE
    # ══════════════════════════════════════════════
    pdf.cover_page()

    # ══════════════════════════════════════════════
    # TABLE OF CONTENTS
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st('', 'TABLE OF CONTENTS')
    toc_items = [
        '1.  Pengantar & Lingkungan Testing',
        '2.  Persiapan QA Tester',
        '3.  Flow A -- Sales Visit (Kunjungan Sales)',
        '4.  Flow B -- Order Management (Pemesanan)',
        '5.  Flow C -- NOO (New Outlet Opening)',
        '6.  Flow D -- Out-of-Route Order',
        '7.  Flow E -- Admin Console (Dashboard)',
        '8.  Flow F -- Reporting & Export',
        '9.  Flow G -- Geofence Detection',
        '10.  Flow H -- Photo & Attachment',
        '11.  Flow I -- Purchase Order & QR',
        '12.  Flow J -- Promo & Bundling',
        '13.  Checklist Keseluruhan',
        '14.  Subagent QA Protocol',
        'Lampiran -- Data Referensi & API Endpoint',
    ]
    for t in toc_items:
        pdf.set_font('U', '', 9)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 5.5, t, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ══════════════════════════════════════════════
    # SECTION 1: PENGANTAR
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(1, 'Pengantar & Lingkungan Testing')

    pdf.bd(
        'Dokumen ini adalah panduan lengkap untuk Quality Assurance (QA) Testing '
        'aplikasi Fleetbase yang akan menggantikan GooVi (manajemen kunjungan sales) '
        'dan KlikOrder (manajemen pemesanan) untuk PT Wahana Inti Mas. '
        'Fleetbase sudah di-deploy di server SanQua AI Proxmox dan siap untuk diuji.'
    )

    pdf.sb('Lingkungan Testing')
    pdf.kv('Console URL', 'http://192.168.6.223:4200')
    pdf.kv('API URL', 'http://192.168.6.223:8000/v1')
    pdf.kv('API Key', 'flb_live_RgeKNhT7Pg8rCcuXp8sD')
    pdf.kv('Admin User', 'reinharttanto@gmail.com')
    pdf.kv('Driver', 'Andi Sales (slug: andi-sales)')
    pdf.kv('Vehicle', 'Motor Andi (B 1234 ABC)')
    pdf.kv('Server', 'LXC 106 -- 192.168.6.223 (SanQua Proxmox)')
    pdf.ln(2)

    pdf.sb('Test Data yang Tersedia')
    pdf.tbl(
        ['Data', 'Jumlah', 'Detail'],
        [
            ['Stores (Toko)', '5', 'Berkah, Jaya, Makmur, Sejahtera, Baru'],
            ['Geofence Zones', '3', 'Radius 10m, 32 titik polygon'],
            ['Products', '8', 'SANQUA(5), LEVONTE(1), BATAVIA(2)'],
            ['Contacts', '4', 'Terhubung ke pemilik toko'],
            ['Driver', '1', 'Andi Sales - aktif'],
            ['Vehicle', '1', 'Motor Andi - linked ke driver'],
            ['Orders', '2', 'Existing test orders'],
        ],
        [35, 25, 120],
        ['L', 'C', 'L']
    )

    pdf.ibox(
        'Semua testing dilakukan di environment DEVELOPMENT (staging), '
        'BUKAN di production. Data test dapat dimodifikasi/dihapus dengan aman. '
        'Jangan gunakan data WIM asli untuk testing.'
    )

    # ══════════════════════════════════════════════
    # SECTION 2: PERSIAPAN QA TESTER
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(2, 'Persiapan QA Tester')

    pdf.sb('Akses yang Dibutuhkan')
    pdf.bu('Akses ke jaringan SanQua (192.168.6.x) atau VPN/SSH jump host')
    pdf.bu('Browser modern (Chrome/Firefox) untuk mengakses console Fleetbase')
    pdf.bu('API testing tool seperti curl, Postman, atau Thunder Client')
    pdf.bu('API Key: flb_live_RgeKNhT7Pg8rCcuXp8sD')
    pdf.bu('Dokumen referensi GooVi + KlikOrder untuk perbandingan fitur')
    pdf.ln(1)

    pdf.sb('Langkah Awal')
    pdf.step(1, 'Buka browser dan akses http://192.168.6.223:4200')
    pdf.step(2, 'Login dengan email admin: reinharttanto@gmail.com')
    pdf.step(3, 'Verifikasi bahwa dashboard utama muncul dengan Company "SanQua"')
    pdf.step(4, 'Test API dengan curl:')
    pdf.code('curl -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Accept: application/json" \\')
    pdf.code('  http://192.168.6.223:8000/v1/places')
    pdf.ln(1)
    pdf.step(5, 'Verifikasi: response array of 5 stores dengan location.coordinates')

    pdf.tbox(
        'Gunakan API Key yang sudah disediakan. Jangan generate API Key baru '
        'karena akan mengubah konfigurasi yang sudah ada.'
    )

    # ══════════════════════════════════════════════
    # SECTION 3: FLOW A -- SALES VISIT
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(3, 'Flow A -- Sales Visit (Kunjungan Sales)')

    pdf.bd(
        'Flow ini mensimulasikan kegiatan sales rep yang melakukan kunjungan '
        'ke toko-toko dalam rute harian. Ini adalah flow utama yang menggantikan '
        'GooVi Visit Card.'
    )

    pdf.sb('A.1 - Check-in di Depo')
    pdf.step(1, 'Simulasikan driver check-in dengan mengirim lokasi ke API:')
    pdf.code('curl -X POST http://192.168.6.223:8000/v1/drivers/')
    pdf.code('  bdd47b89-9ca9-4452-a29c-2bc603347c78/track \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Content-Type: application/json" \\')
    pdf.code('  -d \'{"latitude":-6.2,"longitude":106.8}\'')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: response status 200, driver position tercatat')
    pdf.step(3, 'Cek di console: driver menampilkan status online dan lokasi terakhir')

    pdf.sb('A.2 - Melihat Rute Hari Ini')
    pdf.step(1, 'GET /v1/routes untuk melihat rute yang sudah dibuat:')
    pdf.code('curl -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  http://192.168.6.223:8000/v1/routes')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: route dengan waypoints (5 toko) muncul')
    pdf.step(3, 'Cek bahwa setiap waypoint memiliki place_uuid dan order')

    pdf.sb('A.3 - Navigasi ke Toko')
    pdf.step(1, 'Pilih salah satu toko dari daftar waypoints')
    pdf.step(2, 'Dapatkan detail toko: GET /v1/places/{place_uuid}')
    pdf.step(3, 'Verifikasi: location.coordinates, name, street1, city')

    pdf.sb('A.4 - Geofence Check-in di Toko')
    pdf.step(1, 'Kirim tracking dengan koordinat yang tepat di dalam zona toko:')
    pdf.code('curl -X POST .../drivers/.../track \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -d \'{"latitude":-6.2088,"longitude":106.8456}\'')
    pdf.ln(1)
    pdf.step(2, 'Cek geofence events: GET /v1/geofences/events')
    pdf.step(3, 'Verifikasi: GeofenceEntered event tercatat untuk driver + toko')

    pdf.wbox(
        'Koordinat yang tepat sangat penting untuk geofence detection. '
        'Zona radius 10m. Jika koordinat terlalu jauh, event tidak akan terdeteksi. '
        'Gunakan koordinat yang sudah tercatat di dokumen referensi.'
    )

    pdf.sb('A.5 - Ambil Foto Selfie & Kunjungan')
    pdf.step(1, 'Gunakan POST /v1/drivers/{id}/track dengan multipart/form-data')
    pdf.step(2, 'Lampirkan file foto sebagai attachment')
    pdf.step(3, 'Verifikasi: foto tersimpan dan terlihat di console')

    pdf.sb('A.6 - Input Stok Toko')
    pdf.step(1, 'Update meta data toko dengan stok per SKU:')
    pdf.code('PATCH /v1/places/{place_uuid} \\')
    pdf.code('  -d \'{"meta":{"stock":{"SQA-220-K24":15,"SQA-550-K24":8}}}\'')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: GET /v1/places/{place_uuid} - meta.stock terisi')

    pdf.sb('A.7 - Submit Kunjungan')
    pdf.step(1, 'Jika order > 0: ikuti Flow B (Order Management)')
    pdf.step(2, 'Jika order = 0: buat order dengan status "no-order" dan reason')
    pdf.step(3, 'Verifikasi: order tercatat dan visit completion terkonfirmasi')

    # ══════════════════════════════════════════════
    # SECTION 4: FLOW B -- ORDER MANAGEMENT
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(4, 'Flow B -- Order Management (Pemesanan)')

    pdf.bd(
        'Flow ini menggantikan KlikOrder untuk pembuatan pesanan oleh sales rep. '
        'Setiap order > 0 WAJIB memiliki check-in event yang terverifikasi.'
    )

    pdf.sb('B.1 - Browse Product Catalog')
    pdf.step(1, 'GET /v1/entities untuk melihat semua produk:')
    pdf.code('curl -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  http://192.168.6.223:8000/v1/entities')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: 8 produk WIM dengan SKU, price, meta.brand, meta.category')
    pdf.step(3, 'Filter produk berdasarkan brand: SANQUA, LEVONTE, BATAVIA')
    pdf.step(4, 'Verifikasi: price dalam IDR, meta.brand terisi dengan benar')

    pdf.sb('B.2 - Add to Cart (Frontend)')
    pdf.step(1, 'Pilih produk dari catalog')
    pdf.step(2, 'Tentukan quantity (contoh: 10 karton SANQUA PET 220ML)')
    pdf.step(3, 'Verifikasi: total harga terhitung dengan benar (qty * price)')
    pdf.step(4, 'Jika ada bundling: auto-add free product ke cart')

    pdf.sb('B.3 - Create Order via API')
    pdf.step(1, 'POST /v1/orders dengan payload + entities:')
    pdf.code('curl -X POST http://192.168.6.223:8000/v1/orders \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Content-Type: application/json" \\')
    pdf.code('  -d @- <<EOF')
    pdf.code('  {')
    pdf.code('    "customer_uuid":"<contact_uuid>",')
    pdf.code('    "customer_type":"contact",')
    pdf.code('    "payload":{')
    pdf.code('      "dropoff_uuid":"<place_uuid>",')
    pdf.code('      "entities":[{"name":"SANQUA PET 220ML K24",')
    pdf.code('        "sku":"SQA-220-K24","price":120000,"quantity":10}]')
    pdf.code('    },')
    pdf.code('    "status":"pending","type":"delivery",')
    pdf.code('    "meta":{"payment_method":"cod"}')
    pdf.code('  }')
    pdf.code('  EOF')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: order created dengan public_id, status "pending"')
    pdf.step(3, 'Cek bahwa order memiliki customer_uuid dan payload.entities')

    pdf.sb('B.4 - QR Code Generation')
    pdf.step(1, 'Order public_id digunakan sebagai data QR code')
    pdf.step(2, 'Generate QR: qrcode.js atau library QR di frontend')
    pdf.step(3, 'Verifikasi: QR berisi order public_id yang benar')

    pdf.sb('B.5 - QR Scan Verification')
    pdf.step(1, 'Scan QR code yang di-generate')
    pdf.step(2, 'Cocokkan hasil scan dengan public_id order')
    pdf.step(3, 'PATCH /v1/orders/{id} dengan status "verified"')
    pdf.step(4, 'Verifikasi: status order berubah menjadi "verified"')

    pdf.sb('B.6 - Order History')
    pdf.step(1, 'GET /v1/orders untuk melihat semua orders')
    pdf.step(2, 'Verifikasi: setiap order menampilkan promo/bonus data jika ada')
    pdf.step(3, 'Filter berdasarkan status: pending, verified, completed')

    # ══════════════════════════════════════════════
    # SECTION 5: FLOW C -- NOO
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(5, 'Flow C -- NOO (New Outlet Opening)')

    pdf.bd(
        'NOO (New Outlet Opening) adalah fitur untuk mendaftarkan toko baru '
        'saat kunjungan. Ini menggantikan fitur NOO di GooVi.'
    )

    pdf.sb('C.1 - Create Place (Store)')
    pdf.step(1, 'POST /v1/places dengan data toko baru:')
    pdf.code('curl -X POST http://192.168.6.223:8000/v1/places \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Content-Type: application/json" \\')
    pdf.code('  -d @- <<EOF')
    pdf.code('  {')
    pdf.code('    "name":"TOKO TESTING BARU","type":"store",')
    pdf.code('    "location":{"latitude":-6.2500,"longitude":106.8000},')
    pdf.code('    "street1":"Jl. Testing No. 1","city":"Jakarta",')
    pdf.code('    "country":"ID","phone":"6281234567890"')
    pdf.code('  }')
    pdf.code('  EOF')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: place created dengan uuid, location.coordinates')

    pdf.sb('C.2 - Create Contact (Store Owner)')
    pdf.step(1, 'POST /v1/contacts:')
    pdf.code('curl -X POST http://192.168.6.223:8000/v1/contacts \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Content-Type: application/json" \\')
    pdf.code('  -d @- <<EOF')
    pdf.code('  {')
    pdf.code('    "place_uuid":"<place_uuid_baru>",')
    pdf.code('    "name":"Budi Testing","type":"customer",')
    pdf.code('    "phone":"6281234567890"')
    pdf.code('  }')
    pdf.code('  EOF')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: contact created, place_uuid terhubung ke store')

    pdf.sb('C.3 - Verifikasi NOO')
    pdf.step(1, 'GET /v1/places/{uuid} - data toko baru muncul')
    pdf.step(2, 'GET /v1/contacts - contact baru terdaftar')
    pdf.step(3, 'Verifikasi: relation antara Place dan Contact benar')

    pdf.tbox(
        'Untuk NOO, field yang diperlukan: name, type="store", location, '
        'street1, city, country. Untuk Contact: name, type="customer", '
        'place_uuid, phone.'
    )

    # ══════════════════════════════════════════════
    # SECTION 6: FLOW D -- OUT-OF-ROUTE ORDER
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(6, 'Flow D -- Out-of-Route Order')

    pdf.bd(
        'Out-of-route order adalah pesanan yang dibuat di toko yang TIDAK '
        'termasuk dalam rute harian sales rep. Fitur ini penting karena 51% '
        'out-of-route order saat ini dilakukan via WA/Telepon (melalui sistem).'
    )

    pdf.sb('D.1 - Add Store on the Fly')
    pdf.step(1, 'Buat Place baru untuk toko di luar rute (seperti NOO)')
    pdf.step(2, 'Atau gunakan Place yang sudah ada tetapi tidak di waypoints route')

    pdf.sb('D.2 - Create Order with Off-Route Reason')
    pdf.step(1, 'POST /v1/orders dengan meta.off_route_reason:')
    pdf.code('curl -X POST http://192.168.6.223:8000/v1/orders \\')
    pdf.code('  -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  -H "Content-Type: application/json" \\')
    pdf.code('  -d @- <<EOF')
    pdf.code('  {')
    pdf.code('    "customer_uuid":"<contact_uuid>",')
    pdf.code('    "customer_type":"contact",')
    pdf.code('    "payload":{')
    pdf.code('      "dropoff_uuid":"<place_uuid>",')
    pdf.code('      "entities":[{"name":"SANQUA PET 550ML K24",')
    pdf.code('        "sku":"SQA-550-K24","price":150000,"quantity":5}]')
    pdf.code('    }')
    pdf.code('    "status":"pending","type":"delivery",')
    pdf.code('    "meta":{')
    pdf.code('      "payment_method":"cod",')
    pdf.code('      "off_route":true,')
    pdf.code('      "off_route_reason":"Order by WA dari pemilik toko"')
    pdf.code('    }')
    pdf.code('  }')
    pdf.code('  EOF')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: order created dengan meta.off_route=true')
    pdf.step(3, 'Cek bahwa off_route_reason tersimpan di meta')

    pdf.wbox(
        'Out-of-route order WAJIB memiliki alasan (off_route_reason). '
        'Jika tidak, order harus ditolak oleh sistem. Ini adalah aturan '
        'data integrity untuk mencegah penyalahgunaan.'
    )

    # ══════════════════════════════════════════════
    # SECTION 7: FLOW E -- ADMIN CONSOLE
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(7, 'Flow E -- Admin Console (Dashboard)')

    pdf.bd(
        'Fleetbase Console adalah dashboard admin berbasis Ember.js. '
        'Digunakan oleh Super Admin dan Depot Admin untuk mengelola data.'
    )

    pdf.sb('E.1 - Login ke Console')
    pdf.step(1, 'Buka http://192.168.6.223:4200 di browser')
    pdf.step(2, 'Login dengan email: reinharttanto@gmail.com')
    pdf.step(3, 'Verifikasi: dashboard muncul dengan Company "SanQua"')
    pdf.step(4, 'Cek menu navigasi: sidebar dengan menu Places, Orders, Routes, dll')

    pdf.sb('E.2 - Manage Places (Stores)')
    pdf.step(1, 'Klik menu "Places" di sidebar')
    pdf.step(2, 'Verifikasi: 5 stores terdaftar dengan nama dan alamat')
    pdf.step(3, 'Klik salah satu store: detail muncul (location, name, type)')
    pdf.step(4, 'Coba filter: search by name, type="store"')

    pdf.sb('E.3 - Manage Contacts')
    pdf.step(1, 'Klik menu "Contacts"')
    pdf.step(2, 'Verifikasi: 4 contacts terdaftar dengan type "customer"')
    pdf.step(3, 'Cek bahwa contact memiliki place_uuid yang terhubung ke store')

    pdf.sb('E.4 - Manage Products (Entities)')
    pdf.step(1, 'Klik menu "Entities"')
    pdf.step(2, 'Verifikasi: 8 products dengan type "product"')
    pdf.step(3, 'Cek meta data: brand, category tersimpan dengan benar')
    pdf.step(4, 'Filter berdasarkan brand SANQUA: 5 products muncul')

    pdf.sb('E.5 - Manage Orders')
    pdf.step(1, 'Klik menu "Orders"')
    pdf.step(2, 'Verifikasi: existing orders muncul dengan status')
    pdf.step(3, 'Klik order: detail payload, entities, customer muncul')

    pdf.sb('E.6 - Manage Drivers')
    pdf.step(1, 'Klik menu "Drivers" (atau "Fleet-ops" > "Drivers")')
    pdf.step(2, 'Verifikasi: driver Andi Sales muncul dengan status active')
    pdf.step(3, 'Cek vehicle yang ter-link: Motor Andi')

    pdf.sb('E.7 - Manage Vehicles')
    pdf.step(1, 'Klik menu "Vehicles"')
    pdf.step(2, 'Verifikasi: Motor Andi (B 1234 ABC) terdaftar')

    pdf.sb('E.8 - Manage Users')
    pdf.step(1, 'Klik menu "Users"')
    pdf.step(2, 'Verifikasi: admin user + customer accounts terdaftar')
    pdf.step(3, 'Cek role/type masing-masing user')

    # ══════════════════════════════════════════════
    # SECTION 8: FLOW F -- REPORTING
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(8, 'Flow F -- Reporting & Export')

    pdf.bd(
        'Fleetbase menyediakan dashboard dan reporting built-in. '
        'Untuk laporan kustom WIM, endpoint API dapat digunakan untuk ekspor.'
    )

    pdf.sb('F.1 - Dashboard Built-in')
    pdf.step(1, 'Console dashboard: overview metrics, charts')
    pdf.step(2, 'Verifikasi: total orders, total places, active drivers')
    pdf.step(3, 'Cek bahwa data terisi dengan benar dari test data')

    pdf.sb('F.2 - Export Orders')
    pdf.step(1, 'GET /v1/orders dengan parameter export:')
    pdf.code('curl -H "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" \\')
    pdf.code('  "http://192.168.6.223:8000/v1/orders?limit=50" \\')
    pdf.code('  -o orders-export.json')
    pdf.ln(1)
    pdf.step(2, 'Verifikasi: data orders lengkap dengan promo/bonus info')

    pdf.sb('F.3 - Export Places')
    pdf.step(1, 'GET /v1/places untuk export data toko')
    pdf.step(2, 'Verifikasi: semua stores dengan location, name, city')

    pdf.sb('F.4 - Geofence Events Report')
    pdf.step(1, 'GET /v1/geofences/events untuk melihat history geofence')
    pdf.step(2, 'Verifikasi: event tercatat dengan driver_uuid, zone_uuid, type')

    pdf.ibox(
        'Untuk export CSV, Fleetbase dapat dikustomisasi dengan '
        'artisan command PHP. Lihat dokumentasi implementasi untuk detail.'
    )

    # ══════════════════════════════════════════════
    # SECTION 9: FLOW G -- GEOFENCE DETECTION
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(9, 'Flow G -- Geofence Detection')

    pdf.bd(
        'Geofence detection adalah fitur kritis yang menggantikan check-in '
        'berbasis GPS di GooVi. Sistem menggunakan MySQL spatial queries '
        '(ST_Contains) untuk menentukan apakah driver berada di dalam zona.'
    )

    pdf.sb('G.1 - Verifikasi Zona Geofence')
    pdf.step(1, 'Cek zones: GET /v1/zones')
    pdf.step(2, 'Verifikasi: 3 zones dengan status "active"')
    pdf.step(3, 'Cek trigger_on_entry=1, trigger_on_exit=1')
    pdf.step(4, 'Verifikasi border polygon: 32 titik, radius ~10m')

    pdf.sb('G.2 - Test Check-in di Dalam Zona')
    pdf.step(1, 'Kirim tracking di koordinat yang tepat:')
    pdf.code('curl -X POST .../drivers/.../track \\')
    pdf.code('  -d \'{"latitude":-6.2088,"longitude":106.8456}\'')
    pdf.ln(1)
    pdf.step(2, 'Cek geofence events: GET /v1/geofences/events')
    pdf.step(3, 'Verifikasi: event "entered" muncul untuk driver + zone')

    pdf.sb('G.3 - Test Check-in di Luar Zona')
    pdf.step(1, 'Kirim tracking di koordinat JAUH dari zona:')
    pdf.code('curl -X POST .../drivers/.../track \\')
    pdf.code('  -d \'{"latitude":-6.3000,"longitude":106.8500}\'')
    pdf.ln(1)
    pdf.step(2, 'Cek geofence events: seharusnya TIDAK ada event entered')
    pdf.step(3, 'Verifikasi: sistem tidak mendeteksi check-in palsu')

    pdf.sb('G.4 - Test Check-out (Exit)')
    pdf.step(1, 'Kirim tracking di luar zona setelah sebelumnya di dalam')
    pdf.step(2, 'Cek events: "exited" event muncul')

    pdf.wbox(
        'Geofence detection menggunakan ST_Contains() MySQL. '
        'Presisi tergantung pada kualitas GPS (outdoor: +/-10-20m). '
        'Jangan test indoor: GPS tidak akurat di dalam gedung. '
        'Zona 10m adalah radius minimal yang disarankan.'
    )

    # ══════════════════════════════════════════════
    # SECTION 10: FLOW H -- PHOTO & ATTACHMENT
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(10, 'Flow H -- Photo & Attachment')

    pdf.bd(
        'Fleetbase mendukung attachment pada driver tracking events. '
        'Ini digunakan untuk foto selfie (absensi) dan foto kunjungan (spanduk/flyer).'
    )

    pdf.sb('H.1 - Selfie Photo (Absensi)')
    pdf.step(1, 'Gunakan POST /v1/drivers/{id}/track dengan multipart')
    pdf.step(2, 'Lampirkan foto sebagai file upload')
    pdf.step(3, 'Verifikasi: file tersimpan, url avatar terisi')

    pdf.sb('H.2 - Kunjungan Photo dengan Deskripsi')
    pdf.step(1, 'Sama seperti di atas, tambahkan field description')
    pdf.step(2, 'Verifikasi: foto + description tersimpan di event log')

    pdf.sb('H.3 - View Photo Gallery')
    pdf.step(1, 'Cek di console: driver tracking history')
    pdf.step(2, 'Verifikasi: foto muncul dengan timestamp')

    pdf.ibox(
        'Untuk testing foto, gunakan file gambar kecil (< 1MB) '
        'format JPG/PNG. Foto akan disimpan di storage Fleetbase.'
    )

    # ══════════════════════════════════════════════
    # SECTION 11: FLOW I -- PURCHASE ORDER & QR
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(11, 'Flow I -- Purchase Order & QR Verification')

    pdf.bd(
        'Fitur QR Code verification adalah kunci data integrity untuk '
        'memastikan bahwa order yang dicatat benar-benar direalisasikan. '
        'Ini menjawab masalah trust gap antara GooVi dan KlikOrder.'
    )

    pdf.sb('I.1 - Generate QR Code')
    pdf.step(1, 'Buat order (POST /v1/orders)')
    pdf.step(2, 'Ambil public_id dari response')
    pdf.step(3, 'Generate QR code dari public_id (gunakan library qrcode.js)')
    pdf.step(4, 'Verifikasi: QR berisi string public_id yang valid')

    pdf.sb('I.2 - Scan QR Code')
    pdf.step(1, 'Gunakan kamera untuk scan QR')
    pdf.step(2, 'Cocokkan hasil scan dengan public_id order')
    pdf.step(3, 'Jika cocok: PATCH /v1/orders/{id} status "verified"')
    pdf.step(4, 'Jika tidak cocok: tampilkan error, jangan verifikasi')

    pdf.sb('I.3 - Verifikasi Data Integrity')
    pdf.step(1, 'Cek bahwa order > 0 memiliki check-in event')
    pdf.step(2, 'Cek bahwa order > 0 memiliki QR verification')
    pdf.step(3, 'Jika salah satu tidak ada: order harus di-flag sebagai incomplete')

    pdf.wbox(
        'Ini adalah non-negotiable: setiap order > 0 WAJIB memiliki '
        'check-in event + QR scan verification. Tanpa kedua hal ini, '
        'sistem akan memiliki masalah trust yang sama seperti GooVi-KlikOrder saat ini.'
    )

    # ══════════════════════════════════════════════
    # SECTION 12: FLOW J -- PROMO & BUNDLING
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(12, 'Flow J -- Promo & Bundling')

    pdf.bd(
        'Promo dan bundling adalah fitur KlikOrder yang tidak memiliki '
        'dukungan native di Fleetbase. Implementasi dilakukan melalui '
        'meta data pada Entities dan frontend logic.'
    )

    pdf.sb('J.1 - Product Meta untuk Promo')
    pdf.step(1, 'Cek meta data produk: GET /v1/entities/{id}')
    pdf.step(2, 'Verifikasi: meta.brand, meta.category terisi')
    pdf.step(3, 'Untuk promo, tambahkan meta.promo:')
    pdf.code('PATCH /v1/entities/{entity_uuid} \\')
    pdf.code('  -d \'{"meta":{"promo":{"name":"Beli 10 gratis 1",')
    pdf.code('    "type":"bundling","trigger_qty":10,"free_qty":1}}}\'')
    pdf.ln(1)
    pdf.step(4, 'Verifikasi: promo tersimpan di meta')

    pdf.sb('J.2 - Bundling Logic (Frontend)')
    pdf.step(1, 'Saat menambahkan produk ke cart, cek trigger bundling')
    pdf.step(2, 'Jika qty >= trigger_qty: auto-add free product')
    pdf.step(3, 'Verifikasi: cart menampilkan produk gratis dengan label "BONUS"')
    pdf.step(4, 'Cek bahwa bonus product memiliki meta.is_bonus=true')

    pdf.sb('J.3 - Strata / Volume Discount')
    pdf.step(1, 'Strata = harga berbeda per tier quantity')
    pdf.step(2, 'Contoh: 1-10 karton @ Rp120rb, 11-20 @ Rp115rb, 21+ @ Rp110rb')
    pdf.step(3, 'Verifikasi: harga di cart menyesuaikan dengan quantity')

    pdf.sb('J.4 - Export Promo Data')
    pdf.step(1, 'Export orders: pastikan promo name muncul di output')
    pdf.step(2, 'Verifikasi: bonus product terpisah dari product utama')
    pdf.step(3, 'Cek bahwa promo reference (nomor surat promo) tercantum')

    pdf.ibox(
        'Promo bundling dan strata diimplementasikan di frontend logic. '
        'Fleetbase hanya menyimpan data entities. Untuk promo yang kompleks, '
        'pertimbangkan custom Promo model di backend.'
    )

    # ══════════════════════════════════════════════
    # SECTION 13: CHECKLIST KESELURUHAN
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(13, 'Checklist Keseluruhan')

    pdf.bd('Gunakan checklist ini untuk menandai fitur yang sudah di-test dan lolos.')

    pdf.sb('G0 - Infrastructure')
    pdf.chk([
        'Console Fleetbase dapat diakses (http://192.168.6.223:4200)',
        'API Fleetbase merespon (http://192.168.6.223:8000/v1)',
        'API Key authentication berfungsi',
        'Docker services semua running (8 services)',
    ])

    pdf.sb('G1 - Core Data')
    pdf.chk([
        '5 stores terdaftar dengan lat/lng',
        '3 geofence zones aktif (10m radius)',
        '8 products WIM terdaftar (SANQUA, LEVONTE, BATAVIA)',
        '4 contacts terhubung ke stores',
        'Driver Andi Sales aktif dengan vehicle',
        'API Key: flb_live_RgeKNhT7Pg8rCcuXp8sD berfungsi',
    ])

    pdf.sb('G2 - Visit Workflow')
    pdf.chk([
        'Driver tracking POST berfungsi',
        'Geofence Entered event terdeteksi',
        'Geofence Exited event terdeteksi',
        'Route dengan waypoints dapat diakses',
        'Store detail (name, location, contact) muncul',
        'No-order dengan reason tersimpan',
        'Stock entry per SKU tersimpan',
        'Photo attachment terkirim',
    ])

    pdf.sb('G3 - Order Management')
    pdf.chk([
        'Product catalog dapat diakses',
        'Cart dengan quantity berfungsi',
        'Order created dengan status pending',
        'QR code di-generate dari public_id',
        'QR scan verification (PATCH status)',
        'Out-of-route order dengan reason',
        'Order history menampilkan promo/bonus',
        'Admin order creation via console',
    ])

    pdf.sb('G4 - Reporting & Admin')
    pdf.chk([
        'Dashboard console menampilkan data',
        'Places management (CRUD)',
        'Contacts management (CRUD)',
        'Entities management (CRUD)',
        'Orders management (view, filter)',
        'Drivers & Vehicles management',
        'Users management',
        'Data export (JSON/CSV)',
    ])

    # ══════════════════════════════════════════════
    # SECTION 14: SUBAGENT QA PROTOCOL
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st(14, 'Subagent QA Protocol')

    pdf.bd(
        'Setiap fitur harus di-test oleh 3 subagen AI dengan persona berbeda. '
        'Subagent adalah sesi Hermes Agent terpisah yang bertindak sebagai '
        'pengguna sungguhan. Mereka tidak memiliki konteks sebelumnya.'
    )

    pdf.sb('Subagent A: Sales Rep')
    pdf.bd('Persona: Sales lapangan yang melakukan kunjungan ke toko.')
    pdf.bu('Test flow: check-in, visit card, NOO, order, photo, stock, out-of-route')
    pdf.bu('Bandingkan dengan GooVi flow: apa yang hilang? apa yang berbeda?')
    pdf.bu('Apakah UX cukup sederhana untuk sales rep non-tech?')
    pdf.ln(1)

    pdf.sb('Subagent B: Depot Admin')
    pdf.bd('Persona: Admin depo yang mengelola operasional harian.')
    pdf.bu('Test flow: route plan, admin order, report, export, user management')
    pdf.bu('Bandingkan dengan KlikOrder admin panel')
    pdf.bu('Apakah data integrity rules (check-in + QR) enforceable?')
    pdf.ln(1)

    pdf.sb('Subagent C: Super Admin')
    pdf.bd('Persona: Management WIM yang mengawasi seluruh operasi.')
    pdf.bu('Test flow: dashboard, settings, promo, analytics, full reporting')
    pdf.bu('Bandingkan dengan GooVi Super Admin panel')
    pdf.bu('Apakah reporting cukup untuk decision making?')
    pdf.ln(1)

    pdf.sb('Feedback Structure')
    pdf.bd('Setiap subagent harus memberikan feedback terstruktur:')
    pdf.tbl(
        ['#', 'Pertanyaan', 'Format'],
        [
            ['1', 'What worked?', 'Deskripsi'],
            ['2', 'What felt wrong/missing vs GooVi/KlikOrder?', 'List item'],
            ['3', 'Bugs or edge cases found?', 'List item'],
            ['4', 'Is it suitable for production use?', 'Yes/No/Maybe'],
        ],
        [8, 80, 85],
        ['C', 'L', 'L']
    )

    pdf.sb('Gate Rule')
    pdf.wbox(
        'ALL 3 subagents must agree "Yes" for a feature to be marked DONE. '
        'If any says "No" or "Maybe": fix the issues found and re-run '
        'the subagent loop with new subagents. Unanimous approval required.'
    )

    # ══════════════════════════════════════════════
    # LAMPIRAN
    # ══════════════════════════════════════════════
    pdf.add_page()
    pdf.st('Lampiran', 'Data Referensi & API Endpoint')

    pdf.sb('Store Locations')
    pdf.tbl(
        ['Store', 'Latitude', 'Longitude', 'Zone'],
        [
            ['Toko Berkah', '-6.2088', '106.8456', 'Geofence Toko Berkah'],
            ['Toko Jaya', '-6.2404', '106.7976', 'Geofence Toko Jaya'],
            ['Toko Makmur', '-6.2625', '106.7890', 'Geofence Toko Makmur'],
            ['Toko Sejahtera', '-6.2345', '106.7934', '(no zone)'],
            ['Toko Baru', '-6.2512', '106.8021', '(no zone)'],
        ],
        [45, 28, 28, 55],
        ['L', 'C', 'C', 'L']
    )

    pdf.sb('Product Catalog')
    pdf.tbl(
        ['SKU', 'Name', 'Price', 'Brand'],
        [
            ['SQA-220-K24', 'SANQUA PET 220ML K24', 'Rp120,000', 'SANQUA'],
            ['SQA-550-K24', 'SANQUA PET 550ML K24', 'Rp150,000', 'SANQUA'],
            ['SQA-1500-K12', 'SANQUA PET 1500ML K12', 'Rp130,000', 'SANQUA'],
            ['SQA-120-K40', 'SANQUA CUP 120ML K40', 'Rp80,000', 'SANQUA'],
            ['SQA-330-K24', 'SANQUA CUP 330ML K24', 'Rp100,000', 'SANQUA'],
            ['LEV-220-K24', 'LEVONTE CUP 220ML K24', 'Rp95,000', 'LEVONTE'],
            ['BAT-200-K48', 'BATAVIA CUP 200ML K48', 'Rp115,000', 'BATAVIA'],
            ['BAT-600-K24', 'BATAVIA PET 600ML K24', 'Rp140,000', 'BATAVIA'],
        ],
        [30, 62, 28, 28],
        ['L', 'L', 'C', 'C']
    )

    pdf.sb('API Endpoint Reference')
    pdf.tbl(
        ['Method', 'Endpoint', 'Description'],
        [
            ['GET', '/v1/places', 'List all stores'],
            ['POST', '/v1/places', 'Create new store'],
            ['GET', '/v1/zones', 'List geofence zones'],
            ['GET', '/v1/entities', 'List products'],
            ['POST', '/v1/orders', 'Create order'],
            ['GET', '/v1/orders', 'List orders'],
            ['PATCH', '/v1/orders/{id}', 'Update order status'],
            ['GET', '/v1/contacts', 'List contacts'],
            ['POST', '/v1/contacts', 'Create contact'],
            ['GET', '/v1/drivers', 'List drivers'],
            ['POST', '/v1/drivers/{id}/track', 'Send driver location'],
            ['GET', '/v1/geofences/events', 'List geofence events'],
            ['GET', '/v1/routes', 'List routes'],
            ['GET', '/v1/vehicles', 'List vehicles'],
        ],
        [18, 62, 90],
        ['C', 'L', 'L']
    )

    pdf.ln(2)
    pdf.ibox(
        'Semua endpoint di atas menggunakan API Key authentication. '
        'Tambahkan header: "Authorization: Bearer flb_live_RgeKNhT7Pg8rCcuXp8sD" '
        'Base URL: http://192.168.6.223:8000/v1'
    )

    pdf.ln(3)
    pdf.set_font('U', 'I', 8)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(0, 4, 'Dokumen ini disusun oleh Hermes Agent (Seraphine) untuk PT Wahana Inti Mas. '
                         'Data test environment: LXC 106 (192.168.6.223) - SanQua AI Proxmox. '
                         'September 2026.')

    # Save
    output_path = os.path.expanduser('~/projects/wim-fleetbase/WIM-Fleetbase-QA-Testing-Guidebook.pdf')
    pdf.output(output_path)
    print(f'PDF saved: {output_path}')
    return output_path


if __name__ == '__main__':
    build_pdf()