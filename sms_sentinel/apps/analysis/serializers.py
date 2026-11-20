"""Представление записей Check в JSON (ТЗ, раздел 4.4).

Обязательные поля ТЗ: id, type, language, category, risk_level, risk_score, p_sms, urls, features,
explanation, recommendation, disclaimer, model_versions, created_at. Остальные поля добавлены
для интерфейса: подписи на русском, тон, части адреса для выделения домена и т. п.
"""
from django.urls import reverse
from django.utils import timezone

from ml.risk import load_config

from .models import TONES
from .services import language_label

DISCLAIMER = "Оценка носит вероятностный характер и не гарантирует безопасность."

SMS_CODES = {"safe": "SAFE", "suspicious": "SUSPICIOUS", "fraud": "FRAUDULENT"}
URL_CODES = {"safe": "SAFE", "suspicious": "SUSPICIOUS", "fraud": "DANGEROUS"}


def _link_payload(link):
    return {
        "url": link.url,
        "domain": link.domain,
        "p_url": round(link.p_url, 4),
        "category": URL_CODES[link.category],
        "category_label": link.category_label,
        "tone": TONES[link.category],
        "icon": link.icon,
        "risk_score": link.risk_score,
        "parts": link.parts,
        "checks": link.checks,
    }


def check_payload(check):
    links = list(check.url_results.all())
    is_sms = check.check_type == check.CheckType.SMS
    codes = SMS_CODES if is_sms else URL_CODES
    zones = load_config()["thresholds"]
    p_url_max = max((link.p_url for link in links), default=None)

    return {
        "id": check.pk,
        "type": check.get_check_type_display(),
        "language": check.language or None,
        "category": codes[check.category],
        "risk_level": check.risk_level.upper(),
        "risk_score": check.risk_score,
        "p_sms": check.p_sms,
        "p_url_max": None if p_url_max is None else round(p_url_max, 4),
        "urls": [_link_payload(link) for link in links],
        "features": [feature.code for feature in check.features.all()],
        "explanation": check.explanation,
        "recommendation": check.recommendation,
        "disclaimer": DISCLAIMER,
        "model_versions": {
            "sms": check.sms_model_version.version if check.sms_model_version else None,
            "url": check.url_model_version.version if check.url_model_version else None,
        },
        "created_at": timezone.localtime(check.created_at).isoformat(timespec="seconds"),
        # --- поля для интерфейса ---
        "category_label": check.category_label,
        "tone": check.tone,
        "icon": check.icon,
        "verdict_title": check.verdict_title,
        "risk_level_label": check.get_risk_level_display(),
        "language_name": language_label(check.language) if check.language else "",
        "reliable": check.language == "en" and check.p_sms is not None,
        "text": check.display_text,
        "is_masked": check.is_masked and is_sms,
        "created_display": timezone.localtime(check.created_at).strftime("%d.%m.%Y %H:%M"),
        "versions_label": check.versions,
        "detail_url": reverse("check_detail", args=[check.pk]),
        "delete_url": reverse("check_delete", args=[check.pk]),
        "zones": {"medium": zones["medium"], "high": zones["high"]},
    }


def check_summary(check):
    """Короткая строка для списка истории."""
    codes = SMS_CODES if check.check_type == check.CheckType.SMS else URL_CODES
    return {
        "id": check.pk,
        "type": check.get_check_type_display(),
        "category": codes[check.category],
        "category_label": check.category_label,
        "risk_level": check.risk_level.upper(),
        "risk_score": check.risk_score,
        "p_sms": check.p_sms,
        "fragment": check.short_text,
        "created_at": timezone.localtime(check.created_at).isoformat(timespec="seconds"),
    }
