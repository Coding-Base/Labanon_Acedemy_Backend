# backend/lessons/models.py
# backend/lessons/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
import uuid


class Category(models.Model):
    """
    Admin-defined category for organizing subjects (e.g., Secondary, University, Professional).
    Replaces the hardcoded frontend keyword-matching logic.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#6B7280', help_text="Hex color code for UI display")
    order = models.PositiveIntegerField(default=0, help_text="Display order in filter tabs")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Subject(models.Model):
    """
    Main subject/category for lessons (e.g., Mathematics, Physics, English)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subjects', help_text="Admin-assigned category for this subject"
    )
    is_custom = models.BooleanField(default=False, help_text="Whether this was created by admin via custom input")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class LessonSubfolder(models.Model):
    """
    Department/subfolder under a subject/folder (e.g., Chemical Engineering under Engineering)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='subfolders')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_custom = models.BooleanField(default=False, help_text="Whether this was created by admin via custom input")
    order = models.PositiveIntegerField(default=0, help_text="Display order within subject")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['subject', 'order', 'name']
        unique_together = ('subject', 'name')

    def __str__(self):
        return f"{self.subject.name} - {self.name}"


class Topic(models.Model):
    """
    Topic/Area under a subject (e.g., 'Quadratic Equations' under Mathematics)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    subfolder = models.ForeignKey(LessonSubfolder, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_custom = models.BooleanField(default=False, help_text="Whether this was created by admin via custom input")
    order = models.PositiveIntegerField(default=0, help_text="Display order within subject")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['subject', 'subfolder', 'order', 'name']
        unique_together = ('subfolder', 'name')

    def save(self, *args, **kwargs):
        if self.subfolder_id:
            self.subject = self.subfolder.subject
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.name} - {self.subfolder.name} - {self.name}"


class LessonContent(models.Model):
    """
    Full lesson content tied to a topic, with support for rich text and images
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Rich HTML/text content with embedded images")
    
    # Publisher details
    publisher_name = models.CharField(max_length=255, blank=True)
    publisher_title = models.CharField(max_length=255, blank=True, help_text="e.g., 'Physics Teacher', 'Subject Expert'")
    published_date = models.DateTimeField(auto_now_add=True)
    
    # Linked topic - reference to other related topics in same subject
    linked_topics = models.ManyToManyField(Topic, blank=True, related_name='lessons_linked_to')
    
    # Images embedded in lesson (comma-separated URLs or stored paths)
    embedded_images = models.TextField(blank=True, help_text="JSON list of image URLs embedded in lesson")
    
    # SEO Fields
    slug = models.SlugField(unique=True, max_length=255, blank=True, help_text="URL-friendly identifier for SEO")
    meta_description = models.CharField(max_length=160, blank=True, help_text="SEO meta description (60-160 chars), displayed in search results")
    meta_keywords = models.CharField(max_length=255, blank=True, help_text="Comma-separated keywords for SEO")
    og_image = models.URLField(blank=True, default='', help_text="Open Graph image URL for social sharing")
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated lesson search tags")
    
    # Metadata
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['topic', 'order', 'created_at']

    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not provided"""
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.topic.name} - {self.title}"

    def get_linked_topics_display(self):
        """Return the names of linked topics"""
        return [t.name for t in self.linked_topics.all()]


class StudentLessonProgress(models.Model):
    """
    Track which lessons a student has viewed/completed
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(LessonContent, on_delete=models.CASCADE, related_name='student_progress')
    
    # Progress tracking
    is_viewed = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    
    # Timestamps
    first_viewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'lesson')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.student.username} - {self.lesson.topic.name}"


class LessonSearch(models.Model):
    """
    Track searches performed by students on lesson page (for analytics)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_searches')
    search_query = models.CharField(max_length=500)
    results_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} searched: {self.search_query}"
