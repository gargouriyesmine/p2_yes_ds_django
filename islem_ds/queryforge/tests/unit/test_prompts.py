# test_prompts.py
"""Unit tests for apps/prompts.

Tests:
- TemplateEngine : rendering, variable escaping, missing variable, syntax error
- ContextBudgetManager : within budget, truncation, budget exceeded
- PromptRegistry : cache hit, cache miss, redis down fallback, not found
- PromptVersionManager : create, activate, rollback atomicity
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from django.test import TestCase

from apps.prompts.engine import TemplateEngine, PromptRenderError
from apps.prompts.budget import ContextBudgetManager, BudgetResult, ContextBudgetExceeded
from apps.prompts.registry import PromptRegistry, PromptNotFoundError
from apps.prompts.versioning import PromptVersionManager
from apps.prompts.models import PromptTemplate, PromptVersion
from apps.gateway.providers.base import Message


# ─────────────────────────────────────────────────────────────
#  TemplateEngine
# ─────────────────────────────────────────────────────────────

class TestTemplateEngine(TestCase):

    def setUp(self):
        self.engine = TemplateEngine()

    def test_simple_render(self):
        """Variables are correctly substituted."""
        result = self.engine.render(
            "Réponds à : {{ user_query }}",
            {"user_query": "Quelle est la capitale de la France ?"},
        )
        assert result == "Réponds à : Quelle est la capitale de la France ?"

    def test_multiple_variables(self):
        """Multiple variables are all substituted."""
        result = self.engine.render(
            "{{ greeting }}, {{ name }}!",
            {"greeting": "Bonjour", "name": "Alice"},
        )
        assert result == "Bonjour, Alice!"

    def test_missing_variable_raises(self):
        """Missing variable raises PromptRenderError immediately."""
        with pytest.raises(PromptRenderError) as exc_info:
            self.engine.render("{{ user_query }}", {})
        assert "user_query" in str(exc_info.value)

    def test_syntax_error_raises(self):
        """Invalid Jinja2 syntax raises PromptRenderError."""
        with pytest.raises(PromptRenderError):
            self.engine.render("{{ unclosed", {"x": "y"})

    def test_html_escaping(self):
        """User-provided variables are HTML-escaped (anti-injection)."""
        result = self.engine.render(
            "Query: {{ user_query }}",
            {"user_query": "<script>alert('xss')</script>"},
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_empty_template(self):
        """Empty template renders to empty string."""
        result = self.engine.render("", {})
        assert result == ""


# ─────────────────────────────────────────────────────────────
#  ContextBudgetManager
# ─────────────────────────────────────────────────────────────

class TestContextBudgetManager(TestCase):

    def setUp(self):
        self.manager = ContextBudgetManager(model="gpt-4o-mini")

    def _make_messages(self, *contents):
        """Helper: create a list of Messages."""
        roles = ["system", "user", "assistant", "user", "assistant"]
        return [
            Message(role=roles[i % len(roles)], content=c)
            for i, c in enumerate(contents)
        ]

    def test_within_budget_no_truncation(self):
        """Short messages fit in budget — no truncation."""
        messages = self._make_messages("You are helpful.", "Hello")
        result = self.manager.fit(messages, budget=2048)
        assert isinstance(result, BudgetResult)
        assert result.truncation_applied is False
        assert result.turns_removed == 0
        assert result.total_tokens <= 2048

    def test_truncation_removes_oldest_messages(self):
        """Over-budget messages → oldest history removed first."""
        # system prompt + many long history messages
        long_text = "word " * 300
        messages = self._make_messages(
            "You are helpful.",  # system — never removed
            long_text,           # user turn 1
            long_text,           # assistant turn 1
            long_text,           # user turn 2
            "Short question?",   # user turn 3 — should survive
        )
        result = self.manager.fit(messages, budget=500)
        assert result.truncation_applied is True
        assert result.turns_removed > 0
        # System prompt must always be present
        assert any(m.role == "system" for m in result.messages)

    def test_system_prompt_never_removed(self):
        """System prompt is never truncated even when over budget."""
        system = Message(role="system", content="You are helpful.")
        user = Message(role="user", content="Hi")
        result = self.manager.fit([system, user], budget=2048)
        assert result.messages[0].role == "system"

    def test_budget_exceeded_raises(self):
        """System prompt alone > budget → ContextBudgetExceeded."""
        huge_system = Message(role="system", content="word " * 5000)
        with pytest.raises(ContextBudgetExceeded):
            self.manager.fit([huge_system], budget=100)

    def test_budget_result_metadata(self):
        """BudgetResult contains correct metadata fields."""
        messages = self._make_messages("System.", "Hello")
        result = self.manager.fit(messages, budget=2048)
        assert hasattr(result, "total_tokens")
        assert hasattr(result, "budget_limit")
        assert result.budget_limit == 2048


# ─────────────────────────────────────────────────────────────
#  PromptRegistry
# ─────────────────────────────────────────────────────────────

class TestPromptRegistry(TestCase):

    def setUp(self):
        self.registry = PromptRegistry()

    @patch("apps.prompts.registry._redis")
    def test_cache_hit_returns_version(self, mock_redis):
        """Cache hit → returns PromptVersion without DB query."""
        mock_redis.get.return_value = json.dumps({
            "id": 1,
            "version_number": 3,
            "template_body": "Hello {{ name }}",
            "role": "system",
            "token_budget": 2048,
        }).encode()

        version = self.registry.get_active("knowledge_assistant")

        assert version.version_number == 3
        assert version.template_body == "Hello {{ name }}"
        mock_redis.get.assert_called_once()

    @patch("apps.prompts.registry._redis")
    def test_cache_miss_queries_db(self, mock_redis):
        """Cache miss → falls back to DB."""
        mock_redis.get.return_value = None

        # Create real DB objects
        template = PromptTemplate.objects.create(name="test_template")
        PromptVersion.objects.create(
            template=template,
            version_number=1,
            template_body="Test body",
            is_active=True,
        )

        version = self.registry.get_active("test_template")
        assert version.version_number == 1
        assert version.template_body == "Test body"

    @patch("apps.prompts.registry._redis")
    def test_redis_down_falls_back_to_db(self, mock_redis):
        """Redis ConnectionError → silent fallback to DB."""
        import redis as redis_lib
        mock_redis.get.side_effect = redis_lib.ConnectionError("Redis down")

        template = PromptTemplate.objects.create(name="fallback_template")
        PromptVersion.objects.create(
            template=template,
            version_number=1,
            template_body="Fallback body",
            is_active=True,
        )

        # Should not raise — should return DB result
        version = self.registry.get_active("fallback_template")
        assert version.template_body == "Fallback body"

    @patch("apps.prompts.registry._redis")
    def test_not_found_raises_prompt_not_found_error(self, mock_redis):
        """No active version → raises PromptNotFoundError."""
        mock_redis.get.return_value = None

        with pytest.raises(PromptNotFoundError):
            self.registry.get_active("nonexistent_template")

    @patch("apps.prompts.registry._redis")
    def test_invalidate_deletes_cache_key(self, mock_redis):
        """invalidate() calls Redis delete on the correct key."""
        self.registry.invalidate("knowledge_assistant")
        mock_redis.delete.assert_called_once_with("prompt:active:knowledge_assistant")


# ─────────────────────────────────────────────────────────────
#  PromptVersionManager
# ─────────────────────────────────────────────────────────────

class TestPromptVersionManager(TestCase):

    def setUp(self):
        self.manager = PromptVersionManager()
        self.template = PromptTemplate.objects.create(name="test_mgr_template")

    def test_create_version_increments_number(self):
        """Version numbers auto-increment: 1, 2, 3..."""
        v1 = self.manager.create_version(self.template, "Body v1")
        v2 = self.manager.create_version(self.template, "Body v2")
        v3 = self.manager.create_version(self.template, "Body v3")
        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_create_version_inactive_by_default(self):
        """New versions are inactive by default."""
        v = self.manager.create_version(self.template, "Body")
        assert v.is_active is False

    def test_create_version_with_activate(self):
        """create_version(activate=True) makes the version active."""
        v = self.manager.create_version(self.template, "Body", activate=True)
        assert v.is_active is True

    def test_activate_deactivates_others(self):
        """Activating one version deactivates all others atomically."""
        v1 = self.manager.create_version(self.template, "v1", activate=True)
        v2 = self.manager.create_version(self.template, "v2")

        self.manager.activate(self.template, v2.version_number)

        v1.refresh_from_db()
        v2.refresh_from_db()
        assert v1.is_active is False
        assert v2.is_active is True

    def test_only_one_active_version_at_a_time(self):
        """Only one version can be active at a time."""
        for i in range(3):
            self.manager.create_version(self.template, f"Body {i}", activate=True)

        active_count = self.template.versions.filter(is_active=True).count()
        assert active_count == 1

    def test_rollback_reactivates_previous_version(self):
        """rollback() re-activates a previous version."""
        v1 = self.manager.create_version(self.template, "v1", activate=True)
        v2 = self.manager.create_version(self.template, "v2", activate=True)

        # Rollback to v1
        self.manager.rollback(self.template, v1.version_number)

        v1.refresh_from_db()
        v2.refresh_from_db()
        assert v1.is_active is True
        assert v2.is_active is False

    def test_activate_nonexistent_version_raises(self):
        """Activating a version that doesn't exist raises DoesNotExist."""
        with pytest.raises(PromptVersion.DoesNotExist):
            self.manager.activate(self.template, 999)