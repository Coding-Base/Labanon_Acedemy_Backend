from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from .models import Exam, Subject, Question, Choice, ExamAttempt, StudentAnswer
from .admin_views import bulk_upload_questions_admin


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'time_limit_minutes', 'subject_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['title', 'slug', 'description']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description')
        }),
        ('Settings', {
            'fields': ('time_limit_minutes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def subject_count(self, obj):
        count = obj.subjects.count()
        return format_html(
            '<span style="background-color: #417690; color: white; padding: 5px 10px; border-radius: 3px;">{}</span>',
            count
        )
    subject_count.short_description = 'Subjects'


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'exam', 'question_count', 'created_at']
    list_filter = ['exam', 'created_at']
    search_fields = ['name', 'description', 'exam__title']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Subject Information', {
            'fields': ('exam', 'name', 'description')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def question_count(self, obj):
        count = obj.questions.count()
        return format_html(
            '<span style="background-color: #68a357; color: white; padding: 5px 10px; border-radius: 3px;">{}</span>',
            count
        )
    question_count.short_description = 'Questions'


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4
    fields = ['text', 'is_correct']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text_preview', 'subject', 'year', 'choice_count', 'creator', 'has_image']
    list_filter = ['subject__exam', 'subject', 'year']
    search_fields = ['text', 'subject__name', 'subject__exam__title']
    readonly_fields = ['created_at', 'updated_at', 'choice_count_display']
    inlines = [ChoiceInline]

    fieldsets = (
        ('Question Information', {
            'fields': ('subject', 'text', 'image', 'year', 'creator')
        }),
        ('Statistics', {
            'fields': ('choice_count_display',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def text_preview(self, obj):
        return obj.text[:80] if len(obj.text) > 80 else obj.text
    text_preview.short_description = 'Question'

    def choice_count(self, obj):
        count = obj.choices.count()
        return format_html(
            '<span style="background-color: #f39c12; color: white; padding: 5px 10px; border-radius: 3px;">{}</span>',
            count
        )
    choice_count.short_description = 'Choices'

    def choice_count_display(self, obj):
        return obj.choices.count()
    choice_count_display.short_description = 'Total Choices'

    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Image'


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ['text', 'question_preview', 'is_correct_status']
    list_filter = ['is_correct', 'question__subject__exam']
    search_fields = ['text', 'question__text']
    readonly_fields = []

    fieldsets = (
        ('Choice Information', {
            'fields': ('question', 'text', 'is_correct')
        }),
    )

    def question_preview(self, obj):
        text = obj.question.text[:60]
        return f"{text}..." if len(obj.question.text) > 60 else text
    question_preview.short_description = 'Question'

    def is_correct_status(self, obj):
        if obj.is_correct:
            return format_html(
                '<span style="background-color: #27ae60; color: white; padding: 5px 10px; border-radius: 3px;">✓ Correct</span>'
            )
        return format_html(
            '<span style="background-color: #e74c3c; color: white; padding: 5px 10px; border-radius: 3px;">✗ Incorrect</span>'
        )
    is_correct_status.short_description = 'Status'


class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ['question', 'selected_choice', 'is_correct', 'answered_at']
    can_delete = False


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'exam', 'subject_name', 'score_display', 'submitted_at', 'time_taken']
    list_filter = ['exam', 'subject', 'is_submitted', 'started_at']
    search_fields = ['user__username', 'exam__title', 'subject__name']
    readonly_fields = ['user', 'exam', 'subject', 'started_at', 'submitted_at', 'is_submitted', 'score', 'time_taken_seconds']
    inlines = [StudentAnswerInline]

    fieldsets = (
        ('Attempt Information', {
            'fields': ('user', 'exam', 'subject', 'num_questions', 'time_limit_minutes')
        }),
        ('Performance', {
            'fields': ('score', 'is_submitted')
        }),
        ('Timeline', {
            'fields': ('started_at', 'submitted_at', 'time_taken_seconds')
        }),
    )

    def subject_name(self, obj):
        return obj.subject.name if obj.subject else 'N/A'
    subject_name.short_description = 'Subject'

    def time_taken(self, obj):
        if obj.time_taken_seconds:
            mins = obj.time_taken_seconds // 60
            secs = obj.time_taken_seconds % 60
            return f"{mins}m {secs}s"
        return "N/A"
    time_taken.short_description = 'Time Taken'

    def score_display(self, obj):
        if not obj.is_submitted or obj.score is None:
            return format_html(
                '<span style="background-color: #95a5a6; color: white; padding: 5px 10px; border-radius: 3px;">Not Submitted</span>'
            )
        percentage = round((obj.score / obj.num_questions) * 100, 2) if obj.num_questions > 0 else 0
        color = '#27ae60' if percentage >= 60 else '#e74c3c'
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 5px 10px; border-radius: 3px;">{obj.score}/{obj.num_questions} ({percentage}%)</span>'
        )
    score_display.short_description = 'Score'


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ['question_preview', 'exam_info', 'user', 'is_correct_status', 'answered_at']
    list_filter = ['is_correct', 'exam_attempt__exam', 'answered_at']
    search_fields = ['question__text', 'exam_attempt__user__username']
    readonly_fields = ['exam_attempt', 'question', 'answered_at']

    fieldsets = (
        ('Answer Information', {
            'fields': ('exam_attempt', 'question', 'selected_choice', 'is_correct')
        }),
        ('Timestamp', {
            'fields': ('answered_at',),
            'classes': ('collapse',)
        }),
    )

    def question_preview(self, obj):
        text = obj.question.text[:60]
        return f"{text}..." if len(obj.question.text) > 60 else text
    question_preview.short_description = 'Question'

    def exam_info(self, obj):
        return f"{obj.exam_attempt.exam.title} - {obj.exam_attempt.subject.name}"
    exam_info.short_description = 'Exam - Subject'

    def user(self, obj):
        return obj.exam_attempt.user.username

    def is_correct_status(self, obj):
        if obj.is_correct is None:
            return format_html(
                '<span style="background-color: #95a5a6; color: white; padding: 5px 10px; border-radius: 3px;">Not Answered</span>'
            )
        if obj.is_correct:
            return format_html(
                '<span style="background-color: #27ae60; color: white; padding: 5px 10px; border-radius: 3px;">✓ Correct</span>'
            )
        return format_html(
            '<span style="background-color: #e74c3c; color: white; padding: 5px 10px; border-radius: 3px;">✗ Wrong</span>'
        )
    is_correct_status.short_description = 'Status'


# Customize admin site
admin.site.site_header = 'LightHub Academy Administration'
admin.site.site_title = 'Admin'
# Add custom URLs to admin site
def get_admin_urls():
    urls = [path('cbt/bulk-upload/', bulk_upload_questions_admin, name='cbt_bulk_upload')]
    return urls

# Patch the admin site to include our custom URLs
original_get_urls = admin.site.get_urls

def new_get_urls():
    custom_urls = [path('cbt/bulk-upload/', bulk_upload_questions_admin, name='cbt_bulk_upload')]
    return custom_urls + original_get_urls()

admin.site.get_urls = new_get_urls