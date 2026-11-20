from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "risk_config.yaml"

LEVEL_TO_CATEGORY = {"low": "safe", "medium": "suspicious", "high": "fraud"}


@dataclass
class Risk:
    score: int
    level: str
    category: str


@lru_cache(maxsize=1)
def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def level_for(score: int, config: dict | None = None) -> str:
    thresholds = (config or load_config())["thresholds"]
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def _result(score: float, config: dict) -> Risk:
    value = int(round(max(0.0, min(score, 100.0))))
    level = level_for(value, config)
    return Risk(score=value, level=level, category=LEVEL_TO_CATEGORY[level])


def sms_risk(p_sms: float | None, p_urls: list[float], rule_groups: int, language: str) -> Risk:
    config = load_config()
    reliable = language in config["reliable_languages"] and p_sms is not None
    rules = min(rule_groups / config["rules_saturation"], 1.0)
    text = p_sms if p_sms is not None else rules
    mode = "reliable" if reliable else "unreliable"
    if p_urls:
        weights = config["weights"][mode]
        url = max(p_urls)
        score = 100 * (weights["sms"] * text + weights["url"] * url + weights["rules"] * rules)
        if text >= 0.5 and url >= 0.5:
            score += config["agreement_bonus"]
    else:
        weights = config["weights"]["no_url"][mode]
        score = 100 * (weights["sms"] * text + weights["rules"] * rules)
    return _result(score, config)


def url_risk(p_url: float) -> Risk:
    return _result(100 * p_url, load_config())
