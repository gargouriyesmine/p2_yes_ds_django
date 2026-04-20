from django.db import models


class PromptTemplate(models.Model):
    """
    Un prompt nommé. Par exemple : "knowledge_assistant".
    Un template peut avoir plusieurs versions, mais UNE SEULE active à la fois.
    """
    # Le nom unique du prompt, ex: "knowledge_assistant"
    name = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Une description pour savoir à quoi sert ce prompt
    description = models.TextField(blank=True)
    
    # Django remplit ces dates automatiquement
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_active_version(self):
        """Retourne la version active de ce template, ou None."""
        return self.versions.filter(is_active=True).order_by("-version_number").first()


class PromptVersion(models.Model):
    """
    Une version immuable d'un template de prompt.
    Exemple : knowledge_assistant v1, v2, v3 (v3 = active)
    """
    # Lien vers le PromptTemplate parent
    template = models.ForeignKey(
        PromptTemplate, 
        on_delete=models.CASCADE,  # si on supprime le template, les versions disparaissent aussi
        related_name="versions"    # permet d'écrire template.versions.all()
    )
    
    # Le numéro de version : 1, 2, 3...
    version_number = models.PositiveIntegerField()
    
    # Le texte du prompt avec des variables Jinja2 : {{ user_query }}, {{ context }}
    template_body = models.TextField(
        help_text="Template Jinja2. Utilisez {{ variable }} pour les valeurs dynamiques."
    )
    
    # "system" = instruction pour le LLM | "user" = message de l'utilisateur
    role = models.CharField(
        max_length=20,
        choices=[("system", "System"), ("user", "User")],
        default="system",
    )
    
    # Limite de tokens pour ce prompt (évite les coûts excessifs)
    token_budget = models.PositiveIntegerField(
        default=2048,
        help_text="Nombre max de tokens autorisés pour cette version."
    )
    
    # Une seule version peut être active à la fois par template
    is_active = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notes sur ce qui a changé dans cette version
    notes = models.TextField(blank=True, help_text="Qu'est-ce qui a changé dans cette version ?")

    class Meta:
        # On ne peut pas avoir deux fois la même version pour un même template
        unique_together = [("template", "version_number")]
        ordering = ["-version_number"]  # trier par version décroissante

    def __str__(self):
        status = "ACTIVE" if self.is_active else "inactive"
        return f"{self.template.name} v{self.version_number} [{status}]"


class PromptExecution(models.Model):
    """
    Journal de chaque fois qu'une version de prompt a été utilisée.
    NE JAMAIS supprimer ces lignes — c'est le journal d'audit.
    """
    # Lien vers la version utilisée
    version = models.ForeignKey(
        PromptVersion,
        on_delete=models.PROTECT,  # PROTECT = refuse de supprimer si des exécutions existent
        related_name="executions"
    )
    
    # Le texte final après remplissage des variables Jinja2
    rendered_body = models.TextField()
    
    # Les variables utilisées : {"user_query": "...", "context": "..."}
    variables_used = models.JSONField()
    
    # Nombre de tokens du prompt rendu
    token_count = models.PositiveIntegerField()
    
    executed_at = models.DateTimeField(auto_now_add=True)
