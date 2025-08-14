# -*- coding: utf-8 -*-
"""
plot_margins.py
매출액(또는 총수익), 영업이익, 당기순이익 → 영업이익률/순이익률 계산 & 시각화

- CLI: CSV 입력으로 실행
- 함수: 파이썬 리스트/딕셔너리로 바로 호출

출력:
- margins_chart.png (기본)
- margins_with_values.csv (계산된 비율 포함 데이터)

작성: 당신의 분석 파이프라인에 바로 붙여 쓰세요.
"""
import argparse
import math
import os
import sys
from typing import List, Dict

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

# =========================
# 헬퍼 함수
# =========================

def _enable_korean_font():
    """
    한글 깨짐(□) 방지:
    - Windows  : Malgun Gothic
    - macOS    : AppleGothic
    - Linux    : NanumGothic(설치 시)
    폰트가 없으면 기본 폰트 유지(경고만).
    """
    cand = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]
    found = False
    for f in cand:
        if f in mpl.font_manager.get_font_names():
            plt.rcParams["font.family"] = f
            found = True
            break
    if not found:
        # 일부 환경(Windows)에서는 get_font_names()가 비어 있을 수 있으니 try:
        try:
            plt.rcParams["font.family"] = "Malgun Gothic"
            found = True
        except Exception:
            pass
    # 마이너스 기호가 □로 안 나오게
    plt.rcParams["axes.unicode_minus"] = False
    
def _safe_pct(num, denom):
    """안전한 퍼센트 계산: 분모가 0/None/NaN이면 None 반환"""
    try:
        if denom is None or float(denom) == 0 or pd.isna(denom):
            return None
        return float(num) / float(denom) * 100.0
    except Exception:
        return None


def _fmt_pct(x, digits=2) -> str:
    """백분율 문자열 포맷"""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    return f"{x:.{digits}f}%"


def _annotate_bars(ax, rects, values, offset=3):
    """
    막대 위에 값 라벨(%) 표시
    - rects: bar 객체 리스트
    - values: 각 막대에 표시할 값 리스트(실제 % 값)
    """
    for rect, v in zip(rects, values):
        height = rect.get_height()
        label = _fmt_pct(v)
        ax.text(
            rect.get_x() + rect.get_width() / 2.0,
            height + offset,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
            rotation=0,
        )


def _coerce_numeric(series):
    """쉼표/공백/괄호음수 처리 등 느슨한 숫자 변환"""
    def to_number(x):
        if pd.isna(x):
            return None
        s = str(x).strip()
        if s in {"", "-", "nan", "None", "null"}:
            return None
        neg = s.startswith("(") and s.endswith(")")
        if neg:
            s = s[1:-1]
        s = s.replace(",", "")
        try:
            v = float(s)
            return -v if neg else v
        except Exception:
            return None
    return series.apply(to_number)


# =========================
# 핵심 로직
# =========================
def compute_margins(df: pd.DataFrame) -> pd.DataFrame:
    """
    입력 df(열: period, revenue, operating_profit, net_income) → 비율 계산 칼럼 추가
    - revenue는 '매출액 또는 총수익' 의미로 사용
    """
    need_cols = ["period", "revenue", "operating_profit", "net_income"]
    missing = [c for c in need_cols if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing} (반드시 {need_cols} 필요)")

    # 숫자형 강제 변환(문자 콤마/괄호 허용)
    df = df.copy()
    df["revenue"] = _coerce_numeric(df["revenue"])
    df["operating_profit"] = _coerce_numeric(df["operating_profit"])
    df["net_income"] = _coerce_numeric(df["net_income"])

    # 방어: 분모 음수/0/None 경고
    warn_rows = []
    for i, row in df.iterrows():
        rev = row["revenue"]
        if rev is None or rev == 0:
            warn_rows.append((row["period"], "분모가 없음(0 또는 결측)"))
        elif rev < 0:
            warn_rows.append((row["period"], "분모가 음수(데이터 확인 필요)"))

    # 지표 계산
    df["operating_margin_pct"] = [
        _safe_pct(op, rev) for op, rev in zip(df["operating_profit"], df["revenue"])
    ]
    df["net_margin_pct"] = [
        _safe_pct(ni, rev) for ni, rev in zip(df["net_income"], df["revenue"])
    ]

    # 경고 출력
    if warn_rows:
        print("\n[경고] 일부 기간의 분모(revenue)가 비정상입니다:")
        for p, msg in warn_rows:
            print(f" - {p}: {msg}")

    return df


