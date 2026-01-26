from django.db import models
from django.conf import settings
from django.utils import timezone


class Exam(models.Model):
    """Represents an exam (e.g., JAMB, NECO, WAEC)"""
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(default=120, help_text="Time limit in minutes")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

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


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.question.id} - {self.text}"





class ExamAttempt(models.Model):
    """Represents a student's attempt at an exam"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attempts', null=True, blank=True)
    num_questions = models.PositiveIntegerField()
    time_limit_minutes = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    time_taken_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} - {self.subject.name if self.subject else 'N/A'}"


class StudentAnswer(models.Model):
    """Stores a student's answer to a specific question in an exam attempt"""
    exam_attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='student_answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['question']
        unique_together = ('exam_attempt', 'question')

    def __str__(self):
        return f"{self.exam_attempt.user.username} - Q{self.question.id}"
