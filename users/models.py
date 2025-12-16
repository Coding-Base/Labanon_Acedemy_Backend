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
