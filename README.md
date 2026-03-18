# Pharma Anomaly Detection — Backend FastAPI

## Cấu trúc project

```
pharma_backend/
│
├── backend/
│   ├── main.py          ← FastAPI server — CHẠY FILE NÀY
│   ├── pipeline.py      ← Ghép toàn bộ: OCR → match → rule → ML
│   ├── ocr_module.py    ← Wrap Tesseract OCR
│   ├── drug_matcher.py  ← Fuzzy match tên thuốc → drug master
│   ├── rule_engine.py   ← 15 rules từ PHARMACEUTICAL_RULE.docx
│   └── model_loader.py  ← Load .pkl và predict
│
├── model/
│   ├── isolation_forest.pkl  ← Copy từ Colab sau khi train
│   └── scaler.pkl            ← Copy từ Colab sau khi train
│
├── data/
│   └── drug_master.csv  ← Copy demo2_drug_master_with_norm.csv vào đây
│
├── frontend/
│   └── index.html       ← Giao diện nhóm
│
└── requirements.txt
```

---

## Setup lần đầu (làm 1 lần)

### Bước 1 — Cài thư viện
```bash
pip install -r requirements.txt
```

### Bước 2 — Chuẩn bị data và model
```bash
# Copy drug master
cp demo2_drug_master_with_norm.csv data/drug_master.csv

# Sau khi train xong trên Colab, copy model về
cp isolation_forest.pkl model/
cp scaler.pkl           model/
```

### Bước 3 — Sửa đường dẫn Tesseract (Windows)
Mở `backend/ocr_module.py`, đổi dòng:
```python
TESSERACT_PATH = r"C:\Users\nguye\AppData\Local\..."
# → đổi thành đúng đường dẫn máy bạn
```

---

## Chạy server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Server chạy tại: http://localhost:8000
Docs API:        http://localhost:8000/docs

---

## Test API

### Test bằng Swagger UI
Mở http://localhost:8000/docs → thử POST /detect upload ảnh hóa đơn

### Test bằng curl
```bash
# Upload ảnh
curl -X POST http://localhost:8000/detect \
  -F "file=@hoadon_HD-000012.jpg"

# Gửi JSON
curl -X POST http://localhost:8000/detect/json \
  -H "Content-Type: application/json" \
  -d '{
    "ten_nha_thuoc": "An Khang",
    "tong_tien": 1875100,
    "chi_tiet_thuoc": [
      {"ten_thuoc": "Scandonest 3% Plain", "so_luong": 12,
       "don_vi_tinh": "ống", "don_gia": 17100, "thanh_tien": 205200}
    ]
  }'
```

---

## Cấu trúc JSON output

```json
{
  "ten_nha_thuoc": "AN KHANG",
  "tong_tien": 1875100,
  "invoice_severity": 2,
  "total_mismatch": false,
  "summary": {"total": 5, "ok": 2, "warning": 1, "anomaly": 2},
  "items": [
    {
      "ten_thuoc": "Scandonest 3% Plain",
      "so_luong": 12,
      "don_gia": 17100,
      "price_ref": 17100,
      "severity": 2,
      "flags": ["UNUSUAL_HIGH_QTY_SMALL_INJECTION"],
      "messages": ["Số lượng lọ/ống bất thường (>5)"],
      "is_anomaly_ml": true,
      "anomaly_score": 0.623
    }
  ]
}
```

---

## Frontend gọi API

```javascript
// Upload ảnh
const formData = new FormData();
formData.append("file", imageFile);

fetch("http://localhost:8000/detect", {
    method: "POST",
    body: formData
})
.then(r => r.json())
.then(data => {
    data.items.forEach(item => {
        // severity 0 → xanh, 1 → vàng, 2 → cam, 3 → đỏ
        const color = ['green','yellow','orange','red'][item.severity] || 'green';
    });
});
```
