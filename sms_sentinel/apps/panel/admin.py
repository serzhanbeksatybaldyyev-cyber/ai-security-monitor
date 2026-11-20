from django.contrib import admin

from .models import AdminAction


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target", "details")
    list_filter = ("action",)
    readonly_fields = ("created_at", "actor", "action", "target", "details")
