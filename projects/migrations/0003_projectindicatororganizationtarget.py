from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models
import django.db.models.deletion


TWOPLACES = Decimal('0.01')


def quantize(value):
    return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def split_evenly(value, count):
    total = quantize(value)
    if count <= 0:
        return []
    if count == 1:
        return [total]

    share = (total / Decimal(count)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    values = [share for _ in range(count - 1)]
    remainder = (total - sum(values, Decimal('0'))).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    values.append(remainder)
    return values


def forwards(apps, schema_editor):
    ProjectIndicator = apps.get_model('projects', 'ProjectIndicator')
    ProjectIndicatorOrganizationTarget = apps.get_model('projects', 'ProjectIndicatorOrganizationTarget')

    for project_indicator in ProjectIndicator.objects.all().prefetch_related('project__organizations'):
        organizations = list(project_indicator.project.organizations.all())
        if not organizations:
            continue

        q1_values = split_evenly(project_indicator.q1_target, len(organizations))
        q2_values = split_evenly(project_indicator.q2_target, len(organizations))
        q3_values = split_evenly(project_indicator.q3_target, len(organizations))
        q4_values = split_evenly(project_indicator.q4_target, len(organizations))
        baseline_values = split_evenly(project_indicator.baseline_value, len(organizations))
        current_values = split_evenly(project_indicator.current_value, len(organizations))

        for index, organization in enumerate(organizations):
            q1_target = q1_values[index]
            q2_target = q2_values[index]
            q3_target = q3_values[index]
            q4_target = q4_values[index]
            ProjectIndicatorOrganizationTarget.objects.update_or_create(
                project_indicator=project_indicator,
                organization=organization,
                defaults={
                    'q1_target': q1_target,
                    'q2_target': q2_target,
                    'q3_target': q3_target,
                    'q4_target': q4_target,
                    'target_value': quantize(q1_target + q2_target + q3_target + q4_target),
                    'baseline_value': baseline_values[index],
                    'current_value': current_values[index],
                },
            )


def backwards(apps, schema_editor):
    ProjectIndicator = apps.get_model('projects', 'ProjectIndicator')
    ProjectIndicatorOrganizationTarget = apps.get_model('projects', 'ProjectIndicatorOrganizationTarget')

    for project_indicator in ProjectIndicator.objects.all():
        targets = ProjectIndicatorOrganizationTarget.objects.filter(project_indicator=project_indicator)
        if not targets.exists():
            continue

        q1_total = sum((quantize(target.q1_target) for target in targets), Decimal('0'))
        q2_total = sum((quantize(target.q2_target) for target in targets), Decimal('0'))
        q3_total = sum((quantize(target.q3_target) for target in targets), Decimal('0'))
        q4_total = sum((quantize(target.q4_target) for target in targets), Decimal('0'))
        baseline_total = sum((quantize(target.baseline_value) for target in targets), Decimal('0'))
        current_total = sum((quantize(target.current_value) for target in targets), Decimal('0'))

        project_indicator.q1_target = q1_total
        project_indicator.q2_target = q2_total
        project_indicator.q3_target = q3_total
        project_indicator.q4_target = q4_total
        project_indicator.target_value = quantize(q1_total + q2_total + q3_total + q4_total)
        project_indicator.baseline_value = baseline_total
        project_indicator.current_value = current_total
        project_indicator.save(
            update_fields=['q1_target', 'q2_target', 'q3_target', 'q4_target', 'target_value', 'baseline_value', 'current_value']
        )

    ProjectIndicatorOrganizationTarget.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0002_alter_organization_type'),
        ('projects', '0002_projectindicator_quarterly_targets'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectIndicatorOrganizationTarget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('q1_target', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('q2_target', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('q3_target', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('q4_target', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('target_value', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('current_value', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('baseline_value', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_indicator_targets', to='organizations.organization')),
                ('project_indicator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organization_targets', to='projects.projectindicator')),
            ],
            options={
                'ordering': ['project_indicator__project__name', 'organization__name'],
                'unique_together': {('project_indicator', 'organization')},
            },
        ),
        migrations.RunPython(forwards, backwards),
    ]
