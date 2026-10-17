"""
Загрузка и очистка сырых NetFlow-записей.

Здесь выполняются только операции, НЕ обучаемые на данных (нет fit):
приведение типов, удаление повторов одного события, отбрасывание
некорректных значений. Импутация и масштабирование — внутри sklearn
Pipeline и подгоняются только на train.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NUMERIC_RAW = ["dst_port", "duration", "packet_count", "src_bytes", "dst_bytes",
               "total_requests", "failed_requests"]


def load_raw(path) -> pd.DataFrame:
    # пропуском считаем только пустую ячейку: строку "n/a" ловим явно в clean()
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def quality_report(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_events": int(df["group_id"].nunique()) if "group_id" in df else None,
        "event_repeats": int(len(df) - df["group_id"].nunique()) if "group_id" in df else None,
        "missing_by_column": {c: int(v) for c, v in df.isna().sum().items() if v},
        "rows_with_missing": int(df.isna().any(axis=1).sum()),
    }


def clean(df: pd.DataFrame, dedupe_events: bool = True) -> tuple[pd.DataFrame, dict]:
    """Очистка: типы, некорректные значения, повторы событий.

    dedupe_events=False оставляет повторы — используется только в
    демонстрации утечки данных (раздел Data Leakage).
    """
    out = df.copy()
    report = {"rows_before": int(len(out))}
    for c in NUMERIC_RAW:
        out[c] = pd.to_numeric(out[c], errors="coerce")       # 'n/a' -> NaN
    report["bad_types_to_nan"] = int(out["packet_count"].isna().sum() - df["packet_count"].isna().sum())
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    # отрицательные длительности/объёмы физически невозможны -> NaN
    for c in ["duration", "src_bytes", "dst_bytes", "packet_count"]:
        out.loc[out[c] < 0, c] = np.nan
    if dedupe_events:
        before = len(out)
        out = out.sort_values("timestamp").drop_duplicates("group_id", keep="first")
        report["event_repeats_removed"] = int(before - len(out))
    out = out.sort_values("timestamp").reset_index(drop=True)
    report["rows_after"] = int(len(out))
    return out, report
