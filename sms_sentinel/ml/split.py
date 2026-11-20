"""Стратифицированное разбиение SMS 70/15/15 (задание 6).

Запуск из корня проекта: python -m ml.split
Индексы сохраняются в data/processed/sms_split.json.
"""
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from ml.data.load_sms import PROJECT_ROOT

CLEAN_CSV = PROJECT_ROOT / "data" / "processed" / "sms_clean.csv"
SPLIT_JSON = PROJECT_ROOT / "data" / "processed" / "sms_split.json"
RANDOM_STATE = 42


def load_clean(path: Path = CLEAN_CSV) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8", keep_default_na=False)


def make_split(df: pd.DataFrame, random_state: int = RANDOM_STATE) -> dict[str, list[int]]:
    """Возвращает id записей для train, val и test в пропорции 70/15/15."""
    train, holdout = train_test_split(df, test_size=0.30, stratify=df["label"], random_state=random_state)
    val, test = train_test_split(holdout, test_size=0.50, stratify=holdout["label"], random_state=random_state)
    return {
        "train": sorted(train["id"].tolist()),
        "val": sorted(val["id"].tolist()),
        "test": sorted(test["id"].tolist()),
    }


def save_split(split: dict[str, list[int]], path: Path = SPLIT_JSON) -> None:
    payload = {"random_state": RANDOM_STATE, "source": "data/processed/sms_clean.csv", **split}
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_parts(df: pd.DataFrame | None = None, path: Path = SPLIT_JSON) -> dict[str, pd.DataFrame]:
    """Возвращает выборки train, val и test по сохранённым индексам."""
    data = load_clean() if df is None else df
    split = json.loads(path.read_text(encoding="utf-8"))
    return {name: data[data["id"].isin(split[name])].reset_index(drop=True) for name in ("train", "val", "test")}


def main() -> None:
    df = load_clean()
    split = make_split(df)
    save_split(split)
    for name, part in load_parts(df).items():
        print(f"{name}: {len(part)} записей, доля spam {part['label'].mean():.2%}")


if __name__ == "__main__":
    main()
