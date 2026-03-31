from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('aggregates', '0004_alter_aggregate_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AggregateChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('submitted', 'Submitted'), ('corrected', 'Corrected'), ('reviewed', 'Reviewed'), ('flagged', 'Flagged'), ('approved', 'Approved')], max_length=20)),
                ('comment', models.TextField(blank=True)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('aggregate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history_entries', to='aggregates.aggregate')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='aggregate_change_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