def plot_margins(
    df,
    title: str = "수익성(영업이익률 vs 순이익률)",
    out_png: str = "margins_chart.png",
    dpi: int = 120,
):
    """
    막대(영업/순이익률) + 꺾은선(각 비율의 추이) 동시 표시.
    - 라인 색상은 막대 색상과 '다르게' 보이도록 기본 팔레트에서 다른 색을 사용.
    - 각 막대 위에 % 라벨 표시.
    - 한글 폰트 자동 설정.
    """
    _enable_korean_font()

    df = df.copy()
    if "period" in df.columns:
        df = df.sort_values("period")

    periods = df["period"].astype(str).tolist()
    opm = df["operating_margin_pct"].tolist()
    npm = df["net_margin_pct"].tolist()

    fig, ax = plt.subplots(figsize=(12, 5))

    x = range(len(periods))
    width = 0.38

    # --- 막대 ---
    bars1 = ax.bar([i - width/2 for i in x], [v or 0 for v in opm], width, label="영업이익률", alpha=0.9)
    bars2 = ax.bar([i + width/2 for i in x], [v or 0 for v in npm], width, label="순이익률", alpha=0.9)

    # --- 꺾은선(추이) ---
    # 기본 팔레트에서 막대와 겹치지 않도록 '다른' 색을 선택
    palette = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    line_color1 = palette[2 % len(palette)] if palette else None
    line_color2 = palette[3 % len(palette)] if palette else None

    ax.plot(list(x), opm, marker="o", linewidth=2.0, label="영업이익률(추이)", color=line_color1, zorder=3)
    ax.plot(list(x), npm, marker="o", linewidth=2.0, label="순이익률(추이)", color=line_color2, zorder=3)

    # --- 라벨/격자 ---
    ax.set_title(title)
    ax.set_xlabel("기간")
    ax.set_ylabel("비율(%)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(periods)
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    # 막대 위 % 라벨
    def _fmt(v): return "N/A" if v is None else f"{v:.2f}%"
    for rect, v in zip(bars1, opm):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.5, _fmt(v),
                ha="center", va="bottom", fontsize=9)
    for rect, v in zip(bars2, npm):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.5, _fmt(v),
                ha="center", va="bottom", fontsize=9)

    # y축 여유
    ymax = max([v for v in (opm + npm) if v is not None] + [0])
    ax.set_ylim(0, ymax * 1.2 + 2)

    ax.legend(loc="upper right")
    fig.tight_layout()
    plt.savefig(out_png, dpi=dpi)
    print(f"[저장] 그래프 이미지: {out_png}")


# =========================
# 외부에서 바로 쓰기 좋은 함수
# =========================
def plot_margins_from_records(
    records: List[Dict],
    title: str = "수익성(영업이익률 vs 순이익률)",
    out_png: str = "margins_chart.png",
) -> pd.DataFrame:
    """
    파이썬 리스트[{period, revenue, operating_profit, net_income}, ...]를 받아
    - 비율 계산 후 그래프 저장
    - 계산 결과 DataFrame을 반환
    """
    df = pd.DataFrame.from_records(records)
    df2 = compute_margins(df)
    # 계산치 CSV도 함께 저장
    out_csv = os.path.splitext(out_png)[0] + "_values.csv"
    df2.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"[저장] 계산값 CSV: {out_csv}")
    plot_margins(df2, title=title, out_png=out_png)
    return df2


# =========================
# CLI: CSV 입력으로 실행
# =========================
def _read_csv_loose(path: str) -> pd.DataFrame:
    """CSV 인코딩 자동 시도"""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path, encoding_errors="ignore", engine="python")


def main():
    ap = argparse.ArgumentParser(description="영업이익률/순이익률 시각화")
    ap.add_argument("--csv", help="입력 CSV 경로 (열: period,revenue,operating_profit,net_income)")
    ap.add_argument("--title", default="수익성(영업이익률 vs 순이익률)")
    ap.add_argument("--out", default="margins_chart.png", help="저장 파일명 (PNG)")
    args = ap.parse_args()

    if not args.csv:
        print("사용법: python plot_margins.py --csv your.csv --title '제목' --out chart.png", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.csv):
        print(f"[ERROR] 파일이 존재하지 않습니다: {args.csv}", file=sys.stderr)
        sys.exit(2)

    df = _read_csv_loose(args.csv)

    # 컬럼 이름 유연 매핑(대소문자/언더스코어/한글 혼용을 위해)
    def _norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    colmap = { _norm(c): c for c in df.columns }
    aliases = {
        "period": ["period", "기간", "연도", "년", "연차"],
        "revenue": ["revenue", "sales", "매출", "매출액", "총수익", "영업수익"],
        "operating_profit": ["operatingprofit", "op", "영업이익"],
        "net_income": ["netincome", "profit", "당기순이익", "순이익"],
    }
    resolved = {}
    for key, cands in aliases.items():
        for cand in cands:
            k = _norm(cand)
            if k in colmap:
                resolved[key] = colmap[k]
                break
    missing = [k for k in ["period", "revenue", "operating_profit", "net_income"] if k not in resolved]
    if missing:
        raise ValueError(f"[ERROR] CSV에서 필요한 열을 찾지 못했습니다. 매핑 실패: {missing}")

    df = df.rename(columns={resolved["period"]: "period",
                            resolved["revenue"]: "revenue",
                            resolved["operating_profit"]: "operating_profit",
                            resolved["net_income"]: "net_income"})

    df2 = compute_margins(df)
    out_csv = os.path.splitext(args.out)[0] + "_values.csv"
    df2.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"[저장] 계산값 CSV: {out_csv}")
    plot_margins(df2, title=args.title, out_png=args.out)


if __name__ == "__main__":
    main()
