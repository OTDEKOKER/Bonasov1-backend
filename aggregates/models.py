from django.db import models


class Aggregate(models.Model):
    """Aggregate data entry without respondent linking."""
    
    indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='aggregates'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='aggregates'
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='aggregates'
    )
    
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Store value as JSON to handle different types
    value = models.JSONField()
    
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_aggregates'
    )
    
    class Meta:
        ordering = ['-period_start']
        unique_together = ['indicator', 'project', 'organization', 'period_start', 'period_end']
    
    def __str__(self):
        return f"{self.indicator.code} - {self.organization.name} ({self.period_start})"
