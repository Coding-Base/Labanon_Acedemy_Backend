from rest_framework import serializers
from .models import Country, ExamFolder, FolderExam, FolderSubject, Question, Choice, Exam, ExamAttempt, Subject, StudentAnswer
from django.db.models import Q
from django.utils.text import slugify
from .math_utils import format_math_question, format_math_choices
import json
import re


def format_math_text(text):
    """
    Format text with math notation for proper rendering.
    Uses centralized math_utils module.
    """
    return format_math_question(text)


def resolve_question_image_url(question, request=None):
    """
    Safely resolve an absolute URL for a question's image, supporting Cloudinary,
    remote URLs, and local files without raising exceptions if storage is unconfigured.
    """
    if not question:
        return None
    image_field = getattr(question, 'image', None)
    if not image_field:
        return None
    image_str = str(image_field).strip()
    if not image_str:
        return None
    if image_str.startswith(('http://', 'https://')):
        return image_str
    if image_str.startswith('//'):
        return f"https:{image_str}"
    try:
        url = image_field.url
        if url.startswith(('http://', 'https://')):
            return url
        if url.startswith('//'):
            return f"https:{url}"
        if request:
            return request.build_absolute_uri(url)
        return url
    except Exception:
        if image_str.startswith(('http://', 'https://')):
            return image_str
        try:
            from django.conf import settings
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            fallback_url = f"{media_url.rstrip('/')}/{image_str.lstrip('/')}"
            if request:
                return request.build_absolute_uri(fallback_url)
            return fallback_url
        except Exception:
            return None


class SafeImageField(serializers.ImageField):
    """
    ImageField that safely handles URL generation, catching storage exceptions
    (e.g., Cloudinary configuration errors, missing cloud_name, filesystem errors)
    without crashing serialization.
    """
    def to_representation(self, value):
        if not value:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None
        if val_str.startswith(('http://', 'https://')):
            return val_str
        if val_str.startswith('//'):
            return f"https:{val_str}"
        try:
            url = value.url
            if url.startswith(('http://', 'https://')):
                return url
            if url.startswith('//'):
                return f"https:{url}"
            request = self.context.get('request', None)
            if request is not None:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            try:
                from django.conf import settings
                media_url = getattr(settings, 'MEDIA_URL', '/media/')
                fallback_url = f"{media_url.rstrip('/')}/{val_str.lstrip('/')}"
                request = self.context.get('request', None)
                if request is not None:
                    return request.build_absolute_uri(fallback_url)
                return fallback_url
            except Exception:
                return None


class CountrySerializer(serializers.ModelSerializer):
    flag_image = SafeImageField(required=False, allow_null=True)
    folder_count = serializers.SerializerMethodField()
    exam_count = serializers.SerializerMethodField()

    class Meta:
        model = Country
        fields = [
            'id', 'name', 'code', 'slug', 'flag_image', 'sort_order', 'status',
            'is_visible', 'available_from', 'available_until', 'folder_count',
            'exam_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'folder_count', 'exam_count']

    def get_folder_count(self, obj):
        return obj.tagged_folders.count()

    def get_exam_count(self, obj):
        return Exam.objects.filter(folder_links__folder__country_tags=obj).distinct().count()


class ExamFolderSerializer(serializers.ModelSerializer):
    child_count = serializers.SerializerMethodField()
    exam_count = serializers.SerializerMethodField()
    subject_count = serializers.SerializerMethodField()
    country_tags = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), many=True, required=False
    )
    country_tag_details = CountrySerializer(source='country_tags', many=True, read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True, allow_null=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    cover_image = SafeImageField(required=False, allow_null=True)

    class Meta:
        model = ExamFolder
        fields = [
            'id', 'country', 'country_name', 'country_tags', 'country_tag_details', 'parent', 'parent_name', 'name', 'slug',
            'description', 'icon', 'cover_image', 'sort_order', 'status', 'is_visible',
            'available_from', 'available_until', 'status_before_archive', 'child_count', 'exam_count', 'subject_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'status_before_archive', 'child_count', 'exam_count', 'subject_count']

    def validate(self, attrs):
        instance = self.instance
        parent = attrs.get('parent', instance.parent if instance else None)

        if instance and parent and parent.pk == instance.pk:
            raise serializers.ValidationError({'parent': 'A folder cannot be its own parent.'})

        ancestor = parent
        while ancestor:
            if instance and ancestor.pk == instance.pk:
                raise serializers.ValidationError({'parent': 'Folder nesting cannot contain a cycle.'})
            ancestor = ancestor.parent
        return attrs

    def get_child_count(self, obj):
        return obj.children.count()

    def get_exam_count(self, obj):
        return obj.exam_links.count()

    def get_subject_count(self, obj):
        return obj.subject_links.count()


class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct']
    
    def to_representation(self, instance):
        """Format choice text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['text'] = format_math_text(data['text'])

        # Security: Strip is_correct for students/unauthenticated users during exams
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        is_admin_or_staff = user and (getattr(user, 'is_staff', False) or getattr(user, 'role', '') == 'admin')
        if not is_admin_or_staff and not self.context.get('show_correct_answers', False):
            data.pop('is_correct', None)

        return data


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, required=False)
    assigned_subject_ids = serializers.SerializerMethodField()
    image = SafeImageField(required=False, allow_null=True)

    class Meta:
        model = Question
        fields = ['id', 'subject', 'text', 'image', 'choices', 'year', 'created_at', 'assigned_subject_ids']
        read_only_fields = ['created_at']

    def to_representation(self, instance):
        """Format question text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['text'] = format_math_text(data['text'])
        if instance.image:
            img_str = str(instance.image).strip()
            if img_str.startswith(('http://', 'https://')):
                data['image'] = img_str
            elif img_str.startswith('//'):
                data['image'] = f"https:{img_str}"
        return data

    def create(self, validated_data):
        choices_data = validated_data.pop('choices', [])
        # Handle choices if passed as JSON string in multipart/form-data
        if 'choices_json' in self.initial_data:
            try:
                choices_data = json.loads(self.initial_data['choices_json'])
            except: pass
            
        question = Question.objects.create(**validated_data)
        for choice_data in choices_data:
            Choice.objects.create(question=question, **choice_data)
        return question

    def get_assigned_subject_ids(self, obj):
        return list(obj.assignments.values_list('subject_id', flat=True))


class SubjectSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ['id', 'exam', 'name', 'description', 'question_count', 'created_at']
        read_only_fields = ['created_at']

    def get_question_count(self, obj):
        return Question.objects.filter(
            Q(subject=obj) | Q(assignments__subject=obj)
        ).distinct().count()


class ExamSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)
    subject_count = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    attempt_count = serializers.IntegerField(read_only=True, default=0)
    slug = serializers.SlugField(required=False, allow_blank=True)
    country = serializers.IntegerField(source='folder.country_id', read_only=True)
    country_name = serializers.CharField(source='folder.country.name', read_only=True)
    folder_name = serializers.CharField(source='folder.name', read_only=True)

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'slug', 'description', 'folder', 'country', 'country_name',
            'folder_name', 'institution', 'provider', 'exam_type', 'year', 'difficulty',
            'sort_order', 'status', 'is_visible', 'available_from', 'available_until',
            'time_limit_minutes', 'free_trial_attempts', 'free_trial_questions_per_subject',
            'subject_select_limit', 'subject_count', 'question_count', 'subjects',
            'created_at', 'updated_at', 'attempt_count'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'country', 'country_name', 'folder_name',
            'subject_count', 'question_count', 'attempt_count'
        ]

    def _unique_slug(self, value, instance=None):
        base = slugify(value or 'exam')[:255] or 'exam'
        candidate = base
        suffix = 2
        queryset = Exam.objects.all()
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        while queryset.filter(slug=candidate).exists():
            suffix_text = f'-{suffix}'
            candidate = f'{base[:255 - len(suffix_text)]}{suffix_text}'
            suffix += 1
        return candidate

    def create(self, validated_data):
        if not validated_data.get('slug'):
            validated_data['slug'] = self._unique_slug(validated_data.get('title'))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if not validated_data.get('slug'):
            validated_data.pop('slug', None)
        return super().update(instance, validated_data)

    def get_subject_count(self, obj):
        return obj.subjects.count()

    def get_question_count(self, obj):
        return Question.objects.filter(
            Q(subject__exam=obj) | Q(assignments__subject__exam=obj)
        ).distinct().count()

class StudentAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text', read_only=True)
    correct_choice_id = serializers.SerializerMethodField()
    correct_answer = serializers.SerializerMethodField()
    question_image = serializers.SerializerMethodField()

    class Meta:
        model = StudentAnswer
        fields = ['id', 'question', 'question_text', 'question_image', 'selected_choice', 'selected_choice_text', 'is_correct', 'correct_choice_id', 'correct_answer', 'answered_at']
        read_only_fields = ['is_correct', 'answered_at']

    selected_choice_text = serializers.SerializerMethodField()

    def get_selected_choice_text(self, obj):
        if obj.selected_choice:
            return format_math_text(obj.selected_choice.text)
        return None

    def get_correct_choice_id(self, obj):
        correct_choice = obj.question.choices.filter(is_correct=True).first()
        return correct_choice.id if correct_choice else None

    def get_correct_answer(self, obj):
        correct_choice = obj.question.choices.filter(is_correct=True).first()
        return format_math_text(correct_choice.text) if correct_choice else None

    def get_question_image(self, obj):
        question = getattr(obj, 'question', None)
        if not question or not getattr(question, 'image', None):
            return None
        return resolve_question_image_url(question, self.context.get('request'))
    
    def to_representation(self, instance):
        """Format question and answer text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['question_text'] = format_math_text(data['question_text'])
        if not data.get('question_image') and instance.question and instance.question.image:
            data['question_image'] = resolve_question_image_url(instance.question, self.context.get('request'))
        return data


class ExamAttemptListSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    correct_answers = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = ['id', 'exam_title', 'subject_name', 'num_questions', 'score', 'started_at', 'submitted_at', 'time_taken_seconds', 'is_submitted', 'correct_answers', 'total_questions']
        read_only_fields = fields

    def get_correct_answers(self, obj):
        return obj.student_answers.filter(is_correct=True).count()

    def get_total_questions(self, obj):
        return obj.student_answers.count()


class ExamAttemptDetailSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    student_answers = StudentAnswerSerializer(many=True, read_only=True)
    correct_count = serializers.SerializerMethodField()
    wrong_count = serializers.SerializerMethodField()
    percentage_score = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = ['id', 'user_name', 'exam_title', 'subject_name', 'num_questions', 'time_limit_minutes', 'time_taken_seconds', 'score', 'started_at', 'submitted_at', 'student_answers', 'correct_count', 'wrong_count', 'percentage_score']
        read_only_fields = fields

    def get_correct_count(self, obj):
        return obj.student_answers.filter(is_correct=True).count()

    def get_wrong_count(self, obj):
        return obj.student_answers.exclude(is_correct=True).count()

    def get_percentage_score(self, obj):
        if obj.score is not None:
            return round((obj.score / obj.num_questions) * 100, 2)
        return None


class ExamAttemptCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamAttempt
        fields = ['exam', 'subject', 'num_questions', 'time_limit_minutes']


class SubmitAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAnswer
        fields = ['question', 'selected_choice']
