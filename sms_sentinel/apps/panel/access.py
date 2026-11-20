from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def admin_required(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not request.user.is_staff:
            return render(request, "panel/forbidden.html", status=403)
        return view(request, *args, **kwargs)

    return login_required(guarded)


def can_manage(actor, target):
    if actor.pk == target.pk:
        return False
    if target.is_superuser and not actor.is_superuser:
        return False
    return True
