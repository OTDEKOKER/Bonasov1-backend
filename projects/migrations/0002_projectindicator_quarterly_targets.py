from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


TWOPLACES = Decimal('0.01')


def forwards(apps, schema_editor):
    ProjectIndicator = apps.get_model('projects', 'ProjectIndicator')

    for project_indicator in ProjectIndicator.objects.all():
        total_target = Decimal(str(project_indicator.target_value or 0))
        if total_target <= 0:
            continue
        if any(
            Decimal(str(value or 0)) > 0
            for value in [
                getattr(project_indicator, 'q1_target', 0),
                getattr(project_indicator, 'q2_target', 0),
                getattr(project_indicator, 'q3_target', 0),
                getattr(project_indicator, 'q4_target', 0),
            ]
        ):
            continue

        quarter = (total_target / Decimal('4')).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        q1 = quarter
        q2 = quarter
        q3 = quarter
        q4 = (total_target - q1 - q2 - q3).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        project_indicator.q1_target = q1
        project_indicator.q2_target = q2
        project_indicator.q3_target = q3
        project_indicator.q4_target = q4
        project_indicator.target_value = (q1 + q2 + q3 + q4).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        project_indicator.save(update_fields=['q1_target', 'q2_target', 'q3_target', 'q4_target', 'target_value'])


def backwards(apps, schema_editor):
    ProjectIndicator = apps.get_model('projects', 'ProjectIndicator')

    for project_indicator in ProjectIndicator.objects.all():
        total_target = sum(
            [
                Decimal(str(project_indicator.q1_target or 0)),
                Decimal(str(project_indicator.q2_target or 0)),
                Decimal(str(project_indicator.q3_target or 0)),
                Decimal(str(project_indicator.q4_target or 0)),
            ],
            Decimal('0'),
        ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        project_indicator.target_value = total_target
        project_indicator.save(update_fields=['target_value'])


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectindicator',
            name='q1_target',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='projectindicator',
            name='q2_target',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='projectindicator',
            name='q3_target',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='projectindicator',
            name='q4_target',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.RunPython(forwards, backwards),
    ]
