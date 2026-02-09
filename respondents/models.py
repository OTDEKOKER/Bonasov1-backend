from django.db import models


class Respondent(models.Model):
    """Respondent model for individual data tracking."""
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    
    unique_id = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='respondents'
    )
    
    # Additional demographics
    demographics = models.JSONField(default=dict, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_respondents'
    )
    
    class Meta:
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"{self.unique_id} - {self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Interaction(models.Model):
    """Interaction/data collection record for a respondent."""
    
    respondent = models.ForeignKey(
        Respondent,
        on_delete=models.CASCADE,
        related_name='interactions'
    )
    assessment = models.ForeignKey(
        'indicators.Assessment',
        on_delete=models.SET_NULL,
        null=True,
        related_name='interactions'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interactions'
    )
    
    date = models.DateField()
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_interactions'
    )
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.respondent.unique_id} - {self.date}"


class Response(models.Model):
    """Individual response to an indicator within an interaction."""
    
    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='responses'
    )
    
    # Store value as JSON to handle different types
    value = models.JSONField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['interaction', 'indicator']
    
    def __str__(self):
        return f"{self.interaction} - {self.indicator.code}"
