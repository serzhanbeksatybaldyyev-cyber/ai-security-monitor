"""
Полный воспроизводимый эксперимент: EDA → очистка → Feature Engineering →
split → Feature Selection → Data Leakage demo → обучение и сравнение моделей →
оценка → сохранение pipeline → инференс на новых данных → SHAP → доп. задания.

Запуск из корня проекта:  python -m src.train
Результаты: results/figures/*.png, results/metrics/*.json|csv,
            models/model_best_pipeline.pkl, data/processed/*.csv
"""
from __future__ import annotations

import json
import time
from functools import partial
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shap
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score, roc_curve,
                             classification_report)
from sklearn.model_selection import (GroupShuffleSplit, StratifiedKFold, cross_validate,
                                     train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from src import generate_data
from src.feature_engineering import CAT_FEATURES, NUM_FEATURES, build_features
from src.feature_selection import correlated_pairs, mutual_information, selected_names
from src.preprocessing import clean, load_raw, quality_report

RANDOM_STATE = 42
K_BEST = 8
ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results" / "figures"
MET = ROOT / "results" / "metrics"
PROC = ROOT / "data" / "processed"
MODEL_PATH = ROOT / "models" / "model_best_pipeline.pkl"

sns.set_theme(style="whitegrid", font_scale=0.95)
plt.rcParams["figure.dpi"] = 110
PALETTE = {"Normal": "#4C72B0", "Attack": "#C44E52"}


def savefig(name):
    plt.tight_layout()
    plt.savefig(FIG / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close()


def metrics_of(y_true, y_pred, y_score=None) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    m = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score) if y_score is not None else np.nan,
        "TP": int(tp), "FP": int(fp), "TN": int(tn), "FN": int(fn),
        "FPR": fp / (fp + tn) if fp + tn else 0.0,
    }
    return {k: (round(float(v), 4) if isinstance(v, float) else v) for k, v in m.items()}


def make_preprocessor(num, cat):
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler())])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer([("num", numeric, num), ("cat", categorical, cat)])


def mi_scorer():
    return partial(mutual_info_classif, random_state=RANDOM_STATE)


def make_models():
    return {
        "LogisticRegression": LogisticRegression(max_iter=1000, random_state=RANDOM_STATE,
                                                 class_weight="balanced"),
        "DecisionTree": DecisionTreeClassifier(max_depth=6, random_state=RANDOM_STATE,
                                               class_weight="balanced"),
        "RandomForest": RandomForestClassifier(n_estimators=300, max_depth=10, n_jobs=-1,
                                               random_state=RANDOM_STATE, class_weight="balanced"),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=RANDOM_STATE,
                                                               class_weight="balanced"),
    }


def make_pipe(model, num=NUM_FEATURES, cat=CAT_FEATURES, k=K_BEST):
    return Pipeline([("preprocessor", make_preprocessor(num, cat)),
                     ("selector", SelectKBest(mi_scorer(), k=k)),
                     ("model", model)])


