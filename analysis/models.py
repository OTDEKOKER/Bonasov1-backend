from django.db import models


class Report(models.Model):
    """Saved/generated reports."""
    
    TYPE_CHOICES = [
        ('dashboard', 'Dashboard'),
        ('indicator', 'Indicator Report'),
        ('project', 'Project Report'),
        ('custom', 'Custom Report'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='custom')
    
    # Query/filter parameters
    parameters = models.JSONField(default=dict)
    
    # Cached data
    cached_data = models.JSONField(default=dict, blank=True)
    last_generated = models.DateTimeField(null=True, blank=True)
    
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reports'
    )
    
    is_public = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_reports'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class SavedQuery(models.Model):
    """Saved queries for quick access."""
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    query_params = models.JSONField()
    
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='saved_queries'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class ScheduledReport(models.Model):
    """Scheduled report definition."""

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    report_name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, default='custom')
    parameters = models.JSONField(default=dict)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    recipients = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    next_run = models.DateTimeField()
    last_run = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='scheduled_reports'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.report_name


class CoordinatorTarget(models.Model):
    """Quarterly coordinator portfolio targets per project and indicator."""

    QUARTER_Q1 = 'Q1'
    QUARTER_Q2 = 'Q2'
    QUARTER_Q3 = 'Q3'
    QUARTER_Q4 = 'Q4'
    QUARTER_CHOICES = [
        (QUARTER_Q1, 'Q1'),
        (QUARTER_Q2, 'Q2'),
        (QUARTER_Q3, 'Q3'),
        (QUARTER_Q4, 'Q4'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='coordinator_targets',
    )
    coordinator = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='coordinator_targets',
    )
    indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='coordinator_targets',
    )
    year = models.PositiveIntegerField(help_text='Fiscal year start (e.g. 2025 for FY 2025/26).')
    quarter = models.CharField(max_length=2, choices=QUARTER_CHOICES)
    target_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', 'quarter', 'project__name', 'coordinator__name', 'indicator__name']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'coordinator', 'indicator', 'year', 'quarter'],
                name='uq_coordinator_target_scope_period',
            ),
        ]

    def __str__(self):
        return (
            f"{self.project.name} - {self.coordinator.name} - "
            f"{self.indicator.code} ({self.quarter} {self.year})"
        )
