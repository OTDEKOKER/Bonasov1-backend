from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aggregates", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="aggregate",
            index=models.Index(
                fields=["-period_start"],
                name="agg_period_start_idx",
            ),
        ),
    ]
