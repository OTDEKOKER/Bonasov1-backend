from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='home_dashboard_preferences',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
