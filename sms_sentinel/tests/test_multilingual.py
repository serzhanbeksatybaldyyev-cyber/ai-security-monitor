"""Проверки русского и казахского корпусов и многоязычной модели."""
import json
import re

import pandas as pd
import pytest

from ml.baseline import MODEL_PATH, predict_sms
from ml.language import detect_language
from ml.multilingual import MULTI_CSV, MULTI_SPLIT

RAW = MULTI_CSV.parents[1] / "raw"


@pytest.fixture(scope="module")
def synthetic():
    return {lang: pd.read_csv(RAW / f"synthetic_{lang}.csv", keep_default_na=False) for lang in ("ru", "kk")}


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_size_and_balance_match_english(synthetic, lang):
    df = synthetic[lang]
    assert len(df) == 5137
    assert int(df["label"].sum()) == 621
    assert df["text"].is_unique


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_no_real_phones_or_scam_domains(synthetic, lang):
    for text in synthetic[lang]["text"]:
        for phone in re.findall(r"\+7[\d ]{9,}", text):
            assert phone.startswith("+7 000")
        for url in re.findall(r"http://\S+", text):
            assert url.rstrip(".,!").split("/")[2].endswith((".example", ".test"))


def test_kazakh_texts_are_detected_as_kazakh(synthetic):
    share = (synthetic["kk"]["text"].map(detect_language) == "kk").mean()
    assert share > 0.95


def test_templates_do_not_leak_between_splits():
    corpus = pd.read_csv(MULTI_CSV, keep_default_na=False)
    split = json.loads(MULTI_SPLIT.read_text(encoding="utf-8"))
    part_of = {i: name for name in ("train", "val", "test") for i in split[name]}
    corpus["part"] = corpus["id"].map(part_of)
    synthetic_rows = corpus[corpus["group"] != ""]
    assert (synthetic_rows.groupby("group")["part"].nunique() == 1).all()
    assert set(corpus["language"]) == {"en", "ru", "kk"}


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="нет файла модели")
@pytest.mark.parametrize("text, expected", [
    ("Ваша карта заблокирована! Срочно подтвердите данные: http://card-unlock.example", 1),
    ("Привет! Встречаемся завтра в 18:00 у входа в библиотеку.", 0),
    ("Картаңыз бұғатталды. Деректерді дереу растаңыз: http://bank-verify.example", 1),
    ("Сәлем! Ертең кешке кітапхана жанында кездесейік пе?", 0),
])
def test_model_handles_russian_and_kazakh(text, expected):
    assert predict_sms(text)["label"] == expected
