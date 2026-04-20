# versioning.py
import logging
from django.db import transaction
from .models import PromptTemplate, PromptVersion

logger = logging.getLogger(__name__)


class PromptVersionManager:

    def create_version(self, template, template_body, role="system", token_budget=2048, notes="", activate=False):
        with transaction.atomic():
            last = template.versions.order_by("-version_number").first()
            next_version = 1 if not last else last.version_number + 1
            if activate:
                template.versions.update(is_active=False)
            v = PromptVersion.objects.create(
                template=template,
                version_number=next_version,
                template_body=template_body,
                role=role,
                token_budget=token_budget,
                is_active=activate,
                notes=notes,
            )
            logger.info("prompt_version_created template=%s version=%d", template.name, v.version_number)
            return v

    def activate(self, template, version_number):
        with transaction.atomic():
            template.versions.update(is_active=False)
            v = template.versions.get(version_number=version_number)
            v.is_active = True
            v.save()
            logger.info("prompt_version_activated template=%s version=%d", template.name, v.version_number)
            return v

    def rollback(self, template, version_number):
        return self.activate(template, version_number)