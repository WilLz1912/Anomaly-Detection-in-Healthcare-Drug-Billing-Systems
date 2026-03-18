"""
rule_engine.py
--------------
15 rules từ PHARMACEUTICAL_RULE.docx — gắn flag + severity per dòng thuốc.
"""

import re

# ── Keyword sets ──
KW_INJECTION = {'tiêm', 'truyền', 'iv', 'im', 'ống', 'ampoule', 'vial',
                'dung dịch tiêm', 'bột pha tiêm', 'nhũ tương tiêm'}
KW_TABLET    = {'viên', 'tablet', 'capsule', 'nén', 'vỉ', 'nang', 'bao phim'}
KW_SYRUP     = {'siro', 'suspension', 'hỗn dịch', 'cốm pha', 'bột pha hỗn dịch'}
KW_CTRL      = {'gây nghiện', 'hướng thần', 'opioid', 'morphine',
                'fentanyl', 'codein', 'tramadol', 'methadone'}

# ── Overprice threshold theo dạng bào chế ──
THRESHOLD = {'injection': 1.3, 'tablet': 1.5, 'syrup': 1.4}

# ── Severity mapping ──
FLAG_SEV = {
    'OVERPRICE_INJECTION':              3,
    'OVERPRICE_TABLET':                 3,
    'OVERPRICE_SYRUP':                  3,
    'SUSPICIOUS_LOW_PRICE':             3,
    'SUSPICIOUS_INJECTION_TRANSACTION': 3,
    'CONTROLLED_SUBSTANCE_VOLUME_RISK': 3,
    'TOTAL_MISMATCH':                   2,
    'HIGH_VALUE_TRANSACTION':           2,
    'UNUSUAL_HIGH_QTY_INJECTION':       2,
    'UNUSUAL_HIGH_QTY_SMALL_INJECTION': 2,
    'PACK_AND_PRICE_MANIPULATION':      2,
    'UNUSUAL_HIGH_QTY_TABLET':          1,
    'UNUSUAL_HIGH_QTY_SYRUP':           1,
    'UNUSUAL_HIGH_QTY_BLISTER':         1,
    'UNUSUAL_HIGH_QTY_BOX':             1,
    'UNUSUAL_HIGH_QTY_BOTTLE':          1,
    'PACK_SIZE_MISMATCH':               0,
    'UNIT_DOSAGE_MISMATCH':             1,
    'LOW_CONFIDENCE_MATCH':             1,
}

# ── Messages hiển thị trên UI ──
FLAG_MSG = {
    'OVERPRICE_INJECTION':              'Đơn giá tiêm/truyền vượt {ratio:.0f}% giá tham chiếu',
    'OVERPRICE_TABLET':                 'Đơn giá viên nén vượt {ratio:.0f}% giá tham chiếu',
    'OVERPRICE_SYRUP':                  'Đơn giá siro vượt {ratio:.0f}% giá tham chiếu',
    'SUSPICIOUS_LOW_PRICE':             'Giá thấp bất thường ({ratio:.0f}% so tham chiếu)',
    'TOTAL_MISMATCH':                   'Tổng tiền hóa đơn không khớp tổng các dòng',
    'HIGH_VALUE_TRANSACTION':           'Giao dịch giá trị lớn + số lượng cao',
    'UNUSUAL_HIGH_QTY_INJECTION':       'Số lượng tiêm/truyền bất thường',
    'UNUSUAL_HIGH_QTY_SMALL_INJECTION': 'Số lượng lọ/ống bất thường',
    'UNUSUAL_HIGH_QTY_TABLET':          'Số lượng viên bất thường ',
    'UNUSUAL_HIGH_QTY_SYRUP':           'Số lượng siro bất thường',
    'UNUSUAL_HIGH_QTY_BLISTER':         'Số lượng vỉ bất thường',
    'UNUSUAL_HIGH_QTY_BOX':             'Số lượng hộp bất thường) — nghi bán sỉ',
    'UNUSUAL_HIGH_QTY_BOTTLE':          'Số lượng chai bất thường)',
    'PACK_SIZE_MISMATCH':               'Số lượng không chia hết theo quy cách đóng gói',
    'PACK_AND_PRICE_MANIPULATION':      'Sai quy cách + giá cao — nguy cơ thao túng',
    'SUSPICIOUS_INJECTION_TRANSACTION': 'Tiêm truyền: giá thấp + số lượng cao',
    'CONTROLLED_SUBSTANCE_VOLUME_RISK': 'Thuốc kiểm soát đặc biệt — số lượng lớn',
    'UNIT_DOSAGE_MISMATCH':             'Đơn vị tính không khớp dạng bào chế',
    'LOW_CONFIDENCE_MATCH':             'Không tìm thấy trong danh mục — cần xác minh',
}


