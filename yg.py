import re
import dart_fss as dart
import pandas as pd
from pathlib import Path
CSV_ENCODING = "utf-8-sig"

# ⬇️ 본문 테스트 시 API KEY 채워 넣으세요(여긴 마스킹)
API_KEY = "be958a5b1ba26a963db36ef4b5a348bfc22a2b49"
dart.set_api_key(api_key=API_KEY)

# 회사 선택
corp_list = dart.get_corp_list()
found = corp_list.find_by_corp_name("KB금융", exactly=True)
if not found:
    raise RuntimeError("삼성전자 회사를 찾지 못했습니다.")
corp = found[0]

def _as_df(obj):
    """
    DataFrame 또는 list[DataFrame] → 단일 DataFrame으로 통일.
    여러 개인 경우 첫 번째를 사용(필요 시 concat 전략으로 교체 가능).
    """
    if obj is None:
        return None
    if hasattr(obj, "head"):  # DataFrame
        return obj
    if isinstance(obj, (list, tuple)) and obj:
        first = obj[0]
        return first if hasattr(first, "head") else None
    return None


def _safe_prefix(text: str) -> str:
    """파일명에 쓸 접두사 정제: 한글/영문/숫자/띄어쓰기/._-만 허용, 공백→_"""
    if text is None:
        return ""
    t = re.sub(r"[()]+", "", text).strip()
    t = re.sub(r"[^0-9A-Za-z가-힣 _.\-]+", "", t)
    t = re.sub(r"\s+", "_", t)
    return t


def _iter_save_keys(fs_dict):
    """
    저장 우선순위와 중복 방지:
    - 'cis'가 있으면 'is'는 스킵(동일표 별칭이므로)
    """
    order = ["bs", "cis", "cf", "sce", "is"]
    have_cis = "cis" in fs_dict and fs_dict["cis"] is not None
    for k in order:
        if k == "is" and have_cis:
            continue
        yield k


