from django.db import models


class SocialPost(models.Model):
    """Social media post tracked against an indicator."""

    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter/X'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=255)
    indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='social_posts'
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='social_posts'
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='other')
    url = models.URLField(max_length=500)
    description = models.TextField(blank=True)
    post_date = models.DateField(null=True, blank=True)

    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    interactions = models.PositiveIntegerField(default=0)

    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_social_posts'
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Interactions are derived from likes + comments + shares by default.
        self.interactions = (self.likes or 0) + (self.comments or 0) + (self.shares or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
