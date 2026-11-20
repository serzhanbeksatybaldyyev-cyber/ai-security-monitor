from django import forms

from ml.url_features import MAX_URL_LENGTH, normalize_url

from .models import Check


class SmsForm(forms.Form):
    text = forms.CharField(
        label="Текст сообщения",
        max_length=1000,
        strip=True,
        error_messages={
            "required": "Текст SMS не может быть пустым.",
            "max_length": "Текст не должен быть длиннее 1000 символов.",
        },
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5, "maxlength": 1000, "placeholder": "Вставьте текст сообщения, которое вызвало сомнения", "data-counter": "sms-counter"}),
    )


class UrlForm(forms.Form):
    url = forms.CharField(
        label="Ссылка",
        max_length=MAX_URL_LENGTH,
        strip=True,
        error_messages={"required": "Введите ссылку.", "max_length": f"Ссылка длиннее {MAX_URL_LENGTH} символов."},
        widget=forms.TextInput(attrs={"class": "form-control font-monospace", "placeholder": "https://example.com/page", "autocomplete": "off"}),
    )

    def clean_url(self):
        value = self.cleaned_data["url"]
        try:
            normalize_url(value)
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error
        return value


class HistoryFilterForm(forms.Form):
    date_from = forms.DateField(label="С даты", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    date_to = forms.DateField(label="По дату", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    type = forms.ChoiceField(label="Тип", required=False, choices=[("", "Все")] + list(Check.CheckType.choices), widget=forms.Select(attrs={"class": "form-select"}))
    category = forms.ChoiceField(label="Категория", required=False, choices=[("", "Все")] + list(Check.Category.choices), widget=forms.Select(attrs={"class": "form-select"}))
    level = forms.ChoiceField(label="Уровень риска", required=False, choices=[("", "Все")] + list(Check.Level.choices), widget=forms.Select(attrs={"class": "form-select"}))

    def apply(self, queryset):
        if not self.is_valid():
            return queryset
        data = self.cleaned_data
        if data["date_from"]:
            queryset = queryset.filter(created_at__date__gte=data["date_from"])
        if data["date_to"]:
            queryset = queryset.filter(created_at__date__lte=data["date_to"])
        if data["type"]:
            queryset = queryset.filter(check_type=data["type"])
        if data["category"]:
            queryset = queryset.filter(category=data["category"])
        if data["level"]:
            queryset = queryset.filter(risk_level=data["level"])
        return queryset
