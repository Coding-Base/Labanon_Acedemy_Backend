from django.db import models
from django.conf import settings
from django.utils import timezone


LIBRARY_STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('published', 'Published'),
    ('scheduled', 'Scheduled'),
    ('archived', 'Archived'),
]


class Country(models.Model):
    """A reusable discovery tag for folders in the student exam library."""
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=8, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    flag_image = models.ImageField(upload_to='cbt_countries/', blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=LIBRARY_STATUS_CHOICES, default='published')
    is_visible = models.BooleanField(default=True)
    available_from = models.DateTimeField(blank=True, null=True)
    available_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class ExamFolder(models.Model):
    """A reusable library container for linked exams, subjects, and subfolders."""
    # Kept during the migration window so existing links and integrations remain valid.
    # New code uses country_tags, not this legacy single-country field.
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, related_name='legacy_folders', null=True, blank=True
    )
    country_tags = models.ManyToManyField(Country, related_name='tagged_folders', blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children'
    )
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=80, blank=True, default='folder')
    cover_image = models.ImageField(upload_to='cbt_folders/', blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=LIBRARY_STATUS_CHOICES, default='published')
    status_before_archive = models.CharField(max_length=20, choices=LIBRARY_STATUS_CHOICES, blank=True)
    is_visible = models.BooleanField(default=True)
    available_from = models.DateTimeField(blank=True, null=True)
    available_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['parent', 'slug'], name='unique_folder_slug_per_parent')
        ]

    def __str__(self):
        return self.name


class Exam(models.Model):
    """Represents an exam (e.g., JAMB, NECO, WAEC)"""
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    folder = models.ForeignKey(
        ExamFolder, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams'
    )
    institution = models.CharField(max_length=255, blank=True)
    provider = models.CharField(max_length=255, blank=True)
    exam_type = models.CharField(max_length=120, blank=True)
    year = models.CharField(max_length=10, blank=True)
    difficulty = models.CharField(max_length=40, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=LIBRARY_STATUS_CHOICES, default='published')
    is_visible = models.BooleanField(default=True)
    available_from = models.DateTimeField(blank=True, null=True)
    available_until = models.DateTimeField(blank=True, null=True)
    time_limit_minutes = models.PositiveIntegerField(default=120, help_text="Time limit in minutes")
    free_trial_attempts = models.PositiveIntegerField(
        default=5,
        help_text="Number of free trial attempts allowed per student for this exam"
    )
    free_trial_questions_per_subject = models.PositiveIntegerField(
        default=20,
        help_text="Max questions per subject in free trial mode (0 = no limit)"
    )
    subject_select_limit = models.PositiveIntegerField(
        default=0,
        help_text="Number of subjects a user can select during registration. 0 means they unlock all subjects (no selection)."
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'title']

    def __str__(self):
        return self.title


class Subject(models.Model):
    """Represents a subject under an exam (e.g., Mathematics, Chemistry, Physics)"""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['exam', 'name']
        unique_together = ('exam', 'name')

    def __str__(self):
        return f"{self.exam.title} - {self.name}"


class FolderExam(models.Model):
    """A discovery-only placement of an exam in a library folder."""
    folder = models.ForeignKey(ExamFolder, on_delete=models.CASCADE, related_name='exam_links')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='folder_links')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sort_order', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['folder', 'exam'], name='unique_folder_exam_link')
        ]


class FolderSubject(models.Model):
    """A discovery-only placement of one subject in a library folder."""
    folder = models.ForeignKey(ExamFolder, on_delete=models.CASCADE, related_name='subject_links')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='folder_links')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sort_order', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['folder', 'subject'], name='unique_folder_subject_link')
        ]


class Question(models.Model):
    """Represents a question within a subject"""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    image = models.ImageField(upload_to='cbt_questions/', blank=True, null=True)
    year = models.CharField(max_length=10, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.text[:50]


class QuestionAssignment(models.Model):
    """Optional secondary placement of a bank question in another subject."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='question_assignments')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sort_order', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['question', 'subject'], name='unique_question_subject_assignment')
        ]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.question.id} - {self.text}"





class ExamAttempt(models.Model):
    """Represents a student's attempt at an exam (single or multi-subject)"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attempts', null=True, blank=True)
    test_name = models.CharField(max_length=255, null=True, blank=True, help_text="Custom name for multi-subject exams")
    num_questions = models.PositiveIntegerField()
    time_limit_minutes = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    time_taken_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)
    is_trial_attempt = models.BooleanField(default=False, help_text="Whether this is a free trial attempt (max 5 per exam)")

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        display_name = self.test_name or (self.subject.name if self.subject else 'Multi-Subject')
        trial_label = " [TRIAL]" if self.is_trial_attempt else ""
        return f"{self.user.username} - {self.exam.title} - {display_name}{trial_label}"


class StudentAnswer(models.Model):
    """Stores a student's answer to a specific question in an exam attempt"""
    exam_attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='student_answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='student_answers', null=True, blank=True, help_text="Subject of the question - auto-populated from question")
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['question']
        unique_together = ('exam_attempt', 'question')

    def __str__(self):
        return f"{self.exam_attempt.user.username} - Q{self.question.id} - {self.subject.name if self.subject else 'N/A'}"
    
    def save(self, *args, **kwargs):
        """Auto-populate subject from question on save"""
        if not self.subject and self.question:
            self.subject = self.question.subject
        super().save(*args, **kwargs)
