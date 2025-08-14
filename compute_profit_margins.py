import argparse, os, re, sys
import pandas as pd

# ============== utils ==============
def read_csv(path):
    for enc in ("utf-8-sig","cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path, encoding_errors="ignore", engine="python")

def to_number(x):
    if pd.isna(x): return pd.NA
    s = str(x).strip()
    if s in {"","-","nan","none","null"}: return pd.NA
    neg = s.startswith("(") and s.endswith(")")
    if neg: s = s[1:-1]
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-+]", "", s)
    if s in {"","-","+",".","-.","+."}: return pd.NA
    try:
        v = float(s)
        return -v if neg else v
    except:
        return pd.NA

def norm(s: str) -> str:
    s = re.sub(r"[()\[\]{}]", "", str(s))
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[·,./\\\-_%:;|']", "", s)
    return s.lower()

# 항상 스칼라만 반환하도록 보정
def cell(row: pd.Series, col_label):
    try:
        v = row.loc[col_label]
    except KeyError:
        return pd.NA
    # 중복 컬럼이면 Series가 나올 수 있음 → 첫 번째 비결측 또는 첫 번째 값 선택
    if isinstance(v, pd.Series):
        v2 = v[v.notna()]
        return v2.iloc[0] if not v2.empty else v.iloc[0]
    return v

# ============== period column detection ==============
RE_RANGE = re.compile(r"(?P<start>\d{8})\s*[-~]\s*(?P<end>\d{8})", re.I)

def stringify_col(col):
    if isinstance(col, tuple):
        try:
            return " | ".join(str(x) for x in col)
        except:
            return str(col)
    return str(col)

def detect_period_columns(columns):
    """
    인식 예:
      ('20240101-20241231', ('연결재무제표',))
      "20240101-20241231_연결재무제표"
      (20240101~20241231, Consolidated ...)
      실제 MultiIndex 튜플 등
    """
    out = []
    for c in columns:
        s = stringify_col(c)
        m = RE_RANGE.search(s)
        if not m:
            continue
        start, end = m.group("start"), m.group("end")
        low = s.lower()
        fs = ""
        if "연결" in s or "consolidated" in low:
            fs = "연결"
        elif "별도" in s or "separate" in low:
            fs = "별도"
        out.append((c, start, end, fs))
    return out

def find_concept_and_label_cols(df):
    concept_id_col, label_col = None, None
    for c in df.columns:
        lc = norm(c)
        if concept_id_col is None and ("conceptid" in lc or lc.endswith("conceptid") or lc.endswith("concept_id")):
            concept_id_col = c
        if label_col is None and ("labelko" in lc or lc.endswith("labelko") or lc.endswith("label_ko") or "label" in lc):
            label_col = c
    return concept_id_col, label_col

# ============== pickers ==============
def pick_row_exact_name(df, label_col, names_exact):
    if not label_col:
        return None
    nlabel = df[label_col].astype(str).map(norm)
    mask = nlabel.isin([norm(x) for x in names_exact])  # 정확일치만
    cand = df[mask]
    if cand.empty: return None
    return cand.iloc[0]

def pick_row_by_id(df, concept_id_col, id_list):
    if not concept_id_col:
        return None
    nid = df[concept_id_col].astype(str).map(norm)
    mask = nid.apply(lambda s: any(k in s for k in id_list))
    cand = df[mask]
    if cand.empty: return None
    return cand.iloc[0]

def pct(n, d):
    try:
        if pd.isna(n) or pd.isna(d) or float(d) == 0.0: return pd.NA
        return round(float(n)/float(d)*100.0, 2)
    except:
        return pd.NA

# ============== concepts / names ==============
# 총수익(명시적) 이름 정확일치만 허용
TOTAL_REV_NAMES = ["영업수익", "총수익", "영업수익합계", "총수익합계", "총영업수익"]
TOTAL_REV_IDS   = ["ifrs-full_operatingrevenue","operatingrevenue","ifrs-full_revenue","ifrs_revenue","salesrevenue"]

# 총수익 대체 구성(그로스)
INTEREST_INCOME_IDS = [
    "ifrs-full_revenuefrominterest",
    "ifrs-full_interestrevenuecalculatedusingeffectiveinterestmethod",
    "dart_interestrevenueonfinancialassetsatfairvaluethroughprofitorloss",
]
FEE_INCOME_IDS       = ["ifrs-full_feeandcommissionincome"]
INSURANCE_INCOME_IDS = ["ifrs-full_insurancerevenue"]
INTEREST_INCOME_NAME = ["이자수익"]
FEE_INCOME_NAME      = ["수수료수익"]
INSURANCE_INCOME_NAME= ["보험수익"]

OP_PROFIT_IDS  = ["ifrs-full_profitlossfromoperatingactivities","profitlossfromoperatingactivities"]
OP_PROFIT_NAME = ["영업이익"]

NI_OWNER_IDS   = ["ifrs-full_profitlossattributabletoownersofparent"]
NI_OWNER_NAME  = ["지배기업주주지분순이익","지배기업소유주지분순이익"]
NI_TOTAL_IDS   = ["ifrs-full_profitloss","ifrs_profitloss","profitloss"]
NI_TOTAL_NAME  = ["당기순이익","분기순이익"]

# ============== core ==============
def compute(path, net_kind="owner"):
    df = read_csv(path)

    # 기간 컬럼
    pcols = detect_period_columns(df.columns)
    if not pcols:
        # 숫자열 폴백
        num_cols = [c for c in df.columns
                    if pd.api.types.is_numeric_dtype(df[c]) or df[c].apply(lambda v: to_number(v) is not pd.NA).any()]
        if not num_cols:
            raise RuntimeError("기간/재무제표 열을 찾지 못했습니다.")
        pcols = [(c, "", str(c), "") for c in num_cols]

    # 숫자화
    for col, *_ in pcols:
        df[col] = df[col].apply(to_number)

    concept_id_col, label_col = find_concept_and_label_cols(df)
    if concept_id_col is None and label_col is None:
        raise RuntimeError("concept_id/label 열을 찾지 못했습니다.")

    # 영업이익
    op_row = pick_row_by_id(df, concept_id_col, OP_PROFIT_IDS) or pick_row_exact_name(df, label_col, OP_PROFIT_NAME)

    # 순이익 기준
    if net_kind == "owner":
        ni_row = pick_row_by_id(df, concept_id_col, NI_OWNER_IDS) or pick_row_exact_name(df, label_col, NI_OWNER_NAME)
        ni_kind = "owner"
        if ni_row is None:
            ni_row = pick_row_by_id(df, concept_id_col, NI_TOTAL_IDS) or pick_row_exact_name(df, label_col, NI_TOTAL_NAME)
            ni_kind = "total(fallback)"
    else:
        ni_row = pick_row_by_id(df, concept_id_col, NI_TOTAL_IDS) or pick_row_exact_name(df, label_col, NI_TOTAL_NAME)
        ni_kind = "total"
        if ni_row is None:
            ni_row = pick_row_by_id(df, concept_id_col, NI_OWNER_IDS) or pick_row_exact_name(df, label_col, NI_OWNER_NAME)
            ni_kind = "owner(fallback)"

    # 총수익(명시적) → 없으면 대체합
    total_rev_row = pick_row_exact_name(df, label_col, TOTAL_REV_NAMES) \
                    or pick_row_by_id(df, concept_id_col, TOTAL_REV_IDS)

    # 대체 구성요소
    interest_row = pick_row_by_id(df, concept_id_col, INTEREST_INCOME_IDS) or pick_row_exact_name(df, label_col, INTEREST_INCOME_NAME)
    fee_row      = pick_row_by_id(df, concept_id_col, FEE_INCOME_IDS)      or pick_row_exact_name(df, label_col, FEE_INCOME_NAME)
    ins_row      = pick_row_by_id(df, concept_id_col, INSURANCE_INCOME_IDS)or pick_row_exact_name(df, label_col, INSURANCE_INCOME_NAME)

    rows = []
    for col, start, end, fs in pcols:
        # 분모
        denom = pd.NA
        denom_method = "interest+fee+insurance"
        if total_rev_row is not None:
            v = cell(total_rev_row, col)
            if pd.notna(v):
                denom = v
                denom_method = "explicit_total_revenue"
        if pd.isna(denom):
            parts = []
            for r in (interest_row, fee_row, ins_row):
                parts.append(cell(r, col) if r is not None else pd.NA)
            vals = [float(x) for x in parts if pd.notna(x)]
            if vals:
                denom = sum(vals)

        op = cell(op_row, col) if op_row is not None else pd.NA
        ni = cell(ni_row, col) if ni_row is not None else pd.NA

        rows.append(dict(
            period_end=end or str(col),
            fs_type=fs,
            total_revenue=denom,
            operating_profit=op,
            net_income=ni,
            operating_margin_pct=pct(op, denom),
            net_margin_pct=pct(ni, denom),
            denominator_method=denom_method,
            net_basis=ni_kind
        ))

    out = pd.DataFrame(rows).sort_values("period_end", ascending=False).reset_index(drop=True)
    return out

# ============== cli ==============
def main():
    ap = argparse.ArgumentParser(description="KB금융 CSV에서 분모=총수익으로 영업/순이익률 계산(중복 컬럼 안전)")
    ap.add_argument("--path", required=True, help="CSV 경로")
    ap.add_argument("--net", choices=["owner","total"], default="owner",
                    help="순이익 기준: owner=지배주주, total=전체 당기순이익")
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        print(f"[ERROR] 파일 없음: {args.path}", file=sys.stderr); sys.exit(1)

    try:
        result = compute(args.path, net_kind=args.net)
    except Exception as e:
        print(f"[ERROR] 계산 실패: {e}", file=sys.stderr); sys.exit(2)

    root, ext = os.path.splitext(args.path)
    out_path = root + "_profitability_by_period.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    print("=== 기간별 수익성 (분모=총수익) ===")
    print(result[["period_end","operating_margin_pct","net_margin_pct","denominator_method","net_basis"]].to_string(index=False))
    print(f"\n저장 완료: {out_path}")

if __name__ == "__main__":
    main()