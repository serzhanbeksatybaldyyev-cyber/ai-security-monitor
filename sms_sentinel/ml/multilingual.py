"""Многоязычная модель SMS: английский + русский + казахский (задание 8, расширение).

Запуск из корня проекта: python -m ml.multilingual
1. Собирает единый корпус: английский (sms_clean.csv), русский и казахский (synthetic_*.csv).
2. Делит на train/val/test 70/15/15. Английский делится так же, как раньше (sms_split.json),
   русский и казахский по группам шаблонов, чтобы один шаблон не попал в разные выборки.
3. Обучает тот же pipeline (TF-IDF + 7 признаков + LogisticRegression) на объединённом train.
4. Считает метрики по каждому языку на val и на test (test используется один раз) и на
   независимом рукописном наборе data/raw/custom_ru_kk.csv, который в обучении не участвует.
5. Сохраняет ml/artifacts/sms_multilingual.joblib и .meta.json.
"""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from ml import baseline
from ml.baseline import MODEL_PATH, compute_metrics, save_metadata, train_baseline
from ml.data.load_sms import PROJECT_ROOT
from ml.features import to_frame
from ml.preprocessing import normalize_sms
from ml.split import SPLIT_JSON, load_clean

PROCESSED = PROJECT_ROOT / "data" / "processed"
MULTI_CSV = PROCESSED / "multi_clean.csv"
MULTI_SPLIT = PROCESSED / "multi_split.json"
CUSTOM_CSV = PROJECT_ROOT / "data" / "raw" / "custom_ru_kk.csv"
REPORT = PROJECT_ROOT / "docs" / "08_multilingual_report.md"
OLD_BASELINE = PROJECT_ROOT / "ml" / "artifacts" / "sms_baseline.joblib"
LANGUAGES = ("en", "ru", "kk")
SEED = 42


def build_corpus() -> pd.DataFrame:
    english = load_clean().copy()
    split = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    where = {i: name for name in ("train", "val", "test") for i in split[name]}
    english["id"] = "en-" + english["id"].astype(str).str.zfill(5)
    english["language"] = "en"
    english["group"] = ""
    english["part"] = [where[int(i.split("-")[1])] for i in english["id"]]

    frames = [english]
    for language in ("ru", "kk"):
        raw = pd.read_csv(PROJECT_ROOT / "data" / "raw" / f"synthetic_{language}.csv", encoding="utf-8", keep_default_na=False)
        frame = raw.rename(columns={"text": "text_raw"})[["id", "text_raw", "label", "language", "group"]].copy()
        frame["text_clean"] = frame["text_raw"].map(normalize_sms)
        frame = frame.drop_duplicates("text_clean").reset_index(drop=True)
        frame["part"] = _split_by_group(frame)
        frames.append(frame)
    corpus = pd.concat(frames, ignore_index=True)[["id", "text_raw", "text_clean", "label", "language", "group", "part"]]
    conflicts = corpus.groupby("text_clean")["label"].nunique()
    if (conflicts > 1).any():
        raise ValueError("Одинаковые тексты с разными метками")
    return corpus


def _split_by_group(frame: pd.DataFrame) -> list[str]:
    """Группы шаблонов делятся 70/15/15 отдельно для ham и spam."""
    rng = np.random.default_rng(SEED)
    assignment = {}
    for label in (0, 1):
        groups = sorted(frame.loc[frame["label"] == label, "group"].unique())
        rng.shuffle(groups)
        cut_train, cut_val = round(len(groups) * 0.70), round(len(groups) * 0.85)
        for index, group in enumerate(groups):
            assignment[group] = "train" if index < cut_train else "val" if index < cut_val else "test"
    return [assignment[group] for group in frame["group"]]


def evaluate(model, frame: pd.DataFrame) -> dict:
    predicted = model.predict(frame[["text_raw", "text_clean"]])
    return {**compute_metrics(frame["label"], predicted), "size": int(len(frame)), "spam": int(frame["label"].sum())}


def round_metrics(metrics: dict) -> dict:
    return {key: round(value, 4) if isinstance(value, float) else value for key, value in metrics.items()}


def custom_frame() -> pd.DataFrame:
    custom = pd.read_csv(CUSTOM_CSV, encoding="utf-8", keep_default_na=False)
    frame = pd.DataFrame(to_frame(custom["text"].tolist()))
    frame["label"] = custom["label"].astype(int).values
    frame["language"] = custom["language"].values
    return frame


def main() -> None:
    corpus = build_corpus()
    corpus.to_csv(MULTI_CSV, index=False, encoding="utf-8")
    split = {name: corpus.loc[corpus["part"] == name, "id"].tolist() for name in ("train", "val", "test")}
    MULTI_SPLIT.write_text(json.dumps({"random_state": SEED, **split}), encoding="utf-8")

    train = corpus[corpus["part"] == "train"].reset_index(drop=True)
    model = train_baseline(train)

    by_language = {}
    for language in LANGUAGES:
        for part in ("val", "test"):
            subset = corpus[(corpus["part"] == part) & (corpus["language"] == language)]
            by_language[f"{language}_{part}"] = round_metrics(evaluate(model, subset))
    overall_val = round_metrics(evaluate(model, corpus[corpus["part"] == "val"]))
    overall_test = round_metrics(evaluate(model, corpus[corpus["part"] == "test"]))

    custom = custom_frame()
    custom_new, custom_old = {}, {}
    old = joblib.load(OLD_BASELINE) if OLD_BASELINE.exists() else None
    for language in ("ru", "kk"):
        subset = custom[custom["language"] == language]
        custom_new[language] = round_metrics(evaluate(model, subset))
        if old is not None:
            custom_old[language] = round_metrics(evaluate(old, subset))

    joblib.dump(model, MODEL_PATH, compress=3)
    save_metadata({k: v for k, v in overall_val.items() if k not in ("size", "spam")}, len(train), int((corpus["part"] == "val").sum()))
    meta_path = baseline.META_PATH
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update({
        "languages": list(LANGUAGES),
        "corpus_size": int(len(corpus)),
        "by_language": by_language,
        "overall_test": overall_test,
        "custom_handwritten": {"multilingual": custom_new, "english_only_baseline": custom_old},
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("train:", len(train), "val:", int((corpus['part'] == 'val').sum()), "test:", int((corpus['part'] == 'test').sum()))
    print("overall val:", overall_val)
    for key, value in by_language.items():
        print(key, {k: value[k] for k in ("size", "spam", "precision", "recall", "f1", "fp", "fn")})
    print("custom new:", custom_new)
    print("custom old:", custom_old)


if __name__ == "__main__":
    main()
