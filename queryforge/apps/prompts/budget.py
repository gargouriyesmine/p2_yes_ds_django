"""Token budget manager for prompt contexts.

Uses `tiktoken` to accurately estimate token usage for a given model
and truncates conversation history (oldest turns first) while preserving
the system prompt. Raises `ContextBudgetExceeded` when even the system
prompt alone exceeds the configured budget.
"""

import logging
import tiktoken
from dataclasses import dataclass
from apps.gateway.providers.base import Message

logger = logging.getLogger(__name__)


class ContextBudgetExceeded(Exception):
    """
    Levée quand même après suppression de tout l'historique,
    le prompt dépasse encore le budget (le system prompt seul est trop grand).
    """


@dataclass
class BudgetResult:
    messages: list          # messages finaux (peut-être tronqués)
    total_tokens: int       # nombre de tokens dans les messages finaux
    budget_limit: int       # limite appliquée
    truncation_applied: bool  # True si on a supprimé des messages
    turns_removed: int      # combien de messages ont été supprimés


class ContextBudgetManager:
    """
    Vérifie qu'une liste de messages rentre dans le budget de tokens.
    Si non, supprime les messages les plus anciens jusqu'à ce que ça rentre.
    
    Règle absolue : le system prompt n'est JAMAIS supprimé.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model
        try:
            # tiktoken = la bibliothèque d'OpenAI pour compter les tokens
            # SANS appeler l'API (gratuit, local)
            self._enc = tiktoken.encoding_for_model(model)
        except KeyError:
            # Modèle inconnu → utiliser l'encodage de base (compatible avec la plupart des modèles)
            self._enc = tiktoken.get_encoding("cl100k_base")
            logger.warning("budget_model_unknown model=%s — using cl100k_base", model)

    def _count_tokens(self, messages: list) -> int:
        """Compte le nombre total de tokens dans une liste de messages."""
        total = 0
        for m in messages:
            total += 4          # overhead par message (rôle + délimiteurs)
            total += len(self._enc.encode(m.content))
        total += 2              # tokens de démarrage de la réponse
        return total

    def fit(self, messages: list, budget: int) -> BudgetResult:
        """
        Fait rentrer les messages dans le budget.
        
        Retourne un BudgetResult avec les messages (tronqués ou non) et des métadonnées.
        
        Exemples :
          - 500 tokens, budget 2048  → retourne tel quel, truncation_applied=False
          - 3000 tokens, budget 2048 → supprime les vieux messages, truncation_applied=True
          - system prompt seul = 5000 tokens, budget 2048 → lève ContextBudgetExceeded
        """
        token_count = self._count_tokens(messages)

        # ── Cas 1 : On rentre dans le budget, rien à faire ────────────
        if token_count <= budget:
            return BudgetResult(
                messages=messages,
                total_tokens=token_count,
                budget_limit=budget,
                truncation_applied=False,
                turns_removed=0,
            )

        logger.warning(
            "context_budget_overflow tokens=%d budget=%d — truncation en cours",
            token_count, budget,
        )

        # ── Cas 2 : Trop long → supprimer les messages les plus anciens ──
        # Séparer le system prompt (intouchable) du reste
        system_msgs = [m for m in messages if m.role == "system"]
        history = [m for m in messages if m.role != "system"]

        turns_removed = 0

        # Supprimer un message à la fois depuis le début (le plus ancien)
        # jusqu'à rentrer dans le budget
        while history and self._count_tokens(system_msgs + history) > budget:
            history.pop(0)      # supprime le message le plus ancien
            turns_removed += 1

        final_messages = system_msgs + history
        final_count = self._count_tokens(final_messages)

        # ── Cas 3 : Même sans historique, le system prompt est trop grand ──
        if final_count > budget:
            raise ContextBudgetExceeded(
                f"Même après suppression de tout l'historique, le prompt nécessite "
                f"{final_count} tokens mais le budget est {budget}. "
                f"Le system prompt seul est trop grand — réduisez-le dans l'admin."
            )

        logger.info(
            "context_truncated turns_removed=%d final_tokens=%d budget=%d",
            turns_removed, final_count, budget,
        )

        return BudgetResult(
            messages=final_messages,
            total_tokens=final_count,
            budget_limit=budget,
            truncation_applied=True,
            turns_removed=turns_removed,
        )

