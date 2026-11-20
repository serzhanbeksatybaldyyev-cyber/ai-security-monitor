"""Загрузка набора UCI SMS Spam Collection (задание 3).

Запуск из корня проекта: python -m ml.data.load_sms
Скрипт читает data/raw/SMSSpamCollection и сохраняет data/processed/sms_raw.csv.
"""
import csv
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "SMSSpamCollection"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "sms_raw.csv"

ENCODING = "utf-8"
LABEL_MAP = {"ham": 0, "spam": 1}


def load_sms(path: Path = RAW_PATH) -> pd.DataFrame:
    """Читает исходный файл и возвращает столбцы id, text, label (0 — ham, 1 — spam)."""
    # QUOTE_NONE обязателен: в текстах SMS есть кавычки, без него строки склеиваются.
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["label_raw", "text"],
        encoding=ENCODING,
        quoting=csv.QUOTE_NONE,
        dtype=str,
        keep_default_na=False,
    )

    with open(path, encoding=ENCODING, newline="") as source:
        lines_in_file = sum(1 for line in source if line.strip())
    if len(df) != lines_in_file:
        raise ValueError(f"Прочитано {len(df)} строк, в файле {lines_in_file}.")

    unknown = set(df["label_raw"]) - set(LABEL_MAP)
    if unknown:
        raise ValueError(f"Неизвестные метки: {sorted(unknown)}")

    df["label"] = df["label_raw"].map(LABEL_MAP).astype(int)
    df.insert(0, "id", range(1, len(df) + 1))
    return df[["id", "text", "label"]]


def describe(df: pd.DataFrame, examples: int = 5) -> None:
    """Выводит объём, типы, примеры и распределение классов."""
    print(f"Строк: {len(df)}")
    print("\nТипы столбцов:")
    print(df.dtypes.to_string())

    for label, name in [(0, "ham (безопасное)"), (1, "spam (мошенничество)")]:
        print(f"\nПримеры класса {label}, {name}:")
        for text in df.loc[df["label"] == label, "text"].head(examples):
            print(f"  - {text[:110]}")

    counts = df["label"].value_counts().sort_index()
    print("\nРаспределение классов:")
    for label, count in counts.items():
        print(f"  {label}: {count} ({count / len(df):.2%})")


def main() -> None:
    df = load_sms()
    describe(df)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"\nСохранено: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
