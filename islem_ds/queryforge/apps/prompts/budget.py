# budget.py
import logging
import tiktoken
from dataclasses import dataclass
from apps.gateway.providers.base import Message

logger = logging.getLogger(__name__)


class ContextBudgetExceeded(Exception):
    pass


@dataclass
class BudgetResult:
    messages: list
    total_tokens: int
    budget_limit: int
    truncation_applied: bool
    turns_removed: int


class ContextBudgetManager:

    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model
        try:
            self._enc = tiktoken.encoding_for_model(model)
        except KeyError:
            self._enc = tiktoken.get_encoding("cl100k_base")
            logger.warning("budget_model_unknown model=%s", model)

    def _count_tokens(self, messages: list) -> int:
        total = 0
        for m in messages:
            total += 4
            total += len(self._enc.encode(m.content))
        total += 2
        return total

    def fit(self, messages: list, budget: int) -> BudgetResult:
        token_count = self._count_tokens(messages)

        if token_count <= budget:
            return BudgetResult(
                messages=messages,
                total_tokens=token_count,
                budget_limit=budget,
                truncation_applied=False,
                turns_removed=0,
            )

        system_msgs = [m for m in messages if m.role == "system"]
        history = [m for m in messages if m.role != "system"]
        turns_removed = 0

        while history and self._count_tokens(system_msgs + history) > budget:
            history.pop(0)
            turns_removed += 1

        final_messages = system_msgs + history
        final_count = self._count_tokens(final_messages)

        if final_count > budget:
            raise ContextBudgetExceeded(
                f"System prompt seul nécessite {final_count} tokens, budget={budget}."
            )

        return BudgetResult(
            messages=final_messages,
            total_tokens=final_count,
            budget_limit=budget,
            truncation_applied=True,
            turns_removed=turns_removed,
        )