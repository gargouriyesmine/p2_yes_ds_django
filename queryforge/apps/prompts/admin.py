from django.contrib import admin

from .models import PromptTemplate, PromptVersion, PromptExecution


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_at", "updated_at")
    search_fields = ("name",)


@admin.register(PromptVersion)
class PromptVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_number", "is_active", "created_at")
    list_filter = ("is_active", "role")
    search_fields = ("template__name",)


@admin.register(PromptExecution)
class PromptExecutionAdmin(admin.ModelAdmin):
    list_display = ("version", "token_count", "executed_at")
    readonly_fields = ("rendered_body", "variables_used", "token_count", "executed_at")
    search_fields = ("version__template__name",)
