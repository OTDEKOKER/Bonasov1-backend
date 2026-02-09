from django.db import models


class Profile(models.Model):
    """Extended profile for respondents/participants."""
    
    respondent = models.OneToOneField(
        'respondents.Respondent',
        on_delete=models.CASCADE,
        related_name='profile'
    )
    
    # Extended demographics
    education_level = models.CharField(max_length=100, blank=True)
    employment_status = models.CharField(max_length=100, blank=True)
    income_level = models.CharField(max_length=100, blank=True)
    household_size = models.PositiveIntegerField(null=True, blank=True)
    
    # Health information
    health_status = models.CharField(max_length=100, blank=True)
    disabilities = models.TextField(blank=True)
    
    # Additional custom fields
    custom_fields = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile: {self.respondent.full_name}"


class ProfileField(models.Model):
    """Custom field definitions for profiles."""
    
    FIELD_TYPES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Select'),
        ('multiselect', 'Multi Select'),
        ('boolean', 'Yes/No'),
    ]
    
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    options = models.JSONField(default=list, blank=True, help_text='Options for select fields')
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='profile_fields'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name
