"""Защита отправки проверок: лимит частоты (НФТ-6) и защита от двойного клика (НФТ-3)."""
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

DUPLICATE_WINDOW = 4  # секунд: повтор той же формы возвращает уже созданную запись


def over_limit(user):
    """Считает проверки пользователя в текущей минуте; True, если лимит превышен."""
    key = f"rate:{user.pk}:{timezone.now():%Y%m%d%H%M}"
    seen = cache.get(key, 0) + 1
    cache.set(key, seen, 70)
    return seen > settings.CHECKS_PER_MINUTE


def _fingerprint(user, kind, payload):
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"dup:{user.pk}:{kind}:{digest}"


def recent_duplicate(user, kind, payload):
    """Возвращает id записи, созданной для точно такого же ввода несколько секунд назад."""
    return cache.get(_fingerprint(user, kind, payload))


def remember(user, kind, payload, check_id):
    cache.set(_fingerprint(user, kind, payload), check_id, DUPLICATE_WINDOW)
