"""Базовая модель SMS (задание 7).

Запуск из корня проекта: python -m ml.baseline
Обучает первую модель только на английском train, считает метрики на val и сохраняет
ml/artifacts/sms_baseline.joblib. Тестовая выборка здесь не используется.
Рабочая многоязычная модель обучается командой python -m ml.multilingual.
"""
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from ml.data.load_sms import PROJECT_ROOT
from ml.features import build_sms_pipeline, to_frame
from ml.split import load_parts

ENGLISH_BASELINE_PATH = PROJECT_ROOT / "ml" / "artifacts" / "sms_baseline.joblib"  # первая модель, только английский
MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "sms_multilingual.joblib"  # рабочая модель сайта: en + ru + kk
META_PATH = MODEL_PATH.with_suffix(".meta.json")
VERSION = "sms_multilingual_v2"
ALGORITHM = "TF-IDF (слова 1–2, символы 3–5) + 7 признаков + LogisticRegression(class_weight=balanced), корпус en+ru+kk"
THRESHOLD = 0.5


def train_baseline(train_df):
    """Обучает Logistic Regression вместе с векторизаторами."""
    classifier = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    return build_sms_pipeline(classifier).fit(train_df[["text_raw", "text_clean"]], train_df["label"])


def compute_metrics(y_true, y_pred) -> dict:
    """Метрики для класса «мошенничество» и Confusion Matrix в абсолютных числах."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


@lru_cache(maxsize=1)
def load_baseline(path: Path = MODEL_PATH):
    """Загружает модель один раз. Файл создаётся этим же проектом."""
    return joblib.load(path)


def predict_sms(text: str, model=None) -> dict:
    """Возвращает метку (0 — безопасное, 1 — мошенничество) и вероятность мошенничества."""
    pipeline = load_baseline() if model is None else model
    probability = float(pipeline.predict_proba(to_frame([text]))[0, 1])
    return {"label": int(probability >= THRESHOLD), "probability": probability}


def save_metadata(metrics: dict, train_size: int, val_size: int) -> None:
    card = {
        "model_type": "sms",
        "version": VERSION,
        "algorithm": ALGORITHM,
        "threshold": THRESHOLD,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_size": train_size,
        "val_size": val_size,
        "metrics": {name: round(value, 4) if isinstance(value, float) else value for name, value in metrics.items()},
    }
    META_PATH.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parts = load_parts()
    model = train_baseline(parts["train"])
    val = parts["val"]
    metrics = compute_metrics(val["label"], model.predict(val[["text_raw", "text_clean"]]))
    joblib.dump(model, ENGLISH_BASELINE_PATH, compress=3)
    for name, value in metrics.items():
        print(f"{name}: {value:.4f}" if isinstance(value, float) else f"{name}: {value}")
    print(f"Сохранено: {ENGLISH_BASELINE_PATH.relative_to(PROJECT_ROOT)} (только английский; рабочая модель: python -m ml.multilingual)")


if __name__ == "__main__":
    main()
