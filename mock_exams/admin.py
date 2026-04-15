from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CustomMockExam, MockExamSubject, MockExamQuestion, MockExamOption,
    MockExamFee, MockExamAttempt, MockExamResult, MockExamActivityLog,
    MockExamExternalPlatform
)


@admin.register(CustomMockExam)
class CustomMockExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'admin', 'status', 'is_published', 'total_duration_minutes', 'total_marks', 'total_attempts', 'avg_score', 'created_at']
    list_filter = ['status', 'is_published', 'is_active', 'difficulty_level', 'created_at']
    search_fields = ['title', 'description', 'subject_area']
    readonly_fields = ['total_attempts', 'avg_score', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('admin', 'title', 'description', 'instructions')
        }),
        ('Configuration', {
            'fields': ('total_duration_minutes', 'total_marks', 'passing_marks', 'difficulty_level', 'language')
        }),
        ('Status & Publishing', {
            'fields': ('status', 'is_published', 'is_active')
        }),
        ('External Platform', {
            'fields': ('is_streaming', 'external_platform', 'external_exam_id', 'external_exam_url'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('subject_area', 'exam_year')
        }),
        ('Statistics', {
            'fields': ('total_attempts', 'avg_score', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ['-created_at']


@admin.register(MockExamSubject)
class MockExamSubjectAdmin(admin.ModelAdmin):
    list_display = ['subject_name', 'mock_exam', 'num_questions', 'time_allocation_minutes', 'marks_per_question', 'order']
    list_filter = ['mock_exam', 'time_allocation_minutes']
    search_fields = ['subject_name', 'mock_exam__title']
    ordering = ['mock_exam', 'order']


@admin.register(MockExamQuestion)
class MockExamQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_preview', 'subject', 'question_type', 'difficulty', 'marks', 'order']
    list_filter = ['question_type', 'difficulty', 'subject__mock_exam', 'created_at']
    search_fields = ['question_text', 'subject__subject_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['subject', 'order']
    
    def question_preview(self, obj):
        return obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
    question_preview.short_description = 'Question'


@admin.register(MockExamOption)
class MockExamOptionAdmin(admin.ModelAdmin):
    list_display = ['option_letter', 'option_text_preview', 'question_preview', 'is_correct']
    list_filter = ['is_correct', 'question__subject__mock_exam']
    search_fields = ['option_text', 'question__question_text']
    readonly_fields = ['created_at', 'updated_at']
    
    def option_text_preview(self, obj):
        return obj.option_text[:40] + '...' if len(obj.option_text) > 40 else obj.option_text
    option_text_preview.short_description = 'Option Text'
    
    def question_preview(self, obj):
        return obj.question.question_text[:40] + '...' if len(obj.question.question_text) > 40 else obj.question.question_text
    question_preview.short_description = 'Question'


@admin.register(MockExamFee)
class MockExamFeeAdmin(admin.ModelAdmin):
    list_display = ['mock_exam', 'fee_amount', 'currency', 'discount_percentage', 'final_amount_display']
    list_filter = ['currency', 'discount_percentage', 'created_at']
    search_fields = ['mock_exam__title']
    readonly_fields = ['created_at', 'updated_at']
    
    def final_amount_display(self, obj):
        return f"{obj.currency} {obj.get_final_amount()}"
    final_amount_display.short_description = 'Final Amount'


@admin.register(MockExamAttempt)
class MockExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'exam_title', 'start_time', 'status', 'obtained_marks', 'percentage', 'passed']
    list_filter = ['status', 'passed', 'start_time', 'mock_exam']
    search_fields = ['user__username', 'user__email', 'mock_exam__title']
    readonly_fields = ['start_time', 'end_time', 'created_at', 'updated_at']
    ordering = ['-start_time']
    
    def student_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    student_name.short_description = 'Student'
    
    def exam_title(self, obj):
        return obj.mock_exam.title
    exam_title.short_description = 'Exam'


@admin.register(MockExamResult)
class MockExamResultAdmin(admin.ModelAdmin):
    list_display = ['question_preview', 'attempt_detail', 'is_correct', 'marks_obtained', 'time_spent_seconds']
    list_filter = ['is_correct', 'attempted', 'attempt__mock_exam']
    search_fields = ['question__question_text', 'attempt__user__username']
    readonly_fields = ['created_at', 'updated_at']
    
    def question_preview(self, obj):
        return obj.question.question_text[:40] + '...' if len(obj.question.question_text) > 40 else obj.question.question_text
    question_preview.short_description = 'Question'
    
    def attempt_detail(self, obj):
        return f"{obj.attempt.user.username} - {obj.attempt.start_time.strftime('%Y-%m-%d %H:%M')}"
    attempt_detail.short_description = 'Attempt'


@admin.register(MockExamActivityLog)
class MockExamActivityLogAdmin(admin.ModelAdmin):
    list_display = ['admin_name', 'action_display', 'exam_title', 'affected_students', 'created_at']
    list_filter = ['action', 'created_at', 'admin']
    search_fields = ['admin__username', 'mock_exam__title', 'description']
    readonly_fields = ['created_at', 'change_details_display']
    ordering = ['-created_at']
    
    def admin_name(self, obj):
        return obj.admin.get_full_name() or obj.admin.username if obj.admin else 'System'
    admin_name.short_description = 'Admin'
    
    def action_display(self, obj):
        colors = {
            'create_exam': 'green',
            'update_exam': 'blue',
            'delete_exam': 'red',
            'publish_exam': 'darkgreen',
        }
        color = colors.get(obj.action, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_display.short_description = 'Action'
    
    def exam_title(self, obj):
        return obj.mock_exam.title if obj.mock_exam else 'N/A'
    exam_title.short_description = 'Exam'
    
    def change_details_display(self, obj):
        return format_html('<pre>{}</pre>', str(obj.change_details))
    change_details_display.short_description = 'Changes'


@admin.register(MockExamExternalPlatform)
class MockExamExternalPlatformAdmin(admin.ModelAdmin):
    list_display = ['platform_name', 'platform_type', 'is_active', 'sync_enabled', 'last_sync_time']
    list_filter = ['is_active', 'sync_enabled', 'platform_type']
    search_fields = ['platform_name', 'platform_url']
    readonly_fields = ['last_sync_time', 'created_at', 'updated_at']
    fieldsets = (
        ('Platform Information', {
            'fields': ('platform_name', 'platform_type', 'description')
        }),
        ('Connection Details', {
            'fields': ('platform_url', 'api_endpoint', 'api_key', 'api_secret')
        }),
        ('Configuration', {
            'fields': ('is_active', 'sync_enabled', 'webhook_url', 'auth_headers')
        }),
        ('Statistics', {
            'fields': ('last_sync_time', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
