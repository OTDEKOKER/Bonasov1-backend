from django.db import models


class Indicator(models.Model):
    """Indicator model for tracking metrics."""
    
    TYPE_CHOICES = [
        ('yes_no', 'Yes/No'),
        ('number', 'Number'),
        ('percentage', 'Percentage'),
        ('text', 'Text'),
        ('select', 'Single Select'),
        ('multiselect', 'Multi Select'),
        ('date', 'Date'),
        ('multi_int', 'Multiple Integers'),
    ]
    
    CATEGORY_CHOICES = [
        ('hiv_prevention', 'HIV Prevention'),
        ('ncd', 'Non-Communicable Diseases'),
        ('events', 'Events'),
    ]
    
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='number')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='hiv_prevention')
    unit = models.CharField(max_length=50, blank=True, help_text='e.g., people, sessions, %')
    
    # For select/multiselect types
    options = models.JSONField(default=list, blank=True, help_text='Options for select types')
    
    # For multi_int type
    sub_labels = models.JSONField(default=list, blank=True, help_text='Labels for multi-int fields')
    
    # Aggregation and calculation
    aggregation_method = models.CharField(
        max_length=20,
        choices=[('sum', 'Sum'), ('average', 'Average'), ('count', 'Count'), ('latest', 'Latest')],
        default='sum'
    )
    
    # Visibility and access
    is_active = models.BooleanField(default=True)
    organizations = models.ManyToManyField(
        'organizations.Organization',
        blank=True,
        related_name='indicators'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_indicators'
    )
    
    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Assessment(models.Model):
    """Assessment linking indicators together for data collection."""
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    indicators = models.ManyToManyField(
        Indicator,
        through='AssessmentIndicator',
        related_name='assessments'
    )
    
    # Logic and flow
    logic_rules = models.JSONField(default=dict, blank=True, help_text='Conditional display rules')
    
    is_active = models.BooleanField(default=True)
    organizations = models.ManyToManyField(
        'organizations.Organization',
        blank=True,
        related_name='assessments'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_assessments'
    )
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class AssessmentIndicator(models.Model):
    """Through model for Assessment-Indicator relationship."""
    
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    
    # Conditional display
    depends_on = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependents'
    )
    condition_value = models.JSONField(null=True, blank=True, help_text='Value that triggers display')
    
    class Meta:
        ordering = ['order']
        unique_together = ['assessment', 'indicator']
    
    def __str__(self):
        return f"{self.assessment.name} - {self.indicator.name}"
