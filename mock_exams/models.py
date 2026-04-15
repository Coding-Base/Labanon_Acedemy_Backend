from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
import json


class CustomMockExam(models.Model):
    """
    Main Mock Exam entity - completely separate from CBT Exam model.
    Represents a custom mock exam created by master admin.
    """
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('mixed', 'Mixed'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_mock_exams')
    title = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="Exam instructions shown to students")
    
    # Exam configuration
    total_duration_minutes = models.IntegerField(default=120, validators=[MinValueValidator(5), MaxValueValidator(480)])
    total_marks = models.IntegerField(default=100, validators=[MinValueValidator(1)])
    passing_marks = models.IntegerField(default=50, validators=[MinValueValidator(0)])
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='medium')
    
    # Status & Visibility
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # External Platform Integration
    is_streaming = models.BooleanField(default=False, help_text="True if exam is streamed from external platform")
    external_platform = models.ForeignKey('MockExamExternalPlatform', on_delete=models.SET_NULL, null=True, blank=True, related_name='mock_exams')
    external_exam_id = models.CharField(max_length=255, blank=True, null=True, help_text="ID of exam on external platform")
    external_exam_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL to stream exam from external platform")
    
    # Metadata
    subject_area = models.CharField(max_length=255, blank=True, help_text="e.g., JAMB Biology, WAEC Mathematics")
    exam_year = models.IntegerField(blank=True, null=True, help_text="Year the exam is from/for")
    language = models.CharField(max_length=50, default='English')
    
    # Tracking
    total_attempts = models.IntegerField(default=0)
    avg_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Average score of all attempts")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin', '-created_at']),
            models.Index(fields=['is_published', '-created_at']),
            models.Index(fields=['external_platform']),
        ]
        verbose_name = 'Custom Mock Exam'
        verbose_name_plural = 'Custom Mock Exams'
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    def get_subject_count(self):
        """Get number of subjects in this exam"""
        return self.subjects.count()
    
    def get_total_questions(self):
        """Get total questions across all subjects"""
        return sum(subj.get_question_count() for subj in self.subjects.all())


class MockExamSubject(models.Model):
    """
    Subjects within a CustomMockExam - distinct from CBT Subject.
    """
    mock_exam = models.ForeignKey(CustomMockExam, on_delete=models.CASCADE, related_name='subjects')
    subject_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject_icon = models.URLField(blank=True, null=True, help_text="URL to subject icon/image")
    
    # Question distribution
    num_questions = models.IntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(200)])
    time_allocation_minutes = models.IntegerField(default=20, validators=[MinValueValidator(1)])
    marks_per_question = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    
    order = models.IntegerField(default=0, help_text="Display order in exam")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'id']
        unique_together = ('mock_exam', 'subject_name')
        indexes = [
            models.Index(fields=['mock_exam', 'order']),
        ]
        verbose_name = 'Mock Exam Subject'
        verbose_name_plural = 'Mock Exam Subjects'
    
    def __str__(self):
        return f"{self.mock_exam.title} - {self.subject_name}"
    
    def get_question_count(self):
        """Get total questions in this subject"""
        return self.questions.count()
    
    def get_total_marks(self):
        """Get total marks for this subject"""
        return self.num_questions * self.marks_per_question


class MockExamQuestion(models.Model):
    """
    Questions in mock exam - distinct from CBT Question.
    """
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple Choice'),
        ('radio', 'Radio Button'),
        ('checkbox', 'Checkboxes'),
        ('true_false', 'True/False'),
        ('fill_blank', 'Fill in the Blank'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
        ('matching', 'Matching'),
        ('ordering', 'Ordering'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    subject = models.ForeignKey(MockExamSubject, on_delete=models.CASCADE, related_name='questions')
    
    # Question content
    question_text = models.TextField()
    question_image = models.ImageField(upload_to='mock_exams/questions/', blank=True, null=True, help_text="Question image/diagram")
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES, default='multiple_choice')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='medium')
    
    # Marks
    marks = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    negative_marks = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Penalty for wrong answer")
    
    # Metadata
    explanation = models.TextField(blank=True, help_text="Explanation shown after exam")
    explanation_image = models.ImageField(upload_to='mock_exams/explanations/', blank=True, null=True)
    
    order = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=True)
    # Atomic counter for assigning option order values to avoid race conditions
    option_counter = models.IntegerField(default=0, help_text="Next option order index for this question")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['subject', 'order']),
            models.Index(fields=['difficulty']),
        ]
        verbose_name = 'Mock Exam Question'
        verbose_name_plural = 'Mock Exam Questions'
    
    def __str__(self):
        return f"Q: {self.question_text[:50]}... (Type: {self.get_question_type_display()})"
    
    def get_option_count(self):
        return self.options.count()


