import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .forms import HistoryFilterForm, SmsForm, UrlForm
from .models import Check
from .samples import SMS_SAMPLES, URL_SAMPLES
from .services import language_label
from .workflow import RateLimited, submit_check

HISTORY_PAGE_SIZE = 20


def own_check(request, pk):
    queryset = Check.objects.select_related("sms_model_version", "url_model_version").prefetch_related("url_results", "features")
    return get_object_or_404(queryset, pk=pk, user=request.user)


def result_context(check):
    """Всё, что нужно шаблонам результата для одной записи."""
    links = list(check.url_results.all())
    return {
        "check": check,
        "links": links,
        "language_name": language_label(check.language) if check.language else "",
        "reliable": check.language == "en" and check.p_sms is not None,
        "rules_count": len(check.features.all()),
        "hit_count": sum(1 for row in (links[0].checks if links else []) if row["hit"]),
    }


class CheckPage(LoginRequiredMixin, View):
    """Страница проверки: форма слева, результат справа.

    Страница работает и без JavaScript: форма отправляется обычным POST, а результат
    показывается после редиректа по адресу ?result=<id>. С JavaScript проверка идёт через REST API.
    """

    kind = ""
    form_class = None
    field = ""
    template_name = ""
    samples = ()

    def _form(self, data=None):
        initial = {self.field: self.request.GET.get("sample", "")}
        return self.form_class(data, initial=initial)

    def _shown(self):
        raw = self.request.GET.get("result", "")
        if not raw.isdigit():
            return {}
        check = own_check(self.request, int(raw))
        return result_context(check) if check.check_type == self.kind else {}

    def get(self, request):
        return render(request, self.template_name, {"form": self._form(), "samples": self.samples, **self._shown()})

    def post(self, request):
        form = self._form(request.POST)
        if form.is_valid():
            try:
                check = submit_check(request.user, self.kind, form.cleaned_data[self.field])
            except RateLimited:
                messages.error(request, "Слишком много проверок. Подождите минуту и попробуйте снова.")
                return render(request, self.template_name, {"form": form, "samples": self.samples}, status=429)
            return redirect(f"{reverse(request.resolver_match.url_name)}?result={check.pk}")
        return render(request, self.template_name, {"form": form, "samples": self.samples})


class CheckSmsPage(CheckPage):
    kind = Check.CheckType.SMS
    form_class = SmsForm
    field = "text"
    template_name = "analysis/check_sms.html"
    samples = SMS_SAMPLES


class CheckUrlPage(CheckPage):
    kind = Check.CheckType.URL
    form_class = UrlForm
    field = "url"
    template_name = "analysis/check_url.html"
    samples = URL_SAMPLES


@login_required
def check_detail(request, pk):
    return render(request, "analysis/result.html", result_context(own_check(request, pk)))


@login_required
def check_delete(request, pk):
    check = own_check(request, pk)
    if request.method == "POST":
        check.delete()
        messages.success(request, "Запись удалена из истории.")
        return redirect("history")
    return render(request, "analysis/confirm_delete.html", {"check": check})


def _filtered_history(request):
    form = HistoryFilterForm(request.GET or None)
    rows = form.apply(Check.objects.filter(user=request.user))
    return form, rows.annotate(max_p_url=Max("url_results__p_url")).order_by("-created_at", "-id")


@login_required
def history(request):
    form, rows = _filtered_history(request)
    page = Paginator(rows, HISTORY_PAGE_SIZE).get_page(request.GET.get("page"))
    carried = request.GET.copy()
    carried.pop("page", None)
    context = {
        "form": form,
        "page": page,
        "query": carried.urlencode(),
        "total": rows.count(),
        "filtered": any(value for value in carried.values()),
    }
    return render(request, "analysis/history.html", context)


@login_required
def history_export(request):
    _, rows = _filtered_history(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sentinel_history.csv"'
    response.write("﻿")
    out = csv.writer(response, delimiter=";")
    out.writerow(["Дата", "Тип", "Категория", "Risk Score", "Уровень риска", "P_sms", "P_url", "Текст или ссылка"])
    for check in rows:
        out.writerow([
            timezone.localtime(check.created_at).strftime("%d.%m.%Y %H:%M"),
            check.get_check_type_display(),
            check.category_label,
            check.risk_score,
            check.get_risk_level_display(),
            "" if check.p_sms is None else f"{check.p_sms:.2f}",
            "" if check.max_p_url is None else f"{check.max_p_url:.2f}",
            check.display_text,
        ])
    return response
