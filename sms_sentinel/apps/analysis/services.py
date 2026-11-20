"""Сервис анализа: связывает SMS-модель, URL-анализ, словарь правил и модуль риска.

Публичный интерфейс:
    analyze_sms(text)  -> AnalysisResult
    analyze_url(url)   -> UrlAnalysis
    save_sms_check / save_url_check — анализ плюс запись результата в БД одной транзакцией.
Ни одна ссылка не открывается: адрес разбирается только как строка.
"""
import logging
import re
from dataclasses import asdict, dataclass, field

from django.db import transaction

from ml.language import LANGUAGE_NAMES, detect_language
from ml.preprocessing import EMAIL_RE, MONEY_RE, PHONE_CANDIDATE_RE, normalize_sms
from ml.registry import model_cards
from ml.risk import Risk, sms_risk, url_risk
from ml.rules import find_rule_groups
from ml.url_features import analyse_url, find_urls, normalize_url

from .models import Check, DetectedFeature, ModelVersion, UrlResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- тексты для пользователя

RULE_TEXTS = {
    "URGENCY": "Требование срочного действия",
    "MONEY_TRANSFER": "Просьба оплатить или перевести деньги",
    "BANK_CARD": "Упоминание банка, карты или счёта",
    "ACCOUNT_BLOCK": "Угроза блокировки карты или аккаунта",
    "PRIZE": "Обещание выигрыша, приза или бонуса",
    "CODE_REQUEST": "Просьба сообщить код или пароль",
}

RULE_SHORT = {
    "URGENCY": "Срочность",
    "MONEY_TRANSFER": "Деньги и переводы",
    "BANK_CARD": "Банк и карта",
    "ACCOUNT_BLOCK": "Блокировка аккаунта",
    "PRIZE": "Выигрыш и приз",
    "CODE_REQUEST": "Запрос кода",
}

ADVICE = {
    "sms": {
        "fraud": "Не переходите по ссылкам и не сообщайте данные карты или коды. Свяжитесь с организацией по официальному номеру.",
        "suspicious": "Будьте осторожны: не вводите личные данные и проверьте отправителя через официальный канал.",
        "safe": "Явных признаков мошенничества нет. Если сообщение пришло неожиданно, всё равно проверьте отправителя.",
    },
    "url": {
        "fraud": "Не открывайте ссылку и не вводите на сайте пароли и данные карты. Наберите адрес организации вручную.",
        "suspicious": "Не вводите пароль на этом сайте. Откройте сайт организации, набрав адрес самостоятельно.",
        "safe": "Явных признаков подделки нет. Всё равно убедитесь, что ссылку прислал знакомый отправитель.",
    },
}

LEVEL_FOR_CATEGORY = {"safe": "low", "suspicious": "medium", "fraud": "high"}
MODEL_DOWN_NOTE = "Текстовая модель сейчас недоступна, оценка построена по словарю признаков и ссылкам."
NOTHING_FOUND = {"sms": "Признаков мошенничества не найдено", "url": "Признаков подделки в адресе не найдено"}


# ---------------------------------------------------------------- структуры результата

@dataclass(frozen=True)
class LinkVerdict:
    """Оценка одной ссылки; поля совпадают со столбцами таблицы url_results."""

    url: str
    domain: str
    p_url: float
    category: str
    risk_score: int
    features_json: dict = field(default_factory=dict)

    @property
    def hits(self):
        return [row["reason"] for row in self.features_json.get("checks", []) if row["hit"]]

    def as_row(self):
        return asdict(self)


@dataclass
class AnalysisResult:
    """Итог анализа SMS (ТЗ, задание 12)."""

    language: str
    rule_groups: list
    p_sms: float | None
    links: list
    risk: Risk
    reasons: list
    recommendation: str

    @property
    def p_url_max(self):
        return max((link.p_url for link in self.links), default=None)


@dataclass
class UrlAnalysis:
    link: LinkVerdict
    reasons: list
    recommendation: str


class ModelUnavailable(Exception):
    """Файл модели не найден или не читается."""


# ---------------------------------------------------------------- маскирование текста

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_SHORT_CODE = re.compile(r"(?<![\w*])\d{4,8}(?!\w)")
_MASKED_KINDS = (
    re.compile(EMAIL_RE.pattern, re.IGNORECASE),
    _CARD,
    re.compile(MONEY_RE.pattern, re.IGNORECASE),
    PHONE_CANDIDATE_RE,
    _SHORT_CODE,
)


def mask_text(text):
    """Заменяет почту, номера карт и телефонов, суммы и коды на ***."""
    for pattern in _MASKED_KINDS:
        text = pattern.sub("***", text)
    return text


# ---------------------------------------------------------------- версии моделей

