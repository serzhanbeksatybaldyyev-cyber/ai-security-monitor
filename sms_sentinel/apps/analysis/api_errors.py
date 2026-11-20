"""Единый формат ошибок REST API: {"error": {"code": ..., "message": ...}}."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class ApiError(Exception):
    def __init__(self, code, message, http_status=status.HTTP_400_BAD_REQUEST, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.fields = fields or {}


def error_response(code, message, http_status, fields=None):
    body = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return Response({"error": body}, status=http_status)


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        return error_response(exc.code, exc.message, exc.http_status, exc.fields)
    if isinstance(exc, (Http404, exceptions.NotFound)):
        return error_response("NOT_FOUND", "Запись не найдена.", status.HTTP_404_NOT_FOUND)
    if isinstance(exc, exceptions.NotAuthenticated):
        return error_response("UNAUTHORIZED", "Требуется вход в систему.", status.HTTP_401_UNAUTHORIZED)
    if isinstance(exc, (exceptions.PermissionDenied, DjangoPermissionDenied)):
        return error_response("FORBIDDEN", "Доступ запрещён.", status.HTTP_403_FORBIDDEN)
    if isinstance(exc, exceptions.ParseError):
        return error_response("VALIDATION_ERROR", "Не удалось разобрать тело запроса.", status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, exceptions.MethodNotAllowed):
        return error_response("METHOD_NOT_ALLOWED", "Метод не поддерживается.", status.HTTP_405_METHOD_NOT_ALLOWED)

    response = exception_handler(exc, context)
    if response is not None:
        return error_response("ERROR", "Не удалось выполнить запрос.", response.status_code)
    return None
