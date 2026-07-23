# backend/courses/models.py

from django.db import models
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db.models import Avg, Sum 
import uuid

class Institution(models.Model):
    # Verification status choices
    VERIFICATION_PENDING = 'pending'
    VERIFICATION_APPROVED = 'approved'
    VERIFICATION_REJECTED = 'rejected'
    
    VERIFICATION_CHOICES = [
        (VERIFICATION_PENDING, 'Pending Verification'),
        (VERIFICATION_APPROVED, 'Verified & Approved'),
        (VERIFICATION_REJECTED, 'Verification Rejected'),
    ]
    
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_institutions')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # Added for Certificate Signature Feature
    signer_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of the person signing certificates (e.g. Dr. John Doe)")
    signer_position = models.CharField(max_length=255, blank=True, null=True, help_text="Job title (e.g. Dean of Studies, Registrar)")
    signature_image = models.CharField(max_length=512, blank=True, null=True, help_text="URL to the uploaded signature image")
    # Institution logo to appear on certificates and public pages
    logo_image = models.CharField(max_length=512, blank=True, null=True, help_text="URL to the uploaded institution logo")
    
    # Verification system fields
    verification_status = models.CharField(
        max_length=20, 
        choices=VERIFICATION_CHOICES, 
        default=VERIFICATION_PENDING,
        help_text="Verification status of the institution"
    )
    courses_published_before_verification = models.BooleanField(
        default=False,
        help_text="Whether courses can be seen in marketplace before verification"
    )
    
    # Custom revenue share for this institution (overrides platform default)
    custom_share_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Custom share percentage for this institution (e.g., 85.00 for 85%). Overrides platform default."
    )
    
    # Verification tracking
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_institutions',
        help_text="Admin who verified this institution"
    )
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When institution was verified")
    rejection_reason = models.TextField(blank=True, help_text="Reason for rejection if status is rejected")
    
    # Contact information for verification
    phone = models.CharField(max_length=20, blank=True, help_text="Institution contact phone number")
    email = models.EmailField(blank=True, help_text="Institution contact email")
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name
    
    def is_verified(self):
        """Check if institution is verified."""
        return self.verification_status == self.VERIFICATION_APPROVED