# ==========================================================================
def eda(raw: pd.DataFrame, feat: pd.DataFrame, out: dict):
    ev = raw.drop_duplicates("group_id")
    # 1. Классы
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    vc = ev["label"].map({0: "Normal", 1: "Attack"}).value_counts()
    ax[0].bar(vc.index, vc.values, color=[PALETTE[i] for i in vc.index])
    for i, v in enumerate(vc.values):
        ax[0].text(i, v, f"{v} ({v / vc.sum():.1%})", ha="center", va="bottom")
    ax[0].set_title("Баланс классов Normal / Attack")
    at = ev["attack_type"].value_counts()
    ax[1].barh(at.index[::-1], at.values[::-1], color="#55A868")
    ax[1].set_title("Распределение по типам событий")
    savefig("01_class_balance")

    # 2. Пропуски
    miss = raw.isna().mean().sort_values(ascending=False)
    miss = miss[miss > 0]
    plt.figure(figsize=(7, 3.2))
    plt.bar(miss.index, miss.values * 100, color="#8172B2")
    plt.ylabel("% пропусков")
    plt.title("Доля пропущенных значений по столбцам (сырые данные)")
    savefig("02_missing")

    # 3. Распределения признаков по классам (лог-шкала)
    cols = ["duration", "packet_count", "avg_packet_size", "error_rate",
            "unique_dst_ips", "conn_per_sec", "src_bytes", "bytes_ratio"]
    fig, axes = plt.subplots(2, 4, figsize=(15, 6.5))
    f = feat.assign(cls=feat["label"].map({0: "Normal", 1: "Attack"}))
    for ax, c in zip(axes.ravel(), cols):
        data = f[[c, "cls"]].dropna()
        x = np.log1p(data[c].clip(lower=0)) if c not in ("error_rate", "bytes_ratio") else data[c]
        for cls in ["Normal", "Attack"]:
            ax.hist(x[data["cls"] == cls], bins=40, alpha=0.6, density=True,
                    color=PALETTE[cls], label=cls)
        ax.set_title(c if c in ("error_rate", "bytes_ratio") else f"log1p({c})")
    axes[0, 0].legend()
    savefig("03_feature_distributions")

    # 4. Активность по часам
    plt.figure(figsize=(10, 3.6))
    ct = pd.crosstab(f["hour_of_day"], f["cls"], normalize="columns") * 100
    ct.plot(kind="bar", color=[PALETTE[c] for c in ct.columns], ax=plt.gca(), width=0.85)
    plt.ylabel("% событий класса")
    plt.xlabel("Час суток")
    plt.title("Распределение событий по часам суток")
    savefig("04_hour_of_day")

    # 5. Корреляции
    plt.figure(figsize=(10, 8))
    corr = feat[NUM_FEATURES + ["label"]].corr()
    sns.heatmap(corr, cmap="RdBu_r", center=0, annot=True, fmt=".2f", annot_kws={"size": 7},
                cbar_kws={"shrink": 0.7})
    plt.title("Матрица корреляций (Пирсон)")
    savefig("05_correlation")

    # 6. Boxplot по типам атак
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, c in zip(axes, ["unique_dst_ips", "error_rate", "avg_packet_size"]):
        sns.boxplot(data=f, x="attack_type", y=c, ax=ax, showfliers=False,
                    order=["Normal", "PortScan", "DDoS", "BruteForce", "Exfiltration"])
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=20)
        ax.set_title(c)
    savefig("06_box_by_attack")

    out["eda"] = {
        "describe": feat[["duration", "packet_count", "src_bytes", "dst_bytes",
                          "avg_packet_size", "error_rate", "unique_dst_ips",
                          "conn_per_sec"]].describe().round(3).to_dict(),
        "class_counts": {str(k): int(v) for k, v in vc.items()},
        "attack_type_counts": {str(k): int(v) for k, v in at.items()},
        "missing_share": {k: round(float(v), 4) for k, v in miss.items()},
        "service_counts": ev["service"].value_counts(dropna=False).astype(int)
                                       .rename(index=str).to_dict(),
    }


