#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import config
import reportfinder as rpf ###report finder 함수들
import parser as ps #### 파싱함수
from datetime import date

##################
######config######
##################
homepath = config.homePath
DartFile_path = os.path.join(homepath, 'DartFile')
#BEGINDATE=input("보고서 검색 시작일(8자리로 입력):")
#ENDDATE=input("보고서 검색 종료일(8자리로 입력):")
today = date.today()
try:
    one_year_ago = today.replace(year=today.year - 1)
except ValueError:
    # 만약 오늘이 2월 29일인 경우
    one_year_ago = today.replace(year=today.year - 1, day=28)
###############
###############
###############
def main():
    ### Dart api key
    print("실행위치: " + homepath)
    if not os.path.isdir(DartFile_path):
        os.mkdir(DartFile_path)
    

    # 1. 전체 기업 코드 다운로드
    rpf.download_cc()

    # 2. CORPCODE.xml에서 corp_code(기업코드) 찾기
    target_corp = input('정확한 기업명 입력:')
    corp_code = rpf.find_cc(target_corp)
    if not os.path.isdir(os.path.join(DartFile_path, corp_code)):
        os.mkdir(os.path.join(DartFile_path, corp_code))
    
    # 3. 사업보고서 검색 및 저장(사업보고서)
    enddate = today.strftime("%Y%m%d")
    begindate = one_year_ago.strftime("%Y%m%d")
    rpf.find_finance_report(corp_code, begindate, enddate)

    # 4.사업보고서 파싱 및 손익계산서 데이터프레임 변환
    profit_table = ps.searchandParse(os.path.join(DartFile_path, corp_code)) # class = dataframe
    
    
    #test5. DataFrame 출력 및 CSV 파일로 저장
    if profit_table is not None and not profit_table.empty:
        print("\n--- 손익계산서 파싱 결과 ---")
        print(profit_table.to_string())
        
        # CSV 파일 저장 로직
        try:
            # 저장할 파일명 설정 (예: 00126380_삼성전자_손익계산서.csv)
            csv_filename = f"{corp_code}_{target_corp}_손익계산서.csv"
            # 저장할 전체 경로 설정
            save_path = os.path.join(DartFile_path, csv_filename)
            
            # CSV 파일로 저장
            profit_table.to_csv(save_path, index=False, encoding='utf-8-sig')
            
            print(f"\n성공: 손익계산서 데이터를 다음 경로에 저장했습니다:\n{os.path.abspath(save_path)}")
        
        except Exception as e:
            print(f"\n오류: CSV 파일 저장에 실패했습니다. - {e}")
    else:
        print("\n손익계산서 데이터를 추출하지 못했습니다.")

    #6

  
if __name__ == "__main__":
    main()