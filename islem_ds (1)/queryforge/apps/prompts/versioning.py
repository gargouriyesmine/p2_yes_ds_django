"""Prompt version management: create, activate, rollback.

Provides `PromptVersionManager` with atomic operations to safely
create new versions, activate a version (deactivating others), and
rollback by re-activating a previous version.
"""

import logging

from django.db import transaction

from .models import PromptTemplate, PromptVersion

logger = logging.getLogger(__name__)


class PromptVersionManager:
    """Manage prompt versions for a given `PromptTemplate`."""

    def create_version(
        self,
        template: PromptTemplate,
        template_body: str,
        role: str = "system",
        token_budget: int = 2048,
        notes: str = "",
        activate: bool = False,
    ) -> PromptVersion:
        """Create a new immutable PromptVersion for `template`.

        If `activate` is True, the new version becomes active and all
        other versions are deactivated. The operation is atomic.
        """
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

            logger.info(
                "prompt_version_created template=%s version=%d active=%s",
                template.name,
                v.version_number,
                v.is_active,
            )

            return v

    def activate(self, template: PromptTemplate, version_number: int) -> PromptVersion:
        """Activate the given version number for `template` and deactivate others."""
        with transaction.atomic():
            # deactivate all first to ensure single active
            template.versions.update(is_active=False)
            v = template.versions.get(version_number=version_number)
            v.is_active = True
            v.save()

            logger.info(
                "prompt_version_activated template=%s version=%d",
                template.name,
                v.version_number,
            )

            return v

    def rollback(self, template: PromptTemplate, version_number: int) -> PromptVersion:
        """Rollback to a previous version (alias of `activate`)."""
        return self.activate(template, version_number)

