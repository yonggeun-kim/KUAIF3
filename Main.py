#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import config
import reportfinder as rpf  # corp_code 찾는 용도만 사용
from datetime import date


######config######
##################

homepath = config.homePath
DartFile_path = os.path.join(homepath, 'DartFile')
today = date.today()
try:
    one_year_ago = today.replace(year=today.year - 2)
except ValueError:
    one_year_ago = today.replace(year=today.year - 2, day=28)

##################
##################


def main():
    print("실행위치: " + homepath)
    os.makedirs(DartFile_path, exist_ok=True)

    # 1. 기업명 입력
    target_corp = input('정확한 기업명 입력:')
    
    # 2. 기간 설정
    enddate = today.strftime("%Y%m%d")
    begindate = one_year_ago.strftime("%Y%m%d")

    # 3. dart-fss로 사업보고서의 손익계산서만 DataFrame으로 가져오기(연결 기준)
    try:
        profit_table = rpf.get_income_statement_df_by_name(
            corp_name=target_corp,
            bgn_de=begindate,
            end_de=enddate,
            consolidated=True  # 필요 시 False로 바꿔 개별 재무제표 추출
        )
    except Exception as e:
        print(f"\n손익계산서 추출 실패: {e}")
        profit_table = None

    # 4. 출력 및 CSV 저장
    if profit_table is not None and not profit_table.empty:
        print("\n--- 손익계산서 파싱 결과 ---")
        try:
            # 콘솔에 보기 좋게 출력 (컬럼 폭 제한 완화)
            with pd.option_context("display.max_rows", 60, "display.max_columns", 12, "display.width", 160):
                print(profit_table.to_string())
        except Exception:
            print(profit_table.head())

        try:
            csv_filename = f"_{target_corp}_손익계산서.csv"
            save_path = os.path.join(DartFile_path, csv_filename)
            profit_table.to_csv(save_path, index=False, encoding='utf-8-sig')
            print(f"\n성공: 손익계산서 데이터를 다음 경로에 저장했습니다:\n{os.path.abspath(save_path)}")
        except Exception as e:
            print(f"\n오류: CSV 파일 저장에 실패했습니다. - {e}")
    else:
        print("\n손익계산서 데이터를 추출하지 못했습니다.")
        rpf.debug_income_statement(target_corp, begindate, enddate)

if __name__ == "__main__":
    main()