class MockExamOption(models.Model):
    """
    Answer options for mock exam questions.
    """
    question = models.ForeignKey(MockExamQuestion, on_delete=models.CASCADE, related_name='options')
    
    option_text = models.TextField()
    option_image = models.ImageField(upload_to='mock_exams/options/', blank=True, null=True, help_text="Option image/diagram")
    option_letter = models.CharField(max_length=2, default='A', help_text="A, B, C, D, E, etc.")
    
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField(blank=True)
    
    order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'id']
        unique_together = ('question', 'order')
        verbose_name = 'Mock Exam Option'
        verbose_name_plural = 'Mock Exam Options'
    
    def __str__(self):
        return f"{self.option_letter}. {self.option_text[:40]}..."


class MockExamFee(models.Model):
    """
    Fee configuration for mock exams.
    """
    mock_exam = models.OneToOneField(CustomMockExam, on_delete=models.CASCADE, related_name='fee')
    
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="0 = Free exam")
    currency = models.CharField(max_length=3, default='NGN')
    
    # Discount/Promo
    discount_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    promo_code = models.CharField(max_length=50, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Mock Exam Fee'
        verbose_name_plural = 'Mock Exam Fees'
    
    def __str__(self):
        return f"{self.mock_exam.title} - {self.currency} {self.fee_amount}"
    
    def get_final_amount(self):
        """Calculate final amount after discount"""
        discount = (self.fee_amount * self.discount_percentage) / 100
        return self.fee_amount - discount


class MockExamAttempt(models.Model):
    """
    Records student's attempt/session of a mock exam.
    """
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mock_exam_attempts')
    mock_exam = models.ForeignKey(CustomMockExam, on_delete=models.CASCADE, related_name='attempts')
    
    # Session tracking
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.IntegerField(default=0)
    
    # Results
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    is_submitted = models.BooleanField(default=False)
    total_marks = models.IntegerField(default=0)
    obtained_marks = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grade = models.CharField(max_length=2, blank=True, help_text="A, B, C, D, F, etc.")
    passed = models.BooleanField(default=False)
    
    # Metadata
    device_type = models.CharField(max_length=50, blank=True, help_text="Desktop, Mobile, Tablet")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['user', '-start_time']),
            models.Index(fields=['mock_exam', '-start_time']),
            models.Index(fields=['status']),
        ]
        verbose_name = 'Mock Exam Attempt'
        verbose_name_plural = 'Mock Exam Attempts'
    
    def __str__(self):
        return f"{self.user.username} - {self.mock_exam.title} ({self.get_status_display()})"


class MockExamResult(models.Model):
    """
    Individual question result for each attempt.
    """
    attempt = models.ForeignKey(MockExamAttempt, on_delete=models.CASCADE, related_name='results')
    question = models.ForeignKey(MockExamQuestion, on_delete=models.CASCADE)
    
    # Student's answer
    selected_option = models.ForeignKey(MockExamOption, on_delete=models.SET_NULL, null=True, blank=True)
    student_answer_text = models.TextField(blank=True, help_text="For essay/short answer questions")
    
    # Scoring
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    
    # Timing
    time_spent_seconds = models.IntegerField(default=0)
    attempted = models.BooleanField(default=False, help_text="Whether student attempted or skipped this question")
    marked_for_review = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['question__order']
        unique_together = ('attempt', 'question')
        indexes = [
            models.Index(fields=['attempt', 'question']),
        ]
        verbose_name = 'Mock Exam Result'
        verbose_name_plural = 'Mock Exam Results'
    
    def __str__(self):
        return f"{self.attempt.user.username} - Q{self.question.order} - {self.marks_obtained} marks"


