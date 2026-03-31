from django.db import models


class Aggregate(models.Model):
    """Aggregate data entry without respondent linking."""

    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_REVIEWED = 'reviewed'
    STATUS_FLAGGED = 'flagged'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Coordinator Review'),
        (STATUS_REVIEWED, 'Reviewed - Awaiting Approval'),
        (STATUS_FLAGGED, 'Flagged for Correction'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_aggregates'
    )
    
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

    def save(self, *args, **kwargs):
        if not self.status:
            self.status = self.STATUS_PENDING
        if self.notes is None:
            self.notes = ''
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.indicator.code} - {self.organization.name} ({self.period_start})"


class AggregateChangeLog(models.Model):
    """Structured audit trail for aggregate workflow actions and corrections."""

    ACTION_SUBMITTED = 'submitted'
    ACTION_CORRECTED = 'corrected'
    ACTION_REVIEWED = 'reviewed'
    ACTION_FLAGGED = 'flagged'
    ACTION_APPROVED = 'approved'
    ACTION_CHOICES = [
        (ACTION_SUBMITTED, 'Submitted'),
        (ACTION_CORRECTED, 'Corrected'),
        (ACTION_REVIEWED, 'Reviewed'),
        (ACTION_FLAGGED, 'Flagged'),
        (ACTION_APPROVED, 'Approved'),
    ]

    aggregate = models.ForeignKey(
        Aggregate,
        on_delete=models.CASCADE,
        related_name='history_entries',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    changed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aggregate_change_logs',
    )
    comment = models.TextField(blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.aggregate_id} - {self.action} @ {self.created_at}"


class DerivationRule(models.Model):
    """Rule to derive an output indicator from interaction responses."""

    OPERATOR_CHOICES = [
        ('equals', 'Equals'),
        ('not_equals', 'Not Equals'),
        ('contains', 'Contains'),
    ]

    COUNT_DISTINCT_CHOICES = [
        ('respondent', 'Respondent'),
        ('interaction', 'Interaction'),
    ]

    output_indicator = models.OneToOneField(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='derivation_rule',
    )
    source_indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='derivation_rule_sources',
    )

    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES, default='equals')
    match_value = models.JSONField(null=True, blank=True)
    count_distinct = models.CharField(max_length=20, choices=COUNT_DISTINCT_CHOICES, default='respondent')

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_derivation_rules',
    )

    class Meta:
        ordering = ['output_indicator__code']

    def __str__(self):
        return f"{self.output_indicator.code} derived from {self.source_indicator.code}"
