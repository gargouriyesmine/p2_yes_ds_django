import json
import logging

import redis
from django.conf import settings

from apps.prompts.models import PromptVersion

logger = logging.getLogger(__name__)

# Connexion Redis — utilise l'URL définie dans settings.py (ex: redis://localhost:6379)
_redis = redis.from_url(settings.REDIS_URL)

# Durée de vie du cache : 1 heure (en secondes)
CACHE_TTL = 3600


class PromptNotFoundError(Exception):
    """
    Levée quand aucune version active n'existe pour un template donné.
    On utilise notre propre exception (pas PromptVersion.DoesNotExist)
    pour que les autres modules n'aient pas à connaître les détails de Django ORM.
    """


class PromptRegistry:
    """
    Charge la version active d'un prompt depuis Redis (cache) ou la DB (fallback).
    
    Clé Redis utilisée : "prompt:active:{nom_du_template}"
    Exemple            : "prompt:active:knowledge_assistant"
    """

    def get_active(self, name: str) -> PromptVersion:
        """
        Retourne la PromptVersion active pour le template donné.
        
        Ordre de priorité :
        1. Redis (rapide, ~1ms)
        2. Base de données (fallback si cache vide ou Redis down)
        
        Lève PromptNotFoundError si aucune version active n'existe.
        """
        cache_key = f"prompt:active:{name}"

        # ── Essai 1 : Redis ────────────────────────────────────────────
        try:
            cached = _redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                logger.debug("prompt_cache_hit name=%s version=%s", name, data.get("version_number"))
                # Reconstruire un objet PromptVersion depuis les données JSON
                return PromptVersion(
                    id=data["id"],
                    version_number=data["version_number"],
                    template_body=data["template_body"],
                    role=data["role"],
                    token_budget=data["token_budget"],
                )
        except redis.ConnectionError:
            # Redis est down → pas grave, on continue avec la DB
            logger.warning("prompt_registry_redis_down — fallback to DB for '%s'", name)

        # ── Essai 2 : Base de données ──────────────────────────────────
        try:
            version = (
                PromptVersion.objects
                .select_related("template")   # charge le template en même temps (1 seule requête SQL)
                .get(template__name=name, is_active=True)
            )
        except PromptVersion.DoesNotExist:
            # On lève notre propre exception, plus claire pour les appelants
            raise PromptNotFoundError(
                f"Aucune version active trouvée pour le template '{name}'. "
                f"Créez-en une via l'interface Django Admin et activez-la."
            )

        # ── Écriture dans Redis pour les prochains appels ──────────────
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
                ex=CACHE_TTL,  # expire après 1 heure
            )
            logger.debug("prompt_cache_written name=%s version=%s", name, version.version_number)
        except redis.ConnectionError:
            # Échec d'écriture dans Redis → pas grave, on retourne quand même le résultat
            pass

        return version

    def invalidate(self, name: str) -> None:
        """
        Supprime l'entrée du cache Redis pour ce template.
        
        À appeler APRÈS avoir activé une nouvelle version, pour que
        le prochain appel charge la nouvelle version depuis la DB.
        """
        try:
            _redis.delete(f"prompt:active:{name}")
            logger.info("prompt_cache_invalidated name=%s", name)
        except redis.ConnectionError:
            # Redis down → pas grave, le cache va expirer tout seul après 1h
            pass
