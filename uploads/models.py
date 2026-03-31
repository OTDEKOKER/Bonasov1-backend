from django.db import models
import os


def upload_path(instance, filename):
    return f"uploads/{instance.organization.code if instance.organization else 'general'}/{filename}"


class Upload(models.Model):
    """File uploads model."""
    
    TYPE_CHOICES = [
        ('document', 'Document'),
        ('image', 'Image'),
        ('spreadsheet', 'Spreadsheet'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to=upload_path)
    file_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='document')
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    
    description = models.TextField(blank=True)
    
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='uploads'
    )
    
    # Link to any model
    content_type = models.CharField(max_length=100, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploads'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            ext = os.path.splitext(self.file.name)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                self.file_type = 'image'
            elif ext in ['.xlsx', '.xls', '.csv']:
                self.file_type = 'spreadsheet'
            elif ext in ['.pdf', '.doc', '.docx']:
                self.file_type = 'document'
        super().save(*args, **kwargs)


class ImportJob(models.Model):
    """Track data import jobs."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='import_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    
    errors = models.JSONField(default=list, blank=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='import_jobs'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Import: {self.upload.name} ({self.status})"


class WorkbookTemplate(models.Model):
    """Stored workbook template metadata for report workbook imports/exports."""

    name = models.CharField(max_length=255)
    workbook_family = models.CharField(max_length=100, blank=True, null=True)
    report_category = models.CharField(max_length=100, blank=True, null=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    expected_headers = models.JSONField(default=list, blank=True)
    row_labels = models.JSONField(default=list, blank=True)
    column_labels = models.JSONField(default=list, blank=True)
    source_upload = models.ForeignKey(
        Upload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workbook_templates',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_workbook_templates',
    )

    class Meta:
        ordering = ['name', '-version', '-created_at']

    def __str__(self):
        return f"{self.name} v{self.version}"


class WorkbookExportJob(models.Model):
    """Generated workbook export jobs and downloadable output files."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    SCOPE_CHOICES = [
        ('single_organization', 'Single organization'),
        ('coordinator', 'Coordinator'),
        ('all_organizations', 'All organizations'),
        ('consolidated', 'Consolidated'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    scope = models.CharField(max_length=30, choices=SCOPE_CHOICES)
    reporting_period = models.CharField(max_length=100)
    financial_year_start_month = models.PositiveSmallIntegerField(default=4)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='workbook_export_jobs',
    )
    template = models.ForeignKey(
        WorkbookTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='export_jobs',
    )
    generated_upload = models.ForeignKey(
        Upload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_workbook_exports',
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organization_workbook_exports',
    )
    coordinator = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coordinator_workbook_exports',
    )
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workbook_export_jobs',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Workbook export {self.project_id} {self.reporting_period} ({self.status})"
