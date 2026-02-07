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
    """Records which users have unlocked specific exams or interview subjects via payment."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activations')
    exam_identifier = models.CharField(max_length=255, blank=True, null=True, help_text='Exam id or slug')
    subject_id = models.IntegerField(blank=True, null=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='activations')
    activated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('user', 'exam_identifier', 'subject_id'),)

    def __str__(self):
        if self.subject_id:
            return f"{self.user.username} unlocked subject {self.subject_id}"
        return f"{self.user.username} unlocked exam {self.exam_identifier}"


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