def save_fs_to_csv(fs_dict, out_dir, prefix="", meta=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for key in _iter_save_keys(fs_dict):
        df = _as_df(fs_dict.get(key))
        if df is None or getattr(df, "empty", True):
            continue
        if meta:
            for mk, mv in meta.items():
                df[mk] = mv
        fname = f"{prefix}_{key}.csv" if prefix else f"{key}.csv"
        path = out / fname
        df.to_csv(path, index=False, encoding=CSV_ENCODING)
        saved.append(str(path))
    return saved


def save_fs_to_parquet(fs_dict, out_dir, prefix=""):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for key in _iter_save_keys(fs_dict):
        df = _as_df(fs_dict.get(key))
        if df is None or getattr(df, "empty", True):
            continue
        fname = f"{prefix}_{key}.parquet" if prefix else f"{key}.parquet"
        path = out / fname
        try:
            df.to_parquet(path, index=False)  # 엔진 미설치 시 ImportError
            saved.append(str(path))
        except Exception as e:
            print(f"[경고] Parquet 저장 실패({key}): {e}  → CSV는 정상 저장됩니다.")
    return saved


def search_reports(corp, bgn, end, detail_ty):
    """
    정기공시(A) + 상세유형(A001/2/3), 최종본만, 전체 리스트 반환(오래된→최근 순)
    detail_ty: 'A001'(사업) | 'A002'(반기) | 'A003'(분기)
    """
    res = corp.search_filings(
        bgn_de=bgn,
        end_de=end,
        pblntf_ty="A",
        pblntf_detail_ty=detail_ty,
        last_reprt_at="Y",
        page_count=100,
    )
    # rcept_dt(접수일), rcept_no(접수번호) 기준 정렬
    return sorted(res, key=lambda r: (getattr(r, "rcept_dt", ""), getattr(r, "rcept_no", "")))


def _tables_to_df(tables):
    """dart_fss.xbrl.table.Table 리스트를 DataFrame(들)로 변환."""
    if tables is None:
        return None
    if not isinstance(tables, (list, tuple)):
        tables = [tables]
    dfs = []
    for t in tables:
        if t is None:
            continue
        try:
            # DataFrame으로 직변환(개념/계정과목/구분 열 포함)
            df = t.to_DataFrame(
                lang="ko",
                show_class=True,
                show_concept=True,
                separator=True,
            )
        except Exception:
            df = None
        if df is not None and getattr(df, "empty", False) is False:
            dfs.append(df)
    if not dfs:
        return None
    # 동일 표가 여러 role로 나뉘어 있을 수 있어 첫 번째 유효 표를 반환
    return dfs[0] if len(dfs) == 1 else dfs


def _xbrl_to_fs_dict(xbrl, separate: bool):
    """
    XBRL 객체에서 주요 재무제표를 dict로 수집.
    반환: {'bs': DataFrame|list[DF], 'cis': DF|list[DF], 'is': DF|list[DF], 'cf': DF|list[DF], 'sce': DF|list[DF]}
    (없으면 해당 키는 생략)
    """
    if xbrl is None:
        return None
    out = {}
    # 재무상태표(BS)
    out["bs"] = _tables_to_df(xbrl.get_financial_statement(separate=separate))
    # 포괄손익계산서(CIS) — dart_fss에서는 income_statement가 CIS 성격
    cis_df = _tables_to_df(xbrl.get_income_statement(separate=separate))
    out["cis"] = cis_df
    # 손익계산서(IS) 별칭(있으면 동일 참조로 채움)
    out["is"] = cis_df
    # 현금흐름표(CF)
    out["cf"] = _tables_to_df(xbrl.get_cash_flows(separate=separate))
    # 자본변동표(SCE)
    out["sce"] = _tables_to_df(xbrl.get_changes_in_equity(separate=separate))
    # 모두 None이면 None 반환
    if all(v is None for v in out.values()):
        return None
    # None 항목 제거
    return {k: v for k, v in out.items() if v is not None}


def report_to_fs(report):
    """
    단일 Report에서 XBRL 기반 재무제표를 dict로 반환.
    우선 연결(CFS)을 시도하고 실패 시 개별(OFS)로 재시도.
    """
    try:
        xbrl = report.xbrl
    except Exception:
        # XBRL 자체를 못 여는 경우
        return None
    # 연결 우선
    fs = _xbrl_to_fs_dict(xbrl, separate=False)
    if fs:
        return fs
    # 개별로 재시도
    return _xbrl_to_fs_dict(xbrl, separate=True)


def pick_q1_q3_from_a003(all_a003):
    """
    A003(분기) 묶음에서 1분기/3분기를 각 1건씩 선택.
    report_nm의 '(YYYY.MM)' 패턴을 우선 사용, 없으면 접수월로 추정.
    """
    q1 = q3 = None

    def ym_from_nm(nm):
        m = re.search(r"\((\d{4})\.(\d{2})\)", nm)
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)

    # 오래된→최근 순이라 1분기는 앞쪽에서, 3분기는 뒤쪽에서 찾기
    for rep in all_a003:
        nm = getattr(rep, "report_nm", "") or ""
        y, mm = ym_from_nm(nm)
        if y and mm:
            # 1분기 보고는 통상 4~6월 접수, 명칭에는 3월/4~6월이 섞여 표기될 수 있음
            if (mm == 3 or 4 <= mm <= 6) and q1 is None:
                q1 = rep
            # 3분기 보고는 통상 10~12월 접수, 명칭에는 9월/10~12월이 섞여 표기될 수 있음
            if mm == 9 or 10 <= mm <= 12:
                q3 = rep
    # 보정: 못 찾았으면 접수월로 추정
    if q1 is None:
        for rep in all_a003:
            m = int(getattr(rep, "rcept_dt", "00000000")[4:6] or 0)
            if 4 <= m <= 6:
                q1 = rep
                break
    if q3 is None:
        for rep in reversed(all_a003):
            m = int(getattr(rep, "rcept_dt", "00000000")[4:6] or 0)
            if 10 <= m <= 12:
                q3 = rep
                break
    return q1, q3


