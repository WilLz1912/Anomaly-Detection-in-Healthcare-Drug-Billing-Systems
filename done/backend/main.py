"""
Chạy:
  cd "F:\Kì 4\DAP391m\Project\build\REAL BUILD\backend"
python -m uvicorn main:app --reload --port 8000
"""

import os
import sys  
import traceback

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

# Thêm thư mục backend vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model_loader
from pipeline import run_pipeline, run_pipeline_json

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = FastAPI(
    title="Pharma Anomaly Detection API",
    description="Phát hiện bất thường hóa đơn thuốc — Rule-based + Isolation Forest",
    version="1.0.0"
)

# CORS — cho phép frontend gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Production: đổi thành domain cụ thể
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

from fastapi.staticfiles import StaticFiles

# Mount static — serve style.css, script.js, logo.png
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# ─────────────────────────────────────────────
# Startup: load model
# ─────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    print("🚀 Khởi động Pharma Anomaly API...")
    try:
        model_loader.load_model()
    except FileNotFoundError as e:
        print(f"⚠ {e}")
        print("  Server vẫn chạy nhưng ML predict bị tắt.")
        print("  Rule-based vẫn hoạt động bình thường.")


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class InvoiceItem(BaseModel):
    ten_thuoc:    str
    so_luong:     int
    don_vi_tinh:  str
    don_gia:      float
    thanh_tien:   float

class InvoiceJSON(BaseModel):
    ten_nha_thuoc:    Optional[str] = "Không xác định"
    so_hoa_don:       Optional[str] = ""
    ngay_lap:         Optional[str] = ""
    tong_tien:        Optional[float] = 0
    chi_tiet_thuoc:   list[InvoiceItem]


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "Pharma Anomaly Detection API đang chạy",
        "docs":    "http://localhost:8000/docs",
        "endpoints": {
            "POST /detect":      "Upload ảnh hóa đơn → phân tích",
            "POST /detect/json": "Gửi JSON hóa đơn → phân tích",
            "GET  /health":      "Kiểm tra trạng thái",
        }
    }


@app.get("/health")
def health():
    return {
        "status":              "ok",
        "ml_model_loaded":     model_loader._model is not None,
        "scaler_loaded":       model_loader._scaler is not None,
    }


@app.post("/detect")
async def detect_image(file: UploadFile = File(...)):
    """
    Upload ảnh hóa đơn (JPG/PNG) → OCR → Rule + ML → kết quả màu xanh/đỏ/vàng
    """
    # Validate file type
    if file.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(
            status_code=400,
            detail=f"File không hợp lệ: {file.content_type}. Chỉ nhận JPG/PNG."
        )

    try:
        image_bytes = await file.read()
        result = run_pipeline(image_bytes)
        return result

    except RuntimeError as e:
        # Tesseract chưa cài
        raise HTTPException(status_code=503, detail=str(e))

    except ValueError as e:
        # OCR không parse được
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@app.post("/detect/json")
async def detect_json(invoice: InvoiceJSON):
    """
    Gửi JSON hóa đơn trực tiếp (dùng để test không cần ảnh)
    """
    try:
        invoice_dict = {
            'ten_nha_thuoc':   invoice.ten_nha_thuoc,
            'so_hoa_don':      invoice.so_hoa_don,
            'ngay_lap':        invoice.ngay_lap,
            'tong_tien':       invoice.tong_tien,
            'chi_tiet_thuoc': [
                {
                    'ten_thuoc':   it.ten_thuoc,
                    'so_luong':    it.so_luong,
                    'don_vi_tinh': it.don_vi_tinh,
                    'don_gia':     it.don_gia,
                    'thanh_tien':  it.thanh_tien,
                }
                for it in invoice.chi_tiet_thuoc
            ]
        }
        result = run_pipeline_json(invoice_dict)
        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


# ─────────────────────────────────────────────
# Serve frontend index.html
# ─────────────────────────────────────────────

@app.get("/app")
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend chưa có. Copy index.html vào thư mục frontend/"}


# ─────────────────────────────────────────────
# Chạy trực tiếp
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
