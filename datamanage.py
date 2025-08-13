import pandas as pd
import re
import numpy as np

# ----- 컬럼/텍스트 전처리 -----
CLASS_PATTERNS = [r"(?i)\bclass\s*1\b", r"(?i)\bclass\s*2\b", r"(?i)\bclass\s*3\b"]
ALT_NAME_CANDIDATES = ["account_name", "항목", "과목명"]

def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [(" ".join(map(str, c)) if isinstance(c, tuple) else str(c)) for c in out.columns]
    return out

def _find_first_col(df: pd.DataFrame, pattern: str):
    for c in df.columns:
        if re.search(pattern, str(c)):
            return c
    return None

def build_path_text(row: pd.Series, c1, c2, c3) -> str:
    parts = []
    for c in [c1, c2, c3]:
        if c and c in row and str(row[c]).strip() not in ["", "nan", "None"]:
            parts.append(str(row[c]))
    if parts:
        return " > ".join(parts)
    for cand in ALT_NAME_CANDIDATES:
        if cand in row and str(row[cand]).strip():
            return str(row[cand])
    return ""

# ----- 라벨링(룰) -----
REV_KW = r"(수익|이익|환입|매출)"
EXP_KW = r"(비용|손실|전입|충당금|감가상각|손상|상각)"
NET_KW = r"(손익|결과|영업이익|영업손익|포괄손익)"

def rule_label(text: str) -> str:
    s = (text or "").replace(" ", "")
    if not s: return "HEADER"
    if re.search(NET_KW, s): return "NET"
    if re.search(REV_KW, s): return "REVENUE"
    if re.search(EXP_KW, s): return "EXPENSE"
    return "OTHER"

# ----- 값 컬럼 선택: '별도/개별 재무제표' 제외, '연결재무제표' 우선 -----
EXCLUDE_VALUE_COLS_RE = re.compile(r"(?i)(증감|증가|감소|전년|전년도|전기|누계|비율|율|%|단위|notes?|comment|주석|코드|계정|항목)")
CLASS_RE = re.compile(r"(?i)\bclass\s*\d+\b")

def _to_num(x):
    if pd.isna(x): return np.nan
    s = str(x).strip().replace(",", "")
    if re.fullmatch(r"\(.*\)", s):  # (123) -> -123
        s = "-" + s[1:-1]
    try:
        return float(s)
    except:
        return np.nan

def pick_value_cols(df: pd.DataFrame,
                    prefer_col_regex: str = r"연결\s*재무제표",
                    exclude_col_regex: str = r"(별도\s*재무제표|개별\s*재무제표)") -> list:
    candidates = []
    for c in df.columns:
        if CLASS_RE.search(str(c)): continue
        if EXCLUDE_VALUE_COLS_RE.search(str(c)): continue
        if str(c) in ["__name__","pred_label"]: continue
        if exclude_col_regex and re.search(exclude_col_regex, str(c), flags=re.IGNORECASE):
            continue
        ser = df[c].apply(_to_num)
        if ser.notna().mean() > 0.3:  # 값 비율 기준
            candidates.append(c)
    # 연결 우선 정렬
    if prefer_col_regex:
        pref = re.compile(prefer_col_regex, flags=re.IGNORECASE)
        candidates = sorted(candidates, key=lambda x: (0 if pref.search(str(x)) else 1, str(x)))
    return candidates

# ----- 지표 집계(은행) -----
def sum_by_mask(df_vals: pd.DataFrame, mask: pd.Series) -> pd.Series:
    if mask.sum() == 0:
        return pd.Series({c: np.nan for c in df_vals.columns})
    return df_vals.loc[mask].sum(numeric_only=True)

def compute_metrics_bank(df_l: pd.DataFrame, value_cols: list) -> dict:
    D = df_l.copy()
    V = D[value_cols].applymap(_to_num)
    name = D["__name__"].fillna("")

    # 핵심 항목 키워드(확장)
    nii_mask  = D["pred_label"].eq("NET") & name.str.contains(r"(순이자손익|이자손익|이자이익)")
    fee_mask  = D["pred_label"].eq("NET") & name.str.contains(r"(순수수료손익|수수료손익)")
    ins_mask  = D["pred_label"].eq("NET") & name.str.contains(r"(보험서비스결과|보험서비스손익|보험손익)")
    prov_mask = D["pred_label"].eq("EXPENSE") & name.str.contains(r"(대손충당금|신용손실충당금|대손비용|충당금전입)")
    opx_mask  = D["pred_label"].eq("EXPENSE") & name.str.contains(r"(일반관리비|판매관리비|영업비용|영업경비|직원비용|인건비|감가상각비|임차료|마케팅|광고)")
    ni_mask   = D["pred_label"].eq("NET") & name.str.contains(r"(당기순이익|순이익|지배기업.*순이익|연결당기순이익)")

    metrics = {}
    metrics["NetInterestIncome"] = sum_by_mask(V, nii_mask)
    metrics["NetFeeIncome"]      = sum_by_mask(V, fee_mask)
    metrics["InsuranceServiceResult"] = sum_by_mask(V, ins_mask)
    metrics["OtherNonInterestIncome"] = sum_by_mask(
        V,
        (D["pred_label"].isin(["REVENUE","NET"]) &
         name.str.contains(r"(유가증권|파생|외환|금융상품|평가|배당|기타(영업)?수익|기타손익)") &
         ~fee_mask & ~ins_mask & ~nii_mask)
    )
    prov = sum_by_mask(V, prov_mask)
    opex = sum_by_mask(V, opx_mask)
    # 비용은 절댓값으로 정규화
    metrics["ProvisionExpense"]  = prov.abs()
    metrics["OperatingExpense"]  = opex.abs()
    metrics["NetIncome"]         = sum_by_mask(V, ni_mask)

    core_income = (metrics["NetInterestIncome"].fillna(0)
                 + metrics["NetFeeIncome"].fillna(0)
                 + metrics["OtherNonInterestIncome"].fillna(0)
                 + metrics["InsuranceServiceResult"].fillna(0))
    with np.errstate(divide='ignore', invalid='ignore'):
        metrics["CoreIncome"]      = core_income
        metrics["EfficiencyRatio"] = metrics["OperatingExpense"] / core_income.replace(0, np.nan)
        metrics["CreditCostRatio"] = metrics["ProvisionExpense"] / core_income.replace(0, np.nan)
    return metrics

