from django.conf import settings
from django.db import models


class AdminAction(models.Model):
    class Action(models.TextChoices):
        BLOCK = "block", "Блокировка пользователя"
        UNBLOCK = "unblock", "Разблокировка пользователя"
        GRANT_ADMIN = "grant_admin", "Выдача прав администратора"
        REVOKE_ADMIN = "revoke_admin", "Снятие прав администратора"
        CLEAR_HISTORY = "clear_history", "Очистка истории пользователя"
        ACTIVATE_MODEL = "activate_model", "Смена активной версии модели"
        EXPORT = "export", "Выгрузка статистики"
        LOGIN_LOCKED = "login_locked", "Блокировка входа после неудачных попыток"

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_actions")
    action = models.CharField("Действие", max_length=20, choices=Action.choices)
    target = models.CharField("Объект", max_length=150, blank=True)
    details = models.CharField("Подробности", max_length=255, blank=True)
    created_at = models.DateTimeField("Время", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "admin_actions"
        ordering = ["-created_at", "-id"]
        verbose_name = "действие администратора"
        verbose_name_plural = "журнал действий"

    def __str__(self):
        return f"{self.get_action_display()}: {self.target}"

    @classmethod
    def log(cls, actor, action, target="", details=""):
        return cls.objects.create(actor=actor if actor and actor.is_authenticated else None, action=action, target=str(target)[:150], details=details[:255])
