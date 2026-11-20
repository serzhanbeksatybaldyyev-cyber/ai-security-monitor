import csv

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.analysis.models import Check, DetectedFeature, ModelVersion, UrlResult
from apps.analysis.services import RULE_TEXTS, sync_model_versions
from apps.dashboard.stats import build_snapshot, resolve_period, window_start
from ml.language import LANGUAGE_NAMES
from ml.risk import load_config
from ml.rules import RULE_GROUPS
from ml.url_features import URL_CHECKS

from .access import admin_required, can_manage
from .forms import AllChecksFilterForm, AuditFilterForm, UserFilterForm
from .models import AdminAction

USER_ACTIONS = {
    "block": {
        "title": "Заблокировать пользователя",
        "text": "Пользователь не сможет войти на сайт. Его история сохранится.",
        "button": "Заблокировать",
        "style": "danger",
    },
    "unblock": {
        "title": "Разблокировать пользователя",
        "text": "Пользователь снова сможет входить на сайт.",
        "button": "Разблокировать",
        "style": "primary",
    },
    "grant_admin": {
        "title": "Выдать права администратора",
        "text": "Пользователь получит доступ к панели администратора: статистике всей системы, списку пользователей и журналу действий.",
        "button": "Выдать права",
        "style": "primary",
    },
    "revoke_admin": {
        "title": "Снять права администратора",
        "text": "Пользователь потеряет доступ к панели администратора.",
        "button": "Снять права",
        "style": "danger",
    },
    "clear_history": {
        "title": "Очистить историю пользователя",
        "text": "Все проверки пользователя, найденные ссылки и признаки будут удалены без возможности восстановления.",
        "button": "Очистить историю",
        "style": "danger",
    },
}


def _query_without_page(request):
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()


@admin_required
def overview(request):
    days = resolve_period(request)
    start = window_start(days)
    context = build_snapshot(Check.objects.all(), days)
    period_checks = Check.objects.filter(created_at__date__gte=start).order_by()

    context["users_total"] = User.objects.count()
    context["admins_total"] = User.objects.filter(is_staff=True).count()
    context["blocked_total"] = User.objects.filter(is_active=False).count()
    context["new_users"] = User.objects.filter(date_joined__date__gte=start).count()
    context["active_users"] = period_checks.values("user").distinct().count()

    languages = dict(period_checks.filter(check_type="sms").values_list("language").annotate(n=Count("id")))
    sms_total = sum(languages.values())
    context["languages"] = [
        {"code": code, "label": label, "value": languages.get(code, 0), "width": round(100 * languages.get(code, 0) / sms_total) if sms_total else 0}
        for code, label in LANGUAGE_NAMES.items()
    ]

    context["top_users"] = (
        User.objects.annotate(
            n=Count("checks", filter=Q(checks__created_at__date__gte=start)),
            fraud=Count("checks", filter=Q(checks__created_at__date__gte=start, checks__category="fraud")),
        )
        .filter(n__gt=0)
        .order_by("-n", "username")[:5]
    )
    context["risky_domains"] = (
        UrlResult.objects.filter(check_record__created_at__date__gte=start, category__in=["suspicious", "fraud"])
        .values("domain")
        .annotate(n=Count("id"), top=Max("risk_score"))
        .order_by("-n", "domain")[:5]
    )
    context["models"] = _active_models()
    context["recent"] = Check.objects.select_related("user")[:10]
    return render(request, "panel/overview.html", context)


def _active_models():
    if not ModelVersion.objects.filter(is_active=True).exists():
        sync_model_versions()
    return ModelVersion.objects.filter(is_active=True).annotate(
        used=Count("sms_checks", distinct=True) + Count("url_checks", distinct=True)
    )


@admin_required
def users(request):
    form = UserFilterForm(request.GET or None)
    queryset = form.apply(User.objects.all()).annotate(
        checks_total=Count("checks", distinct=True),
        fraud_total=Count("checks", filter=Q(checks__category="fraud"), distinct=True),
        last_check=Max("checks__created_at"),
    ).order_by("-is_staff", "username")
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    context = {"form": form, "page": page, "query": _query_without_page(request), "total": queryset.count()}
    return render(request, "panel/users.html", context)


@admin_required
def user_detail(request, pk):
    target = get_object_or_404(User, pk=pk)
    checks = Check.objects.filter(user=target).order_by()
    by_category = dict(checks.values_list("category").annotate(n=Count("id")))
    by_type = dict(checks.values_list("check_type").annotate(n=Count("id")))
    context = {
        "target": target,
        "profile": UserProfile.for_user(target),
        "checks_total": checks.count(),
        "by_category": [{"code": code, "label": label, "value": by_category.get(code, 0)} for code, label in Check.Category.choices],
        "sms_total": by_type.get("sms", 0),
        "url_total": by_type.get("url", 0),
        "recent": Check.objects.filter(user=target)[:10],
        "actions": AdminAction.objects.filter(target=target.username).select_related("actor")[:10],
        "can_manage": can_manage(request.user, target),
    }
    return render(request, "panel/user_detail.html", context)


