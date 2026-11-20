"""Пауза после серии неудачных входов (ФТ-1.3): 5 попыток, затем блокировка на 60 секунд."""
from django.conf import settings
from django.core.cache import cache

from apps.panel.models import AdminAction

LOCKED_MESSAGE = f"Слишком много неудачных попыток. Повторите через {settings.LOGIN_LOCK_SECONDS} секунд."


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def _keys(request, username):
    base = f"login:{(username or '').strip().lower()}:{client_ip(request)}"
    return base + ":fails", base + ":locked"


def is_locked(request, username):
    return bool(cache.get(_keys(request, username)[1]))


def register_failure(request, username):
    """Запоминает неудачу. Возвращает число оставшихся попыток или None, если вход заблокирован."""
    fails_key, locked_key = _keys(request, username)
    fails = cache.get(fails_key, 0) + 1
    left = settings.LOGIN_MAX_ATTEMPTS - fails
    if left <= 0:
        cache.set(locked_key, True, settings.LOGIN_LOCK_SECONDS)
        cache.delete(fails_key)
        AdminAction.log(None, AdminAction.Action.LOGIN_LOCKED, (username or "")[:150], f"IP {client_ip(request)}")
        return None
    cache.set(fails_key, fails, settings.LOGIN_LOCK_SECONDS * 10)
    return left


def forget(request, username):
    cache.delete_many(_keys(request, username))
