import requests
import zipfile
import xml.etree.ElementTree as ET
import time
import os
from config import API_KEY

api_key = API_KEY

def find_finance_report(homepath, corp_code): ###### begin end는 8자리 날짜로 구성
    disc_url = 'https://opendart.fss.or.kr/api/list.json'
    xbrl_url = 'https://opendart.fss.or.kr/api/document.xml'
    DartFile_path = os.path.join(homepath, 'DartFile')

    reports_path = os.path.join(DartFile_path, str(corp_code) + '_reports') ####찾은 보고서들 저장 위치
    if not os.path.isdir(reports_path): 
        os.mkdir(reports_path)
    
    # 페이지네이션 설정
    max_pages = 10  # 최대 10페이지 (1000건까지 시도)

    for page in range(1, max_pages + 1):
        params = {
            'crtfc_key': api_key,
            'corp_code': corp_code,
            'bgn_de': '20240101', # 시작일
            'end_de': '20241231', # 종료일
            'page_count': 100,
            'page_no': page
        }

        res = requests.get(disc_url, params=params).json()

        if res.get('status') != '000':
            print(f"API 오류 (page {page}): {res.get('message')}")
            break

        if not res.get('list'):
            print(f"데이터 없음 (page {page}) → 중단")
            break  # 더 이상 데이터 없으면 중단

        for item in res.get('list', []):
            report_nm = item['report_nm']
            rcept_dt = item['rcept_dt']
            rcept_no = item['rcept_no']

            if '사업보고서' in report_nm or '반기보고서' in report_nm or '분기보고서' in report_nm:
                print(f"다운로드: {report_nm} ({rcept_dt}) → rcept_no: {rcept_no}")

                #### 각각의 zip 다운 및 압축해제
                file_params = {
                    'crtfc_key': api_key,
                    'rcept_no': rcept_no
                }

                xbrl_zip_path = os.path.join(reports_path, f'{rcept_no}.zip')
                with open(xbrl_zip_path, 'wb') as f:
                    f.write(requests.get(xbrl_url, params=file_params).content)
                print(f'{xbrl_zip_path} 다운로드 완료!')

                extract_folder_path = os.path.join(reports_path, f'xbrl_{rcept_no}')
                with zipfile.ZipFile(xbrl_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder_path)

                # zip 파일 삭제
                if os.path.exists(xbrl_zip_path):
                    os.remove(xbrl_zip_path)
                print(f'{extract_folder_path} 폴더에 압축 해제 완료!')

        # rate limit 대응 (0.7초 대기)
        time.sleep(0.7)
    
