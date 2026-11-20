from django.contrib import admin

from .models import Check, DetectedFeature, ModelVersion, UrlResult


class UrlResultInline(admin.TabularInline):
    model = UrlResult
    fields = ("domain", "p_url", "category", "risk_score")
    readonly_fields = fields
    extra = 0
    can_delete = False


class DetectedFeatureInline(admin.TabularInline):
    model = DetectedFeature
    fields = ("code", "title", "weight")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user", "check_type", "language", "category", "risk_score", "risk_level")
    list_filter = ("check_type", "category", "risk_level", "language", "created_at")
    search_fields = ("user__username",)
    exclude = ("input_text", "input_masked", "explanation")
    readonly_fields = ("user", "check_type", "language", "category", "risk_score", "risk_level", "p_sms", "recommendation", "sms_model_version", "url_model_version", "created_at")
    inlines = [UrlResultInline, DetectedFeatureInline]

    def has_add_permission(self, request):
        return False


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("version", "model_type", "algorithm", "threshold", "trained_at", "is_active")
    list_filter = ("model_type", "is_active")


@admin.register(DetectedFeature)
class DetectedFeatureAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "weight", "check_record")
    list_filter = ("code",)
    readonly_fields = ("check_record", "code", "title", "weight")
