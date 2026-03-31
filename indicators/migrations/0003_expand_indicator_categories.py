from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0002_alter_indicator_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='indicator',
            name='category',
            field=models.CharField(
                choices=[
                    ('hiv_prevention', 'HIV Prevention'),
                    ('ncd', 'Non-Communicable Diseases'),
                    ('mental_health', 'Mental Health'),
                    ('gbv', 'GBV'),
                    ('sti', 'STI'),
                    ('trainings', 'Trainings'),
                    ('media', 'Media'),
                    ('events', 'Events'),
                ],
                default='hiv_prevention',
                max_length=30,
            ),
        ),
    ]
