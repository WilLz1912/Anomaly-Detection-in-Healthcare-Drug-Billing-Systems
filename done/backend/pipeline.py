"""
pipeline.py
-----------
Ghép toàn bộ: OCR → drug_match → rule_check → ML predict

Hàm duy nhất cần gọi từ FastAPI:
    result = run_pipeline(image_bytes)
    result = run_pipeline_json(invoice_dict)  # nếu đã có JSON
"""

import os
import sys

# Thêm thư mục backend vào path khi chạy trực tiếp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr_module  import ocr_from_bytes
from drug_matcher import DrugMatcher
from rule_engine  import RuleEngine
from model_loader import predict_item

# ── Singleton resources (load 1 lần) ──
_matcher     = None
_rule_engine = RuleEngine()

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DRUG_MASTER_PATH = r"F:\Kì 4\DAP391m\Project\build\REAL BUILD\demo2_drug_master_with_norm.csv"


def _get_matcher() -> DrugMatcher:
    global _matcher
    if _matcher is None:
        if not os.path.exists(DRUG_MASTER_PATH):
            print(f"⚠ Drug master không tìm thấy: {DRUG_MASTER_PATH}")
            print("  → Drug matching bị bỏ qua, price_ref sẽ = 0")
            return None
        _matcher = DrugMatcher(DRUG_MASTER_PATH)
        print(f"✅ Drug master loaded: {DRUG_MASTER_PATH}")
    return _matcher


def _empty_match(ten_thuoc: str) -> dict:
    return {
        'matched': False, 'tenThuoc_master': ten_thuoc,
        'dangBaoChe': '', 'price_ref': None,
        'is_import': False, 'key_quality': 0,
        'match_score': 0, 'match_type': 'none',
    }


# ─────────────────────────────────────────────
# Core pipeline logic
# ─────────────────────────────────────────────

def _process_invoice(invoice: dict) -> dict:
    """
    Nhận dict invoice (từ OCR hoặc JSON trực tiếp)
    → Trả về dict kết quả phân tích đầy đủ.
    """
    chi_tiet  = invoice.get('chi_tiet_thuoc', [])
    tong_tien = float(invoice.get('tong_tien', 0) or 0)

    # ── Step 1: Drug matching ──────────────────────────────────────
    matcher = _get_matcher()
    if matcher:
        match_results = matcher.match_batch(chi_tiet)
    else:
        match_results = [_empty_match(it.get('ten_thuoc', '')) for it in chi_tiet]

    # ── Step 2: Rule engine ────────────────────────────────────────
    invoice_result = _rule_engine.check_invoice(invoice, match_results)

    # ── Step 3: ML predict per item ───────────────────────────────
    for item_res in invoice_result['items']:
        ml = predict_item(item_res, tong_tien)
        item_res['is_anomaly_ml'] = ml['is_anomaly_ml']
        item_res['anomaly_score'] = ml['anomaly_score']

        # Hybrid: nếu ML nói anomaly nhưng rule chưa flag → thêm warning
        if ml['is_anomaly_ml'] and not item_res['flags']:
            item_res['flags'].append('ML_ANOMALY')
            item_res['messages'].append(
                f"ML phát hiện bất thường (score={ml['anomaly_score']:.2f})"
            )
            item_res['severity'] = max(item_res['severity'], 1)

    # Cập nhật invoice_severity sau khi có ML
    all_flags = invoice_result['invoice_flags'][:]
    for it in invoice_result['items']:
        all_flags.extend(it['flags'])

    from rule_engine import FLAG_SEV
    invoice_result['invoice_severity'] = max(
        (FLAG_SEV.get(f, 1) for f in all_flags), default=0
    )

    return invoice_result


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run_pipeline(image_bytes: bytes) -> dict:
    """
    Input : bytes ảnh hóa đơn (từ FastAPI UploadFile.read())
    Output: dict kết quả phân tích

    Raises:
        RuntimeError: Tesseract chưa cài
        ValueError:   OCR không parse được dòng thuốc nào
    """
    # Step 0: OCR
    invoice = ocr_from_bytes(image_bytes)

    if not invoice.get('chi_tiet_thuoc'):
        raise ValueError(
            "OCR không parse được dòng thuốc nào. "
            "Kiểm tra chất lượng ảnh hoặc định dạng hóa đơn."
        )

    return _process_invoice(invoice)


def run_pipeline_json(invoice_dict: dict) -> dict:
    """
    Input : dict hóa đơn JSON (dùng để test không cần ảnh)
    Output: dict kết quả phân tích

    Format JSON input:
    {
        "ten_nha_thuoc": "An Khang",
        "ngay_lap": "18/09/2025",
        "tong_tien": 1875100,
        "chi_tiet_thuoc": [
            {
                "ten_thuoc": "Scandonest 3% Plain",
                "so_luong": 12,
                "don_vi_tinh": "ống",
                "don_gia": 17100,
                "thanh_tien": 205200
            }
        ]
    }
    """
    return _process_invoice(invoice_dict)