class MockExamActivityLog(models.Model):
    """
    Audit log for admin activities on mock exams.
    """
    ACTION_CHOICES = [
        ('create_exam', 'Create Exam'),
        ('update_exam', 'Update Exam'),
        ('delete_exam', 'Delete Exam'),
        ('publish_exam', 'Publish Exam'),
        ('archive_exam', 'Archive Exam'),
        ('add_subject', 'Add Subject'),
        ('update_subject', 'Update Subject'),
        ('delete_subject', 'Delete Subject'),
        ('add_question', 'Add Question'),
        ('update_question', 'Update Question'),
        ('delete_question', 'Delete Question'),
        ('set_fee', 'Set Fee'),
        ('update_fee', 'Update Fee'),
        ('configure_platform', 'Configure External Platform'),
        ('sync_platform', 'Sync Platform Exams'),
    ]
    
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='mock_exam_activities')
    mock_exam = models.ForeignKey(CustomMockExam, on_delete=models.CASCADE, null=True, blank=True, related_name='activity_logs')
    
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    change_details = models.JSONField(default=dict, help_text="Detailed changes made")
    
    # Impact metrics
    affected_students = models.IntegerField(default=0, help_text="Number of students affected by this action")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin', '-created_at']),
            models.Index(fields=['mock_exam', '-created_at']),
            models.Index(fields=['action']),
        ]
        verbose_name = 'Mock Exam Activity Log'
        verbose_name_plural = 'Mock Exam Activity Logs'
    
    def __str__(self):
        return f"{self.admin.username} - {self.get_action_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class MockExamExternalPlatform(models.Model):
    """
    Configuration for external exam platforms.
    Allows pulling/streaming exams from JAMB, WAEC, etc.
    """
    PLATFORM_TYPES = [
        ('jamb', 'JAMB'),
        ('waec', 'WAEC'),
        ('neco', 'NECO'),
        ('custom_api', 'Custom API'),
        ('iframe', 'iFrame Embed'),
    ]
    
    platform_name = models.CharField(max_length=255, unique=True)
    platform_type = models.CharField(max_length=50, choices=PLATFORM_TYPES)
    description = models.TextField(blank=True)
    
    # Connection details
    platform_url = models.URLField(max_length=500)
    api_key = models.CharField(max_length=500, blank=True, help_text="API key for authentication")
    api_secret = models.CharField(max_length=500, blank=True, help_text="API secret for authentication")
    api_endpoint = models.URLField(max_length=500, blank=True, help_text="API endpoint URL")
    
    # Configuration
    is_active = models.BooleanField(default=True)
    sync_enabled = models.BooleanField(default=False, help_text="Allow syncing exams from this platform")
    last_sync_time = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    webhook_url = models.URLField(max_length=500, blank=True, help_text="Webhook URL for platform notifications")
    auth_headers = models.JSONField(default=dict, help_text="Custom headers for API requests")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['platform_name']
        indexes = [
            models.Index(fields=['is_active']),
        ]
        verbose_name = 'Mock Exam External Platform'
        verbose_name_plural = 'Mock Exam External Platforms'
    
    def __str__(self):
        return f"{self.platform_name} ({self.get_platform_type_display()})"
    
    def get_auth_headers(self):
        """Get authorization headers for API requests"""
        if self.auth_headers:
            return self.auth_headers
        
        # Default headers
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers


# ===== SIGNALS =====
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=MockExamQuestion)
def create_default_options(sender, instance, created, **kwargs):
    """
    Auto-create 4 default options (A, B, C, D) when a question is created.
    This replaces the need for dynamic option creation.
    """
    if created:
        # Create options A, B, C, D
        options_data = [
            ('A', 0),
            ('B', 1),
            ('C', 2),
            ('D', 3),
        ]
        
        for letter, order in options_data:
            MockExamOption.objects.create(
                question=instance,
                option_letter=letter,
                order=order,
                option_text='',  # Empty initially, user will fill it in
                is_correct=False
            )
