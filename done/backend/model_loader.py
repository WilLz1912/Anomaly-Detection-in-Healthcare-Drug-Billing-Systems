"""
model_loader.py
---------------
Load isolation_forest.pkl + scaler.pkl đã train.
Cung cấp hàm predict_item() dùng trong pipeline.
"""

import os
import pickle
import numpy as np

# ── Đường dẫn mặc định (tính từ thư mục backend) ──
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = r"F:\Kì 4\DAP391m\Project\build\REAL BUILD\model\isolation_forest.pkl"
SCALER_PATH = r"F:\Kì 4\DAP391m\Project\build\REAL BUILD\model\scaler.pkl"

# ── Features theo đúng thứ tự khi train ──
# PHẢI khớp với FEATURES trong train_anomaly_model.ipynb
FEATURES = [
    'price_ratio',
    'log_donGia',
    'log_thanh',
    'log_soLuong',
    'soLuong',
    'key_quality',
    'is_injection',
    'is_tablet',
    'is_syrup',
    'is_import',
    'date_missing',
]

_model  = None
_scaler = None


def load_model():
    """Load model + scaler vào memory. Gọi 1 lần khi khởi động FastAPI."""
    global _model, _scaler

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy model: {MODEL_PATH}\n"
            "Hãy train model trước: chạy train_anomaly_model.ipynb trên Colab\n"
            "rồi copy isolation_forest.pkl + scaler.pkl vào thư mục model/"
        )
    if not os.path.exists(SCALER_PATH):
        raise FileNotFoundError(f"Không tìm thấy scaler: {SCALER_PATH}")

    with open(MODEL_PATH,  'rb') as f: _model  = pickle.load(f)
    with open(SCALER_PATH, 'rb') as f: _scaler = pickle.load(f)
    print(f"✅ Model loaded: {MODEL_PATH}")
    print(f"✅ Scaler loaded: {SCALER_PATH}")


def _build_feature_vector(item_result: dict, tong_tien: float) -> list:
    """
    Chuyển item_result (output rule_engine) thành vector features.
    Đúng thứ tự với FEATURES list.
    """
    import math, re

    don_gia   = float(item_result.get('don_gia',    0) or 0)
    thanh     = float(item_result.get('thanh_tien', 0) or 0)
    so_luong  = float(item_result.get('so_luong',   0) or 0)
    price_ref = float(item_result.get('price_ref',  0) or 0)
    form_type = item_result.get('form_type', 'other')
    key_q     = int(item_result.get('key_quality', 3) or 3)

    # Lấy thêm từ match result nếu cần
    is_import   = int(item_result.get('is_import', False))
    date_missing = 0   # không có từ hóa đơn mới → mặc định 0

    price_ratio = (don_gia / price_ref) if price_ref > 0 else 1.0
    price_ratio = min(price_ratio, 10.0)  # clip

    return [
        price_ratio,
        math.log1p(don_gia),
        math.log1p(thanh),
        math.log1p(so_luong),
        so_luong,
        key_q,
        int(form_type == 'injection'),
        int(form_type == 'tablet'),
        int(form_type == 'syrup'),
        is_import,
        date_missing,
    ]


def predict_item(item_result: dict, tong_tien: float = 0) -> dict:
    """
    Nhận item_result từ rule_engine.check_item()
    → Trả về {'is_anomaly_ml': bool, 'anomaly_score': float}

    anomaly_score: 0.0 (bình thường) → 1.0 (rất bất thường)
    """
    if _model is None or _scaler is None:
        # Model chưa load → trả về mặc định, không crash pipeline
        return {'is_anomaly_ml': False, 'anomaly_score': 0.0}

    vec  = _build_feature_vector(item_result, tong_tien)
    X    = np.array([vec])
    X_s  = _scaler.transform(X)

    pred  = _model.predict(X_s)[0]          # -1=anomaly, 1=normal
    score = float(-_model.decision_function(X_s)[0])

    # Normalize về [0, 1] xấp xỉ
    score_norm = min(1.0, max(0.0, score + 0.5))

    return {
        'is_anomaly_ml': bool(pred == -1),
        'anomaly_score': round(score_norm, 3),
    }