# ==========================================================================
def leakage_demo(raw: pd.DataFrame, feat_clean: pd.DataFrame, out: dict):
    """Неправильные vs правильные варианты pipeline."""
    res = []
    # признаки считаются для уникальных событий, повторы наследуют их по group_id
    key_cols = NUM_FEATURES + CAT_FEATURES + ["flagged_by_ids", "conn_id"]
    raw_dup, _ = clean(raw, dedupe_events=False)
    fmap = feat_clean.set_index("group_id")[NUM_FEATURES + CAT_FEATURES]
    all_rows = raw_dup[["group_id", "conn_id", "flagged_by_ids", "label"]].join(fmap, on="group_id")
    X_all, y_all, groups = all_rows[key_cols], all_rows["label"], all_rows["group_id"]

    def dt_pipe(num):
        return Pipeline([("preprocessor", make_preprocessor(num, CAT_FEATURES)),
                         ("model", DecisionTreeClassifier(random_state=RANDOM_STATE))])

    # A. Повторы событий: случайный split vs group split
    Xtr, Xte, ytr, yte = train_test_split(X_all, y_all, test_size=0.3,
                                          random_state=RANDOM_STATE, stratify=y_all)
    p = dt_pipe(NUM_FEATURES).fit(Xtr, ytr)
    overlap = len(set(groups.loc[Xtr.index]) & set(groups.loc[Xte.index]))
    res.append({"experiment": "A1. Случайный split с повторами событий (НЕПРАВИЛЬНО)",
                **metrics_of(yte, p.predict(Xte)), "test_rows": len(Xte),
                "shared_groups": overlap})
    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=RANDOM_STATE)
    tr, te = next(gss.split(X_all, y_all, groups=groups))
    p = dt_pipe(NUM_FEATURES).fit(X_all.iloc[tr], y_all.iloc[tr])
    res.append({"experiment": "A2. GroupShuffleSplit по group_id (ПРАВИЛЬНО)",
                **metrics_of(y_all.iloc[te], p.predict(X_all.iloc[te])), "test_rows": len(te),
                "shared_groups": len(set(groups.iloc[tr]) & set(groups.iloc[te]))})

    # B. Признак-суррогат метки / технический идентификатор (на чистых данных)
    Xc = feat_clean[key_cols]
    yc = feat_clean["label"]
    Xtr, Xte, ytr, yte = train_test_split(Xc, yc, test_size=0.3, random_state=RANDOM_STATE,
                                          stratify=yc)
    def rf_pipe(num):
        return Pipeline([("preprocessor", make_preprocessor(num, CAT_FEATURES)),
                         ("model", RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=-1,
                                                          random_state=RANDOM_STATE))])

    for name, num in [("B1. + flagged_by_ids (суррогат метки, НЕПРАВИЛЬНО)",
                       NUM_FEATURES + ["flagged_by_ids"]),
                      ("B2. + conn_id (технический ID, НЕПРАВИЛЬНО)", NUM_FEATURES + ["conn_id"]),
                      ("B3. Без утекающих признаков (ПРАВИЛЬНО)", NUM_FEATURES)]:
        p = rf_pipe(num).fit(Xtr, ytr)
        res.append({"experiment": name, **metrics_of(yte, p.predict(Xte)), "test_rows": len(Xte)})
        if "conn_id" in num:
            imp = pd.Series(p.named_steps["model"].feature_importances_,
                            index=p.named_steps["preprocessor"].get_feature_names_out())
            out["conn_id_importance"] = round(float(imp.get("num__conn_id", 0)), 4)

    # C. Порядок операций: масштабирование и SelectKBest на всём датасете до split.
    #    Для наглядности эффект показываем на малой обучающей выборке и
    #    большом числе шумовых признаков — классическая ловушка отбора признаков.
    rng = np.random.default_rng(RANDOM_STATE)
    small = feat_clean.sample(200, random_state=RANDOM_STATE)
    noise = pd.DataFrame(rng.normal(size=(len(small), 5000)), index=small.index).add_prefix("noise_")
    y_s = small["label"]
    # «метка» — случайная: честная модель должна давать ROC-AUC ≈ 0.5
    y_rand = pd.Series(rng.integers(0, 2, len(small)), index=small.index)
    Xs = noise
    sel = SelectKBest(f_classif, k=10)
    Xsel = sel.fit_transform(StandardScaler().fit_transform(Xs), y_rand)      # fit на ВСЁМ
    Xtr, Xte, ytr, yte = train_test_split(Xsel, y_rand, test_size=0.3,
                                          random_state=RANDOM_STATE, stratify=y_rand)
    lr = LogisticRegression(max_iter=1000).fit(Xtr, ytr)
    wrong = metrics_of(yte, lr.predict(Xte), lr.predict_proba(Xte)[:, 1])
    Xtr, Xte, ytr, yte = train_test_split(Xs, y_rand, test_size=0.3,
                                          random_state=RANDOM_STATE, stratify=y_rand)
    pipe = Pipeline([("scaler", StandardScaler()),
                     ("selector", SelectKBest(f_classif, k=10)),
                     ("model", LogisticRegression(max_iter=1000))]).fit(Xtr, ytr)
    right = metrics_of(yte, pipe.predict(Xte), pipe.predict_proba(Xte)[:, 1])
    res.append({"experiment": "C1. SelectKBest+Scaler fit до split, случайная метка (НЕПРАВИЛЬНО)",
                **wrong, "test_rows": len(yte)})
    res.append({"experiment": "C2. SelectKBest+Scaler внутри Pipeline (ПРАВИЛЬНО)",
                **right, "test_rows": len(yte)})

    df = pd.DataFrame(res)
    df.to_csv(MET / "leakage_demo.csv", index=False)
    out["leakage"] = res

    plt.figure(figsize=(10, 4.2))
    short = ["A1 random split\n+повторы", "A2 group split", "B1 +flagged\n_by_ids",
             "B2 +conn_id", "B3 честно", "C1 отбор\nдо split", "C2 отбор\nв Pipeline"]
    vals = df["f1"].to_numpy()
    colors = ["#C44E52", "#55A868", "#C44E52", "#C44E52", "#55A868", "#C44E52", "#55A868"]
    bars = plt.bar(short, vals, color=colors)
    for b, v in zip(bars, vals):
        plt.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.3f}", ha="center")
    plt.ylim(0, 1.08)
    plt.ylabel("F1 на test")
    plt.title("Data Leakage: красные — с утечкой, зелёные — корректный pipeline")
    savefig("07_leakage_f1")