def _kw_in(text: str, kws: set) -> bool:
    t = text.lower()
    return any(k in t for k in kws)


# ── Patterns phân loại dạng bào chế ──────────────────────────────────────────
# Thứ tự ưu tiên: Tablet → Syrup → loại trừ oral/bôi/hít → Injection → DVT fallback

# Dạng UỐNG/bôi/hít — phải loại trừ TRƯỚC injection để tránh nhầm
_ORAL_EXCL = (
    'hỗn dịch uống', 'dung dịch uống',
    'bột pha hỗn dịch uống', 'thuốc bột pha hỗn dịch uống',
    'cốm pha hỗn dịch uống', 'thuốc cốm pha hỗn dịch uống',
    'nhỏ mắt', 'nhỏ tai', 'nhỏ mũi', 'xịt mũi',
    'bôi da', 'bôi ngoài', 'kem bôi', 'gel bôi', 'thuốc mỡ',
    'đặt âm đạo', 'thụt trực tràng', 'thuốc đạn',
    'dùng ngoài da', 'phun mù', 'khí dung', 'hít qua',
)

# Dạng INJECTION rõ ràng
_INJ_PATTERNS = (
    'dung dịch tiêm', 'dịch tiêm', 'dung dịch truyền', 'dịch truyền',
    'bột pha tiêm', 'bột đông khô pha tiêm', 'thuốc bột pha tiêm',
    'thuốc tiêm', 'thuốc đông khô', 'nhũ tương tiêm', 'hỗn dịch tiêm',
    'dung dịch đậm đặc để pha tiêm', 'dung dịch đậm đặc pha tiêm',
    'bột pha dung dịch tiêm', 'bột và dung môi pha tiêm',
    'dung môi pha tiêm',
)

# Dạng TABLET — bắt đầu bằng "viên"
_TAB_STARTS = (
    'viên nén', 'viên nang', 'viên bao', 'viên sủi',
    'viên ngậm', 'viên đặt', 'viên hoàn', 'viên phân tán',
    'viên nhai', 'viên phóng thích',
)

# Dạng SYRUP
_SYR_PATTERNS = (
    'siro', 'sirô', 'hỗn dịch uống', 'dung dịch uống',
    'cốm pha hỗn dịch', 'bột pha hỗn dịch uống',
)


def get_form_type(dang_bao_che: str, don_vi_tinh: str = "") -> str:
    """
    Phân loại dạng bào chế chính xác dựa trên dangBaoChe + donViTinh.

    Thứ tự ưu tiên:
      1. Tablet  — dangBaoChe bắt đầu bằng "viên" (rõ ràng nhất)
      2. Syrup   — oral liquid (trước injection để tránh nhầm "truyền")
      3. Loại trừ oral/bôi/hít khỏi injection
      4. Injection — chứa "tiêm"/"truyền" SAU KHI đã loại oral
      5. DVT fallback — khi dangBaoChe trống/không rõ
    """
    dbc = str(dang_bao_che or '').lower().strip()
    dvt = str(don_vi_tinh  or '').lower().strip()

    # ── 1. TABLET ──────────────────────────────────────────────────
    if dbc.startswith('viên') or any(dbc.startswith(p) for p in _TAB_STARTS):
        return 'tablet'
    if any(k in dbc for k in ('tablet', 'capsule', 'cap.')):
        return 'tablet'

    # ── 2. SYRUP ───────────────────────────────────────────────────
    if any(p in dbc for p in _SYR_PATTERNS):
        return 'syrup'

    # ── 3. Loại trừ oral/bôi/hít (không phải injection) ───────────
    # Chỉ loại trừ khi KHÔNG có từ khóa tiêm trong cùng chuỗi
    is_oral = any(p in dbc for p in _ORAL_EXCL)
    has_inj = any(p in dbc for p in _INJ_PATTERNS) or 'tiêm' in dbc
    if is_oral and not has_inj:
        return 'other'

    # ── 4. INJECTION (sau khi đã loại oral thuần) ──────────────────
    if any(p in dbc for p in _INJ_PATTERNS):
        return 'injection'
    if 'tiêm' in dbc or 'truyền' in dbc:
        return 'injection'

    # ── 5. Fallback theo donViTinh khi dangBaoChe trống/không rõ ───
    if dvt in ('ống', 'lọ', 'bơm tiêm', 'bút tiêm', 'túi'):
        return 'injection'
    if dvt == 'viên':
        return 'tablet'
    if dvt in ('chai', 'gói'):
        return 'syrup'

    return 'other'


