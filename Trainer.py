#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import config
import reportfinder as rpf
import datamanage as dm
from datetime import date

######config######
##################

homepath = config.homePath
DartFile_path = os.path.join(homepath, 'Trainfile')
today = date.today()
try:
    one_year_ago = today.replace(year=today.year - 2)
except ValueError:
    one_year_ago = today.replace(year=today.year - 2, day=28)

##################
##################

labels = [
    ("삼성전자", 0),
    ("SK하이닉스", 0),
    ("LG에너지솔루션", 0),
    ("삼성바이오로직스", 0),
    ("한화에어로스페이스", 0),
    ("현대차", 0),
    ("KB금융", 1),
    ("두산에너빌리티", 0),
    ("HD현대중공업", 0),
    ("기아", 0),
    ("셀트리온", 0),
    ("NAVER", 2),
    ("신한지주", 1),
    ("한화오션", 0),
    ("카카오", 2),
    ("현대모비스", 0),
    ("삼성물산", 2),
    ("HD한국조선해양", 0),
    ("한국전력", 2),
    ("삼성생명", 1),
    ("POSCO홀딩스", 0),
    ("하나금융지주", 1),
    ("알테오젠", 0),
    ("HMM", 2),
    ("메리츠금융지주", 1),
    ("삼성화재", 1),
    ("현대로템", 0),
    ("LG화학", 0),
    ("SK스퀘어", 1),
    ("삼성SDI", 0),
    ("HD현대일렉트릭", 0),
    ("케이티앤지", 0),
    ("삼성중공업", 0),
    ("SK이노베이션", 0),
    ("고려아연", 0),
    ("기업은행", 1),
    ("크래프톤", 2),
    ("포스코퓨처엠", 0),
    ("KT", 2),
    ("SK", 2),
    ("에코프로비엠", 0),
    ("LG전자", 0),
    ("카카오뱅크", 1),
    ("삼성전기", 0),
    ("SK텔레콤", 2),
    ("삼성에스디에스", 2),
    ("LG", 2),
]

def main():
    print("실행위치: " + homepath)
    os.makedirs(DartFile_path, exist_ok=True)

    # 1. 기간 설정
    enddate = today.strftime("%Y%m%d")
    begindate = one_year_ago.strftime("%Y%m%d")

    # 2. 기업명 순환
    for target_corp, type in labels:
    
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

        # 4. dataframe 정제
        head_profit_table = dm.drop_rows_where_class3_filled(profit_table)

        
        # 4.1 CSV 저장(임시)
        if head_profit_table is not None and not head_profit_table.empty:
            try:
                csv_filename = f"_{target_corp}_{type}.csv"
                save_path = os.path.join(DartFile_path, csv_filename)
                head_profit_table.to_csv(save_path, index=False, encoding='utf-8-sig')
                print(f"\n성공: 손익계산서 데이터를 다음 경로에 저장했습니다:\n{os.path.abspath(save_path)}")
            except Exception as e:
                print(f"\n오류: CSV 파일 저장에 실패했습니다. - {e}")
        else:
            print("\n손익계산서 데이터를 추출하지 못했습니다.")
            rpf.debug_income_statement(target_corp, begindate, enddate)

if __name__ == "__main__":
    main()