def _apply_user_action(actor, target, action):
    if action == "block":
        target.is_active = False
        target.save(update_fields=["is_active"])
        return "Пользователь заблокирован."
    if action == "unblock":
        target.is_active = True
        target.save(update_fields=["is_active"])
        return "Пользователь разблокирован."
    if action == "grant_admin":
        target.is_staff = True
        target.save(update_fields=["is_staff"])
        return "Права администратора выданы."
    if action == "revoke_admin":
        target.is_staff = False
        target.save(update_fields=["is_staff"])
        return "Права администратора сняты."
    deleted = Check.objects.filter(user=target).count()
    Check.objects.filter(user=target).delete()
    return f"Удалено проверок: {deleted}."


@admin_required
def user_action(request, pk, action):
    if action not in USER_ACTIONS:
        raise Http404
    target = get_object_or_404(User, pk=pk)
    if not can_manage(request.user, target):
        messages.error(request, "Это действие нельзя выполнить для своей учётной записи или для главного администратора.")
        return redirect("panel_user", pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            note = _apply_user_action(request.user, target, action)
            AdminAction.log(request.user, action, target.username, note)
        messages.success(request, note)
        return redirect("panel_user", pk=pk)
    return render(request, "panel/confirm.html", {"target": target, "action": action, **USER_ACTIONS[action]})


def _all_checks(request):
    form = AllChecksFilterForm(request.GET or None)
    queryset = form.apply(Check.objects.select_related("user", "sms_model_version", "url_model_version"))
    return form, queryset


@admin_required
def checks(request):
    form, queryset = _all_checks(request)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    context = {"form": form, "page": page, "query": _query_without_page(request), "total": queryset.count(), "languages": LANGUAGE_NAMES}
    return render(request, "panel/checks.html", context)


@admin_required
def checks_export(request):
    _, queryset = _all_checks(request)
    AdminAction.log(request.user, AdminAction.Action.EXPORT, "все проверки", f"строк: {queryset.count()}")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sentinel_all_checks.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["№", "Дата", "Пользователь", "Тип", "Язык", "Категория", "Уровень риска", "Risk Score", "P_sms", "Модели"])
    for check in queryset:
        writer.writerow([
            check.pk,
            timezone.localtime(check.created_at).strftime("%d.%m.%Y %H:%M"),
            check.user.username,
            check.get_check_type_display(),
            check.language,
            check.category_label,
            check.get_risk_level_display(),
            check.risk_score,
            "" if check.p_sms is None else f"{check.p_sms:.2f}",
            check.versions,
        ])
    return response


@admin_required
def models_page(request):
    if not ModelVersion.objects.exists():
        sync_model_versions()
    versions = ModelVersion.objects.annotate(used=Count("sms_checks", distinct=True) + Count("url_checks", distinct=True))
    hits = dict(DetectedFeature.objects.order_by().values_list("code").annotate(n=Count("id")))
    rules = [
        {"code": code, "title": RULE_TEXTS[code], "patterns": len(patterns), "hits": hits.get(code, 0)}
        for code, patterns in RULE_GROUPS.items()
    ]
    url_rules = [{"label": label, "weight": weight, "reason": reason} for _, label, _, _, weight, reason in URL_CHECKS]
    context = {"versions": versions, "config": load_config(), "rules": rules, "url_rules": url_rules}
    return render(request, "panel/models.html", context)


@admin_required
@require_POST
def model_activate(request, pk):
    version = get_object_or_404(ModelVersion, pk=pk)
    with transaction.atomic():
        ModelVersion.objects.filter(model_type=version.model_type).update(is_active=False)
        version.is_active = True
        version.save(update_fields=["is_active"])
        AdminAction.log(request.user, AdminAction.Action.ACTIVATE_MODEL, version.version, f"тип: {version.get_model_type_display()}")
    messages.success(request, f"Активная версия {version.get_model_type_display()}-модели: {version.version}.")
    return redirect("panel_models")


@admin_required
@require_POST
def models_sync(request):
    sync_model_versions()
    messages.success(request, "Сведения о моделях обновлены из файлов метаданных.")
    return redirect("panel_models")


@admin_required
def audit(request):
    form = AuditFilterForm(request.GET or None)
    queryset = form.apply(AdminAction.objects.select_related("actor"))
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    context = {"form": form, "page": page, "query": _query_without_page(request), "total": queryset.count()}
    return render(request, "panel/audit.html", context)
