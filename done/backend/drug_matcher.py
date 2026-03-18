"""
drug_matcher.py
---------------
Match tên thuốc từ OCR vào drug master CSV để lấy price_ref,
dangBaoChe, loaiGia, key_quality cho rule engine + ML model.

Thứ tự match:
  1. Exact match (tenThuoc_norm)
  2. Fuzzy match tên thuốc  (threshold 82)
  3. Fuzzy match hoạt chất  (threshold 75, fallback)
  4. Không match → price_ref = None, flag LOW_CONFIDENCE
"""

import re
import unicodedata
import pandas as pd
from rapidfuzz import process, fuzz


# ─────────────────────────────────────────────
# Text normalization
# ─────────────────────────────────────────────

def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower().strip()
    text = _remove_accents(text)
    text = re.sub(r"[®™©°•]", "", text)
    text = re.sub(r"[^\w\s,./%-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────
# DrugMatcher
# ─────────────────────────────────────────────

class DrugMatcher:
    FUZZY_NAME_THRESHOLD   = 82
    FUZZY_ACTIVE_THRESHOLD = 75

    def __init__(self, csv_path: str):
        self.df = self._load(csv_path)
        self._name_list   = self.df["tenThuoc_norm"].tolist()
        self._active_list = self.df["hoatChat_norm"].fillna("").tolist()

    def _load(self, path: str) -> pd.DataFrame:
        df = pd.read_csv(path, low_memory=False)
        if "tenThuoc_norm" not in df.columns:
            df["tenThuoc_norm"] = df["tenThuoc"].apply(normalize)
        if "hoatChat_norm" not in df.columns:
            df["hoatChat_norm"] = df["hoatChat"].apply(normalize)
        df["is_import"] = df["loaiGia"].str.contains("nhập khẩu", case=False, na=False)
        return df

    def _row_to_result(self, row: pd.Series, score: float, match_type: str) -> dict:
        return {
            "matched":          True,
            "tenThuoc_master":  row["tenThuoc"],
            "hoatChat_master":  row.get("hoatChat", ""),
            "dangBaoChe":       row.get("dangBaoChe", ""),
            "donViTinh_master": row.get("donViTinh", ""),
            "quyCachDongGoi":   row.get("quyCachDongGoi", ""),
            "price_ref":        float(row["price_ref"]) if pd.notna(row.get("price_ref")) else None,
            "loaiGia":          row.get("loaiGia", ""),
            "is_import":        bool(row.get("is_import", False)),
            "key_quality":      int(row.get("key_quality", 1)),
            "match_score":      round(score, 1),
            "match_type":       match_type,
        }

    def _no_match(self, ten_thuoc: str) -> dict:
        return {
            "matched":          False,
            "tenThuoc_master":  ten_thuoc,
            "dangBaoChe":       "",
            "price_ref":        None,
            "is_import":        False,
            "key_quality":      0,
            "match_score":      0,
            "match_type":       "none",
        }

    def match(self, ten_thuoc: str, hoat_chat: str = "") -> dict:
        q_name   = normalize(ten_thuoc)
        q_active = normalize(hoat_chat)

        # 1. Exact
        mask = self.df["tenThuoc_norm"] == q_name
        if mask.any():
            return self._row_to_result(self.df[mask].iloc[0], 100.0, "exact")

        # 2. Fuzzy tên
        if q_name:
            hit = process.extractOne(
                q_name, self._name_list,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=self.FUZZY_NAME_THRESHOLD
            )
            if hit:
                _, score, idx = hit
                return self._row_to_result(self.df.iloc[idx], score, "fuzzy_name")

        # 3. Fuzzy hoạt chất
        if q_active:
            hit = process.extractOne(
                q_active, self._active_list,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=self.FUZZY_ACTIVE_THRESHOLD
            )
            if hit:
                _, score, idx = hit
                return self._row_to_result(self.df.iloc[idx], score, "fuzzy_active")

        return self._no_match(ten_thuoc)

    def match_batch(self, items: list) -> list:
        """items: list of dict có key 'ten_thuoc' (và tùy chọn 'hoat_chat')"""
        return [
            self.match(
                it.get("ten_thuoc", "") or it.get("tenThuoc", ""),
                it.get("hoat_chat", "") or it.get("hoatChat", "")
            )
            for it in items
        ]