class Course(models.Model):
    COURSE_TYPE_CHOICES = [
        ('beginner', 'Beginner Course'),
        ('intermediate', 'Intermediate Course'),
        ('advanced', 'Advanced Course'),
        ('master', 'Master Course'),
        ('specialized', 'Specialized Course'),
        ('certification', 'Certification Program'),
        ('bootcamp', 'Bootcamp'),
        ('workshop', 'Workshop'),
        ('other', 'Other'),
    ]

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses')
    institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    image = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Course type badge
    course_type = models.CharField(max_length=50, choices=COURSE_TYPE_CHOICES, default='other', help_text='Type/badge for course listing')
    # Course level and outcomes
    level = models.CharField(max_length=50, default='Beginner', blank=True, help_text='Course difficulty level')
    outcome = models.TextField(blank=True, help_text='What students will learn')
    required_tools = models.TextField(blank=True, help_text='Tools/software required')
    # scheduled course support
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    meeting_time = models.TimeField(null=True, blank=True)
    meeting_place = models.CharField(max_length=100, blank=True)
    meeting_link = models.CharField(max_length=512, blank=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    views_count = models.PositiveIntegerField(default=0, help_text='Number of times the course detail has been viewed')

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

    is_series = models.BooleanField(default=False, help_text='Designates this course as an umbrella Series course')


class SeriesItem(models.Model):
    """Sub-course entry under an umbrella Series course."""
    series = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='series_items')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='parent_series')
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        unique_together = ('series', 'course')

    def __str__(self):
        return f"{self.series.title} -> {self.course.title} (Order: {self.order})"



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
    KIND_MATERIAL = 'material'

    KIND_CHOICES = [
        (KIND_COURSE, 'Course Purchase'),
        (KIND_DIPLOMA, 'Diploma Enrollment'),
        (KIND_UNLOCK, 'Account Unlock'),
        (KIND_MATERIAL, 'Material Purchase'),
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
    # ISO 4217 currency code for this payment (e.g., 'NGN', 'USD')
    currency = models.CharField(max_length=3, default='NGN', help_text='ISO 4217 currency code (e.g., NGN, USD)')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_COURSE)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    creator_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount to course/diploma creator")
    
    # Payment provider
    payment_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_PAYSTACK)
    
    # Paystack integration
    paystack_reference = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="Paystack reference code")
    recipient_code = models.CharField(max_length=255, blank=True, null=True, help_text="Paystack recipient code for tutor sub-account")
    
    # Flutterwave integration
    flutterwave_reference = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="Flutterwave tx_ref code")
    flutterwave_transaction_id = models.CharField(max_length=255, blank=True, null=True, help_text="Flutterwave transaction ID")
    
    provider_reference = models.CharField(max_length=255, blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When payment was verified")
    
    # Webhook tracking for payment reconciliation
    webhook_received = models.BooleanField(default=False, help_text="Whether webhook confirmation received from gateway")
    webhook_received_at = models.DateTimeField(null=True, blank=True, help_text="When webhook was received from gateway")
    webhook_attempts = models.IntegerField(default=0, help_text="Number of times webhook was received for this payment")
    
    # Gateway fees tracking
    gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Fee charged by payment gateway (Paystack/Flutterwave)")
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount received after gateway fee")
    # Attribution: optional link to Visit that led to this payment
    visit = models.ForeignKey('Visit', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    # Promo attribution (optional) - stores code used and discount amount applied
    promo_code = models.CharField(max_length=64, blank=True, null=True, help_text='Promo code applied to this payment')
    promo_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Discount amount applied from promo')

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
    
    # Rich text sections for diploma details (HTML content from rich text editor)
    overview = models.TextField(blank=True, help_text="Overview of the diploma program")
    admissions = models.TextField(blank=True, help_text="Admissions information and requirements")
    academics = models.TextField(blank=True, help_text="Academic details and curriculum")
    tuition_financing = models.TextField(blank=True, help_text="Tuition fees and financing options")
    careers = models.TextField(blank=True, help_text="Career prospects and alumni success")
    student_experience = models.TextField(blank=True, help_text="Student experience and testimonials")


class Visit(models.Model):
    """Simple visit/pageview model to capture referrer and UTM attributes."""
    path = models.CharField(max_length=1024, blank=True)
    full_url = models.CharField(max_length=2048, blank=True)
    referrer = models.CharField(max_length=2048, blank=True, null=True)
    utm_source = models.CharField(max_length=255, blank=True, null=True)
    utm_medium = models.CharField(max_length=255, blank=True, null=True)
    utm_campaign = models.CharField(max_length=255, blank=True, null=True)
    utm_term = models.CharField(max_length=255, blank=True, null=True)
    utm_content = models.CharField(max_length=255, blank=True, null=True)
    user_agent = models.CharField(max_length=1024, blank=True, null=True)
    ip_address = models.CharField(max_length=45, blank=True, null=True)
    # Session and landing/exit
    session_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    is_landing = models.BooleanField(default=False)
    is_exit = models.BooleanField(default=False)

    # Geo enrichment
    country = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    region = models.CharField(max_length=128, blank=True, null=True)
    city = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Visit {self.path or self.full_url} @ {self.created_at.isoformat()}"


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


class PaymentSplitConfig(models.Model):
    """Singleton config for payment split ratios managed by master admin.

    - `tutor_share`: Percentage share given to individual tutors (e.g., 95.00)
    - `institution_share`: Percentage share given to institutions/schools (e.g., 90.00)
    The platform share is implicitly `100 - creator_share`.
    """
    tutor_share = models.DecimalField(max_digits=5, decimal_places=2, default=95.00, help_text="Percent share for tutors")
    institution_share = models.DecimalField(max_digits=5, decimal_places=2, default=90.00, help_text="Percent share for institutions/schools")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, help_text="Admin user who last updated these values")

    class Meta:
        verbose_name = "Payment Split Config"

    def __str__(self):
        return f"Splits (tutor={self.tutor_share}%, institution={self.institution_share}%)"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj


class ReferralSettings(models.Model):
    """Singleton settings for referral rewards managed by master admin."""
    points_per_success = models.PositiveIntegerField(default=1000)
    # Fractional percent stored as decimal fraction. Example: 0.05 represents 5%.
    referral_percent = models.DecimalField(max_digits=8, decimal_places=6, default=Decimal('0.05'), help_text='Decimal fraction representing percent of platform share to award (e.g., 0.05 means 5%)')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Referral Settings"
        verbose_name_plural = "Referral Settings"

    def __str__(self):
        return f"Referral settings ({self.points_per_success} points)"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj


class ReferralProfile(models.Model):
    """Referral wallet/profile for each user."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_profile')
    code = models.CharField(max_length=24, unique=True, db_index=True)
    # Store as currency-like credit with two decimal places
    points_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.code}"


class ReferralRelationship(models.Model):
    """Links a referred user to the referrer whose code they used."""
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referrals_made')
    referred = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referred_by_relationship')
    code_used = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['referrer', '-created_at']),
            models.Index(fields=['code_used']),
        ]

    def __str__(self):
        return f"{self.referrer} referred {self.referred}"


class ReferralEvent(models.Model):
    SIGNUP_VERIFIED = 'signup_verified'
    COURSE_PURCHASE = 'course_purchase'
    MATERIAL_PURCHASE = 'material_purchase'
    POINTS_REDEEMED = 'points_redeemed'

    EVENT_CHOICES = [
        (SIGNUP_VERIFIED, 'Signup Verified'),
        (COURSE_PURCHASE, 'Course Purchase'),
        (MATERIAL_PURCHASE, 'Material Purchase'),
        (POINTS_REDEEMED, 'Points Redeemed'),
    ]

    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_events')
    referred = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='referral_events_as_referred')
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    points = models.DecimalField(max_digits=12, decimal_places=2, help_text="Positive for awards, negative for redemptions")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='referral_events')
    material_id = models.UUIDField(null=True, blank=True, db_index=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='referral_events')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['referrer', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
            models.Index(fields=['referred', 'event_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['referred', 'event_type'],
                condition=models.Q(event_type='signup_verified'),
                name='unique_referral_signup_verified',
            ),
            models.UniqueConstraint(
                fields=['referred', 'event_type', 'course'],
                condition=models.Q(event_type='course_purchase'),
                name='unique_referral_course_purchase',
            ),
            models.UniqueConstraint(
                fields=['referred', 'event_type', 'material_id'],
                condition=models.Q(event_type='material_purchase'),
                name='unique_referral_material_purchase',
            ),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.points} for {self.referrer}"


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


class ModuleQuiz(models.Model):
    """Quiz for a module that students must complete before moving to next module.
    
    This is DISTINCT from CBT exams. These are inline module quizzes within courses.
    """
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name='quiz', help_text='Each module can have one quiz')
    title = models.CharField(max_length=255, default='Module Quiz')
    description = models.TextField(blank=True)
    passing_score = models.PositiveIntegerField(default=70, help_text='Minimum percentage score to pass (0-100)')
    is_required = models.BooleanField(default=True, help_text='Must student pass this quiz to proceed to next module?')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Module Quiz'
        verbose_name_plural = 'Module Quizzes'

    def __str__(self):
        return f"Quiz: {self.module.title}"

    def calculate_total_points(self):
        """Calculate total possible points for this quiz."""
        return sum(q.points for q in self.questions.all()) or 0


class QuizQuestion(models.Model):
    """A question within a module quiz."""
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(help_text='Question text/prompt')
    order = models.PositiveIntegerField(default=0, help_text='Display order within quiz')
    points = models.PositiveIntegerField(default=1, help_text='Points awarded for correct answer')
    explanation = models.TextField(blank=True, help_text='Explanation shown after answering')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Quiz Question'

    def __str__(self):
        return f"Q{self.order + 1}: {self.text[:50]}"


class QuizOption(models.Model):
    """An option/choice for a quiz question."""
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=500, help_text='Option text')
    is_correct = models.BooleanField(default=False, help_text='Is this the correct answer?')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'Quiz Option'

    def __str__(self):
        return f"{self.question.text[:30]} - {self.text[:50]}"


class ModuleQuizAttempt(models.Model):
    """Records a student's attempt at a module quiz."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True, help_text='Score achieved (0-100 percentage)')
    total_points = models.PositiveIntegerField(default=0)
    earned_points = models.PositiveIntegerField(default=0)
    passed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'quiz')
        verbose_name = 'Module Quiz Attempt'

    def __str__(self):
        return f"{self.user.username} - {self.quiz.module.title} (Score: {self.score}%)"


