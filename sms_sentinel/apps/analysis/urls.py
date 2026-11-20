from django.urls import path

from . import views

urlpatterns = [
    path("check/sms/", views.CheckSmsPage.as_view(), name="check_sms"),
    path("check/url/", views.CheckUrlPage.as_view(), name="check_url"),
    path("checks/<int:pk>/", views.check_detail, name="check_detail"),
    path("checks/<int:pk>/delete/", views.check_delete, name="check_delete"),
    path("history/", views.history, name="history"),
    path("history/export/", views.history_export, name="history_export"),
]
