import json

from ml.baseline import ALGORITHM, META_PATH, THRESHOLD, VERSION
from ml.url_features import FEATURE_NAMES

URL_VERSION = "url_rules_v1"
URL_ALGORITHM = f"Правила по {len(FEATURE_NAMES)} признакам адреса (до обучения URL-модели в заданиях 10–11)"


def sms_card():
    if META_PATH.exists():
        card = json.loads(META_PATH.read_text(encoding="utf-8"))
    else:
        card = {"version": VERSION, "algorithm": ALGORITHM, "threshold": THRESHOLD, "metrics": {}, "trained_at": None}
    card["model_type"] = "sms"
    return card


def url_card():
    return {
        "model_type": "url",
        "version": URL_VERSION,
        "algorithm": URL_ALGORITHM,
        "threshold": 0.5,
        "trained_at": None,
        "metrics": {"features": len(FEATURE_NAMES)},
    }


def model_cards():
    return [sms_card(), url_card()]
