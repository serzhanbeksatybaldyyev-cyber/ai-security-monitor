"""
Модуль 2 (Студент 2). Классификация HTTP-запросов: Normal / SQL Injection / XSS.

Признаки: TF-IDF по символьным n-граммам (2–5 символов, analyzer="char_wb").
Почему символы, а не слова: сигнатуры атак — это фрагменты вроде "' or",
"--", "<scr", "onerror=", "union sel", которые плохо выделяются словарной
токенизацией, зато устойчиво ловятся символьными n-граммами, в том числе
при изменённом регистре и вставке пробелов.

Модели:
* Logistic Regression — основная: даёт откалиброванные вероятности и
  интерпретируемые веса признаков;
* Multinomial Naive Bayes — быстрый baseline для сравнения.

Векторизатор находится ВНУТРИ Pipeline, поэтому словарь и IDF обучаются
только на train (и на train-фолдах внутри GridSearchCV).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

import config
from src.common.io_utils import make_events_frame
from src.common.metrics import evaluate_classifier, false_positive_rate
from src.nlp.preprocess import normalize_request

CLASSES = config.TEXT_CLASSES


def build_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        preprocessor=normalize_request,  # декодирование + нормализация
        lowercase=False,                 # уже сделано в normalize_request
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=2,
        max_features=50_000,
        sublinear_tf=True,
    )


def build_logreg_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", build_vectorizer()),
        ("model", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ])


def build_nb_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", build_vectorizer()),
        ("model", MultinomialNB()),
    ])


def train_nlp_models(df: pd.DataFrame) -> tuple[dict, dict]:
    """Обучение и сравнение LogReg и Naive Bayes.

    Гиперпараметры подбираются кросс-валидацией на train; test используется
    один раз — для итоговой оценки.
    """
    X = df[config.TEXT_COL].astype(str)
    y = df[config.TEXT_LABEL_COL].astype(str)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.TEST_SIZE, stratify=y, random_state=config.RANDOM_STATE
    )
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=config.RANDOM_STATE)

    candidates = {
        "logistic_regression": (build_logreg_pipeline(), {"model__C": [1, 10, 30]}),
        "naive_bayes": (build_nb_pipeline(), {"model__alpha": [0.01, 0.1, 1.0]}),
    }
    models, metrics = {}, {}
    for name, (pipe, grid) in candidates.items():
        search = GridSearchCV(pipe, grid, scoring="f1_macro", cv=cv, n_jobs=-1)
        search.fit(X_train, y_train)
        best = search.best_estimator_
        y_pred = best.predict(X_test)
        m = evaluate_classifier(y_test, y_pred, labels=CLASSES)
        m["best_params"] = search.best_params_
        m["cv_f1_macro"] = round(float(search.best_score_), 4)
        # FPR: доля Normal-запросов, ошибочно помеченных как атака
        m["false_positive_rate"] = round(
            false_positive_rate(y_test != "Normal", y_pred != "Normal"), 4
        )
        models[name], metrics[name] = best, m

    metrics["dataset"] = {
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "class_distribution": {k: int(v) for k, v in y.value_counts().items()},
    }
    return models, metrics


def classify_requests(model: Pipeline, requests) -> pd.DataFrame:
    """Классифицирует список запросов.

    Возвращает: request, prediction, confidence, prob_<класс>, needs_review.
    confidence — вероятность выбранного класса, а НЕ вероятность того,
    что это реальная атака в вашей системе.
    """
    requests = pd.Series(list(requests), dtype=str)
    proba = model.predict_proba(requests)
    classes = list(model.classes_)
    out = pd.DataFrame({"request": requests})
    out["prediction"] = np.array(classes)[proba.argmax(axis=1)]
    out["confidence"] = proba.max(axis=1).round(4)
    for i, c in enumerate(classes):
        out[f"prob_{c}"] = proba[:, i].round(4)
    out["needs_review"] = out["confidence"] < config.NLP_REVIEW_THRESHOLD
    return out


def check_attack_type(model: Pipeline, request: str, attack: str) -> dict:
    """Проверка одного запроса на ВЫБРАННЫЙ аналитиком вид атаки.

    Аналитик сначала выбирает вид атаки (кнопка на вкладке «HTTP-запросы»),
    затем модель отвечает, есть ли в запросе признаки именно этой атаки.

    verdict:
      "detected"     — модель относит запрос к выбранной атаке;
      "other_attack" — выбранной атаки нет, но есть признаки другой;
      "clean"        — модель считает запрос нормальным.
    """
    classes = list(model.classes_)
    if attack not in config.ATTACK_TYPES or attack not in classes:
        raise ValueError(f"Неизвестный вид атаки: {attack!r}. Допустимо: {config.ATTACK_TYPES}")
    res = classify_requests(model, [request]).iloc[0]
    prediction = str(res["prediction"])
    if prediction == attack:
        verdict = "detected"
    elif prediction != "Normal":
        verdict = "other_attack"
    else:
        verdict = "clean"
    return {
        "attack": attack,
        "probability": float(res[f"prob_{attack}"]),
        "prediction": prediction,
        "confidence": float(res["confidence"]),
        "needs_review": bool(res["needs_review"]),
        "verdict": verdict,
        "probs": {c: float(res[f"prob_{c}"]) for c in classes},
    }


def explain_request(model: Pipeline, request: str, top_k: int = 8,
                    target_class: str | None = None) -> pd.DataFrame:
    """Какие n-граммы сильнее всего повлияли на прогноз (только для LogReg).

    Вклад n-граммы = TF-IDF вес в запросе × коэффициент модели для класса.
    target_class — класс, «за» который считаются вклады (например, вид атаки,
    выбранный аналитиком); по умолчанию — предсказанный класс.
    """
    clf = model.named_steps["model"]
    if not hasattr(clf, "coef_"):
        return pd.DataFrame(columns=["ngram", "contribution"])
    vec = model.named_steps["tfidf"]
    x = vec.transform([request])
    if target_class is not None and target_class in list(clf.classes_):
        cls_idx = list(clf.classes_).index(target_class)
    else:
        cls_idx = int(np.argmax(clf.predict_proba(x)[0]))
    coef = clf.coef_[cls_idx]
    idx = x.nonzero()[1]
    contrib = x.toarray()[0, idx] * coef[idx]
    names = vec.get_feature_names_out()[idx]
    df = pd.DataFrame({"ngram": names, "contribution": contrib.round(4)})
    return df.sort_values("contribution", ascending=False).head(top_k).reset_index(drop=True)


def http_events(source_df: pd.DataFrame, classified: pd.DataFrame) -> pd.DataFrame:
    """Перевод результатов в единую схему событий."""
    n = len(classified)
    ts = (pd.to_datetime(source_df[config.TEXT_TIME_COL], errors="coerce", format="mixed")
          .dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("").to_numpy()
          if config.TEXT_TIME_COL in source_df.columns else [""] * n)
    truth = (source_df[config.TEXT_LABEL_COL].astype(str).to_numpy()
             if config.TEXT_LABEL_COL in source_df.columns else [""] * n)
    return make_events_frame(
        event_id=[f"http-{i:06d}" for i in range(1, n + 1)],
        timestamp=ts,
        source_module=["http"] * n,
        model_name=["LogisticRegression"] * n,
        prediction=classified["prediction"].to_numpy(),
        score=classified["confidence"].to_numpy(),
        is_alert=(classified["prediction"] != "Normal").to_numpy(),
        needs_review=classified["needs_review"].to_numpy(),
        ground_truth=truth,
        details=classified["request"].str.slice(0, 160).to_numpy(),
        status=[config.PREDICTION_STATUS] * n,
    )