def yoy_growth(series: pd.Series) -> pd.Series:
    return (series - series.shift(-1)) / (series.shift(-1).replace(0, np.nan))

def render_report_bank(metrics: dict, used_cols: list) -> str:
    lines = []
    lines.append("[섹터] bank\n")
    lines.append("[핵심 지표, 최근기간 기준]")
    for k, v in metrics.items():
        val = v.iloc[0] if len(v)>0 else np.nan
        if "Ratio" in k or "Margin" in k:
            lines.append(f"- {k}: {val:.2%}" if pd.notna(val) else f"- {k}: N/A")
        else:
            lines.append(f"- {k}: {val:,.0f}" if pd.notna(val) else f"- {k}: N/A")
    lines.append("\n[참고] 사용된 값 컬럼(왼쪽이 최근): " + " | ".join(map(str, used_cols[:6])))
    lines.append("\n(참고) 본 인사이트는 정보 제공 목적이며 투자 판단의 최종 책임은 투자자 본인에게 있습니다.")
    return "\n".join(lines)

def analyze_income_statement(df: pd.DataFrame,
                             sector: str = "bank",
                             prefer_col_regex: str = r"연결\s*재무제표",
                             exclude_col_regex: str = r"(별도\s*재무제표|개별\s*재무제표)"):
    """
    입력: 손익계산서 DF (head_profit_table 권장)
    출력: (metrics_df, report_text, used_value_cols)
    """
    if df is None or len(df)==0:
        raise ValueError("입력 DataFrame이 비었습니다.")

    D = _normalize_cols(df)
    c1 = _find_first_col(D, CLASS_PATTERNS[0])
    c2 = _find_first_col(D, CLASS_PATTERNS[1])
    c3 = _find_first_col(D, CLASS_PATTERNS[2])

    D["__name__"]   = D.apply(lambda r: build_path_text(r, c1, c2, c3), axis=1)
    D["pred_label"] = D["__name__"].map(rule_label)

    value_cols = pick_value_cols(D, prefer_col_regex=prefer_col_regex, exclude_col_regex=exclude_col_regex)
    if not value_cols:
        raise RuntimeError("숫자 값 컬럼을 찾지 못했습니다. (연결/별도 컬럼명 확인 필요)")

    if sector == "bank":
        metrics = compute_metrics_bank(D, value_cols)
        report  = render_report_bank(metrics, value_cols)
    else:
        # 제조/기타 섹터 로직이 필요하면 확장 가능
        metrics = compute_metrics_bank(D, value_cols)
        report  = render_report_bank(metrics, value_cols)

    metrics_df = pd.DataFrame({k: v for k, v in metrics.items()})
    return metrics_df, report, value_cols

def drop_rows_where_class3_filled(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # 헤더 문자열 안에 'class 3'가 들어간 열 전부 찾기 (대소문자/공백 무시)
    c3_cols = [c for c in out.columns if re.search(r'(?i)\bclass\s*3\b', str(c))]
    if not c3_cols:
        # 어떤 파일은 class3 자체가 없음 → 그대로 반환
        return out

    # "채워짐" 판정: NaN/빈칸/'---'/'...' 등은 비어있다고 간주
    def is_filled_series(s: pd.Series) -> pd.Series:
        s_str = s.astype(str).str.strip()
        return s.notna() & ~(s_str.eq('') | s_str.str.lower().eq('nan') |
                             s_str.str.fullmatch(r'-+') | s_str.str.fullmatch(r'\.+'))

    # 여러 개라면 하나라도 채워져 있으면 drop
    filled_mask = None
    for col in c3_cols:
        cur = is_filled_series(out[col])
        filled_mask = cur if filled_mask is None else (filled_mask | cur)

    return out.loc[~filled_mask].copy()