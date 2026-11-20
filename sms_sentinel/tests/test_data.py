"""Проверки наборов данных (задание 3)."""
import csv
import io
import re
import zipfile
from pathlib import Path

import pandas as pd

from ml.data.load_sms import RAW_PATH, load_sms
from ml.data.verify_source import MEMBER, compare_with_archive

CUSTOM_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "custom_ru_kk.csv"
RESERVED_HOST = re.compile(r"\.(example|test)$|(^|\.)example\.(com|org)$")


def custom() -> pd.DataFrame:
    return pd.read_csv(CUSTOM_PATH, encoding="utf-8")


def test_load_sms_keeps_every_line_and_binary_labels():
    df = load_sms()
    with open(RAW_PATH, encoding="utf-8") as source:
        assert len(df) == sum(1 for _ in source)
    assert list(df.columns) == ["id", "text", "label"]
    assert set(df["label"]) == {0, 1}
    assert df["id"].is_unique


def test_load_sms_does_not_merge_rows_on_quotes(tmp_path):
    path = tmp_path / "sample.tsv"
    path.write_text('ham\t"quoted start\nspam\tsecond "line\n', encoding="utf-8")
    df = load_sms(path)
    assert df["label"].tolist() == [0, 1]
    assert df["text"].tolist() == ['"quoted start', 'second "line']


def test_compare_with_archive_detects_equal_and_changed_file():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MEMBER, b"ham\thello\n")
    assert compare_with_archive(buffer.getvalue(), b"ham\thello\n")
    assert not compare_with_archive(buffer.getvalue(), b"ham\tchanged\n")


def test_custom_set_size_and_balance():
    df = custom()
    assert (df["language"] == "ru").sum() >= 100
    assert (df["language"] == "kk").sum() >= 50
    assert set(df["label"]) == {0, 1}
    for _, part in df.groupby("language"):
        assert 0.45 <= part["label"].mean() <= 0.55
    assert df["label_author"].notna().all()
    assert df["text"].is_unique


def test_custom_set_has_no_real_links_cards_or_phones():
    with open(CUSTOM_PATH, encoding="utf-8", newline="") as source:
        texts = [row["text"] for row in csv.DictReader(source)]
    for text in texts:
        for host in re.findall(r"https?://([^/\s]+)", text):
            assert RESERVED_HOST.search(host), host
        assert not re.search(r"\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}", text)
        for phone in re.findall(r"\+?\d[\d ()-]{8,}\d", text):
            assert set(re.sub(r"\D", "", phone)[1:]) == {"0"}, phone
