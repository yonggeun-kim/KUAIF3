import xml.etree.ElementTree as ET
import pandas as pd
import os
import config
import dart_fss as dart

api_key = config.API_KEY
disc_url = 'https://opendart.fss.or.kr/api/list.json'
# xbrl 원본 ZIP (binary)  # <<< CHANGED
xbrl_url = 'https://opendart.fss.or.kr/api/fnlttXbrl.xml'   # <<< CHANGED
DartFile_path = os.path.join(config.homePath, 'DartFile')


def get_income_statement_df_by_name(corp_name: str,
                                    bgn_de: str ,
                                    end_de: str | None = None,
                                    consolidated: bool = True) -> pd.DataFrame:
    """
    corp_name: 'KB금융', '삼성전자' 등 정확 회사명
    bgn_de / end_de: 'YYYYMMDD'
    consolidated: True=연결 우선 (실패 시 개별로 폴백)
    """
    
    dart.set_api_key(api_key=config.API_KEY)

    # 1) 회사 객체
    corp_list = dart.get_corp_list()
    hits = corp_list.find_by_corp_name(corp_name, exactly=True)
    # --- 후보 기업 전부 모으기(정확일치 먼저, 그 다음 유사검색) ----------------------
    hits_exact = corp_list.find_by_corp_name(corp_name, exactly=True) or []     
    hits_fuzzy = corp_list.find_by_corp_name(corp_name, exactly=False) or []    
    candidates = []                                                              
    seen_codes = set()                                                           
    for c in (hits_exact + hits_fuzzy):                                          
        if c.corp_code not in seen_codes:
            candidates.append(c)
            seen_codes.add(c.corp_code)
    if not candidates:                                                           
        raise ValueError(f"기업명을 찾지 못했습니다: {corp_name}")

    errors = []                                                                   

    # --- 후보들을 순차 시도: 성공하면 즉시 반환 -----------------------------------
    for corp in candidates:                                                      
        try:
            # 1) 사업보고서만 검색 (a001)
            filings = corp.search_filings(
                bgn_de=bgn_de,
                end_de=end_de,
                pblntf_detail_ty='a001',   # 사업보고서만
                last_reprt_at='Y'          # (가능하면) 최종보고서만
            )
            if len(filings) == 0:
                raise ValueError("검색 기간 내 사업보고서 없음")

            # 최신 1건 선택
            filing = sorted(filings, key=lambda f: getattr(f, 'rcept_dt', ''), reverse=True)[0]

            # 2) XBRL → 손익계산서(IS) 우선, 안 되면 개별 폴백
            xbrl = getattr(filing, "xbrl", None)
            tables = []
            if xbrl is not None:
                tables = xbrl.get_income_statement(separate=not consolidated)
                if not tables and consolidated:
                    tables = xbrl.get_income_statement(separate=True)

            # 3) IS가 전혀 안 잡히면 extract_fs로 IS→CIS 순서로 폴백
            if not tables:
                fs = corp.extract_fs(bgn_de=bgn_de, end_de=end_de, fs_tp=('is','cis'))
                df_is = fs.get('is') if hasattr(fs, 'get') else None
                if isinstance(df_is, pd.DataFrame) and not df_is.empty:
                    best_df = df_is
                else:
                    df_cis = fs.get('cis') if hasattr(fs, 'get') else None
                    if isinstance(df_cis, pd.DataFrame) and not df_cis.empty:
                        best_df = df_cis
                    else:
                        raise ValueError("extract_fs: IS/CIS 모두 비어있음")
            else:
                # XBRL에서 표가 잡힌 경우: 가장 큰 표 사용
                dfs = [t.to_DataFrame() for t in tables]
                best_df = max(dfs, key=lambda d: d.shape[0])

            # 4) 공통 클린업 후 성공 반환
            best_df.columns = [str(c).strip() for c in best_df.columns]
            best_df = best_df[~best_df.apply(lambda r: r.astype(str).str.contains("단위").any(), axis=1)]

            # (옵션) 어떤 코드로 성공했는지 로그
            print(f"[OK] {corp.corp_name}({corp.corp_code}) 사업보고서에서 추출 성공: "
                  f"{getattr(filing, 'rcept_dt', '')} {getattr(filing, 'report_nm', '')}")
            return best_df

        except Exception as e:
            errors.append(f"{corp.corp_name}({corp.corp_code}): {e}")            
            continue                                                             

    # 여기까지 왔다면 모든 후보 실패
    raise ValueError("모든 후보 코드에서 추출 실패:\n - " + "\n - ".join(errors))

def debug_income_statement(corp_name: str, bgn_de: str, end_de: str | None = None) -> None:
    """기업 선택, 사업보고서(a001) 목록, XBRL 유무, 역할(role) 이름을 빠르게 점검"""
    try:
        dart.set_api_key(api_key=config.API_KEY)
    except Exception:
        pass

    try:
        corp_list = dart.get_corp_list()
        hits = corp_list.find_by_corp_name(corp_name, exactly=False)
        print("\n[DEBUG] 후보 기업들:", [(c.corp_name, c.corp_code) for c in hits[:5]])
        if not hits:
            print("[DEBUG] 기업 검색 결과 없음"); return
        corp = hits[0]

        filings = corp.search_filings(
            bgn_de=bgn_de, end_de=end_de,
            pblntf_detail_ty='a001',  # 사업보고서
            last_reprt_at='Y'
        )
        if len(filings) == 0:
            print("[DEBUG] 기간 내 사업보고서 없음"); return

        # 최신순 상위 3건만 출력
        filings = sorted(filings, key=lambda f: getattr(f, 'rcept_dt', ''), reverse=True)
        print("[DEBUG] 사업보고서 상위 3건:")
        for f in filings[:3]:
            print(" -", getattr(f, 'rcept_dt', ''), getattr(f, 'report_nm', ''), 
                  "xbrl?", bool(getattr(f, 'xbrl', None)), "rcept_no:", getattr(f, 'rcept_no', ''))

        # 가장 최신 건의 역할(role) 이름 훑기
        xbrl = getattr(filings[0], 'xbrl', None)
        if xbrl is None:
            print("[DEBUG] 최신 사업보고서에 XBRL 연결이 없음"); return

        roles = getattr(xbrl, 'roles', []) or []
        print(f"[DEBUG] 역할(roles) 개수: {len(roles)}")
        for role in roles[:20]:  # 너무 길어지지 않게 20개 제한
            rid = getattr(role, 'id', '')
            rdef = getattr(role, 'definition', '')
            print("   ·", rid, "=>", rdef)
    except Exception as e:
        print("[DEBUG] 진단 중 예외:", e)