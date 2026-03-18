"""
ocr_module.py
-------------
Nhận image bytes → trả về dict hóa đơn chuẩn cho pipeline.
Tái sử dụng logic từ ocr.py gốc của nhóm, chỉ bọc lại thành function.
"""

import re
import io
import unicodedata
from datetime import datetime
from PIL import Image

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# ── Đường dẫn Tesseract (Windows) ──
# Đổi thành đường dẫn máy bạn nếu khác
TESSERACT_PATH = r"C:\Users\nguye\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _fix_vietnamese(text: str) -> str:
    """Sửa lỗi OCR tiếng Việt phổ biến (giữ nguyên từ ocr.py gốc)."""
    if not text:
        return text
    fixes = {
        'BỆNH VIÊN': 'BỆNH VIỆN',
        'H0Á': 'HÓA',
        'th0ại': 'thoại',
        'Gày': 'Ngày',
    }
    for wrong, correct in fixes.items():
        text = text.replace(wrong, correct)
    return text


def _run_tesseract(img: Image.Image) -> str:
    """Thử nhiều config PSM, lấy kết quả dài nhất."""
    import pytesseract as pyt
    import os

    if os.path.exists(TESSERACT_PATH):
        pyt.pytesseract.tesseract_cmd = TESSERACT_PATH

    configs = ['--psm 6 --oem 3', '--psm 11 --oem 3', '--psm 3 --oem 3']
    best = ""
    for cfg in configs:
        try:
            t = pyt.image_to_string(img, lang='vie', config=cfg)
            if len(t.split()) > len(best.split()):
                best = t
        except Exception:
            continue

    if not best:
        best = pyt.image_to_string(img, lang='vie')

    return _fix_vietnamese(best)


def _to_float(s: str) -> float:
    """'1,520,000' hoặc '1.520.000' → 1520000.0"""
    return float(re.sub(r'[,\.](?=\d{3})', '', s.replace(',', '')))


# ─────────────────────────────────────────────
# Parse text → structured invoice
# ─────────────────────────────────────────────

def _parse_invoice_text(text: str) -> dict:
    """
    Parse text thô từ OCR thành dict invoice chuẩn.
    Giữ đúng logic regex từ ocr.py gốc, cải thiện robustness.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # ── Tên nhà thuốc ──
    ten_nha_thuoc = "Không xác định"
    for line in lines[:6]:
        if any(kw in line.upper() for kw in ['NHÀ THUỐC', 'BỆNH VIỆN', 'PHARMACY', 'AN KHANG', 'PHARMACITY']):
            ten_nha_thuoc = line.strip()
            break
    if ten_nha_thuoc == "Không xác định" and lines:
        ten_nha_thuoc = lines[0]  # fallback: dòng đầu tiên

    # ── Số hóa đơn ──
    so_hoa_don = ""
    for line in lines:
        m = re.search(r'(?:Số hóa đơn|HD)[:\s]*([A-Z0-9\-]+)', line, re.IGNORECASE)
        if m:
            so_hoa_don = m.group(1).strip()
            break

    # ── Ngày lập ──
    ngay_lap = datetime.now().strftime("%d/%m/%Y")
    for line in lines:
        m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', line)
        if m:
            ngay_lap = m.group(1)
            break

    # ── Tổng tiền ──
    tong_tien = 0.0
    for line in lines:
        if re.search(r'T[ổÔ]NG\s*C[ộÔ]NG|TONG\s*CONG', line, re.IGNORECASE):
            nums = re.findall(r'[\d\.,]+', line)
            for n in reversed(nums):
                clean = re.sub(r'[,\.](?=\d{3})', '', n).replace(',', '')
                if clean.isdigit() and int(clean) > 1000:
                    tong_tien = float(clean)
                    break
            break

    # ── Bảng thuốc ──
    chi_tiet = []
    in_table = False

    for line in lines:
        # Detect header
        if re.search(r'Tên\s+thu[oố]c|Ten\s+thuoc|Số\s+lượng|So\s+luong', line, re.IGNORECASE):
            in_table = True
            continue

        # Kết thúc bảng
        if in_table and re.search(r'T[ổÔ]NG\s*C[ộÔ]NG|TONG\s*CONG', line, re.IGNORECASE):
            in_table = False
            continue

        if not in_table:
            continue

        # Pattern: <Tên thuốc>  <SL>  <ĐVT>  <Đơn giá>  <Thành tiền>
        m = re.match(
            r'^(.+?)\s+'           # tên thuốc
            r'(\d+)\s+'            # số lượng
            r'([^\d\s]{1,15})\s+'  # đơn vị tính
            r'([\d\.,]+)\s+'       # đơn giá
            r'([\d\.,]+)\s*$',     # thành tiền
            line
        )
        if m:
            try:
                chi_tiet.append({
                    'ten_thuoc':    m.group(1).strip(),
                    'so_luong':     int(m.group(2)),
                    'don_vi_tinh':  m.group(3).strip(),
                    'don_gia':      _to_float(m.group(4)),
                    'thanh_tien':   _to_float(m.group(5)),
                })
            except ValueError:
                continue

    return {
        'ten_nha_thuoc': ten_nha_thuoc,
        'so_hoa_don':    so_hoa_don,
        'ngay_lap':      ngay_lap,
        'tong_tien':     tong_tien,
        'chi_tiet_thuoc': chi_tiet,
    }


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def ocr_from_bytes(image_bytes: bytes) -> dict:
    """
    Nhận bytes ảnh từ FastAPI UploadFile.read()
    → Trả về dict invoice chuẩn.

    Raises:
        RuntimeError: nếu pytesseract chưa cài
        ValueError: nếu không parse được dòng thuốc nào
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError(
            "pytesseract chưa cài. Chạy: pip install pytesseract\n"
            "Và cài Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki"
        )

    img = Image.open(io.BytesIO(image_bytes))
    raw_text = _run_tesseract(img)
    invoice  = _parse_invoice_text(raw_text)

    return invoice


def ocr_from_path(image_path: str) -> dict:
    """Tiện ích test local — đọc file ảnh từ đường dẫn."""
    with open(image_path, 'rb') as f:
        return ocr_from_bytes(f.read())
