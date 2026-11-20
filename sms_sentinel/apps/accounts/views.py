from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render, resolve_url

from apps.analysis.models import Check

from . import lockout
from .forms import LoginForm, ProfileForm, RegisterForm, StyledPasswordChangeForm
from .models import UserProfile


class LimitedLoginView(LoginView):
    """Вход с паузой после серии неудачных попыток."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def _username(self):
        return self.request.POST.get("username", "")

    def get_default_redirect_url(self):
        if self.request.user.is_staff:
            return resolve_url("panel_overview")
        return resolve_url(settings.LOGIN_REDIRECT_URL)

    def post(self, request, *args, **kwargs):
        if lockout.is_locked(request, self._username()):
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, lockout.LOCKED_MESSAGE)
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        if form.has_error("__all__", "inactive"):
            return super().form_invalid(form)
        left = lockout.register_failure(self.request, self._username())
        form.add_error(None, lockout.LOCKED_MESSAGE if left is None else f"Осталось попыток: {left}.")
        return super().form_invalid(form)

    def form_valid(self, form):
        lockout.forget(self.request, self._username())
        return super().form_valid(form)


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserProfile.for_user(user)
        login(request, user)
        messages.success(request, "Аккаунт создан. Добро пожаловать в Sentinel!")
        return redirect("dashboard")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    settings_row = UserProfile.for_user(request.user)
    form = ProfileForm(instance=settings_row)
    password_form = StyledPasswordChangeForm(request.user)
    if request.method == "POST" and request.POST.get("section") == "settings":
        form = ProfileForm(request.POST, instance=settings_row)
        if form.is_valid():
            form.save()
            messages.success(request, "Настройки сохранены.")
            return redirect("profile")
    if request.method == "POST" and request.POST.get("section") == "password":
        password_form = StyledPasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Пароль изменён.")
            return redirect("profile")
    context = {
        "form": form,
        "password_form": password_form,
        "profile": settings_row,
        "checks_total": Check.objects.filter(user=request.user).count(),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def clear_history(request):
    checks = Check.objects.filter(user=request.user)
    if request.method == "POST":
        deleted = checks.count()
        checks.delete()
        messages.success(request, f"История очищена. Удалено записей: {deleted}.")
        return redirect("profile")
    return render(request, "accounts/clear_history.html", {"checks_total": checks.count()})
