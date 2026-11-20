from django.urls import path

from . import views

urlpatterns = [
    path("", views.overview, name="panel_overview"),
    path("users/", views.users, name="panel_users"),
    path("users/<int:pk>/", views.user_detail, name="panel_user"),
    path("users/<int:pk>/<slug:action>/", views.user_action, name="panel_user_action"),
    path("checks/", views.checks, name="panel_checks"),
    path("checks/export/", views.checks_export, name="panel_checks_export"),
    path("models/", views.models_page, name="panel_models"),
    path("models/sync/", views.models_sync, name="panel_models_sync"),
    path("models/<int:pk>/activate/", views.model_activate, name="panel_model_activate"),
    path("audit/", views.audit, name="panel_audit"),
]
