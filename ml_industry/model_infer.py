# C:\workspace\KUAIF3\ml_industry\model_infer.py
import re
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

MODEL_DIR = Path(r"C:\workspace\KUAIF3\ml_industry\models")

_LABEL_ID_TO_NAME = {
    1: "banking",
    2: "manufacturing",
    0: "other",   # 선택
}
# 신뢰도 임계치
_CONF_TH = 0.60

_VEC = None
_CLF = None

def _load_model():
    global _VEC, _CLF
    if _VEC is None or _CLF is None:
        _VEC = joblib.load(MODEL_DIR / "industry_vectorizer.pkl")
        _CLF = joblib.load(MODEL_DIR / "industry_classifier.pkl")

def _extract_text_for_infer(df: pd.DataFrame, look_rows: int = 150) -> str:
    cols = [df.columns[0]]
    for c in df.columns[1:6]:
        s = str(c).lower()
        if any(k in s for k in ["label", "라벨", "항목", "계정", "name"]):
            cols.append(c)
    cols = list(dict.fromkeys(cols))
    parts = []
    head = min(look_rows, len(df))
    for c in cols:
        parts += df[c].astype(str).head(head).tolist()
    return " | ".join(parts)

def predict_industry_from_df(df: pd.DataFrame):
    """모델 예측 (성공 시: (label_id, label_name, conf), 실패 시 예외 발생)"""
    _load_model()
    text = _extract_text_for_infer(df)
    X = _VEC.transform([text])
    proba = _CLF.predict_proba(X)[0]
    classes = _CLF.classes_
    idx = int(np.argmax(proba))
    label_id = int(classes[idx])
    conf = float(proba[idx])
    label_name = _LABEL_ID_TO_NAME.get(label_id, "other")
    return label_id, label_name, conf

# ---------- 낮은 신뢰도/실패 시 백업: 규칙 기반 ----------
def rule_based_industry(df: pd.DataFrame) -> str:
    text = " ".join(df.iloc[:,0].astype(str).head(120).tolist())
    if re.search(r"RevenueFromInterest|이자수익|InsuranceRevenue|보험수익|FeeAndCommissionIncome|수수료수익", text, re.I):
        return "banking"
    if re.search(r"\bifrs-full_Revenue\b|매출|매출액|GrossProfit|매출총이익|OperatingIncomeLoss|영업이익", text, re.I):
        return "manufacturing"
    return "manufacturing"  # 보수적 기본값

def decide_industry(df: pd.DataFrame):
    """ML 우선, 신뢰도 낮으면 규칙 보완."""
    try:
        lid, lname, conf = predict_industry_from_df(df)
        if conf < _CONF_TH or lname == "other":
            fallback = rule_based_industry(df)
            return lname, conf, f"low_conf_fallback:{fallback}"
        return lname, conf, "ml"
    except Exception as e:
        fb = rule_based_industry(df)
        return fb, 0.0, f"ml_error_fallback:{e}"