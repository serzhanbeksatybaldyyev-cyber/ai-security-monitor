"""Сводная статистика проверок для Dashboard, страницы «Статистика» и панели администратора.

Все числа считаются агрегирующими запросами к БД, поэтому время ответа почти не зависит
от числа записей (НФТ-2). Для графиков отдаётся готовый словарь `chart`, который шаблон
передаёт в Chart.js через json_script.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.analysis.models import TONES, Check, DetectedFeature
from apps.analysis.services import RULE_SHORT

PERIOD_CHOICES = (7, 30, 90)
DEFAULT_PERIOD = 30

PLURAL_LABELS = {"safe": "Безопасные", "suspicious": "Подозрительные", "fraud": "Мошеннические"}
LEVEL_TONES = {"low": "safe", "medium": "warn", "high": "fraud"}


def resolve_period(request):
    raw = request.GET.get("period", str(DEFAULT_PERIOD))
    return int(raw) if raw.isdigit() and int(raw) in PERIOD_CHOICES else DEFAULT_PERIOD


def window_start(days):
    return timezone.localdate() - timedelta(days=days - 1)


def _counts(queryset, field):
    return dict(queryset.values_list(field).annotate(n=Count("id")).order_by())


def _share(value, total):
    return round(100 * value / total) if total else 0


def _daily_series(queryset, start, days):
    """Число проверок по дням и категориям; дни без проверок заполняются нулями."""
    per_day = defaultdict(lambda: defaultdict(int))
    rows = (
        queryset.annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
        .values_list("day", "category")
        .annotate(n=Count("id"))
        .order_by()
    )
    for day, category, n in rows:
        per_day[day][category] = n

    labels, series = [], {code: [] for code, _ in Check.Category.choices}
    for offset in range(days):
        day = start + timedelta(days=offset)
        labels.append(day.strftime("%d.%m"))
        for code in series:
            series[code].append(per_day[day][code])
    totals = [sum(values) for values in zip(*series.values())]
    return labels, series, totals


def build_snapshot(checks, days):
    start = window_start(days)
    scope = checks.filter(created_at__date__gte=start).order_by()

    total = scope.count()
    by_kind = _counts(scope, "check_type")
    by_category = _counts(scope, "category")
    by_level = _counts(scope, "risk_level")
    average = scope.aggregate(value=Avg("risk_score"))["value"]

    categories = [
        {
            "code": code,
            "label": PLURAL_LABELS[code],
            "tone": TONES[code],
            "value": by_category.get(code, 0),
            "share": _share(by_category.get(code, 0), total),
        }
        for code, _ in Check.Category.choices
    ]
    levels = [
        {"code": code, "label": label, "tone": LEVEL_TONES[code], "value": by_level.get(code, 0)}
        for code, label in Check.Level.choices
    ]

    top_rows = list(
        DetectedFeature.objects.filter(check_record__in=scope)
        .values_list("code")
        .annotate(n=Count("id"))
        .order_by("-n", "code")[:5]
    )
    peak = max((n for _, n in top_rows), default=0)
    top_signs = [
        {"code": code, "label": RULE_SHORT.get(code, code), "value": n, "width": _share(n, peak)}
        for code, n in top_rows
    ]

    day_labels, day_series, day_totals = _daily_series(scope, start, days)
    chart = {
        "categories": {
            "labels": [item["label"] for item in categories],
            "values": [item["value"] for item in categories],
            "tones": [item["tone"] for item in categories],
        },
        "daily": {
            "labels": day_labels,
            "totals": day_totals,
            "series": [
                {"label": PLURAL_LABELS[code], "tone": TONES[code], "values": values}
                for code, values in day_series.items()
            ],
        },
        "levels": {
            "labels": [item["label"] for item in levels],
            "values": [item["value"] for item in levels],
            "tones": [item["tone"] for item in levels],
        },
        "signs": {
            "labels": [item["label"] for item in top_signs],
            "values": [item["value"] for item in top_signs],
        },
    }

    return {
        "period": str(days),
        "periods": [str(value) for value in PERIOD_CHOICES],
        "total": total,
        "sms_total": by_kind.get("sms", 0),
        "url_total": by_kind.get("url", 0),
        "average_score": round(average) if average is not None else 0,
        "categories": categories,
        "levels": levels,
        "top_signs": top_signs,
        "chart": chart,
    }
