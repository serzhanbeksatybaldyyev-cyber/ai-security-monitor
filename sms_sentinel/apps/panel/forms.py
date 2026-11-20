from django import forms
from django.db.models import Q

from apps.analysis.forms import HistoryFilterForm
from ml.language import LANGUAGE_NAMES

from .models import AdminAction


class UserFilterForm(forms.Form):
    q = forms.CharField(label="Поиск", required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Логин или e-mail"}))
    role = forms.ChoiceField(label="Роль", required=False, choices=[("", "Все"), ("admin", "Администраторы"), ("user", "Пользователи")], widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(label="Статус", required=False, choices=[("", "Все"), ("active", "Активные"), ("blocked", "Заблокированные")], widget=forms.Select(attrs={"class": "form-select"}))

    def apply(self, queryset):
        if not self.is_valid():
            return queryset
        data = self.cleaned_data
        if data["q"]:
            queryset = queryset.filter(Q(username__icontains=data["q"]) | Q(email__icontains=data["q"]))
        if data["role"]:
            queryset = queryset.filter(is_staff=data["role"] == "admin")
        if data["status"]:
            queryset = queryset.filter(is_active=data["status"] == "active")
        return queryset


class AllChecksFilterForm(HistoryFilterForm):
    user = forms.CharField(label="Пользователь", required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Логин"}))
    language = forms.ChoiceField(label="Язык", required=False, choices=[("", "Все")] + list(LANGUAGE_NAMES.items()), widget=forms.Select(attrs={"class": "form-select"}))

    def apply(self, queryset):
        queryset = super().apply(queryset)
        if not self.is_valid():
            return queryset
        if self.cleaned_data["user"]:
            queryset = queryset.filter(user__username__iexact=self.cleaned_data["user"].strip())
        if self.cleaned_data["language"]:
            queryset = queryset.filter(language=self.cleaned_data["language"])
        return queryset


class AuditFilterForm(forms.Form):
    action = forms.ChoiceField(label="Действие", required=False, choices=[("", "Все")] + list(AdminAction.Action.choices), widget=forms.Select(attrs={"class": "form-select"}))

    def apply(self, queryset):
        if self.is_valid() and self.cleaned_data["action"]:
            return queryset.filter(action=self.cleaned_data["action"])
        return queryset
