from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0003_alter_organization_code'),
        ('projects', '0003_projectindicatororganizationtarget'),
        ('uploads', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkbookTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('workbook_family', models.CharField(blank=True, max_length=100, null=True)),
                ('report_category', models.CharField(blank=True, max_length=100, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('is_active', models.BooleanField(default=True)),
                ('expected_headers', models.JSONField(blank=True, default=list)),
                ('row_labels', models.JSONField(blank=True, default=list)),
                ('column_labels', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_workbook_templates', to=settings.AUTH_USER_MODEL)),
                ('source_upload', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workbook_templates', to='uploads.upload')),
            ],
            options={'ordering': ['name', '-version', '-created_at']},
        ),
        migrations.CreateModel(
            name='WorkbookExportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('scope', models.CharField(choices=[('single_organization', 'Single organization'), ('coordinator', 'Coordinator'), ('all_organizations', 'All organizations'), ('consolidated', 'Consolidated')], max_length=30)),
                ('reporting_period', models.CharField(max_length=100)),
                ('financial_year_start_month', models.PositiveSmallIntegerField(default=4)),
                ('errors', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('coordinator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coordinator_workbook_exports', to='organizations.organization')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workbook_export_jobs', to=settings.AUTH_USER_MODEL)),
                ('generated_upload', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_workbook_exports', to='uploads.upload')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='organization_workbook_exports', to='organizations.organization')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workbook_export_jobs', to='projects.project')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='export_jobs', to='uploads.workbooktemplate')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
