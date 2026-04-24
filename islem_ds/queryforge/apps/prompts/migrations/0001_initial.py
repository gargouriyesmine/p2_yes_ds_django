from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PromptTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="PromptVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField()),
                ("template_body", models.TextField(help_text="Template Jinja2. Utilisez {{ variable }} pour les valeurs dynamiques.")),
                ("role", models.CharField(
                    choices=[("system", "System"), ("user", "User")],
                    default="system",
                    max_length=20,
                )),
                ("token_budget", models.PositiveIntegerField(
                    default=2048,
                    help_text="Nombre max de tokens autorisés pour cette version.",
                )),
                ("is_active", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.TextField(blank=True, help_text="Qu'est-ce qui a changé dans cette version ?")),
                ("template", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="versions",
                    to="prompts.prompttemplate",
                )),
            ],
            options={
                "ordering": ["-version_number"],
            },
        ),
        migrations.AddConstraint(
            model_name="promptversion",
            constraint=models.UniqueConstraint(
                fields=["template", "version_number"],
                name="unique_template_version",
            ),
        ),
        migrations.CreateModel(
            name="PromptExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rendered_body", models.TextField()),
                ("variables_used", models.JSONField()),
                ("token_count", models.PositiveIntegerField()),
                ("executed_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="executions",
                    to="prompts.promptversion",
                )),
            ],
        ),
    ]