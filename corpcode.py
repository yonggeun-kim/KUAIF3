import os
import pandas as pd
################
import requests
import zipfile
import xml.etree.ElementTree as ET
import config

api_key = config.API_KEY

def download_cc():
    corp_code_url = f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}'
    with open('corpCode.zip', 'wb') as f:
        f.write(requests.get(corp_code_url).content)
    with zipfile.ZipFile('corpCode.zip', 'r') as zip_ref:
        zip_ref.extractall(config.homePath)
    if os.path.exists('corpCode.zip'):
        os.remove('corpCode.zip')
    print(f'기업코드 다운 완료')

def find_cc(target_corp):
    tree = ET.parse(os.path.join(config.homePath, 'CORPCODE.xml'))
    root = tree.getroot()
    corp_code = None

    for el in tree.getroot().findall('list'):
        if el.find('corp_name').text == target_corp:
            corp_code = el.find('corp_code').text
            print(f'{target_corp} corp_code:', corp_code)
            break
    return corp_code

