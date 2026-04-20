# backend/lessons/admin.py
from django.contrib import admin
from .models import Subject, Topic, LessonContent, StudentLessonProgress, LessonSearch


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_custom', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_custom', 'created_at')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'is_custom', 'order', 'created_at')
    search_fields = ('name', 'subject__name')
    list_filter = ('subject', 'is_custom', 'created_at')
    ordering = ('subject', 'order')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(LessonContent)
class LessonContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'publisher_name', 'is_published', 'order', 'published_date')
    search_fields = ('title', 'topic__name', 'topic__subject__name')
    list_filter = ('is_published', 'topic__subject', 'published_date')
    filter_horizontal = ('linked_topics',)
    readonly_fields = ('id', 'published_date', 'created_at', 'updated_at')
    fieldsets = (
        ('Content', {
            'fields': ('topic', 'title', 'content', 'embedded_images')
        }),
        ('Publisher Info', {
            'fields': ('publisher_name', 'publisher_title', 'published_date')
        }),
        ('Related Content', {
            'fields': ('linked_topics',)
        }),
        ('Publishing', {
            'fields': ('is_published', 'order')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudentLessonProgress)
class StudentLessonProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'is_viewed', 'is_completed', 'updated_at')
    search_fields = ('student__username', 'lesson__title')
    list_filter = ('is_viewed', 'is_completed', 'updated_at')
    readonly_fields = ('id', 'first_viewed_at', 'completed_at', 'updated_at')


@admin.register(LessonSearch)
class LessonSearchAdmin(admin.ModelAdmin):
    list_display = ('student', 'search_query', 'results_count', 'created_at')
    search_fields = ('student__username', 'search_query')
    list_filter = ('created_at',)
    readonly_fields = ('id', 'created_at')
