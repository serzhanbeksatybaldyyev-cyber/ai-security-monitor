"""REST API учётных записей (ТЗ, раздел 4.4): регистрация, вход, выход."""
from django.contrib.auth import login, logout
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.api_errors import ApiError

from . import lockout
from .forms import LoginForm, RegisterForm
from .models import UserProfile


def _user_payload(user):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "date_joined": user.date_joined.isoformat(timespec="seconds"),
        "is_staff": user.is_staff,
    }


class _Open(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class RegisterView(_Open):
    def post(self, request):
        form = RegisterForm(request.data)
        if not form.is_valid():
            fields = {name: [str(message) for message in messages] for name, messages in form.errors.items()}
            first = next(iter(fields.values()))[0]
            raise ApiError("VALIDATION_ERROR", first, fields=fields)
        user = form.save()
        UserProfile.for_user(user)
        login(request._request, user)
        return Response(_user_payload(user), status=status.HTTP_201_CREATED)


class LoginView(_Open):
    def post(self, request):
        username = str(request.data.get("username", ""))
        if lockout.is_locked(request._request, username):
            raise ApiError("RATE_LIMITED", lockout.LOCKED_MESSAGE, status.HTTP_429_TOO_MANY_REQUESTS)
        form = LoginForm(request._request, data=request.data)
        if not form.is_valid():
            if form.has_error("__all__", "inactive"):
                raise ApiError("FORBIDDEN", "Учётная запись заблокирована администратором.", status.HTTP_403_FORBIDDEN)
            left = lockout.register_failure(request._request, username)
            if left is None:
                raise ApiError("RATE_LIMITED", lockout.LOCKED_MESSAGE, status.HTTP_429_TOO_MANY_REQUESTS)
            raise ApiError("UNAUTHORIZED", f"Неверный логин или пароль. Осталось попыток: {left}.", status.HTTP_401_UNAUTHORIZED)
        lockout.forget(request._request, username)
        login(request._request, form.get_user())
        return Response(_user_payload(form.get_user()))


class LogoutView(_Open):
    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
