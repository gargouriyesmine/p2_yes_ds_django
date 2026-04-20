# registry.py
import json
import logging

import redis
from django.conf import settings

from apps.prompts.models import PromptVersion

logger = logging.getLogger(__name__)

_redis = redis.from_url(settings.REDIS_URL)

CACHE_TTL = 3600


class PromptNotFoundError(Exception):
    pass


class PromptRegistry:

    def get_active(self, name: str) -> PromptVersion:
        cache_key = f"prompt:active:{name}"
        try:
            cached = _redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return PromptVersion(
                    id=data["id"],
                    version_number=data["version_number"],
                    template_body=data["template_body"],
                    role=data["role"],
                    token_budget=data["token_budget"],
                )
        except redis.ConnectionError:
            logger.warning("prompt_registry_redis_down — fallback to DB for '%s'", name)

        try:
            version = (
                PromptVersion.objects
                .select_related("template")
                .get(template__name=name, is_active=True)
            )
        except PromptVersion.DoesNotExist:
            raise PromptNotFoundError(
                f"Aucune version active trouvée pour le template '{name}'."
            )

        try:
            _redis.set(
                cache_key,
                json.dumps({
                    "id": version.id,
                    "version_number": version.version_number,
                    "template_body": version.template_body,
                    "role": version.role,
                    "token_budget": version.token_budget,
                }),
                ex=CACHE_TTL,
            )
        except redis.ConnectionError:
            pass

        return version

    def invalidate(self, name: str) -> None:
        try:
            _redis.delete(f"prompt:active:{name}")
        except redis.ConnectionError:
            pass