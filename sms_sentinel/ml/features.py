"""Признаки SMS (задание 6): TF-IDF на словах и символах плюс ручные признаки.

Вход pipeline — таблица со столбцами text_raw и text_clean. Векторизаторы находятся
внутри Pipeline, поэтому fit выполняется только на переданной обучающей выборке,
а словарь сохраняется в одном файле с моделью.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MaxAbsScaler

from ml.preprocessing import normalize_sms
from ml.rules import find_rule_groups

# Токены вида <url> и знаки ! и ? считаются отдельными словами.
TOKEN_PATTERN = r"<\w+>|\w\w+|[!?]"

MANUAL_FEATURES = (
    "length_chars",
    "upper_ratio",
    "exclamation_count",
    "has_url",
    "has_money",
    "has_phone",
    "rule_group_count",
)


def to_frame(texts: list[str]) -> pd.DataFrame:
    """Готовит исходные тексты к подаче в pipeline. Использует normalize_sms."""
    return pd.DataFrame({"text_raw": texts, "text_clean": [normalize_sms(text) for text in texts]})


def _manual_row(text_raw: str, text_clean: str) -> list[float]:
    letters = sum(char.isalpha() for char in text_raw)
    upper = sum(char.isupper() for char in text_raw)
    return [
        len(text_raw),
        upper / letters if letters else 0.0,
        text_raw.count("!"),
        float("<url>" in text_clean),
        float("<money>" in text_clean),
        float("<phone>" in text_clean),
        len(find_rule_groups(text_clean)),
    ]


class ManualFeatures(BaseEstimator, TransformerMixin):
    """Считает ручные признаки по столбцам text_raw и text_clean."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = [_manual_row(raw, clean) for raw, clean in zip(X["text_raw"], X["text_clean"])]
        return np.array(rows, dtype=float).reshape(len(rows), len(MANUAL_FEATURES))

    def get_feature_names_out(self, input_features=None):
        return np.array(MANUAL_FEATURES, dtype=object)


def build_feature_pipeline() -> Pipeline:
    """Возвращает pipeline признаков. Обучается только через fit на train."""
    word_tfidf = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
        lowercase=False,
        token_pattern=TOKEN_PATTERN,
    )
    char_tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        sublinear_tf=True,
        lowercase=False,
    )
    manual = Pipeline([("extract", ManualFeatures()), ("scale", MaxAbsScaler())])

    union = ColumnTransformer(
        [
            ("word", word_tfidf, "text_clean"),
            ("char", char_tfidf, "text_clean"),
            ("manual", manual, ["text_raw", "text_clean"]),
        ],
        sparse_threshold=1.0,
    )
    return Pipeline([("features", union)])


def build_sms_pipeline(classifier) -> Pipeline:
    """Добавляет классификатор к pipeline признаков."""
    return Pipeline([*build_feature_pipeline().steps, ("classifier", classifier)])
