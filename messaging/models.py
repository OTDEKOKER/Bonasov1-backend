from django.db import models


class Message(models.Model):
    """Internal messaging system."""
    
    TYPE_CHOICES = [
        ('notification', 'Notification'),
        ('alert', 'Alert'),
        ('message', 'Message'),
        ('reminder', 'Reminder'),
    ]
    
    sender = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='message')
    subject = models.CharField(max_length=255)
    content = models.TextField()
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subject} - {self.recipient.username}"


class Notification(models.Model):
    """System notifications."""
    
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    title = models.CharField(max_length=255)
    content = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    
    is_read = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"
