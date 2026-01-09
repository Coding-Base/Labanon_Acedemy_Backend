# backend/courses/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Avg, Sum 
import uuid

class Institution(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_institutions')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # Added for Certificate Signature Feature
    signer_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of the person signing certificates (e.g. Dr. John Doe)")
    signer_position = models.CharField(max_length=255, blank=True, null=True, help_text="Job title (e.g. Dean of Studies, Registrar)")
    signature_image = models.CharField(max_length=512, blank=True, null=True, help_text="URL to the uploaded signature image")
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Course(models.Model):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses')
    institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    image = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # scheduled course support
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    meeting_time = models.TimeField(null=True, blank=True)
    meeting_place = models.CharField(max_length=100, blank=True)
    meeting_link = models.CharField(max_length=512, blank=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    # --- Helper Methods for Real Stats ---
    def get_student_count(self):
        """Count users who have purchased this course."""
        return self.enrollments.filter(purchased=True).count()

    def get_average_rating(self):
        """Calculate average rating from reviews."""
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0.0

    def get_ratings_count(self):
        """Count total reviews."""
        return self.reviews.count()

    def get_total_duration(self):
        """Sum up duration of all lessons."""
        total_minutes = self.modules.aggregate(
            total=Sum('lessons__duration_minutes')
        )['total'] or 0
        
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{int(hours)}h {int(minutes)}m"


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    video = models.CharField(max_length=512, blank=True)  # store Cloudinary public id or remote URL
    # S3 video reference (optional)
    video_s3 = models.ForeignKey(
        'videos.Video', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='lessons'
    )
    # YouTube embed URL (optional)
    youtube_url = models.URLField(blank=True, null=True)
    
    # Added duration field for stat calculation
    duration_minutes = models.PositiveIntegerField(default=0, help_text="Duration in minutes")
    
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.module.title} - {self.title}"


class Enrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user} -> {self.course}"


class Payment(models.Model):
    PENDING = 'pending'
    SUCCESS = 'success'
    FAILED = 'failed'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (SUCCESS, 'Success'),
        (FAILED, 'Failed'),
    ]

    KIND_COURSE = 'course'
    KIND_DIPLOMA = 'diploma'
    KIND_UNLOCK = 'unlock'

    KIND_CHOICES = [
        (KIND_COURSE, 'Course Purchase'),
        (KIND_DIPLOMA, 'Diploma Enrollment'),
        (KIND_UNLOCK, 'Account Unlock'),
    ]

    # Payment provider choices
    PROVIDER_PAYSTACK = 'paystack'
    PROVIDER_FLUTTERWAVE = 'flutterwave'
    PROVIDER_CHOICES = [
        (PROVIDER_PAYSTACK, 'Paystack'),
        (PROVIDER_FLUTTERWAVE, 'Flutterwave'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    diploma = models.ForeignKey('Diploma', on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_COURSE)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    creator_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount to course/diploma creator")
    
    # Payment provider
    payment_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_PAYSTACK)
    
    # Paystack integration
    paystack_reference = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="Paystack reference code")
    
    # Flutterwave integration
    flutterwave_reference = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="Flutterwave tx_ref code")
    flutterwave_transaction_id = models.CharField(max_length=255, blank=True, null=True, help_text="Flutterwave transaction ID")
    
    provider_reference = models.CharField(max_length=255, blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When payment was verified")

    def __str__(self):
        return f"Payment {self.id} {self.user} {self.amount} {self.status}"


class CartItem(models.Model):
    """Simple cart item representing a course added to a user's cart."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart_items')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cart_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"CartItem {self.user} -> {self.course}"


class Diploma(models.Model):
    """Diploma represents an onsite/in-person learning program offered by an institution."""
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='diplomas')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='diplomas')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=512, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration = models.CharField(max_length=255, blank=True, help_text="e.g., 6 months, 1 year")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    meeting_place = models.CharField(max_length=255, help_text="Physical location of the program")
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.institution.name})"


class DiplomaEnrollment(models.Model):
    """Enrollment for a diploma program."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='diploma_enrollments')
    diploma = models.ForeignKey(Diploma, on_delete=models.CASCADE, related_name='enrollments')
    purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'diploma')
        ordering = ['-purchased_at']

    def __str__(self):
        return f"{self.user} -> {self.diploma.title}"


class Portfolio(models.Model):
    """Institution portfolio that showcases their work and can be published with a public link."""
    institution = models.OneToOneField(Institution, on_delete=models.CASCADE, related_name='portfolio')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    overview = models.TextField(blank=True, help_text="Short overview of the institution")
    image = models.CharField(max_length=512, blank=True, help_text="Main portfolio image/logo")
    website = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    theme_color = models.CharField(max_length=7, blank=True, default='', help_text='Hex color for portfolio theming')
    published = models.BooleanField(default=False)
    public_token = models.CharField(max_length=32, unique=True, blank=True, help_text="Unique token for public link")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Portfolio: {self.institution.name}"

    def save(self, *args, **kwargs):
        if not self.public_token:
            import uuid
            self.public_token = str(uuid.uuid4()).replace('-', '')[:32]
        super().save(*args, **kwargs)


class PortfolioGalleryItem(models.Model):
    """Gallery items for institution portfolio."""
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='gallery_items')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=512, help_text="URL to image/video thumbnail")
    url = models.URLField(blank=True, null=True, help_text="Link to full media if different")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f"{self.portfolio.institution.name} - {self.title}"


class PaystackSubAccount(models.Model):
    """Paystack sub-account for tutors and institutions."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paystack_subaccount')
    bank_code = models.CharField(max_length=10, help_text="Bank code from Paystack")
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=255)
    subaccount_code = models.CharField(max_length=100, blank=True, null=True, unique=True, help_text="Paystack subaccount_code")
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.account_number}"

    class Meta:
        verbose_name_plural = "Paystack Sub-accounts"


class FlutterwaveSubAccount(models.Model):
    """Flutterwave sub-account for tutors and institutions."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flutterwave_subaccount')
    bank_code = models.CharField(max_length=10, help_text="Bank code from Flutterwave")
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=255)
    subaccount_id = models.CharField(max_length=100, blank=True, null=True, unique=True, help_text="Flutterwave subaccount_id")
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.account_number}"

    class Meta:
        verbose_name_plural = "Flutterwave Sub-accounts"


class Certificate(models.Model):
    """Certificate of completion for courses."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates')
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='certificate', null=True, blank=True)
    certificate_id = models.CharField(max_length=50, unique=True, help_text="Unique certificate ID")
    issue_date = models.DateTimeField(auto_now_add=True)
    completion_date = models.DateField(null=True, blank=True)
    is_downloaded = models.BooleanField(default=False)
    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['certificate_id']),
        ]

    def __str__(self):
        return f"Certificate: {self.user.username} - {self.course.title}"

    def mark_downloaded(self):
        self.is_downloaded = True
        self.download_count += 1
        self.last_downloaded_at = timezone.now()
        self.save()


class Review(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)]) # 1-5 stars
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating} stars for {self.course.title} by {self.user.username}"