class QuizAnswer(models.Model):
    """Records student's answer to a specific quiz question."""
    attempt = models.ForeignKey(ModuleQuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(QuizOption, on_delete=models.SET_NULL, null=True, blank=True, help_text='The option the student selected')
    is_correct = models.BooleanField(default=False)
    points_earned = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"{self.attempt.user.username} - Q{self.question.order + 1}"


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


class ActivationFee(models.Model):
    """Admin-configurable activation fees.

    - type: 'exam' (global exam unlock) or 'interview' (per-subject unlock)
    - exam_identifier: optional identifier (could be numeric id or slug stored as text)
    - subject_id: optional subject id (for interview subject fees)
    - currency: ISO code, default 'NGN'
    - amount: decimal fee
    """
    TYPE_EXAM = 'exam'
    TYPE_INTERVIEW = 'interview'
    TYPE_ACCOUNT = 'account'
    TYPE_CHOICES = [
        (TYPE_EXAM, 'Exam (global)'),
        (TYPE_INTERVIEW, 'Interview Subject'),
        (TYPE_ACCOUNT, 'Account Activation'),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_EXAM)
    exam_identifier = models.CharField(max_length=255, blank=True, null=True, help_text='Exam id or slug for which this fee applies')
    subject_id = models.IntegerField(blank=True, null=True, help_text='Subject id (for interview subjects)')
    # For account activation fees, specify which role this fee applies to (tutor or institution)
    ACCOUNT_ROLE_TUTOR = 'tutor'
    ACCOUNT_ROLE_INSTITUTION = 'institution'
    ACCOUNT_ROLE_CHOICES = [
        (ACCOUNT_ROLE_TUTOR, 'Tutor'),
        (ACCOUNT_ROLE_INSTITUTION, 'Institution'),
    ]
    account_role = models.CharField(max_length=32, choices=ACCOUNT_ROLE_CHOICES, blank=True, null=True, help_text='Role this account activation fee applies to')
    currency = models.CharField(max_length=8, default='NGN')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='activation_fee_updates')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        if self.type == self.TYPE_INTERVIEW and self.subject_id:
            return f"Interview Subject Fee {self.subject_id} - {self.currency} {self.amount}"
        if self.type == self.TYPE_ACCOUNT and self.account_role:
            return f"Account Activation Fee ({self.account_role}) - {self.currency} {self.amount}"
        if self.exam_identifier:
            return f"Exam Fee {self.exam_identifier} - {self.currency} {self.amount}"
        return f"Activation Fee {self.currency} {self.amount}"


