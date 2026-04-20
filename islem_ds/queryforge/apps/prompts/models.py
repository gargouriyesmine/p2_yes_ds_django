# models.py
from django.db import models


class PromptTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_active_version(self):
        return self.versions.filter(is_active=True).order_by("-version_number").first()


class PromptVersion(models.Model):
    template = models.ForeignKey(PromptTemplate, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    template_body = models.TextField()
    role = models.CharField(max_length=20, choices=[("system", "System"), ("user", "User")], default="system")
    token_budget = models.PositiveIntegerField(default=2048)
    is_active = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("template", "version_number")]
        ordering = ["-version_number"]

    def __str__(self):
        status = "ACTIVE" if self.is_active else "inactive"
        return f"{self.template.name} v{self.version_number} [{status}]"


class PromptExecution(models.Model):
    version = models.ForeignKey(PromptVersion, on_delete=models.PROTECT, related_name="executions")
    rendered_body = models.TextField()
    variables_used = models.JSONField()
    token_count = models.PositiveIntegerField()
    executed_at = models.DateTimeField(auto_now_add=True)