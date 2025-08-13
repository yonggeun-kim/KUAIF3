#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic DART XML Income Statement Parser (KR, IFRS)
- Robust across major KR large-cap filers (제조/IT/차/화학/철강/통신/플랫폼/금융지주 등)
- Handles synonyms (KOR/ENG), finance-industry items, negative formats (△, parentheses)
- Works for 사업/반기/분기 보고서 XML (dart4.xsd style)

API
---
from generic_income_parser import (
    parse_income_statement_df,
    parse_income_statement_numeric_df,
    parse_many_income_statements,
)

df = parse_income_statement_df(".../보고서.xml", prefer_consolidated=True)
df_num = parse_income_statement_numeric_df(".../보고서.xml")

Batch:
results = parse_many_income_statements(["A.xml","B.xml"], to_numeric=True)
"""

from __future__ import annotations
from typing import Union, Tuple, List, Optional, Dict
from pathlib import Path
from html import unescape
import re
import unicodedata
import pandas as pd
import os

# --------------------- Dictionaries / Keywords ---------------------
# Common IFRS income-statement items (Korean & English)
LINE_ITEMS_COMMON = [
    # Korean
    "매출액","매출","수익","매출수익","매출원가","매출총이익","판매비와관리비","영업이익","영업손실",
    "기타수익","기타비용","영업외수익","영업외비용","지분법이익","지분법손실",
    "금융수익","금융비용","법인세비용","법인세차감전순이익","법인세비용차감전순이익",
    "당기순이익","분기순이익","반기순이익","기간순손익",
    "지배기업 소유주지분","비지배지분","기본주당이익","희석주당이익",
    "총포괄손익","기타포괄손익","기타포괄손익누계액","확정급여제도 재측정요소",
    "환산차이","현금흐름위험회피","재평가잉여금",
    "법인세차감전","이자수익","이자비용","배당수익","외환손익","파생상품손익",
    # English
    "income statement","statement of comprehensive income","comprehensive income",
    "revenue","sales","cost of sales","gross profit","selling and administrative expenses",
    "operating profit","operating loss","other income","other expenses",
    "finance income","finance costs","share of profit","share of loss",
    "profit before income tax","profit for the period",
    "profit attributable to owners of parent","non-controlling interests",
    "basic earnings per share","diluted earnings per share",
]

# Finance industry specific (KB금융 등)
LINE_ITEMS_FINANCE = [
    "이자수익","이자비용","이자이익","수수료수익","수수료비용","수수료이익",
    "대손충당금전입액","신용손실충당금전입","대손비용",
    "유가증권관련손익","외환및파생상품관련손익","외환손익","파생상품손익",
    "영업수익","영업비용","영업이익(손실)",
    "보증관련손익","기타영업손익",
    # English
    "interest income","interest expense","net interest income",
    "fee income","fee expense","net fee income","credit loss allowance",
]

HEADER_HINTS = [
    "과목","계정과목","항목","구 분","구분","손익","단위","요약","제","기말","당기","전기",
    "3개월","누계","기간","회계연도","사업연도","Fiscal year","Statement",
]

TITLE_KEYWORDS = [
    # Korean
    "손익계산서","포괄손익계산서","연결손익계산서","연결포괄손익계산서","요약연결손익계산서",
    "별도손익계산서","(요약)손익계산서","(요약)포괄손익계산서","요약 포괄손익계산서",
    # English
    "income statement","statement of comprehensive income","consolidated statement of comprehensive income",
]

# --------------------- Helpers ---------------------
TABLE_RE   = re.compile(r"<TABLE\b.*?>.*?</TABLE>", re.IGNORECASE | re.DOTALL)
TR_RE      = re.compile(r"<TR\b.*?>.*?</TR>", re.IGNORECASE | re.DOTALL)
CELL_RE    = re.compile(r"<T[HD]\b.*?>(.*?)</T[HD]>", re.IGNORECASE | re.DOTALL)

SPACE_RE   = re.compile(r"\s+")
TAG_RE     = re.compile(r"<.*?>", re.DOTALL)

NUM_TOKEN  = re.compile(r"[0-9]")
NUM_SHAPE  = re.compile(r"[\d,()\-△]")

PERIOD_TOKEN = re.compile(r"(제\s*\d+\s*기|당기|전기|전전기|누계|3개월|3\s*months|year|period|FY)", re.IGNORECASE)

def normalize_text(s: str) -> str:
    s = unescape(s)
    s = s.replace("&nbsp;"," ")
    s = s.replace("\u3000"," ")  # ideographic space
    s = unicodedata.normalize("NFKC", s)
    s = SPACE_RE.sub(" ", s)
    return s.strip()

def strip_tags_keep_text(html: str) -> str:
    return normalize_text(TAG_RE.sub(" ", html))

def numeric_like(s: str) -> bool:
    return bool(NUM_TOKEN.search(s)) and bool(NUM_SHAPE.search(s))

def extract_tables(doc: str) -> List[str]:
    return list(TABLE_RE.findall(doc))

def extract_rows(table_html: str) -> List[List[str]]:
    trs = TR_RE.findall(table_html)
    rows: List[List[str]] = []
    for tr in trs:
        cells = CELL_RE.findall(tr)
        cleaned = [strip_tags_keep_text(c) for c in cells]
        cleaned = [c for c in cleaned if c != ""]
        if cleaned:
            rows.append(cleaned)
    return rows

# --------------------- Scoring ---------------------
def score_table_context(ctx: str, tbl: str, prefer_consolidated: bool = True) -> float:
    score = 0.0
    for kw in TITLE_KEYWORDS:
        if kw in ctx or kw in tbl: score += 5.0
    # Line items presence
    for li in LINE_ITEMS_COMMON: 
        if li in ctx or li in tbl: score += 1.5
    for li in LINE_ITEMS_FINANCE:
        if li in ctx or li in tbl: score += 1.8
    # Consolidated preference
    if prefer_consolidated and (("연결" in ctx) or ("연결" in tbl)):
        score += 2.0
    return score

def score_table_rows(rows: List[List[str]]) -> float:
    if not rows or len(rows) < 5: 
        return -1.0
    flat = " ".join(" ".join(r) for r in rows)
    li_hits = sum(li in flat for li in LINE_ITEMS_COMMON) + sum(li in flat for li in LINE_ITEMS_FINANCE)
    num_cells = sum(numeric_like(c) for r in rows for c in r)
    total_cells = sum(len(r) for r in rows)
    num_density = num_cells / max(1, total_cells)
    # header presence
    header_bonus = 0.0
    first_rows = rows[:12]
    for r in first_rows:
        joined = " ".join(r)
        if any(h in joined for h in HEADER_HINTS): 
            header_bonus = 1.0; break
        if PERIOD_TOKEN.search(joined):
            header_bonus = 0.6
    size_bonus = min(len(rows), 120) / 120.0  # prefer non-tiny tables
    return li_hits*8 + num_density*5 + header_bonus*2 + size_bonus

# --------------------- Header detection & DataFrame build ---------------------
def find_header_index(rows: List[List[str]]) -> int:
    # Prefer first row that looks like header by hints or period tokens
    for i, r in enumerate(rows[:15]):
        joined = " ".join(r)
        if any(h in joined for h in HEADER_HINTS) or PERIOD_TOKEN.search(joined):
            return i
    return 0

def drop_redundant_header_rows(data: List[List[str]]) -> List[List[str]]:
    # Remove rows that repeat header-like cells mid table
    if not data: return data
    header = data[0]
    out = [header]
    for r in data[1:]:
        joined = " ".join(r)
        if any(h in joined for h in HEADER_HINTS) and sum(c in header for c in r) >= max(2, len(header)//2):
            continue
        out.append(r)
    return out

def build_dataframe(rows: List[List[str]]) -> pd.DataFrame:
    hidx = find_header_index(rows)
    max_len = max(len(r) for r in rows)
    header = rows[hidx] + [""]*(max_len - len(rows[hidx]))
    body   = [r + [""]*(max_len - len(r)) for r in rows[hidx+1:]]
    # Clean unit rows
    body = [r for r in body if not any(("단위" in c) for c in r)]
    # Drop repeated headers inside body
    body = drop_redundant_header_rows([header] + body)[1:]
    cols = [ (h if h else f"열{j}") for j, h in enumerate(header) ]
    # Tidy column label variants
    cols = [c.replace("구 분","구분").replace("계 정","계정").replace("계정 과목","계정과목") for c in cols]
    df = pd.DataFrame(body, columns=cols)
    # Trim all cells
    df = df.applymap(lambda x: x.strip() if isinstance(x,str) else x)
    # Drop empty trailing columns
    while df.shape[1] > 1 and df.iloc[:, -1].replace("", pd.NA).isna().all():
        df = df.iloc[:, :-1]
    return df

# --------------------- Post-process: numeric conversion ---------------------
def _parse_korean_number(s: str) -> Optional[float]:
    if not isinstance(s, str): 
        return None
    t = s.strip()
    if t == "": return None
    # remove spaces
    t = t.replace(" ", "")
    # handle △ as minus
    neg = False
    if "△" in t:
        neg = True
        t = t.replace("△","")
    # parentheses negative e.g. (1,234)
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    # percentage -> strip % but keep for separate cols
    if t.endswith("%"):
        t = t[:-1]
    # thousands commas
    t = t.replace(",", "")
    # if not numeric now, return None
    if not re.fullmatch(r"[-+]?\d+(\.\d+)?", t or "x"):
        return None
    val = float(t)
    if neg: val = -val
    return val

def to_numeric_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        # Try to convert numbers where possible; keep text if fails
        parsed = out[c].map(_parse_korean_number)
        # If majority are numbers, adopt numeric column
        if parsed.notna().mean() >= 0.5:
            out[c] = parsed
    return out

# --------------------- Main parsers ---------------------
def parse_income_statement_df(xml_path: Union[str, Path], prefer_consolidated: bool = True) -> pd.DataFrame:
    xml_path = Path(xml_path)
    raw = xml_path.read_text(encoding="utf-8", errors="ignore")
    doc = normalize_text(raw)

    candidates: List[Tuple[float, List[List[str]]]] = []
    for m in TABLE_RE.finditer(doc):
        tbl = m.group(0)
        ctx = doc[max(0, m.start()-1800):m.start()]  # slightly larger window
        ctx_score = score_table_context(ctx, tbl, prefer_consolidated=prefer_consolidated)
        rows = extract_rows(tbl)
        row_score = score_table_rows(rows)
        if row_score < 0: 
            continue
        total = ctx_score + row_score
        candidates.append((total, rows))

    if not candidates:
        raise ValueError("No candidate income-statement-like tables found. Consider adjusting keywords.")

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_rows = candidates[0][1]
    return build_dataframe(best_rows)

def parser(xml_path: Union[str, Path], prefer_consolidated: bool = True) -> pd.DataFrame:
    df = parse_income_statement_df(xml_path, prefer_consolidated=prefer_consolidated)
    return to_numeric_df(df)

def searchandParse(xbrl_path):
    try:
        # 1. 가장 최신 날짜의 XBRL 폴더 찾기
        # 'xbrl_'로 시작하는 폴더 목록을 가져옵니다.
        all_dirs = [d for d in os.listdir(xbrl_path) if 
                    os.path.isdir(os.path.join(xbrl_path, d)) and d.startswith('xbrl_')]

        if not all_dirs:
            print(f"오류: '{xbrl_path}' 경로에 'xbrl_'로 시작하는 폴더가 없습니다.")
            return None

        # 폴더 이름을 기준으로 내림차순 정렬하여 가장 최신 폴더를 찾습니다.
        # 이름 형식이 'xbrl_YYYYMMDD...'이므로 문자열 정렬로 충분합니다.
        latest_folder_name = sorted(all_dirs, reverse=True)[0]
        latest_folder_path = os.path.join(xbrl_path, latest_folder_name)
        print(f"1. 최신 보고서 폴더를 찾았습니다: {latest_folder_name}")

        # 2. 폴더 내부의 XML 파일 목록 확인
        files_in_folder = os.listdir(latest_folder_path)
        xml_files = [f for f in files_in_folder if f.endswith('.xml')]

        if not xml_files:
            print(f"오류: '{latest_folder_name}' 폴더에 XML 파일이 없습니다.")
            return None

        # 3. 파싱할 대상 파일 결정
        target_xml_file = None
        if len(xml_files) == 1:
            # XML 파일이 하나만 있는 경우
            target_xml_file = xml_files[0]
            print(f"2. 폴더 내에 XML 파일이 하나만 있어 해당 파일을 대상으로 지정합니다.")
        else:
            # XML 파일이 여러 개인 경우, 파일 이름이 가장 짧은 것을 선택 (연결재무제표)
            xml_files.sort(key=len)
            target_xml_file = xml_files[0]
            print(f"2. 폴더 내에 여러 XML 파일이 있어 연결손익계산서를 대상으로 지정합니다.")
        
        final_path = os.path.join(latest_folder_path, target_xml_file)
        print(f"3. 최종 파싱 대상 파일 경로: {final_path}")
        
        return parser(final_path)

    except FileNotFoundError:
        print(f"오류: '{xbrl_path}' 경로를 찾을 수 없습니다.")
        return None
    except Exception as e:
        print(f"알 수 없는 오류가 발생했습니다: {e}")
        return None

