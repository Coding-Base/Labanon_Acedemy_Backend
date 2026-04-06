from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


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
    
    # Email verification fields
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, unique=True, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class InstitutionProfile(models.Model):
    """Extended profile for institution users with detailed registration data."""
    
    INSTITUTION_TYPES = [
        ('university', 'University'),
        ('polytechnic', 'Polytechnic'),
        ('secondary_school', 'Secondary School'),
        ('training_org', 'Training Organization'),
        ('professional_institute', 'Professional Institute'),
        ('tutorial_center', 'Tutorial Center'),
    ]
    
    POSITION_CHOICES = [
        ('president', 'President/Rector'),
        ('vice_chancellor', 'Vice Chancellor/Principal'),
        ('provost', 'Provost'),
        ('dean', 'Dean'),
        ('hod', 'Head of Department (HOD)'),
        ('teaching_staff', 'Teaching Staff'),
        ('it_admin', 'IT/Admin Staff'),
        ('others', 'Others'),
    ]
    
    PURPOSE_CHOICES = [
        ('host_courses', 'Host courses'),
        ('recruitment_exams', 'Organise recruitment exams or online exams'),
        ('certificates', 'Launch certificate programs'),
        ('partnerships', 'Explore partnership opportunities'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='institution_profile')
    
    # Contact Person Information
    full_name = models.CharField(max_length=255)
    job_title = models.CharField(max_length=255)
    work_email = models.EmailField()
    
    # Institution Information
    institution_name = models.CharField(max_length=255)
    institution_type = models.CharField(max_length=50, choices=INSTITUTION_TYPES)
    position = models.CharField(max_length=50, choices=POSITION_CHOICES)
    department = models.CharField(max_length=255)
    country = models.CharField(max_length=255)
    
    # Purpose (JSON array stored as text, separated by commas for simplicity)
    purpose = models.TextField(help_text="Comma-separated purposes selected during registration")
    
    # Calculated Permissions (automatically set based on institution_type)
    can_create_diploma_courses = models.BooleanField(default=False)
    can_create_degree_programs = models.BooleanField(default=False)
    can_upload_projects = models.BooleanField(default=False)
    allowed_certifications = models.TextField(
        default='completion',
        help_text="Comma-separated list of allowed certification types"
    )
    dashboard_variant = models.CharField(
        max_length=50,
        default='tutorial',
        help_text="Determines which dashboard template to use"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Institution Profile'
        verbose_name_plural = 'Institution Profiles'
    
    def save(self, *args, **kwargs):
        """Calculate permissions based on institution type."""
        self._calculate_permissions()
        super().save(*args, **kwargs)
    
    def _calculate_permissions(self):
        """Set permissions and dashboard variant based on institution_type."""
        if self.institution_type == 'university':
            self.can_create_diploma_courses = True
            self.can_create_degree_programs = True
            self.can_upload_projects = True
            self.allowed_certifications = 'all'
            self.dashboard_variant = 'university'
        elif self.institution_type == 'polytechnic':
            self.can_create_diploma_courses = True
            self.can_create_degree_programs = False
            self.can_upload_projects = True
            self.allowed_certifications = 'diploma,professional'
            self.dashboard_variant = 'polytechnic'
        elif self.institution_type == 'secondary_school':
            self.can_create_diploma_courses = False
            self.can_create_degree_programs = False
            self.can_upload_projects = True
            self.allowed_certifications = 'completion,achievement'
            self.dashboard_variant = 'school'
        elif self.institution_type in ['training_org', 'professional_institute']:
            self.can_create_diploma_courses = False
            self.can_create_degree_programs = False
            self.can_upload_projects = False
            self.allowed_certifications = 'completion,professional'
            self.dashboard_variant = 'training'
        elif self.institution_type == 'tutorial_center':
            self.can_create_diploma_courses = False
            self.can_create_degree_programs = False
            self.can_upload_projects = False
            self.allowed_certifications = 'completion'
            self.dashboard_variant = 'tutorial'
    
    def __str__(self):
        return f"{self.institution_name} ({self.institution_type})"
    
    def get_purpose_list(self):
        """Return purpose as a list."""
        return [p.strip() for p in self.purpose.split(',') if p.strip()]
    
    def get_certifications_list(self):
        """Return allowed certifications as a list."""
        return [c.strip() for c in self.allowed_certifications.split(',') if c.strip()]


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