# ==========================================================================
def main():
    for d in (FIG, MET, PROC, MODEL_PATH.parent):
        d.mkdir(parents=True, exist_ok=True)
    out: dict = {"random_state": RANDOM_STATE}

    if not generate_data.RAW_PATH.exists():
        generate_data.main()
    raw = load_raw(generate_data.RAW_PATH)
    out["raw_quality"] = quality_report(raw)
    out["raw_dtypes"] = raw.dtypes.astype(str).to_dict()

    df, rep = clean(raw)
    out["cleaning"] = rep
    feat = build_features(df)
    feat.to_csv(PROC / "netflow_features.csv", index=False)
    out["processed_shape"] = list(feat.shape)
    out["missing_after_fe"] = {c: int(v) for c, v in feat[NUM_FEATURES + CAT_FEATURES]
                               .isna().sum().items() if v}
    eda(raw, feat, out)

    # -------------------- Train / Test split ----------------------------
    X = feat[NUM_FEATURES + CAT_FEATURES]
    y = feat["label"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y)
    out["split"] = {"train": len(X_train), "test": len(X_test),
                    "train_attack_share": round(float(y_train.mean()), 4),
                    "test_attack_share": round(float(y_test.mean()), 4)}

    # -------------------- Feature Selection (только train) ---------------
    out["corr_pairs_train"] = correlated_pairs(X_train[NUM_FEATURES], 0.9)
    mi = mutual_information(X_train[NUM_FEATURES], y_train)
    out["mutual_information"] = mi.round(4).to_dict()
    plt.figure(figsize=(8, 4.5))
    plt.barh(mi.index[::-1], mi.values[::-1], color="#4C72B0")
    plt.xlabel("Mutual Information с меткой (train)")
    plt.title("Информативность признаков (SelectKBest, mutual_info_classif)")
    savefig("08_mutual_information")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    n_total = len(make_preprocessor(NUM_FEATURES, CAT_FEATURES).fit(X_train)
                  .get_feature_names_out())
    k_grid = [2, 4, 6, 8, 10, 12, 15, n_total]
    k_res = []
    for k in k_grid:
        s = cross_validate(make_pipe(RandomForestClassifier(
            n_estimators=150, max_depth=10, random_state=RANDOM_STATE, n_jobs=-1,
            class_weight="balanced"), k=k), X_train, y_train, cv=cv,
            scoring=["f1", "recall"])
        k_res.append({"k": k, "cv_f1": round(s["test_f1"].mean(), 4),
                      "cv_f1_std": round(s["test_f1"].std(), 4),
                      "cv_recall": round(s["test_recall"].mean(), 4)})
    out["k_selection"] = k_res
    kd = pd.DataFrame(k_res)
    plt.figure(figsize=(7, 3.8))
    plt.errorbar(kd["k"], kd["cv_f1"], yerr=kd["cv_f1_std"], marker="o", label="F1 (CV)")
    plt.plot(kd["k"], kd["cv_recall"], marker="s", label="Recall (CV)")
    plt.axvline(K_BEST, ls="--", c="gray")
    plt.xlabel("k — число отбираемых признаков")
    plt.ylabel("метрика (5-fold CV на train)")
    plt.title("Выбор k для SelectKBest (Random Forest)")
    plt.legend()
    savefig("09_k_selection")

    # -------------------- Data Leakage ----------------------------------
    leakage_demo(raw, feat, out)

    # -------------------- Обучение и сравнение ---------------------------
    rows, fitted, scores = [], {}, {}
    for name, model in make_models().items():
        pipe = make_pipe(model)
        cvs = cross_validate(pipe, X_train, y_train, cv=cv, scoring=["f1", "recall", "roc_auc"])
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        t_fit = time.perf_counter() - t0
        t0 = time.perf_counter()
        y_pred = pipe.predict(X_test)
        t_pred = (time.perf_counter() - t0) / len(X_test) * 1e6
        y_score = pipe.predict_proba(X_test)[:, 1]
        m = metrics_of(y_test, y_pred, y_score)
        rows.append({"model": name, **m,
                     "cv_f1_mean": round(cvs["test_f1"].mean(), 4),
                     "cv_f1_std": round(cvs["test_f1"].std(), 4),
                     "cv_recall_mean": round(cvs["test_recall"].mean(), 4),
                     "fit_time_s": round(t_fit, 3), "predict_us_per_row": round(t_pred, 2),
                     "selected_features": selected_names(pipe)})
        fitted[name], scores[name] = pipe, y_score
    comp = pd.DataFrame(rows)
    comp.drop(columns="selected_features").to_csv(MET / "model_comparison.csv", index=False)
    out["models"] = rows

    # основная модель — из трёх базовых по методичке: max F1, при близком F1 (<0.01) — max Recall
    base = comp[comp["model"].isin(["LogisticRegression", "DecisionTree", "RandomForest"])]
    top = base["f1"].max()
    best_name = base[base["f1"] >= top - 0.01].sort_values("recall", ascending=False)["model"].iloc[0]
    best = fitted[best_name]
    out["best_model"] = best_name
    joblib.dump(best, MODEL_PATH)

    # Графики сравнения
    mlong = comp.melt(id_vars="model", value_vars=["accuracy", "precision", "recall", "f1", "roc_auc"])
    plt.figure(figsize=(10, 4.2))
    sns.barplot(data=mlong, x="variable", y="value", hue="model")
    plt.ylim(0.5, 1.02)
    plt.xlabel("")
    plt.ylabel("значение на test")
    plt.title("Сравнение моделей на тестовой выборке")
    plt.legend(loc="lower right", fontsize=8)
    savefig("10_model_comparison")

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for name, s in scores.items():
        fpr, tpr, _ = roc_curve(y_test, s)
        ax[0].plot(fpr, tpr, label=f"{name} (AUC={roc_auc_score(y_test, s):.3f})")
        pr, rc, _ = precision_recall_curve(y_test, s)
        ax[1].plot(rc, pr, label=name)
    ax[0].plot([0, 1], [0, 1], "k--", lw=0.8)
    ax[0].set(xlabel="False Positive Rate", ylabel="True Positive Rate (Recall)", title="ROC-кривые")
    ax[1].set(xlabel="Recall", ylabel="Precision", title="Precision-Recall кривые")
    ax[0].legend(fontsize=8)
    ax[1].legend(fontsize=8)
    savefig("11_roc_pr")

    fig, axes = plt.subplots(1, 4, figsize=(17, 3.8))
    for ax, (name, pipe) in zip(axes, fitted.items()):
        cm = confusion_matrix(y_test, pipe.predict(X_test))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax,
                    xticklabels=["Normal", "Attack"], yticklabels=["Normal", "Attack"])
        ax.set(title=name, xlabel="Прогноз", ylabel="Истина")
    savefig("12_confusion_matrices")

    # -------------------- Оценка выбранной модели ------------------------
    y_pred = best.predict(X_test)
    out["best_report"] = classification_report(y_test, y_pred, target_names=["Normal", "Attack"],
                                               output_dict=True)
    plt.figure(figsize=(4.6, 3.9))
    sns.heatmap(confusion_matrix(y_test, y_pred), annot=True, fmt="d", cmap="Blues", cbar=False,
                xticklabels=["Normal", "Attack"], yticklabels=["Normal", "Attack"])
    plt.xlabel("Прогноз модели")
    plt.ylabel("Истинная метка")
    plt.title(f"Confusion Matrix — {best_name}")
    savefig("13_confusion_best")

    # Recall по типам атак (какие атаки пропускаются)
    at_test = feat.loc[X_test.index, "attack_type"]
    rec_by = {t: round(float((y_pred[(at_test == t).to_numpy()] == 1).mean()), 4)
              for t in ["PortScan", "DDoS", "BruteForce", "Exfiltration"]}
    out["recall_by_attack_type"] = rec_by
    out["fpr_by_normal_subtype"] = {}

    # Порог
    s = scores[best_name]
    thr = np.linspace(0.05, 0.95, 19)
    th_rows = [{"threshold": round(t, 2), **metrics_of(y_test, (s >= t).astype(int), s)} for t in thr]
    out["thresholds"] = th_rows
    td = pd.DataFrame(th_rows)
    plt.figure(figsize=(7.5, 3.8))
    for c in ["precision", "recall", "f1"]:
        plt.plot(td["threshold"], td[c], marker=".", label=c)
    plt.axvline(0.5, ls="--", c="gray")
    plt.xlabel("Порог вероятности класса Attack")
    plt.title(f"Влияние порога на метрики ({best_name})")
    plt.legend()
    savefig("14_threshold")

    # Важность признаков (встроенная)
    sel = selected_names(best)
    imp = pd.Series(best.named_steps["model"].feature_importances_, index=sel).sort_values()
    out["feature_importance"] = imp.sort_values(ascending=False).round(4).to_dict()
    plt.figure(figsize=(7, 4))
    plt.barh(imp.index, imp.values, color="#55A868")
    plt.title(f"Feature Importance (MDI) — {best_name}")
    savefig("15_feature_importance")

    # -------------------- Воспроизводимость ------------------------------
    again = make_pipe(make_models()[best_name]).fit(X_train, y_train)
    out["reproducible"] = bool(np.allclose(again.predict_proba(X_test), best.predict_proba(X_test), atol=1e-9) and np.array_equal(again.predict(X_test), best.predict(X_test)))

    # -------------------- Новые данные: загрузка pipeline ----------------
    loaded = joblib.load(MODEL_PATH)
    new_raw = generate_data.make_dataset(n_normal=1500, seed=7)
    new_raw.to_csv(ROOT / "data" / "raw" / "netflow_new_day.csv", index=False)
    new_df, _ = clean(new_raw)
    new_feat = build_features(new_df)
    new_pred = loaded.predict(new_feat[NUM_FEATURES + CAT_FEATURES])
    new_score = loaded.predict_proba(new_feat[NUM_FEATURES + CAT_FEATURES])[:, 1]
    out["new_data"] = {"rows": len(new_feat), **metrics_of(new_feat["label"], new_pred, new_score)}
    sample = new_feat.assign(p_attack=new_score.round(3), pred=new_pred)
    sample[["timestamp", "src_ip", "dst_ip", "service", "packet_count", "error_rate",
            "unique_dst_ips", "conn_per_sec", "attack_type", "p_attack", "pred"]] \
        .sort_values("p_attack", ascending=False).head(12) \
        .to_csv(MET / "new_data_top_alerts.csv", index=False)

    # -------------------- SHAP ------------------------------------------
    Xt = best.named_steps["selector"].transform(best.named_steps["preprocessor"].transform(X_test))
    Xt = pd.DataFrame(np.asarray(Xt.todense()) if hasattr(Xt, "todense") else Xt, columns=sel,
                      index=X_test.index)
    explainer = shap.TreeExplainer(best.named_steps["model"])
    sv = explainer(Xt.iloc[:300])
    sv1 = sv[..., 1]
    mean_abs = pd.Series(np.abs(sv1.values).mean(axis=0), index=sel).sort_values(ascending=False)
    out["shap_mean_abs"] = mean_abs.round(4).to_dict()
    plt.figure()
    shap.plots.beeswarm(sv1, show=False, max_display=10)
    plt.title("SHAP summary (класс Attack)")
    savefig("16_shap_summary")
    plt.figure()
    shap.plots.bar(sv1, show=False, max_display=10)
    plt.title("Mean |SHAP|")
    savefig("17_shap_bar")

    full = explainer(Xt)[..., 1]
    yp = best.predict(X_test)
    tp_idx = np.where((y_test.to_numpy() == 1) & (yp == 1))[0]
    fn_idx = np.where((y_test.to_numpy() == 1) & (yp == 0))[0]
    i_tp = tp_idx[np.argmax(best.predict_proba(X_test)[tp_idx, 1])]
    plt.figure()
    shap.plots.waterfall(full[i_tp], show=False, max_display=9)
    plt.title(f"Почему событие признано атакой ({feat.loc[X_test.index[i_tp], 'attack_type']})")
    savefig("18_shap_waterfall_tp")
    out["shap_tp_example"] = {
        "attack_type": str(feat.loc[X_test.index[i_tp], "attack_type"]),
        "raw": feat.loc[X_test.index[i_tp], ["service", "packet_count", "avg_packet_size",
                                             "error_rate", "unique_dst_ips", "conn_per_sec"]]
                   .astype(str).to_dict()}
    if len(fn_idx):
        i_fn = fn_idx[np.argmax(best.predict_proba(X_test)[fn_idx, 1])]
        plt.figure()
        shap.plots.waterfall(full[i_fn], show=False, max_display=9)
        plt.title(f"False Negative: пропущенная атака ({feat.loc[X_test.index[i_fn], 'attack_type']})")
        savefig("19_shap_waterfall_fn")
        out["fn_types"] = feat.loc[X_test.index[fn_idx], "attack_type"].value_counts().to_dict()

    # -------------------- Доп. задания ----------------------------------
    extras(feat, X_train, X_test, y_train, y_test, best, best_name, out)

    (MET / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                                      encoding="utf-8")
    print(comp.drop(columns="selected_features").to_string(index=False))
    print("best:", best_name, "| reproducible:", out["reproducible"], "| new:", out["new_data"])


