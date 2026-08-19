# backend/lessons/serializers.py
from rest_framework import serializers
from .models import Category, Subject, LessonSubfolder, Topic, LessonContent, StudentLessonProgress, LessonSearch


class CategorySerializer(serializers.ModelSerializer):
    subjects_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'color', 'order', 'is_active', 'created_at', 'subjects_count']
        read_only_fields = ['id', 'created_at']

    def get_subjects_count(self, obj):
        return obj.subjects.count()


class SubjectSerializer(serializers.ModelSerializer):
    topics_count = serializers.SerializerMethodField()
    subfolders_count = serializers.SerializerMethodField()
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    category_name = serializers.SerializerMethodField()
    category_color = serializers.SerializerMethodField()
    
    class Meta:
        model = Subject
        fields = ['id', 'name', 'description', 'category', 'category_name', 'category_color', 'is_custom', 'created_at', 'topics_count', 'subfolders_count']
        read_only_fields = ['id', 'created_at']
    
    def get_topics_count(self, obj):
        return obj.topics.count()

    def get_subfolders_count(self, obj):
        return obj.subfolders.count()

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_category_color(self, obj):
        return obj.category.color if obj.category else None



class LessonSubfolderSerializer(serializers.ModelSerializer):
    topics_count = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = LessonSubfolder
        fields = ['id', 'subject', 'subject_name', 'name', 'description', 'is_custom', 'order', 'created_at', 'topics_count']
        read_only_fields = ['id', 'created_at']

    def get_topics_count(self, obj):
        return obj.topics.count()


class TopicSerializer(serializers.ModelSerializer):
    lessons_count = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subfolder_name = serializers.CharField(source='subfolder.name', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'subject', 'subject_name', 'subfolder', 'subfolder_name', 'name', 'description', 'is_custom', 'order', 'created_at', 'lessons_count']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        subfolder = attrs.get('subfolder') or getattr(self.instance, 'subfolder', None)
        subject = attrs.get('subject') or getattr(self.instance, 'subject', None)
        if subfolder:
            attrs['subject'] = subfolder.subject
        elif subject:
            subfolder, _ = LessonSubfolder.objects.get_or_create(
                subject=subject,
                name='General',
                defaults={'is_custom': False, 'order': 0}
            )
            attrs['subfolder'] = subfolder
        else:
            raise serializers.ValidationError({'subfolder': 'Subfolder is required.'})
        return attrs
    
    def get_lessons_count(self, obj):
        return obj.lessons.filter(is_published=True).count()


class LessonContentSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    subject_name = serializers.CharField(source='topic.subject.name', read_only=True)
    subfolder_name = serializers.CharField(source='topic.subfolder.name', read_only=True)
    subfolder = serializers.UUIDField(source='topic.subfolder_id', read_only=True)
    subject = serializers.UUIDField(source='topic.subject_id', read_only=True)
    category_name = serializers.SerializerMethodField()
    category_color = serializers.SerializerMethodField()
    linked_topics_data = serializers.SerializerMethodField()
    
    class Meta:
        model = LessonContent
        fields = [
            'id', 'topic', 'topic_name', 'subject', 'subject_name', 'subfolder', 'subfolder_name',
            'category_name', 'category_color',
            'title', 'content',
            'publisher_name', 'publisher_title', 'published_date',
            'linked_topics', 'linked_topics_data', 'embedded_images',
            'slug', 'meta_description', 'meta_keywords', 'og_image', 'tags',
            'is_published', 'order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'published_date', 'created_at', 'updated_at']
    
    def get_category_name(self, obj):
        cat = getattr(obj.topic.subject, 'category', None)
        return cat.name if cat else None

    def get_category_color(self, obj):
        cat = getattr(obj.topic.subject, 'category', None)
        return cat.color if cat else None

    def get_linked_topics_data(self, obj):
        """Return full topic data for linked topics"""
        return [
            {'id': t.id, 'name': t.name, 'subject_name': t.subject.name, 'subfolder_name': t.subfolder.name}
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
    Serializer for displaying a subject with all its topics and subfolders (folder view)
    """
    topics = TopicSerializer(many=True, read_only=True)
    subfolders = LessonSubfolderSerializer(many=True, read_only=True)
    category_name = serializers.SerializerMethodField()
    category_color = serializers.SerializerMethodField()
    
    class Meta:
        model = Subject
        fields = ['id', 'name', 'description', 'category', 'category_name', 'category_color', 'is_custom', 'created_at', 'topics', 'subfolders']
        read_only_fields = ['id', 'created_at']

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_category_color(self, obj):
        return obj.category.color if obj.category else None



class TopicDetailSerializer(serializers.ModelSerializer):
    """
    Detailed topic view with all its lessons
    """
    lessons = LessonContentSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subfolder_name = serializers.CharField(source='subfolder.name', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'subject', 'subject_name', 'subfolder', 'subfolder_name', 'name', 'description', 'order', 'created_at', 'lessons']
        read_only_fields = ['id', 'created_at']