def sync_model_versions():
    """Переносит сведения из файлов метаданных моделей в таблицу model_versions."""
    for card in model_cards():
        row, created = ModelVersion.objects.get_or_create(
            model_type=card["model_type"],
            version=card["version"],
            defaults={
                "algorithm": card["algorithm"],
                "metrics_json": card.get("metrics", {}),
                "threshold": card.get("threshold", 0.5),
                "trained_at": card.get("trained_at"),
            },
        )
        if not created:
            row.algorithm = card["algorithm"]
            row.metrics_json = card.get("metrics", {})
            row.threshold = card.get("threshold", 0.5)
            row.trained_at = card.get("trained_at")
        if created:
            # Появилась новая версия модели (например, после переобучения): она становится рабочей.
            ModelVersion.objects.filter(model_type=card["model_type"]).exclude(pk=row.pk).update(is_active=False)
            row.is_active = True
        elif not ModelVersion.objects.filter(model_type=card["model_type"], is_active=True).exclude(pk=row.pk).exists():
            row.is_active = True
        row.save()


def active_version(model_type):
    found = ModelVersion.objects.filter(model_type=model_type, is_active=True).first()
    if found is None:
        sync_model_versions()
        found = ModelVersion.objects.filter(model_type=model_type, is_active=True).first()
    return found


def language_label(code):
    return LANGUAGE_NAMES.get(code, LANGUAGE_NAMES["other"])


# ---------------------------------------------------------------- анализ

def _text_probability(text):
    from ml.baseline import predict_sms

    try:
        return predict_sms(text)["probability"]
    except (FileNotFoundError, OSError) as error:
        log.error("SMS-модель недоступна: %s", type(error).__name__)
        raise ModelUnavailable from error


def split_for_display(url, host):
    """Делит адрес на три части, чтобы в интерфейсе выделить домен."""
    at = url.lower().find(host) if host else -1
    if at < 0:
        return {"before": url, "host": "", "after": ""}
    return {"before": url[:at], "host": url[at:at + len(host)], "after": url[at + len(host):]}


def _judge_link(raw_url):
    try:
        address = normalize_url(raw_url)
    except ValueError:
        return None
    report = analyse_url(address)
    risk = url_risk(report["probability"])
    return LinkVerdict(
        url=raw_url,
        domain=report["host"],
        p_url=report["probability"],
        category=risk.category,
        risk_score=risk.score,
        features_json={
            "parts": split_for_display(raw_url, report["host"]),
            "features": report["features"],
            "checks": report["checks"],
        },
    )


def analyze_sms(text):
    language = detect_language(text)
    groups = find_rule_groups(normalize_sms(text))

    p_sms, note = None, None
    try:
        p_sms = round(_text_probability(text), 4)
    except ModelUnavailable:
        note = MODEL_DOWN_NOTE

    links = [verdict for verdict in map(_judge_link, find_urls(text)) if verdict]
    risk = sms_risk(p_sms, [link.p_url for link in links], len(groups), language)

    reasons = [RULE_TEXTS[code] for code in groups]
    reasons += [f"Ссылка {link.domain}: " + ", ".join(link.hits) for link in links if link.hits]
    if p_sms is not None and p_sms >= 0.5:
        reasons.append(f"Текстовая модель оценивает вероятность мошенничества в {p_sms:.0%}")
    if note:
        reasons.append(note)

    return AnalysisResult(
        language=language,
        rule_groups=groups,
        p_sms=p_sms,
        links=links,
        risk=risk,
        reasons=reasons or [NOTHING_FOUND["sms"]],
        recommendation=ADVICE["sms"][risk.category],
    )


def analyze_url(url):
    link = _judge_link(url)
    if link is None:
        raise ValueError("Некорректная ссылка.")
    reasons = [hit.capitalize() for hit in link.hits]
    return UrlAnalysis(link=link, reasons=reasons or [NOTHING_FOUND["url"]], recommendation=ADVICE["url"][link.category])


# ---------------------------------------------------------------- сохранение

def save_sms_check(user, text, store_text):
    result = analyze_sms(text)
    with transaction.atomic():
        check = Check.objects.create(
            user=user,
            check_type=Check.CheckType.SMS,
            input_text=text if store_text else None,
            input_masked=mask_text(text),
            language=result.language,
            category=result.risk.category,
            risk_level=result.risk.level,
            risk_score=result.risk.score,
            p_sms=result.p_sms,
            explanation=result.reasons,
            recommendation=result.recommendation,
            sms_model_version=active_version("sms"),
            url_model_version=active_version("url") if result.links else None,
        )
        UrlResult.objects.bulk_create(UrlResult(check_record=check, **link.as_row()) for link in result.links)
        DetectedFeature.objects.bulk_create(
            DetectedFeature(check_record=check, code=code, title=RULE_TEXTS[code], weight=1.0) for code in result.rule_groups
        )
    return check


def save_url_check(user, url):
    result = analyze_url(url)
    link = result.link
    with transaction.atomic():
        check = Check.objects.create(
            user=user,
            check_type=Check.CheckType.URL,
            input_text=url,
            input_masked=url,
            category=link.category,
            risk_level=LEVEL_FOR_CATEGORY[link.category],
            risk_score=link.risk_score,
            explanation=result.reasons,
            recommendation=result.recommendation,
            url_model_version=active_version("url"),
        )
        UrlResult.objects.create(check_record=check, **link.as_row())
    return check