def extras(feat, X_train, X_test, y_train, y_test, best, best_name, out):
    # 1. Многоклассовая классификация по типам атак
    yt_m = feat.loc[X_train.index, "attack_type"]
    ye_m = feat.loc[X_test.index, "attack_type"]
    mc = make_pipe(RandomForestClassifier(n_estimators=300, max_depth=12, n_jobs=-1,
                                          random_state=RANDOM_STATE,
                                          class_weight="balanced"), k=10).fit(X_train, yt_m)
    pm = mc.predict(X_test)
    labels = ["Normal", "PortScan", "DDoS", "BruteForce", "Exfiltration"]
    rep = classification_report(ye_m, pm, labels=labels, output_dict=True, zero_division=0)
    out["multiclass"] = {k: {m: round(v, 4) for m, v in rep[k].items()} for k in labels + ["macro avg"]}
    out["multiclass"]["accuracy"] = round(rep["accuracy"], 4)
    plt.figure(figsize=(6.4, 5))
    sns.heatmap(confusion_matrix(ye_m, pm, labels=labels), annot=True, fmt="d", cmap="Greens",
                cbar=False, xticklabels=labels, yticklabels=labels)
    plt.xticks(rotation=30, ha="right")
    plt.title("Многоклассовая классификация (Random Forest)")
    plt.xlabel("Прогноз")
    plt.ylabel("Истина")
    savefig("20_multiclass_cm")

    # 2. Isolation Forest (без учителя): обучение только на Normal из train
    pre = make_preprocessor(NUM_FEATURES, CAT_FEATURES)
    iso = Pipeline([("preprocessor", pre), ("model", IsolationForest(
        n_estimators=300, contamination=0.05, random_state=RANDOM_STATE))])
    iso.fit(X_train[y_train == 0])
    ip = (iso.predict(X_test) == -1).astype(int)
    out["isolation_forest"] = metrics_of(y_test, ip, -iso.score_samples(X_test))
    out["isolation_forest"]["recall_by_type"] = {
        t: round(float(ip[(ye_m == t).to_numpy()].mean()), 4) for t in labels}

    # 3. Состязательное возмущение: атакующий меняет packet_count/duration/bytes
    adv = []
    attack_idx = y_test[y_test == 1].index
    for f in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0]:
        Xa = X_test.loc[attack_idx].copy()
        for c in ["packet_count", "duration", "src_bytes", "dst_bytes"]:
            Xa[c] = Xa[c] * f
        Xa["avg_packet_size"] = (Xa["src_bytes"] + Xa["dst_bytes"]) / Xa["packet_count"]
        r = float(best.predict(Xa).mean())
        Xb = X_test.loc[attack_idx].copy()
        Xb["conn_per_sec"] = Xb["conn_per_sec"] / f if f >= 1 else Xb["conn_per_sec"]
        Xb["unique_dst_ips"] = np.maximum(1, np.round(Xb["unique_dst_ips"] / f)) if f >= 1 \
            else Xb["unique_dst_ips"]
        r2 = float(best.predict(Xb).mean())
        adv.append({"factor": f, "recall_volume_perturbed": round(r, 4),
                    "recall_slowdown": round(r2, 4)})
    out["adversarial"] = adv
    ad = pd.DataFrame(adv)
    plt.figure(figsize=(7, 3.6))
    plt.plot(ad["factor"], ad["recall_volume_perturbed"], marker="o",
             label="масштаб packet_count/duration/bytes ×f")
    plt.plot(ad["factor"][ad["factor"] >= 1], ad["recall_slowdown"][ad["factor"] >= 1], marker="s",
             label="замедление атаки: conn_per_sec, unique_dst_ips ÷f")
    plt.xlabel("коэффициент возмущения f")
    plt.ylabel("Recall на атаках test")
    plt.ylim(0, 1.05)
    plt.title("Устойчивость к состязательному возмущению признаков")
    plt.legend(fontsize=8)
    savefig("21_adversarial")

    # 4. Сдвиг распределения: тип атаки, не встречавшийся в train
    tr_mask = feat.loc[X_train.index, "attack_type"] != "Exfiltration"
    p = make_pipe(make_models()[best_name]).fit(X_train[tr_mask], y_train[tr_mask])
    pt = p.predict(X_test)
    out["unseen_attack"] = {
        "recall_exfiltration_unseen": round(float(pt[(ye_m == "Exfiltration").to_numpy()].mean()), 4),
        "recall_exfiltration_seen": out["recall_by_attack_type"]["Exfiltration"],
        "overall_recall_unseen": round(float(recall_score(y_test, pt)), 4),
    }

    # 5. Крайние значения k
    out["k_extremes"] = {}
    for k in [2, "all"]:
        pk = make_pipe(make_models()[best_name], k=k).fit(X_train, y_train)
        out["k_extremes"][str(k)] = metrics_of(y_test, pk.predict(X_test),
                                               pk.predict_proba(X_test)[:, 1])
        if k == 2:
            out["k_extremes"]["2_features"] = selected_names(pk)

    # 6. Accuracy-ловушка: «всегда Normal»
    out["dummy_all_normal"] = metrics_of(y_test, np.zeros(len(y_test), dtype=int))


if __name__ == "__main__":
    main()
