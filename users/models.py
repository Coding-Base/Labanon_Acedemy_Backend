from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    # Role choices for different account types
    TUTOR = 'tutor'
    STUDENT = 'student'
    INSTITUTION = 'institution'
    RESEARCHER = 'researcher'
    ADMIN = 'admin'

    ROLE_CHOICES = [
        (TUTOR, 'Tutor'),
        (STUDENT, 'Student'),
        (INSTITUTION, 'Institution'),
        (RESEARCHER, 'Researcher'),
        (ADMIN, 'Admin'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=STUDENT)
    institution_name = models.CharField(max_length=255, blank=True, null=True)
    is_unlocked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.role})"


class TrialConfig(models.Model):
    """Singleton model to store system-wide trial days for tutor/institution accounts."""
    id = models.IntegerField(primary_key=True, default=1)
    trial_days = models.PositiveIntegerField(default=30)

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"TrialConfig({self.trial_days} days)"


class Review(models.Model):
    """User-submitted reviews/testimonials. Can include CBT metadata for exam reviews."""
    CATEGORY_GENERAL = 'general'
    CATEGORY_CBT = 'cbt'

    ROLE_CHOICES = [
        ('student', 'Student'),
        ('tutor', 'Tutor'),
        ('institution', 'Institution'),
        ('other', 'Other')
    ]

    author = models.ForeignKey('User', null=True, blank=True, on_delete=models.SET_NULL, related_name='reviews')
    name = models.CharField(max_length=200, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    rating = models.PositiveSmallIntegerField(default=5)
    message = models.TextField()
    is_approved = models.BooleanField(default=False)
    category = models.CharField(max_length=30, default=CATEGORY_GENERAL)

    # CBT specific metadata
    cbt_exam = models.CharField(max_length=255, blank=True, null=True)
    cbt_subject = models.CharField(max_length=255, blank=True, null=True)
    cbt_score = models.FloatField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        display = self.name or (self.author.username if self.author else 'Anonymous')
        return f"Review by {display} ({self.role}) - {self.rating}/5"
