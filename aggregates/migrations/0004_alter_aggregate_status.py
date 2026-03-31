from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aggregates', '0003_aggregate_approval_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aggregate',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('pending', 'Pending Coordinator Review'),
                    ('reviewed', 'Reviewed - Awaiting Approval'),
                    ('flagged', 'Flagged for Correction'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
