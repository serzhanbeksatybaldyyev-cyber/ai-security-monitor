"""
Отбор признаков. Все методы подгоняются ТОЛЬКО на train-выборке.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif


def correlated_pairs(X_train: pd.DataFrame, threshold: float = 0.9) -> list[tuple[str, str, float]]:
    """Пары числовых признаков с |r| > threshold (мультиколлинеарность)."""
    corr = X_train.corr(numeric_only=True)
    pairs = []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if abs(r) > threshold:
                pairs.append((cols[i], cols[j], round(float(r), 3)))
    return pairs


def mutual_information(X_train: pd.DataFrame, y_train, random_state: int = 42) -> pd.Series:
    """MI каждого числового признака с меткой (медианная импутация по train)."""
    Xn = X_train.fillna(X_train.median(numeric_only=True))
    mi = mutual_info_classif(Xn, y_train, random_state=random_state)
    return pd.Series(mi, index=X_train.columns).sort_values(ascending=False)


def selected_names(pipe) -> list[str]:
    """Имена признаков, оставленных SelectKBest внутри обученного Pipeline."""
    names = pipe.named_steps["preprocessor"].get_feature_names_out()
    mask = pipe.named_steps["selector"].get_support()
    return [n.split("__", 1)[1] for n in np.asarray(names)[mask]]