class ActivationUnlock(models.Model):
    """Records which users have unlocked specific exams or interview subjects via payment.
    
    For exam unlocks: stores up to 5 selected subjects via the selected_exam_subjects M2M.
    For interview subject unlocks: uses the legacy subject_id field.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activations')
    exam_identifier = models.CharField(max_length=255, blank=True, null=True, help_text='Exam id or slug')
    subject_id = models.IntegerField(blank=True, null=True, help_text='Legacy field for interview subject unlocks')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='activations')
    activated_at = models.DateTimeField(auto_now_add=True)
    
    # For CBT exam unlocks: store selected subjects (max 5)
    selected_exam_subjects = models.ManyToManyField('cbt.Subject', blank=True, related_name='student_unlocks', help_text='Selected subjects for CBT exam (max 5)')

    class Meta:
        unique_together = (('user', 'exam_identifier'),)  # One unlock per user per exam (subjects tracked in M2M)
        indexes = [
            models.Index(fields=['user', 'exam_identifier']),
            models.Index(fields=['user', 'subject_id']),
        ]

    def clean(self):
        """Validate max 5 subjects selected for exam unlocks."""
        if self.exam_identifier and self.selected_exam_subjects.count() > 5:
            raise ValueError('Maximum 5 subjects can be selected for an exam unlock')

    def __str__(self):
        if self.subject_id:
            return f"{self.user.username} unlocked interview subject {self.subject_id}"
        if self.exam_identifier:
            subjects = list(self.selected_exam_subjects.values_list('name', flat=True))
            return f"{self.user.username} unlocked {self.exam_identifier}: {', '.join(subjects)}"
        return f"{self.user.username} activation unlock"
    
    def get_selected_subjects(self):
        """Get list of selected subjects for this exam unlock."""
        return list(self.selected_exam_subjects.values('id', 'name', 'exam_id'))


class GospelVideo(models.Model):
    """Gospel video managed by master admin to be displayed to all platform users."""
    youtube_url = models.URLField(max_length=512, help_text='YouTube video URL')
    scheduled_time = models.TimeField(
        help_text='Time of day (HH:MM) when video should pop up on user dashboards'
    )
    title = models.CharField(max_length=255, default='Gospel Message', blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Gospel Video - {self.title} ({self.scheduled_time})"

    @staticmethod
    def get_active():
        """Get the currently active gospel video, or None."""
        return GospelVideo.objects.filter(is_active=True).order_by('-updated_at').first()


class VerificationDocument(models.Model):
    """Documents submitted by institutions for verification."""
    
    DOCUMENT_TYPE_CHOICES = [
        ('business_registration', 'Business Registration Document'),
        ('tax_id', 'Tax ID/Certificate'),
        ('ownership_certificate', 'Ownership Certificate'),
        ('accreditation', 'Accreditation Certificate'),
        ('establishment_proof', 'Proof of Establishment'),
        ('director_id', 'Director/Owner ID'),
        ('address_proof', 'Address Proof'),
        ('other', 'Other Document'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name='verification_documents'
    )
    # Link to the compliance submission folder
    submission = models.ForeignKey(
        'ComplianceSubmission',
        on_delete=models.CASCADE,
        related_name='institution_documents',
        null=True,
        blank=True,
        help_text="Compliance submission folder this document belongs to"
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    document_file = models.CharField(
        max_length=512,
        help_text="URL to uploaded document (PDF, image, etc.)"
    )
    document_name = models.CharField(max_length=255, help_text="Original filename")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_documents'
    )
    review_notes = models.TextField(blank=True, help_text="Admin notes on the document")
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Verification Document'
        verbose_name_plural = 'Verification Documents'
    
    def __str__(self):
        return f"{self.institution.name} - {self.get_document_type_display()}"


class TutorVerificationDocument(models.Model):
    """Documents submitted by tutors for verification."""
    
    DOCUMENT_TYPE_CHOICES = [
        ('id_card', 'National ID / Passport'),
        ('qualification', 'Educational Qualification'),
        ('teaching_certificate', 'Teaching Certificate'),
        ('experience_proof', 'Experience Reference'),
        ('address_proof', 'Address Proof'),
        ('other', 'Other Document'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='verification_documents'
    )
    # Link to the compliance submission folder
    submission = models.ForeignKey(
        'ComplianceSubmission',
        on_delete=models.CASCADE,
        related_name='tutor_documents',
        null=True,
        blank=True,
        help_text="Compliance submission folder this document belongs to"
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    document_file = models.CharField(
        max_length=512,
        help_text="URL to uploaded document (PDF, image, etc.)"
    )
    document_name = models.CharField(max_length=255, help_text="Original filename")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_tutor_documents'
    )
    review_notes = models.TextField(blank=True, help_text="Admin notes on the document")
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Tutor Verification Document'
        verbose_name_plural = 'Tutor Verification Documents'
    
    def __str__(self):
        return f"{self.tutor.username} - {self.get_document_type_display()}"


class ComplianceSubmission(models.Model):
    """
    Container for a batch of compliance documents submitted by a tutor or institution.
    This groups multiple documents into a single submission folder that can be reviewed together.
    """
    
    ENTITY_TYPE_TUTOR = 'tutor'
    ENTITY_TYPE_INSTITUTION = 'institution'
    
    ENTITY_TYPE_CHOICES = [
        (ENTITY_TYPE_TUTOR, 'Tutor'),
        (ENTITY_TYPE_INSTITUTION, 'Institution'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
    # Submission identity
    submission_id = models.CharField(max_length=100, unique=True, help_text="Unique batch ID for this submission")
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES)
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='compliance_submissions'
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='compliance_submissions'
    )
    
    # Contact information
    contact_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    comments = models.TextField(blank=True, help_text="Submission comments from the user")
    
    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_compliance_submissions'
    )
    review_notes = models.TextField(blank=True, help_text="Admin notes on the submission")
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Compliance Submission'
        verbose_name_plural = 'Compliance Submissions'
        unique_together = [('entity_type', 'tutor', 'submitted_at')]
    
    def __str__(self):
        entity = self.tutor.username if self.tutor else self.institution.name
        return f"{entity} - {self.submission_id}"
    
    def get_all_documents(self):
        """
        Get all documents in this submission, whether from tutor or institution.
        Returns a combined queryset of both types.
        """
        from django.db.models import Q
        if self.entity_type == self.ENTITY_TYPE_TUTOR:
            return self.tutor_documents.all()
        else:
            return self.institution_documents.all()


class LegalDocument(models.Model):
    """Legal/agreement documents that can be downloaded by institutions and tutors."""
    
    DOCUMENT_TYPE_CHOICES = [
        ('terms_of_service', 'Terms of Service'),
        ('creator_agreement', 'Creator Agreement'),
        ('data_privacy', 'Data Privacy Policy'),
        ('intellectual_property', 'Intellectual Property Agreement'),
        ('payment_terms', 'Payment Terms & Conditions'),
        ('code_of_conduct', 'Code of Conduct'),
        ('other', 'Other'),
    ]
    
    RECIPIENT_TYPE_CHOICES = [
        ('all', 'All Users'),
        ('specific', 'Specific Recipients'),
    ]
    
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    document_file = models.CharField(
        max_length=512,
        help_text="URL to the PDF/document file"
    )
    version = models.CharField(max_length=20, default='1.0')
    is_active = models.BooleanField(default=True)
    
    # Recipient targeting
    recipient_type = models.CharField(
        max_length=20,
        choices=RECIPIENT_TYPE_CHOICES,
        default='all',
        help_text="Whether to send to all users or specific recipients"
    )
    tutor_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='legal_documents_assigned_as_tutor',
        help_text="Tutors who should receive this document"
    )
    institution_recipients = models.ManyToManyField(
        'Institution',
        blank=True,
        related_name='legal_documents_assigned',
        help_text="Institutions who should receive this document"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this document was assigned to specific recipients"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Legal Document'
        verbose_name_plural = 'Legal Documents'
    
    def __str__(self):
        return f"{self.title} (v{self.version})"
