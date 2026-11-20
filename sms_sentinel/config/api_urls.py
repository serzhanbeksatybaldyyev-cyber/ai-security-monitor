"""Маршруты REST API, подключаются по адресу /api/v1/ (ТЗ, раздел 4.4)."""
from django.urls import path

from apps.accounts import api as accounts_api
from apps.analysis import api as analysis_api

urlpatterns = [
    path("auth/register/", accounts_api.RegisterView.as_view(), name="api_register"),
    path("auth/login/", accounts_api.LoginView.as_view(), name="api_login"),
    path("auth/logout/", accounts_api.LogoutView.as_view(), name="api_logout"),
    path("check/sms/", analysis_api.CheckSmsView.as_view(), name="api_check_sms"),
    path("check/url/", analysis_api.CheckUrlView.as_view(), name="api_check_url"),
    path("checks/", analysis_api.ChecksView.as_view(), name="api_checks"),
    path("checks/<int:pk>/", analysis_api.CheckDetailView.as_view(), name="api_check_detail"),
    path("stats/summary/", analysis_api.StatsSummaryView.as_view(), name="api_stats_summary"),
    path("health/", analysis_api.HealthView.as_view(), name="api_health"),
]
