"""REST API (ТЗ, раздел 4.4): проверки, история, статистика, состояние."""
from django.core.paginator import Paginator
from django.db.models import Max
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.stats import build_snapshot, resolve_period
from ml.registry import model_cards

from .api_errors import ApiError
from .forms import HistoryFilterForm, SmsForm, UrlForm
from .models import Check
from .serializers import check_payload, check_summary
from .workflow import RateLimited, submit_check

PAGE_SIZE = 20


class SessionAuth(SessionAuthentication):
    """Сессионная проверка с CSRF; без входа API отвечает 401, а не 403."""

    def authenticate_header(self, request):
        return "Session"


class PrivateView(APIView):
    authentication_classes = [SessionAuth]
    permission_classes = [IsAuthenticated]


def _own_checks(request):
    return Check.objects.filter(user=request.user).select_related("sms_model_version", "url_model_version").prefetch_related("url_results", "features")


def _validation_failure(form, field):
    messages = form.errors.get(field) or ["Некорректный ввод."]
    return ApiError("VALIDATION_ERROR", messages[0], fields={field: list(messages)})


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from ml.baseline import MODEL_PATH

        cards = {card["model_type"]: {"version": card["version"], "algorithm": card["algorithm"]} for card in model_cards()}
        cards["sms"]["loaded"] = MODEL_PATH.exists()
        cards["url"]["loaded"] = True
        return Response({"status": "ok", "models": cards})


class _CheckView(PrivateView):
    kind = ""
    form_class = None
    field = ""

    def post(self, request):
        form = self.form_class(request.data if hasattr(request.data, "get") else {})
        if not form.is_valid():
            raise _validation_failure(form, self.field)
        try:
            check = submit_check(request.user, self.kind, form.cleaned_data[self.field])
        except RateLimited as error:
            raise ApiError("RATE_LIMITED", "Слишком много проверок. Подождите минуту и попробуйте снова.", status.HTTP_429_TOO_MANY_REQUESTS) from error
        check = _own_checks(request).get(pk=check.pk)
        return Response(check_payload(check))


class CheckSmsView(_CheckView):
    kind = Check.CheckType.SMS
    form_class = SmsForm
    field = "text"


class CheckUrlView(_CheckView):
    kind = Check.CheckType.URL
    form_class = UrlForm
    field = "url"


class ChecksView(PrivateView):
    def get(self, request):
        query = request.query_params
        form = HistoryFilterForm({
            "date_from": query.get("date_from", ""),
            "date_to": query.get("date_to", ""),
            "type": query.get("type", ""),
            "category": query.get("category", ""),
            "level": query.get("risk_level", ""),
        })
        if not form.is_valid():
            field = next(iter(form.errors))
            raise _validation_failure(form, field)
        queryset = form.apply(Check.objects.filter(user=request.user)).annotate(max_p_url=Max("url_results__p_url")).order_by("-created_at", "-id")
        page = Paginator(queryset, PAGE_SIZE).get_page(query.get("page"))
        return Response({
            "count": page.paginator.count,
            "page": page.number,
            "pages": page.paginator.num_pages,
            "results": [check_summary(check) for check in page],
        })


class CheckDetailView(PrivateView):
    def get(self, request, pk):
        return Response(check_payload(self._find(request, pk)))

    def delete(self, request, pk):
        self._find(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _find(request, pk):
        found = _own_checks(request).filter(pk=pk).first()
        if found is None:
            raise ApiError("NOT_FOUND", "Запись не найдена.", status.HTTP_404_NOT_FOUND)
        return found


class StatsSummaryView(PrivateView):
    def get(self, request):
        return Response(build_snapshot(Check.objects.filter(user=request.user), resolve_period(request)))
