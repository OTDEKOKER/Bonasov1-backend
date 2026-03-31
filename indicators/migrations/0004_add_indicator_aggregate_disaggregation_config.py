from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("indicators", "0003_expand_indicator_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicator",
            name="aggregate_disaggregation_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Structured matrix configuration for aggregate entry and reporting",
            ),
        ),
    ]
