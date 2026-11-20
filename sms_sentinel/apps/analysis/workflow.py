"""Единая точка отправки проверки для веб-страниц и REST API."""
from apps.accounts.models import UserProfile

from . import throttle
from .models import Check
from .services import save_sms_check, save_url_check


class RateLimited(Exception):
    """Пользователь превысил число проверок в минуту."""


def submit_check(user, kind, value):
    """Выполняет проверку и возвращает запись Check.

    Повтор точно такого же ввода в течение нескольких секунд не создаёт дубликат
    и не расходует лимит (защита от двойной отправки формы).
    """
    earlier = throttle.recent_duplicate(user, kind, value)
    if earlier:
        existing = Check.objects.filter(pk=earlier, user=user).first()
        if existing:
            return existing

    if throttle.over_limit(user):
        raise RateLimited

    if kind == Check.CheckType.SMS:
        check = save_sms_check(user, value, UserProfile.for_user(user).store_sms_text)
    else:
        check = save_url_check(user, value)
    throttle.remember(user, kind, value, check.pk)
    return check
