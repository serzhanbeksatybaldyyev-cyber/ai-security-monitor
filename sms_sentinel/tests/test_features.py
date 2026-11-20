"""Тесты разбиения, признаков и базовой модели (задания 6 и 7)."""
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from ml.baseline import MODEL_PATH, compute_metrics, predict_sms, train_baseline
from ml.features import MANUAL_FEATURES, ManualFeatures, build_feature_pipeline, build_sms_pipeline, to_frame
from ml.rules import RULE_GROUPS, find_rule_groups
from ml.split import load_clean, load_parts, make_split

COLUMNS = ["text_raw", "text_clean"]
SPAM = [
    "URGENT! You won a prize, call 09061701461 now",
    "Free cash! Claim your bonus at http://win.example",
    "Your account is blocked, send $100 today!",
    "Winner! Call now to claim your reward",
] * 3
HAM = [
    "Are we meeting for lunch tomorrow",
    "See you at home tonight",
    "Please bring the notes for class",
    "Ok I will call you later today",
] * 3


@pytest.fixture(scope="module")
def small_data():
    texts = SPAM + HAM
    frame = to_frame(texts)
    frame["label"] = [1] * len(SPAM) + [0] * len(HAM)
    return frame


def test_split_sizes_are_disjoint_and_stratified():
    df = load_clean()
    split = make_split(df)
    train, val, test = set(split["train"]), set(split["val"]), set(split["test"])
    assert not (train & val or train & test or val & test)
    assert len(train | val | test) == len(df)
    assert len(train) / len(df) == pytest.approx(0.70, abs=0.01)
    assert len(val) / len(df) == pytest.approx(0.15, abs=0.01)
    assert len(test) / len(df) == pytest.approx(0.15, abs=0.01)

    parts = load_parts(df)
    for part in parts.values():
        assert part["label"].mean() == pytest.approx(df["label"].mean(), abs=0.005)


def test_split_is_reproducible():
    df = load_clean()
    assert make_split(df) == make_split(df)


def test_vectorizer_learns_only_from_fit_data(small_data):
    pipeline = build_feature_pipeline().fit(small_data[COLUMNS])
    new_word = "zzzuniqueword"
    vocabulary = pipeline.named_steps["features"].named_transformers_["word"].vocabulary_
    before = dict(vocabulary)
    pipeline.transform(to_frame([f"{new_word} {new_word}"]))
    assert new_word not in vocabulary
    assert vocabulary == before


def test_matrix_shapes_match_rows(small_data):
    pipeline = build_feature_pipeline()
    train = pipeline.fit_transform(small_data[COLUMNS])
    other = pipeline.transform(small_data[COLUMNS].head(5))
    assert train.shape[0] == len(small_data)
    assert other.shape == (5, train.shape[1])


def test_manual_features_values():
    frame = to_frame(["WIN!! Pay $5 at http://x.example or call 09061701461"])
    row = dict(zip(MANUAL_FEATURES, ManualFeatures().transform(frame)[0]))
    assert row["length_chars"] == len(frame["text_raw"][0])
    assert row["exclamation_count"] == 2
    assert row["has_url"] == row["has_money"] == row["has_phone"] == 1
    assert 0 < row["upper_ratio"] < 1
    assert row["rule_group_count"] >= 1


def test_manual_features_handle_text_without_letters():
    assert ManualFeatures().transform(to_frame(["123"]))[0, 1] == 0


def test_rules_have_six_groups_and_detect_three_languages():
    assert len(RULE_GROUPS) >= 6
    assert "URGENCY" in find_rule_groups("срочно подтвердите")
    assert "ACCOUNT_BLOCK" in find_rule_groups("картаңыз бұғатталды")
    assert "PRIZE" in find_rule_groups("you won a prize")
    assert find_rule_groups("see you at lunch") == []


def test_saved_pipeline_keeps_vectorizer(small_data, tmp_path):
    model = train_baseline(small_data)
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    loaded = joblib.load(path)
    frame = small_data[COLUMNS]
    assert (loaded.predict(frame) == model.predict(frame)).all()
    assert np.allclose(loaded.predict_proba(frame), model.predict_proba(frame))


def test_compute_metrics_counts():
    metrics = compute_metrics([0, 0, 1, 1], [0, 1, 1, 0])
    assert (metrics["tn"], metrics["fp"], metrics["fn"], metrics["tp"]) == (1, 1, 1, 1)
    assert metrics["accuracy"] == metrics["precision"] == metrics["recall"] == metrics["f1"] == 0.5


def test_predict_sms_with_passed_model(small_data):
    model = train_baseline(small_data)
    result = predict_sms("URGENT! You won a prize, call now", model=model)
    assert set(result) == {"label", "probability"}
    assert result["label"] == 1
    assert 0 <= result["probability"] <= 1


def test_predict_sms_uses_saved_artifact_on_new_text():
    assert MODEL_PATH.exists()
    safe = predict_sms("Hey, are we still meeting for lunch tomorrow?")
    fraud = predict_sms("URGENT! Your bank account has been suspended. Verify now at http://verify.example/login")
    assert safe["label"] == 0
    assert fraud["label"] == 1


def test_build_sms_pipeline_keeps_steps_in_order():
    pipeline = build_sms_pipeline(LogisticRegression())
    assert [name for name, _ in pipeline.steps] == ["features", "classifier"]
    assert isinstance(pipeline, type(build_feature_pipeline()))
    assert isinstance(to_frame(["text"]), pd.DataFrame)
