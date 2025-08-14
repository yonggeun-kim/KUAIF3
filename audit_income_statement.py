# filename: audit_income_statement.py
import argparse, os, re, sys
import pandas as pd

def _read_csv(path):
    for enc in ("utf-8-sig","cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path, encoding_errors="ignore", engine="python")

def _norm(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = re.sub(r"[()\[\]{}]", "", s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[·,./\\\-_%:;|]", "", s)
    return s.lower()

def _to_number(x):
    if pd.isna(x): return pd.NA
    s = str(x).strip()
    if s in {"","-","nan","none","null"}: return pd.NA
    neg = s.startswith("(") and s.endswith(")")
    if neg: s = s[1:-1]
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-+]", "", s)
    if s in {"","-","+",".","-.","+."}: return pd.NA
    try:
        v = float(s) if "." in s else int(s)
        return -v if neg else v
    except: return pd.NA

# 핵심 계정 후보(라벨 + IFRS ID)
DENOM_KO = ["매출액","영업수익","수익","수익합계","총수익","영업수익합계","영업수익(수익)"]
DENOM_ID = ["ifrs-full_revenue","ifrs_revenue","ifrsfull_revenue",
            "ifrs-full_salesrevenue","ifrs_salesrevenue",
            "operatingrevenue","ifrs-full_operatingrevenue","dart_operatingrevenue"]
OP_KO = ["영업이익","영업이익손실","영업손익"]
OP_ID = ["ifrs-full_operatingincomeloss","ifrs_operatingincomeloss",
         "ifrsfull_operatingincomeloss","profitlossfromoperatingactivities"]
NET_KO = ["당기순이익","당기순이익손실","지배주주순이익","지배기업소유주지분순이익","순이익"]
NET_ID = ["ifrs-full_profitloss","ifrs_profitloss","ifrsfull_profitloss",
          "profitloss","profitlossattributabletoownersofparent"]

# 기간 금액 컬럼 후보
PERIOD_SETS = [
    dict(labels=["thstrm_nm","frmtrm_nm","bfefrm_nm"],
         dates =["thstrm_dt","frmtrm_dt","bfefrm_dt"],
         amts  =["thstrm_amount","frmtrm_amount","bfefrm_amount"]),
    dict(labels=["당기명","전기명","전전기명"],
         dates =["당기일자","전기일자","전전기일자"],
         amts  =["당기금액","전기금액","전전기금액"]),
    dict(labels=["thstrm_nm","frmtrm_nm","bfefrm_nm"],
         dates =["thstrm_dt","frmtrm_dt","bfefrm_dt"],
         amts  =["thstrm_add_amount","frmtrm_add_amount","bfefrm_add_amount"]),
]

def find_col_by_hint(df, hints):
    nc = {_norm(c): c for c in df.columns}
    for h in hints:
        key = _norm(h)
        for nk, orig in nc.items():
            if key == nk or key in nk:
                return orig
    return None

def match_row(df, name_col, id_col, ko_list, id_list, prefer_owner=False):
    df["_nm_norm"] = df[name_col].astype(str).map(_norm) if name_col else ""
    df["_id_norm"] = df[id_col].astype(str).map(_norm) if id_col else ""
    by_id = df[df["_id_norm"].apply(lambda s: any(t in s for t in id_list))] if id_col else pd.DataFrame()
    by_nm = df[df["_nm_norm"].apply(lambda s: any(t in s for t in ko_list))] if name_col else pd.DataFrame()
    cand = by_id if not by_id.empty else by_nm
    if cand.empty: return None
    if prefer_owner:
        cand = cand.sort_values(by="_id_norm", key=lambda s: s.str.contains("ownersofparent").fillna(False), ascending=False)
        cand = cand.sort_values(by="_nm_norm", key=lambda s: s.str.contains("지배").fillna(False), ascending=False)
    return cand.iloc[0]

def audit(path, debug=False):
    df = _read_csv(path)

    # 구조 파악: 세로형(계정행)인지 확인
    name_col = None
    for cand in ["account_nm","account_name","account","계정","계정과목","ifrs_account_name","account_detail"]:
        if cand in df.columns: name_col = cand; break
        for c in df.columns:
            if _norm(cand) in _norm(c): name_col = c; break
        if name_col: break

    id_col = None
    for cand in ["account_id","ifrs_account_id","taxonomy","element_id"]:
        if cand in df.columns: id_col = cand; break
        for c in df.columns:
            if _norm(cand) in _norm(c): id_col = c; break
        if id_col: break

    # 기간셋 찾기
    chosen = None
    nc = {_norm(c): c for c in df.columns}
    for s in PERIOD_SETS:
        ok = True; res = {"labels":[],"dates":[],"amts":[]}
        for k,hints in [("labels",s["labels"]),("dates",s["dates"]),("amts",s["amts"])]:
            for h in hints:
                key = _norm(h); hit = None
                for nk,orig in nc.items():
                    if key == nk or key in nk: hit = orig; break
                if not hit: ok=False; break
                res[k].append(hit)
            if not ok: break
        if ok: chosen = res; break

    notes = []
    ok = True

    # 손익계산서인지 1차 확인(계정열 존재 + 기간 금액열 존재)
    if not (name_col or id_col):
        ok = False
        notes.append("계정명/IFRS ID 열(account_nm/account_id)이 보이지 않습니다. 손익계산서 원본이 아닐 수 있습니다.")
    if not chosen:
        ok = False
        notes.append("기간별 금액 열(thstrm_amount 등)을 찾지 못했습니다. 피벗/요약표일 수 있습니다.")

    # 핵심 계정 존재 확인
    denom_row = op_row = net_row = None
    if ok:
        denom_row = match_row(df.copy(), name_col, id_col, DENOM_KO, DENOM_ID, prefer_owner=False)
        op_row    = match_row(df.copy(), name_col, id_col, OP_KO, OP_ID, prefer_owner=False)
        net_row   = match_row(df.copy(), name_col, id_col, NET_KO, NET_ID, prefer_owner=True)

        if denom_row is None:
            ok = False; notes.append("분모(매출액/영업수익/수익) 계정을 찾지 못했습니다.")
        if op_row is None:
            notes.append("영업이익 계정을 찾지 못했습니다. (금융사는 '영업손익'으로 표기될 수 있음)")
        if net_row is None:
            ok = False; notes.append("당기순이익(지배주주) 계정을 찾지 못했습니다.")

    # 금액 값 존재/스케일 체크
    if ok and chosen:
        amt_cols = chosen["amts"]
        # 숫자화
        for c in amt_cols: df[c] = df[c].apply(_to_number)

        def has_any_value(row):
            return any(pd.notna(row[c]) for c in amt_cols)

        if denom_row is not None and not has_any_value(denom_row):
            ok = False; notes.append("분모 계정의 기간별 금액이 모두 결측입니다.")
        if net_row is not None and not has_any_value(net_row):
            ok = False; notes.append("당기순이익 계정의 기간별 금액이 모두 결측입니다.")

        # 스케일 경고(원/천원/백만원 등 단위 미기재 시 비정상치 감지)
        def typical_scale_warn(row, label):
            vals = [row[c] for c in amt_cols if pd.notna(row[c])]
            if not vals: return
            vmax = max(abs(v) for v in vals)
            if vmax and (vmax < 1e3):
                notes.append(f"경고: {label} 금액 최대치가 {vmax:,}로 매우 작습니다. 단위(천원/백만원) 누락 여부 확인 필요.")
            if vmax and (vmax > 1e14):
                notes.append(f"경고: {label} 금액 최대치가 {vmax:,}로 매우 큽니다. 단위 곱셈(×1,000 등) 과다 적용 가능성.")

        if denom_row is not None: typical_scale_warn(denom_row, "분모(매출/영업수익)")
        if net_row   is not None: typical_scale_warn(net_row,   "당기순이익")

    # 요약 출력
    verdict = "PASS ✅ 손익계산서로서 핵심 항목이 존재합니다." if ok else "FAIL ❌ 손익계산서로 보기 어려움(핵심 항목/기간 금액 누락)"
    print(f"\n[진단 결과] {verdict}\n")

    # 근거 표시
    if name_col or id_col:
        def show_row(title, row):
            if row is None:
                print(f"- {title}: 미탐지")
            else:
                nm = row.get(name_col, "") if name_col else ""
                idv = row.get(id_col, "") if id_col else ""
                print(f"- {title}: name='{nm}' | id='{idv}'")
        show_row("분모(매출/영업수익/수익)", denom_row)
        show_row("영업이익/영업손익", op_row)
        show_row("당기순이익(지배 우선)", net_row)

    if chosen:
        print("\n- 탐지한 기간 금액 열:", ", ".join(chosen["amts"]))
        print("- 탐지한 기간 라벨 열:", ", ".join(chosen["labels"]))
        print("- 탐지한 기간 일자 열:", ", ".join(chosen["dates"]))

    if notes:
        print("\n[비고/조치 안내]")
        for n in notes:
            print("• " + n)

    # 디버그 모드: 컬럼/샘플 미리보기
    if debug:
        print("\n[DEBUG] columns:", list(df.columns)[:60])
        print("\n[DEBUG] head(8):")
        print(df.head(8).to_string(index=False))

def main():
    ap = argparse.ArgumentParser(description="KB금융 손익계산서 CSV 적정성 점검")
    ap.add_argument("--path", required=True)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        print(f"[ERROR] 파일 없음: {args.path}", file=sys.stderr); sys.exit(1)
    audit(args.path, debug=args.debug)

if __name__ == "__main__":
    main()
