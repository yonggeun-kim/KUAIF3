import os
import pandas as pd
import config
import corpcode as cc ##corpcode 관련 함수들
import reportfinder as rpf ###report finder 함수들

######config######
homePath = os.getcwd()
DartFile_path = os.path.join(homePath, 'DartFile')
###############

def main():
    ### Dart api key
    print(homePath) ### testcode
    if not os.path.isdir(DartFile_path):
        os.mkdir(DartFile_path)


    # 1. 전체 기업 코드 다운로드
    cc.download_cc()


    # 2. CORPCODE.xml에서 corp_code(기업코드) 찾기
    target_corp = input('기업명 입력:')
    corp_code = cc.find_cc(target_corp)

    # 3. 재무제표 공시 검색 및 저장(사업, 반기, 분기보고서)
    BEGINDATE=input("보고서 검색 시작일(8자리로 입력):")
    ENDDATE=input("보고서 검색 종료일(8자리로 입력):")
    rpf.find_finance_report(corp_code, BEGINDATE, ENDDATE)

    # 4. 실적보고서 관련 공시 검색 및 저장
    ##rpf.find_other_report(corp_code, BEGINDATE, ENDDATE)


if __name__ == "__main__":
    main()