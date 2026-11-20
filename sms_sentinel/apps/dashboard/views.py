from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.analysis.models import Check

from .stats import build_snapshot, resolve_period

RECENT_ROWS = 8


@login_required
def dashboard(request):
    own = Check.objects.filter(user=request.user)
    context = build_snapshot(own, resolve_period(request))
    context["recent"] = own[:RECENT_ROWS]
    return render(request, "dashboard/dashboard.html", context)


@login_required
def stats(request):
    own = Check.objects.filter(user=request.user)
    return render(request, "dashboard/stats.html", build_snapshot(own, resolve_period(request)))
