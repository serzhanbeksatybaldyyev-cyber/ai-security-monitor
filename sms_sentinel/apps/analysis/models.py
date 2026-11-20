from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

URL_CATEGORY_NAMES = {"safe": "Безопасная", "suspicious": "Подозрительная", "fraud": "Опасная"}

# Как категория выглядит в интерфейсе: цветовой тон и иконка (цвет никогда не единственный носитель смысла).
TONES = {"safe": "safe", "suspicious": "warn", "fraud": "fraud"}
ICONS = {"safe": "i-ok", "suspicious": "i-warn", "fraud": "i-stop"}

VERDICT_TITLES = {
    "sms": {"safe": "Признаков мошенничества нет", "suspicious": "Есть признаки обмана", "fraud": "Похоже на мошенничество"},
    "url": {"safe": "Признаков подделки нет", "suspicious": "Ссылка вызывает сомнения", "fraud": "Опасная ссылка"},
}


class Category(models.TextChoices):
    SAFE = "safe", "Безопасное"
    SUSPICIOUS = "suspicious", "Подозрительное"
    FRAUD = "fraud", "Мошенническое"


class ModelVersion(models.Model):
    class ModelType(models.TextChoices):
        SMS = "sms", "SMS"
        URL = "url", "URL"

    model_type = models.CharField("Тип модели", max_length=3, choices=ModelType.choices)
    version = models.CharField("Версия", max_length=50)
    algorithm = models.CharField("Алгоритм", max_length=200)
    metrics_json = models.JSONField("Метрики", default=dict, blank=True)
    threshold = models.FloatField("Порог", default=0.5)
    trained_at = models.DateTimeField("Дата обучения", null=True, blank=True)
    is_active = models.BooleanField("Активна", default=False)

    class Meta:
        db_table = "model_versions"
        ordering = ["model_type", "-id"]
        constraints = [models.UniqueConstraint(fields=["model_type", "version"], name="unique_model_version")]
        verbose_name = "версия модели"
        verbose_name_plural = "версии моделей"

    def __str__(self):
        return self.version


class Check(models.Model):
    class CheckType(models.TextChoices):
        SMS = "sms", "SMS"
        URL = "url", "URL"

    Category = Category

    class Level(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checks")
    check_type = models.CharField("Тип", max_length=3, choices=CheckType.choices)
    input_text = models.TextField("Полный текст", null=True, blank=True)
    input_masked = models.TextField("Маскированный текст", blank=True)
    language = models.CharField("Язык", max_length=8, blank=True)
    category = models.CharField("Категория", max_length=12, choices=Category.choices)
    risk_level = models.CharField("Уровень риска", max_length=8, choices=Level.choices)
    risk_score = models.PositiveSmallIntegerField("Risk Score", validators=[MaxValueValidator(100)])
    p_sms = models.FloatField("P_sms", null=True, blank=True)
    explanation = models.JSONField("Причины", default=list, blank=True)
    recommendation = models.TextField("Рекомендация", blank=True)
    sms_model_version = models.ForeignKey(ModelVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="sms_checks")
    url_model_version = models.ForeignKey(ModelVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="url_checks")
    created_at = models.DateTimeField("Дата проверки", auto_now_add=True)

    class Meta:
        db_table = "checks"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"], name="checks_user_created_idx"),
            models.Index(fields=["category"], name="checks_category_idx"),
        ]
        verbose_name = "проверка"
        verbose_name_plural = "проверки"

    def __str__(self):
        return f"{self.get_check_type_display()} №{self.pk} — {self.category}"

    @property
    def is_masked(self):
        return self.input_text is None

    @property
    def display_text(self):
        return self.input_masked if self.input_text is None else self.input_text

    @property
    def short_text(self):
        text = self.display_text
        return text if len(text) <= 60 else text[:60] + "…"

    @property
    def category_label(self):
        if self.check_type == self.CheckType.URL:
            return URL_CATEGORY_NAMES[self.category]
        return self.get_category_display()

    @property
    def tone(self):
        return TONES[self.category]

    @property
    def icon(self):
        return ICONS[self.category]

    @property
    def verdict_title(self):
        return VERDICT_TITLES[self.check_type][self.category]

    @property
    def p_url(self):
        values = [result.p_url for result in self.url_results.all()]
        return max(values) if values else None

    @property
    def versions(self):
        return ", ".join(str(version) for version in (self.sms_model_version, self.url_model_version) if version)


class UrlResult(models.Model):
    check_record = models.ForeignKey(Check, on_delete=models.CASCADE, related_name="url_results", db_column="check_id")
    url = models.CharField("Ссылка", max_length=2048)
    domain = models.CharField("Домен", max_length=255, db_index=True)
    p_url = models.FloatField("P_url")
    category = models.CharField("Категория", max_length=12, choices=Category.choices)
    risk_score = models.PositiveSmallIntegerField("Risk Score", validators=[MaxValueValidator(100)])
    features_json = models.JSONField("Признаки", default=dict)

    class Meta:
        db_table = "url_results"
        ordering = ["id"]
        verbose_name = "результат по ссылке"
        verbose_name_plural = "результаты по ссылкам"

    def __str__(self):
        return self.domain

    @property
    def category_label(self):
        return URL_CATEGORY_NAMES[self.category]

    @property
    def tone(self):
        return TONES[self.category]

    @property
    def icon(self):
        return ICONS[self.category]

    @property
    def parts(self):
        return self.features_json.get("parts", {"before": self.url, "host": "", "after": ""})

    @property
    def checks(self):
        return self.features_json.get("checks", [])


class DetectedFeature(models.Model):
    check_record = models.ForeignKey(Check, on_delete=models.CASCADE, related_name="features", db_column="check_id")
    code = models.CharField("Код", max_length=30, db_index=True)
    title = models.CharField("Название", max_length=200)
    weight = models.FloatField("Вес", default=1.0)

    class Meta:
        db_table = "detected_features"
        ordering = ["id"]
        verbose_name = "сработавший признак"
        verbose_name_plural = "сработавшие признаки"

    def __str__(self):
        return self.code
