# backend/lessons/serializers.py
from rest_framework import serializers
from .models import Subject, Topic, LessonContent, StudentLessonProgress, LessonSearch


class SubjectSerializer(serializers.ModelSerializer):
    topics_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Subject
        fields = ['id', 'name', 'description', 'is_custom', 'created_at', 'topics_count']
        read_only_fields = ['id', 'created_at']
    
    def get_topics_count(self, obj):
        return obj.topics.count()


class TopicSerializer(serializers.ModelSerializer):
    lessons_count = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'subject', 'subject_name', 'name', 'description', 'is_custom', 'order', 'created_at', 'lessons_count']
        read_only_fields = ['id', 'created_at']
    
    def get_lessons_count(self, obj):
        return obj.lessons.filter(is_published=True).count()


class LessonContentSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    subject_name = serializers.CharField(source='topic.subject.name', read_only=True)
    linked_topics_data = serializers.SerializerMethodField()
    
    class Meta:
        model = LessonContent
        fields = [
            'id', 'topic', 'topic_name', 'subject_name', 'title', 'content',
            'publisher_name', 'publisher_title', 'published_date',
            'linked_topics', 'linked_topics_data', 'embedded_images',
            'slug', 'meta_description', 'meta_keywords', 'og_image',
            'is_published', 'order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'published_date', 'created_at', 'updated_at']
    
    def get_linked_topics_data(self, obj):
        """Return full topic data for linked topics"""
        return [
            {'id': t.id, 'name': t.name, 'subject_name': t.subject.name}
            for t in obj.linked_topics.all()
        ]


class StudentLessonProgressSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    topic_name = serializers.CharField(source='lesson.topic.name', read_only=True)
    
    class Meta:
        model = StudentLessonProgress
        fields = [
            'id', 'student', 'lesson', 'lesson_title', 'topic_name',
            'is_viewed', 'is_completed', 'time_spent_seconds',
            'first_viewed_at', 'completed_at', 'updated_at'
        ]
        read_only_fields = ['id', 'student', 'first_viewed_at', 'completed_at', 'updated_at']


class LessonSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonSearch
        fields = ['id', 'student', 'search_query', 'results_count', 'created_at']
        read_only_fields = ['id', 'student', 'created_at']


class SubjectFolderSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying a subject with all its topics (folder view)
    """
    topics = TopicSerializer(many=True, read_only=True)
    
    class Meta:
        model = Subject
        fields = ['id', 'name', 'description', 'is_custom', 'created_at', 'topics']
        read_only_fields = ['id', 'created_at']


class TopicDetailSerializer(serializers.ModelSerializer):
    """
    Detailed topic view with all its lessons
    """
    lessons = LessonContentSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'subject', 'subject_name', 'name', 'description', 'order', 'created_at', 'lessons']
        read_only_fields = ['id', 'created_at']
