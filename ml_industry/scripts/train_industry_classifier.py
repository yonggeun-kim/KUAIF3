# C:\workspace\KUAIF3\ml_industry\scripts\train_industry_classifier.py
import os
import re
import glob
import joblib
import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# ===== 경로 설정 =====
BASE_DIR = Path(__file__).resolve().parent.parent
TRAIN_DIR = BASE_DIR / "train_data"
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True, parents=True)

def read_csv_flex(path: Path) -> pd.DataFrame:
    """다양한 인코딩으로 CSV 읽기"""
    last_err = None
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"CSV 읽기 실패: {path} / {last_err}")

def extract_label_from_filename(filename: str):
    """
    예: '_기업은행_1.csv' → 1
    """
    m = re.search(r"_(\d+)\.csv$", filename)
    if not m:
        raise ValueError(f"파일명에서 라벨을 추출할 수 없습니다: {filename}")
    return int(m.group(1))

def collect_training_data():
    texts, labels = [], []
    files = glob.glob(str(TRAIN_DIR / "*.csv"))

    if not files:
        raise RuntimeError(f"학습용 CSV가 없습니다: {TRAIN_DIR}")

    for file_path in files:
        label = extract_label_from_filename(os.path.basename(file_path))
        df = read_csv_flex(Path(file_path))

        # 텍스트 추출: 첫 열 + 항목/계정명 포함된 열 일부
        cols = [df.columns[0]]
        for c in df.columns[1:6]:
            s = str(c).lower()
            if any(k in s for k in ["label", "라벨", "항목", "계정", "name"]):
                cols.append(c)
        cols = list(dict.fromkeys(cols))

        parts = []
        head = min(150, len(df))
        for c in cols:
            parts += df[c].astype(str).head(head).tolist()

        text = " | ".join(parts)
        texts.append(text)
        labels.append(label)

    return texts, labels

def train_and_save_model():
    texts, labels = collect_training_data()

    # 벡터화
    vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1,2))
    X = vectorizer.fit_transform(texts)
    y = labels

    # 학습/검증 분리
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", multi_class="auto")
    clf.fit(X_train, y_train)

    # 평가
    y_pred = clf.predict(X_test)
    print("[INFO] Accuracy:", accuracy_score(y_test, y_pred))
    print(classification_report(y_test, y_pred))

    # 모델 저장
    joblib.dump(vectorizer, MODEL_DIR / "industry_vectorizer.pkl")
    joblib.dump(clf, MODEL_DIR / "industry_classifier.pkl")
    print(f"[OK] 모델 저장 완료 → {MODEL_DIR}")

if __name__ == "__main__":
    train_and_save_model()
