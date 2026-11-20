from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Language(models.TextChoices):
        RU = "ru", "Русский"
        KK = "kk", "Қазақша"
        EN = "en", "English"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    store_sms_text = models.BooleanField("Хранить полный текст SMS", default=False)
    preferred_language = models.CharField("Язык интерфейса", max_length=2, choices=Language.choices, default=Language.RU)

    class Meta:
        db_table = "user_profile"
        verbose_name = "профиль"
        verbose_name_plural = "профили"

    def __str__(self):
        return f"Профиль {self.user}"

    @classmethod
    def for_user(cls, user):
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
