# C:\workspace\KUAIF3\agent_fin_report.py
# 간단 AI 에이전트: 은행 손익계산서(XBRL CSV) → 지표/변화율 계산 → 요약리포트 생성
import re
import sys
import pandas as pd
import numpy as np
from pathlib import Path

# ====== 경로 기본값 (원하면 그대로 두고 실행만 해도 됨) ======
DEFAULT_CSV = Path(r"C:\workspace\KUAIF3\DartFile\_KB금융_손익계산서.csv")
DEFAULT_OUTDIR = DEFAULT_CSV.parent / "out"

# ====== 유틸 ======
def extract_period(colname: str) -> str:
    """('20240101-20241231', ('연결재무제표',)) 같은 헤더에서 기간만 추출"""
    s = str(colname)
    m = re.search(r"(\d{8})(?:-(\d{8}))?", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)
    return s

def read_csv_flex(path: Path) -> pd.DataFrame:
    last = None
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last = e
    raise RuntimeError(f"CSV 읽기 실패: {path}\n마지막 오류: {last}")

def find_row_index(concept_series: pd.Series, pattern: str, regex: bool = True):
    m = concept_series.str.contains(pattern, case=False, regex=regex, na=False)
    idx = list(concept_series.index[m])
    return idx[0] if idx else None

# ====== 핵심 로직 ======
def load_and_tidy(csv_path: Path) -> pd.DataFrame:
    df = read_csv_flex(csv_path)

    # 첫 번째 열: XBRL concept id/라벨 계열
    concept = df.iloc[:, 0].astype(str)

    # 은행업 XBRL에서 자주 쓰는 라벨/컨셉 id
    idx_operating = find_row_index(concept, r"ProfitLossFromOperatingActivities")   # 영업이익
    idx_net       = find_row_index(concept, r"^ifrs-full_ProfitLoss$")             # 당기순이익
    idx_int_rev   = find_row_index(concept, r"ifrs-full_RevenueFromInterest")      # 이자수익
    idx_ins_rev   = find_row_index(concept, r"ifrs-full_InsuranceRevenue")         # 보험수익

    # '연결재무제표' 열만 사용 (은행은 연결 기준을 더 많이 봄)
    consol_cols = [c for c in df.columns if "연결재무제표" in str(c)]
    if not consol_cols:
        raise RuntimeError("연결재무제표 열을 찾지 못했습니다. CSV 구조를 확인하세요.")

    period_map = {c: extract_period(c) for c in consol_cols}

    records = []
    for col, period in period_map.items():
        rec = {"period": period}

        def safe_get(idx):
            if idx is None:
                return np.nan
            return pd.to_numeric(df.loc[idx, col], errors="coerce")

        rec["operating_profit"]  = safe_get(idx_operating)
        rec["net_income"]        = safe_get(idx_net)
        rec["interest_revenue"]  = safe_get(idx_int_rev)
        rec["insurance_revenue"] = safe_get(idx_ins_rev)

        # (단순 프록시) 총수익 ~ 이자수익 + 보험수익
        rec["revenue_proxy"] = np.nansum([rec["interest_revenue"], rec["insurance_revenue"]])

        if not np.isnan(rec["revenue_proxy"]) and rec["revenue_proxy"] != 0:
            rec["operating_margin_pct"] = (rec["operating_profit"] / rec["revenue_proxy"]) * 100
            rec["net_margin_pct"]       = (rec["net_income"]     / rec["revenue_proxy"]) * 100
        else:
            rec["operating_margin_pct"] = np.nan
            rec["net_margin_pct"]       = np.nan

        records.append(rec)

    tidy = pd.DataFrame(records).sort_values("period").reset_index(drop=True)

    # 전기 대비 변화율(%)
    for col in ["operating_profit", "net_income", "revenue_proxy",
                "operating_margin_pct", "net_margin_pct"]:
        tidy[f"{col}_chg_pct"] = tidy[col].pct_change() * 100

    return tidy

def build_simple_insights(tidy: pd.DataFrame) -> str:
    def pct(x):
        return "NA" if pd.isna(x) else f"{x:+.2f}%"

    latest = tidy.iloc[-1].to_dict()
    out = []
    out.append(f"- 최근 기간: **{latest['period']}**")

    if len(tidy) >= 2:
        out.append(f"- 영업이익 변화율: {pct(latest.get('operating_profit_chg_pct'))}")
        out.append(f"- 순이익 변화율: {pct(latest.get('net_income_chg_pct'))}")
        out.append(f"- 영업이익률 변화: {pct(latest.get('operating_margin_pct_chg_pct'))}")
        out.append(f"- 순이익률 변화: {pct(latest.get('net_margin_pct_chg_pct'))}")
    else:
        out.append("- 비교할 전기 데이터가 부족합니다.")

    # 아주 단순한 경고 룰
    alerts = []
    if len(tidy) >= 2:
        if pd.notna(latest.get("operating_profit_chg_pct")) and latest["operating_profit_chg_pct"] <= -15:
            alerts.append("경고: 영업이익 급락")
        if pd.notna(latest.get("net_income_chg_pct")) and latest["net_income_chg_pct"] <= -15:
            alerts.append("경고: 순이익 급락")

    out.append("\n## 이상 신호")
    if alerts:
        out.extend([f"- {a}" for a in alerts])
    else:
        out.append("- 감지되지 않음")

    return "# 자동 분석 리포트(간단)\n\n" + "\n".join(out) + "\n"

def run(csv_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    tidy = load_and_tidy(csv_path)

    tidy_path = out_dir / "financial_auto_tidy.csv"
    report_path = out_dir / "financial_auto_report.md"

    tidy.to_csv(tidy_path, index=False, encoding="utf-8-sig")
    report = build_simple_insights(tidy)
    report_path.write_text(report, encoding="utf-8")

    print(f"[OK] 정규화 테이블 저장: {tidy_path}")
    print(f"[OK] 인사이트 리포트 저장: {report_path}")

# ====== 진입점 ======
if __name__ == "__main__":
    # 사용법:
    #   1) 인자 없이 실행 → DEFAULT_CSV 사용
    #   2) 특정 CSV 지정   → python agent_fin_report.py "C:\...\_KB금융_손익계산서.csv"
    csv_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    out_dir = DEFAULT_OUTDIR if len(sys.argv) <= 2 else Path(sys.argv[2])

    if not csv_arg.exists():
        raise SystemExit(f"CSV를 찾을 수 없습니다: {csv_arg}")

    print(f"[INFO] 입력 CSV: {csv_arg}")
    print(f"[INFO] 출력 폴더: {out_dir}")
    run(csv_arg, out_dir)