from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "store_sms_text", "preferred_language")
    list_filter = ("store_sms_text", "preferred_language")
    search_fields = ("user__username", "user__email")
