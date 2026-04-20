from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import PromptExecution, PromptTemplate, PromptVersion
from .registry import PromptRegistry
from .versioning import PromptVersionManager

_manager = PromptVersionManager()
_registry = PromptRegistry()


class PromptVersionInline(admin.TabularInline):
    model = PromptVersion
    extra = 0
    fields = ("version_number", "role", "token_budget", "is_active", "notes", "created_at")
    readonly_fields = ("version_number", "created_at")
    ordering = ("-version_number",)
    show_change_link = True


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "active_version_badge", "created_at", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [PromptVersionInline]

    @admin.display(description="Version active")
    def active_version_badge(self, obj):
        active = obj.get_active_version()
        if active:
            return mark_safe(
                f'<span style="background-color:#28a745;color:white;padding:2px 10px;border-radius:12px;font-weight:bold;">v{active.version_number}</span>'
            )
        return mark_safe(
            '<span style="background-color:#dc3545;color:white;padding:2px 10px;border-radius:12px;font-weight:bold;">Aucune</span>'
        )


@admin.register(PromptVersion)
class PromptVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_number", "role", "token_budget", "is_active", "created_at")
    list_filter = ("is_active", "role", "template")
    search_fields = ("template__name", "notes")
    
    # ✅ CORRECTION ICI
    readonly_fields = ("created_at",)

    actions = ["action_activate", "action_rollback"]

    @admin.action(description="✅ Activer la version sélectionnée")
    def action_activate(self, request, queryset):
        count = 0
        for version in queryset.select_related("template"):
            _manager.activate(version.template, version.version_number)
            _registry.invalidate(version.template.name)
            count += 1
        self.message_user(request, f"{count} version(s) activée(s).")

    @admin.action(description="⏪ Rollback vers la version précédente")
    def action_rollback(self, request, queryset):
        templates_seen = set()
        rolled_back = 0
        errors = []

        for version in queryset.select_related("template"):
            template = version.template

            if template.id in templates_seen:
                continue

            templates_seen.add(template.id)

            previous = (
                PromptVersion.objects
                .filter(template=template, is_active=False)
                .order_by("-version_number")
                .first()
            )

            if previous is None:
                errors.append(f"'{template.name}' : aucune version précédente.")
                continue

            _manager.rollback(template, previous.version_number)
            _registry.invalidate(template.name)
            rolled_back += 1

        if rolled_back:
            self.message_user(request, f"Rollback effectué pour {rolled_back} template(s).")

        for error in errors:
            self.message_user(request, error, level="warning")


@admin.register(PromptExecution)
class PromptExecutionAdmin(admin.ModelAdmin):
    list_display = ("version", "token_count", "executed_at")
    readonly_fields = ("version", "rendered_body", "variables_used", "token_count", "executed_at")
    search_fields = ("version__template__name",)
    list_filter = ("version__template",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False