def run():
    # 2024년 접수 기준: 분기/반기
    a003_all = search_reports(corp, "20240101", "20241231", "A003")  # 분기
    a002_all = search_reports(corp, "20240101", "20241231", "A002")  # 반기

    # 1분기 / 3분기 각각 1건 선택 후 추출
    rep_q1, rep_q3 = pick_q1_q3_from_a003(a003_all)

        # 1분기
    if rep_q1:
        try:
            fs = report_to_fs(rep_q1)
            label = "Q1"
            prefix = f"{rep_q1.rcept_dt}_{_safe_prefix(label)}"
            meta = {"rcept_dt": rep_q1.rcept_dt, "report_nm": rep_q1.report_nm}
            saved_csv = save_fs_to_csv(fs, out_dir="exports_KB", prefix=prefix, meta=meta) if fs else []
            saved_pq  = save_fs_to_parquet(fs, out_dir="exports_KB", prefix=prefix) if fs else []
            print(
                f"[{'OK' if fs else '스킵'}] 1분기: {rep_q1.report_nm} ({rep_q1.rcept_dt}) "
                f"keys={list(fs.keys()) if fs else None} | CSV {len(saved_csv)}개, Parquet {len(saved_pq)}개 저장"
            )
        except Exception as e:
            print(f"[실패] 1분기 추출: {e}")
    else:
        print("[스킵] 1분기 없음/판별불가)")

    # 3분기
    if rep_q3:
        try:
            fs = report_to_fs(rep_q3)
            label = "Q3"
            prefix = f"{rep_q3.rcept_dt}_{_safe_prefix(label)}"
            meta = {"rcept_dt": rep_q3.rcept_dt, "report_nm": rep_q3.report_nm}
            saved_csv = save_fs_to_csv(fs, out_dir="exports_KB", prefix=prefix, meta=meta) if fs else []
            saved_pq  = save_fs_to_parquet(fs, out_dir="exports_KB", prefix=prefix) if fs else []
            print(
                f"[{'OK' if fs else '스킵'}] 3분기: {rep_q3.report_nm} ({rep_q3.rcept_dt}) "
                f"keys={list(fs.keys()) if fs else None} | CSV {len(saved_csv)}개, Parquet {len(saved_pq)}개 저장"
            )
        except Exception as e:
            print(f"[실패] 3분기 추출: {e}")
    else:
        print("[스킵] 3분기 없음/판별불가")

    # 반기 최신
    if a002_all:
        rep_h1 = a002_all[-1]
        try:
            fs = report_to_fs(rep_h1)
            label = "H1"
            prefix = f"{rep_h1.rcept_dt}_{_safe_prefix(label)}"
            meta = {"rcept_dt": rep_h1.rcept_dt, "report_nm": rep_h1.report_nm}
            saved_csv = save_fs_to_csv(fs, out_dir="exports_KB", prefix=prefix, meta=meta) if fs else []
            saved_pq  = save_fs_to_parquet(fs, out_dir="exports_KB", prefix=prefix) if fs else []
            print(
                f"[{'OK' if fs else '스킵'}] 반기: {rep_h1.report_nm} ({rep_h1.rcept_dt}) "
                f"keys={list(fs.keys()) if fs else None} | CSV {len(saved_csv)}개, Parquet {len(saved_pq)}개 저장"
            )
        except Exception as e:
            print(f"[실패] 반기 추출: {e}")
    else:
        print("[스킵] 반기 없음")

    a001_2024 = search_reports(corp, "20240101", "20241231", "A001")
    a001_2025 = search_reports(corp, "20250101", "20251231", "A001")
    
    # FY2023(접수2024)
    if a001_2024:
        rep = a001_2024[-1]
        try:
            fs = report_to_fs(rep)
            label = "FY2023_recv2024"
            prefix = f"{rep.rcept_dt}_{_safe_prefix(label)}"
            meta = {"rcept_dt": rep.rcept_dt, "report_nm": rep.report_nm}
            saved_csv = save_fs_to_csv(fs, out_dir="exports_KB", prefix=prefix, meta=meta) if fs else []
            saved_pq  = save_fs_to_parquet(fs, out_dir="exports_KB", prefix=prefix) if fs else []
            print(
                f"[{'OK' if fs else '스킵'}] FY2023(접수2024): {rep.report_nm} ({rep.rcept_dt}) "
                f"keys={list(fs.keys()) if fs else None} | CSV {len(saved_csv)}개, Parquet {len(saved_pq)}개 저장"
            )
        except Exception as e:
            print(f"[실패] FY2023(접수2024) 추출: {e}")
    else:
        print("[스킵] FY2023(접수2024) 없음")

    # FY2024(접수2025)
    if a001_2025:
        rep = a001_2025[-1]
        try:
            fs = report_to_fs(rep)
            label = "FY2024_recv2025"
            prefix = f"{rep.rcept_dt}_{_safe_prefix(label)}"
            meta = {"rcept_dt": rep.rcept_dt, "report_nm": rep.report_nm}
            saved_csv = save_fs_to_csv(fs, out_dir="exports_KB", prefix=prefix, meta=meta) if fs else []
            saved_pq  = save_fs_to_parquet(fs, out_dir="exports_KB", prefix=prefix) if fs else []
            print(
                f"[{'OK' if fs else '스킵'}] FY2024(접수2025): {rep.report_nm} ({rep.rcept_dt}) "
                f"keys={list(fs.keys()) if fs else None} | CSV {len(saved_csv)}개, Parquet {len(saved_pq)}개 저장"
            )
        except Exception as e:
            print(f"[실패] FY2024(접수2025) 추출: {e}")
    else:
        print("[스킵] FY2024(접수2025) 없음")



if __name__ == "__main__":
    run()
