from django.db import models
from django.conf import settings


class Message(models.Model):
    """Messages from users (institution, tutor, student) to admin."""
    MESSAGE_TYPE_CONTACT = 'contact'
    MESSAGE_TYPE_SUPPORT = 'support'
    MESSAGE_TYPE_REPORT = 'report'
    MESSAGE_TYPE_FEEDBACK = 'feedback'

    MESSAGE_TYPE_CHOICES = [
        (MESSAGE_TYPE_CONTACT, 'Contact Admin'),
        (MESSAGE_TYPE_SUPPORT, 'Support Request'),
        (MESSAGE_TYPE_REPORT, 'Report Issue'),
        (MESSAGE_TYPE_FEEDBACK, 'Feedback'),
    ]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='received_messages',
        help_text="Usually the master admin"
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default=MESSAGE_TYPE_CONTACT)
    is_read = models.BooleanField(default=False)
    is_replied = models.BooleanField(default=False)
    reply_message = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
        ]

    def __str__(self):
        return f"Message from {self.sender} to {self.recipient}: {self.subject}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
