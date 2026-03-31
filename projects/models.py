from decimal import Decimal, InvalidOperation

from django.db import models


class Project(models.Model):
    """Project model for scoping data collection."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    funder = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    start_date = models.DateField()
    end_date = models.DateField()

    indicators = models.ManyToManyField(
        'indicators.Indicator',
        through='ProjectIndicator',
        related_name='projects'
    )

    organizations = models.ManyToManyField(
        'organizations.Organization',
        blank=True,
        related_name='projects'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_projects'
    )

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def progress_percentage(self):
        """Calculate project progress based on targets."""
        indicators = self.projectindicator_set.all()
        if not indicators:
            return 0
        total = sum(1 for indicator in indicators if indicator.current_value >= indicator.target_value)
        return int((total / indicators.count()) * 100)


class ProjectIndicator(models.Model):
    """Through model for Project-Indicator with aggregate quarterly targets."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    indicator = models.ForeignKey('indicators.Indicator', on_delete=models.CASCADE)
    q1_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q2_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q3_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q4_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    target_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    baseline_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        unique_together = ['project', 'indicator']

    def __str__(self):
        return f"{self.project.name} - {self.indicator.name}"

    @staticmethod
    def _to_decimal(value):
        if value in (None, ""):
            return Decimal('0')
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0')

    def refresh_rollups(self, save=True):
        targets = list(self.organization_targets.all())
        if not targets:
            self.target_value = sum(
                (
                    self._to_decimal(self.q1_target),
                    self._to_decimal(self.q2_target),
                    self._to_decimal(self.q3_target),
                    self._to_decimal(self.q4_target),
                ),
                Decimal('0'),
            )
        else:
            self.q1_target = sum((self._to_decimal(target.q1_target) for target in targets), Decimal('0'))
            self.q2_target = sum((self._to_decimal(target.q2_target) for target in targets), Decimal('0'))
            self.q3_target = sum((self._to_decimal(target.q3_target) for target in targets), Decimal('0'))
            self.q4_target = sum((self._to_decimal(target.q4_target) for target in targets), Decimal('0'))
            self.target_value = sum((self._to_decimal(target.target_value) for target in targets), Decimal('0'))
            self.current_value = sum((self._to_decimal(target.current_value) for target in targets), Decimal('0'))
            self.baseline_value = sum((self._to_decimal(target.baseline_value) for target in targets), Decimal('0'))

        if save:
            super().save(
                update_fields=[
                    'q1_target',
                    'q2_target',
                    'q3_target',
                    'q4_target',
                    'target_value',
                    'current_value',
                    'baseline_value',
                ]
            )

    def save(self, *args, **kwargs):
        if self.pk and self.organization_targets.exists():
            self.refresh_rollups(save=False)
        else:
            self.target_value = sum(
                (
                    self._to_decimal(self.q1_target),
                    self._to_decimal(self.q2_target),
                    self._to_decimal(self.q3_target),
                    self._to_decimal(self.q4_target),
                ),
                Decimal('0'),
            )
        super().save(*args, **kwargs)


class ProjectIndicatorOrganizationTarget(models.Model):
    """Organization-specific quarterly targets for a project indicator."""

    project_indicator = models.ForeignKey(
        ProjectIndicator,
        on_delete=models.CASCADE,
        related_name='organization_targets',
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='project_indicator_targets',
    )
    q1_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q2_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q3_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    q4_target = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    target_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    baseline_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        unique_together = ['project_indicator', 'organization']
        ordering = ['project_indicator__project__name', 'organization__name']

    def __str__(self):
        return f"{self.project_indicator.project.name} - {self.organization.name} - {self.project_indicator.indicator.name}"

    def save(self, *args, **kwargs):
        self.target_value = sum(
            (
                ProjectIndicator._to_decimal(self.q1_target),
                ProjectIndicator._to_decimal(self.q2_target),
                ProjectIndicator._to_decimal(self.q3_target),
                ProjectIndicator._to_decimal(self.q4_target),
            ),
            Decimal('0'),
        )
        super().save(*args, **kwargs)
        self.project_indicator.refresh_rollups()

    def delete(self, *args, **kwargs):
        project_indicator = self.project_indicator
        super().delete(*args, **kwargs)
        project_indicator.refresh_rollups()


class Task(models.Model):
    """Task model for project activities."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')

    assigned_to = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )

    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tasks'
    )

    class Meta:
        ordering = ['due_date', '-priority']

    def __str__(self):
        return f"{self.name} ({self.project.name})"


class Deadline(models.Model):
    """Deadline model for reporting deadlines."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('overdue', 'Overdue'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='deadlines')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    indicators = models.ManyToManyField('indicators.Indicator', blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submitted_deadlines'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.name} - {self.due_date}"
