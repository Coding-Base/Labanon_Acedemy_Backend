from rest_framework import serializers
from .models import Question, Choice, Exam, ExamAttempt, Subject, StudentAnswer
from .math_utils import format_math_question, format_math_choices
import json
import re


def format_math_text(text):
    """
    Format text with math notation for proper rendering.
    Uses centralized math_utils module.
    """
    return format_math_question(text)


class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct']
    
    def to_representation(self, instance):
        """Format choice text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['text'] = format_math_text(data['text'])
        return data


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'subject', 'text', 'image', 'choices', 'year', 'created_at']
        read_only_fields = ['created_at']

    def to_representation(self, instance):
        """Format question text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['text'] = format_math_text(data['text'])
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


class SubjectSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ['id', 'exam', 'name', 'description', 'question_count', 'created_at']
        read_only_fields = ['created_at']

    def get_question_count(self, obj):
        return obj.questions.count()


class ExamSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)
    subject_count = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'slug', 'description', 'time_limit_minutes', 'subject_count', 'subjects', 'created_at']
        read_only_fields = ['created_at']

    def get_subject_count(self, obj):
        return obj.subjects.count()


class StudentAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text', read_only=True)
    correct_choice_id = serializers.SerializerMethodField()
    correct_answer = serializers.SerializerMethodField()
    question_image = serializers.ImageField(source='question.image', read_only=True)

    class Meta:
        model = StudentAnswer
        fields = ['id', 'question', 'question_text', 'question_image', 'selected_choice', 'is_correct', 'correct_choice_id', 'correct_answer', 'answered_at']
        read_only_fields = ['is_correct', 'answered_at']

    def get_correct_choice_id(self, obj):
        correct_choice = obj.question.choices.filter(is_correct=True).first()
        return correct_choice.id if correct_choice else None

    def get_correct_answer(self, obj):
        correct_choice = obj.question.choices.filter(is_correct=True).first()
        return format_math_text(correct_choice.text) if correct_choice else None
    
    def to_representation(self, instance):
        """Format question and answer text with LaTeX when serializing"""
        data = super().to_representation(instance)
        data['question_text'] = format_math_text(data['question_text'])
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
        return obj.student_answers.filter(is_correct=False).count()

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
