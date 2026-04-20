# engine.py
import logging
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

logger = logging.getLogger(__name__)


class PromptRenderError(Exception):
    pass


_jinja_env = Environment(
    autoescape=True,
    undefined=StrictUndefined,
)


class TemplateEngine:

    def render(self, template_body: str, variables: dict) -> str:
        try:
            template = _jinja_env.from_string(template_body)
            rendered = template.render(**variables)
            logger.debug("template_rendered length=%d", len(rendered))
            return rendered
        except UndefinedError as e:
            raise PromptRenderError(
                f"Variable manquante : {e}. Variables fournies : {list(variables.keys())}"
            ) from e
        except TemplateSyntaxError as e:
            raise PromptRenderError(
                f"Erreur de syntaxe ligne {e.lineno} : {e}"
            ) from e