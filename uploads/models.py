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
