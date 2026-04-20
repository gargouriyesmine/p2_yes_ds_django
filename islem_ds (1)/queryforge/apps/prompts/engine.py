"""Jinja2 template engine for prompt rendering.

Provides a safe, strict renderer that raises clear errors when variables
are missing or template syntax is invalid. Auto-escaping is enabled to
mitigate injection via user-provided variables.
"""

import logging
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

logger = logging.getLogger(__name__)


class PromptRenderError(Exception):
    """
    Levée quand le rendu du template échoue.
    Deux causes possibles :
      1. Une variable est manquante  : {{ context }} mais "context" pas fourni
      2. Erreur de syntaxe Jinja2   : {{ user_query | unknown_filter }}
    """


# On crée l'environnement Jinja2 UNE SEULE FOIS (performance)
# autoescape=True    → HTML-escape toutes les variables (sécurité anti-injection)
# StrictUndefined    → variable manquante = erreur immédiate (pas de valeur vide silencieuse)
_jinja_env = Environment(
    autoescape=True,
    undefined=StrictUndefined,
)


class TemplateEngine:

    def render(self, template_body: str, variables: dict) -> str:
        """
        Remplace les {{ variables }} dans template_body par leurs valeurs réelles.
        
        Exemple :
            template_body = "Réponds à : {{ user_query }}"
            variables     = {"user_query": "Quelle est la capitale de la France ?"}
            résultat      = "Réponds à : Quelle est la capitale de la France ?"
        
        Lève PromptRenderError si une variable est manquante ou si la syntaxe est invalide.
        """
        try:
            template = _jinja_env.from_string(template_body)
            rendered = template.render(**variables)

            logger.debug(
                "template_rendered longueur=%d variables=%s",
                len(rendered),
                list(variables.keys()),
            )
            return rendered

        except UndefinedError as e:
            # Variable manquante dans le dict fourni
            raise PromptRenderError(
                f"Variable manquante dans le template : {e}. "
                f"Variables fournies : {list(variables.keys())}"
            ) from e

        except TemplateSyntaxError as e:
            # Syntaxe Jinja2 invalide dans le template_body
            raise PromptRenderError(
                f"Erreur de syntaxe dans le template à la ligne {e.lineno} : {e}"
            ) from e