def _pack_size(quy_cach: str):
    if not quy_cach:
        return None
    nums = re.findall(r'\d+', quy_cach)
    if not nums:
        return None
    ns = [int(n) for n in nums]
    return ns[0] * ns[1] if len(ns) >= 2 else ns[0]


class RuleEngine:

    def check_item(self, item: dict, match: dict) -> dict:
        """
        item  : dict từ OCR (ten_thuoc, so_luong, don_vi_tinh, don_gia, thanh_tien)
        match : dict từ DrugMatcher

        Returns dict: flags, messages, severity, details
        """
        flags    = []
        messages = []
        details  = {}

        ten      = item.get('ten_thuoc', '') or item.get('tenThuoc', '')
        dbc      = item.get('dangBaoChe', '') or match.get('dangBaoChe', '')
        dvt      = item.get('don_vi_tinh', '') or item.get('donViTinh', '')
        sl       = float(item.get('so_luong', 0) or item.get('soLuong', 0) or 0)
        don_gia  = float(item.get('don_gia',  0) or item.get('donGia',  0) or 0)
        thanh    = float(item.get('thanh_tien', 0) or item.get('thanhTien', 0) or 0)
        gia_tc   = float(item.get('gia_tham_chieu', 0) or item.get('giaThamChieu', 0) or 0)
        quy_cach = item.get('quyCachDongGoi', '') or match.get('quyCachDongGoi', '')
        hoat_chat = item.get('hoat_chat', '') or item.get('hoatChat', '')

        # Lấy price_ref: ưu tiên giaThamChieu trong item, fallback drug master
        price_ref = gia_tc if gia_tc > 0 else (match.get('price_ref') or 0)
        is_import = match.get('is_import', False)
        form_type = get_form_type(dbc, dvt)

        # ── RULE 11: Low confidence ──────────────────────────────────
        if not match.get('matched') or match.get('key_quality', 3) == 0:
            flags.append('LOW_CONFIDENCE_MATCH')
            messages.append(FLAG_MSG['LOW_CONFIDENCE_MATCH'])

        # ── RULE 1: Overprice ────────────────────────────────────────
        if price_ref > 0 and don_gia > 0:
            ratio = don_gia / price_ref
            details['price_ratio'] = round(ratio, 3)
            thr = THRESHOLD.get(form_type, 1.5)
            if is_import:
                thr = max(1.3, thr - 0.2)

            if form_type == 'injection' and don_gia > thr * price_ref:
                flags.append('OVERPRICE_INJECTION')
                messages.append(FLAG_MSG['OVERPRICE_INJECTION'].format(ratio=ratio * 100))
            elif form_type == 'tablet' and don_gia > thr * price_ref:
                flags.append('OVERPRICE_TABLET')
                messages.append(FLAG_MSG['OVERPRICE_TABLET'].format(ratio=ratio * 100))
            elif form_type == 'syrup' and don_gia > thr * price_ref:
                flags.append('OVERPRICE_SYRUP')
                messages.append(FLAG_MSG['OVERPRICE_SYRUP'].format(ratio=ratio * 100))

            # ── RULE 2: Suspicious low price ────────────────────────
            if don_gia < 0.6 * price_ref:
                flags.append('SUSPICIOUS_LOW_PRICE')
                messages.append(FLAG_MSG['SUSPICIOUS_LOW_PRICE'].format(ratio=ratio * 100))

        # ── RULE 6: High quantity ────────────────────────────────────
        dvt_l = dvt.lower()
        if form_type == 'injection' and sl > 5:
            flags.append('UNUSUAL_HIGH_QTY_INJECTION')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_INJECTION'].format(th=5, dvt=dvt))
        elif form_type == 'tablet' and sl > 200:
            flags.append('UNUSUAL_HIGH_QTY_TABLET')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_TABLET'].format(th=200))
        elif form_type == 'syrup' and sl > 10:
            flags.append('UNUSUAL_HIGH_QTY_SYRUP')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_SYRUP'].format(th=10))

        if dvt_l in ('ống', 'lọ') and sl > 5 and 'UNUSUAL_HIGH_QTY_INJECTION' not in flags:
            flags.append('UNUSUAL_HIGH_QTY_SMALL_INJECTION')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_SMALL_INJECTION'].format(th=5))
        if dvt_l == 'vỉ' and sl > 50:
            flags.append('UNUSUAL_HIGH_QTY_BLISTER')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_BLISTER'].format(th=50))
        if dvt_l == 'hộp' and sl > 20:
            flags.append('UNUSUAL_HIGH_QTY_BOX')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_BOX'].format(th=20))
        if dvt_l == 'chai' and sl > 10:
            flags.append('UNUSUAL_HIGH_QTY_BOTTLE')
            messages.append(FLAG_MSG['UNUSUAL_HIGH_QTY_BOTTLE'].format(th=10))

        # ── RULE 5: Pack size mismatch ───────────────────────────────
        pack = _pack_size(quy_cach)
        if pack and pack > 1 and sl > 0 and sl % pack != 0:
            flags.append('PACK_SIZE_MISMATCH')
            messages.append(FLAG_MSG['PACK_SIZE_MISMATCH'])
            details['pack_size'] = pack
            if any(f in flags for f in ('OVERPRICE_INJECTION', 'OVERPRICE_TABLET', 'OVERPRICE_SYRUP')):
                flags.append('PACK_AND_PRICE_MANIPULATION')
                messages.append(FLAG_MSG['PACK_AND_PRICE_MANIPULATION'])

        # ── RULE 8: Controlled substance ────────────────────────────
        if any(k in (hoat_chat + ten).lower() for k in KW_CTRL) and sl > 5:
            flags.append('CONTROLLED_SUBSTANCE_VOLUME_RISK')
            messages.append(FLAG_MSG['CONTROLLED_SUBSTANCE_VOLUME_RISK'])

        # ── RULE 9: Unit dosage mismatch ────────────────────────────
        if dvt_l == 'lọ' and form_type == 'tablet':
            flags.append('UNIT_DOSAGE_MISMATCH')
            messages.append(FLAG_MSG['UNIT_DOSAGE_MISMATCH'])

        # ── RULE 12: High value ──────────────────────────────────────
        if thanh > 50_000_000 and sl > 10:
            flags.append('HIGH_VALUE_TRANSACTION')
            messages.append(FLAG_MSG['HIGH_VALUE_TRANSACTION'])

        # ── RULE 13: Suspicious injection ───────────────────────────
        if form_type == 'injection' and sl > 5 and price_ref > 0 and don_gia < 0.7 * price_ref:
            flags.append('SUSPICIOUS_INJECTION_TRANSACTION')
            messages.append(FLAG_MSG['SUSPICIOUS_INJECTION_TRANSACTION'])

        # ── Severity ─────────────────────────────────────────────────
        flags    = list(dict.fromkeys(flags))
        messages = list(dict.fromkeys(messages))
        severity = max((FLAG_SEV.get(f, 1) for f in flags), default=0)

        return {
            'ten_thuoc':   ten,
            'so_luong':    int(sl),
            'don_vi_tinh': dvt,
            'don_gia':     don_gia,
            'thanh_tien':  thanh,
            'price_ref':   price_ref,
            'form_type':   form_type,
            'flags':       flags,
            'messages':    messages,
            'severity':    severity,
            'match_score': match.get('match_score', 0),
            'match_type':  match.get('match_type', 'none'),
            'details':     details,
        }

    def check_invoice(self, invoice: dict, match_results: list) -> dict:
        """
        invoice       : dict từ OCR (ten_nha_thuoc, ngay_lap, tong_tien, chi_tiet_thuoc)
        match_results : list từ DrugMatcher.match_batch()
        """
        chi_tiet  = invoice.get('chi_tiet_thuoc', [])
        tong_tien = float(invoice.get('tong_tien', 0) or 0)

        items = [
            self.check_item(item, match)
            for item, match in zip(chi_tiet, match_results)
        ]

        # Total mismatch
        computed  = sum(it.get('thanh_tien', 0) for it in chi_tiet)
        mismatch  = False
        inv_flags = []
        if tong_tien > 0 and computed > 0:
            diff = abs(tong_tien - computed) / max(tong_tien, computed)
            if diff > 0.01:
                mismatch = True
                inv_flags.append('TOTAL_MISMATCH')

        all_flags     = inv_flags + [f for it in items for f in it['flags']]
        inv_severity  = max((FLAG_SEV.get(f, 1) for f in all_flags), default=0)

        n_ok   = sum(1 for it in items if it['severity'] == 0)
        n_warn = sum(1 for it in items if it['severity'] == 1)
        n_anom = sum(1 for it in items if it['severity'] >= 2)

        return {
            'ten_nha_thuoc':   invoice.get('ten_nha_thuoc', ''),
            'so_hoa_don':      invoice.get('so_hoa_don', ''),
            'ngay_lap':        invoice.get('ngay_lap', ''),
            'tong_tien':       tong_tien,
            'computed_total':  round(computed, 2),
            'total_mismatch':  mismatch,
            'invoice_flags':   inv_flags,
            'invoice_severity': inv_severity,
            'items':           items,
            'summary': {
                'total':   len(items),
                'ok':      n_ok,
                'warning': n_warn,
                'anomaly': n_anom,
            },
        }