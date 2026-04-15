from rest_framework import serializers
from .models import (
    CustomMockExam, MockExamSubject, MockExamQuestion, MockExamOption,
    MockExamFee, MockExamAttempt, MockExamResult, MockExamActivityLog,
    MockExamExternalPlatform
)


class MockExamOptionSerializer(serializers.ModelSerializer):
    """
    Serializer for MockExamOption.
    
    Options are AUTO-CREATED when a question is created (A, B, C, D).
    This serializer mainly handles reading and updating existing options.
    """
    # Write-only file field for image uploads
    option_image_file = serializers.ImageField(write_only=True, required=False)
    
    class Meta:
        model = MockExamOption
        fields = ['id', 'question', 'option_text', 'option_image', 'option_image_file',
                  'option_letter', 'is_correct', 'explanation', 'order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'question', 'option_letter', 'order', 'option_image', 'created_at', 'updated_at']
    
    def update(self, instance, validated_data):
        """Handle file upload if present"""
        # Extract the write-only file field
        image_file = validated_data.pop('option_image_file', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle image file upload
        if image_file:
            instance.option_image = image_file
        
        instance.save()
        return instance


class MockExamQuestionSerializer(serializers.ModelSerializer):
    options = MockExamOptionSerializer(many=True, read_only=True)
    # Write-only file fields for image uploads
    question_image_file = serializers.ImageField(write_only=True, required=False)
    explanation_image_file = serializers.ImageField(write_only=True, required=False)
    
    class Meta:
        model = MockExamQuestion
        fields = ['id', 'subject', 'question_text', 'question_image', 'question_image_file',
                  'question_type', 'difficulty', 'marks', 'negative_marks', 'explanation', 
                  'explanation_image', 'explanation_image_file', 'order', 'is_mandatory', 
                  'options', 'created_at', 'updated_at']
        read_only_fields = ['id', 'question_image', 'explanation_image', 'created_at', 'updated_at', 'options']
    
    def create(self, validated_data):
        """Handle file uploads during creation"""
        # Extract write-only file fields
        question_image_file = validated_data.pop('question_image_file', None)
        explanation_image_file = validated_data.pop('explanation_image_file', None)
        
        # Create the question instance
        instance = MockExamQuestion.objects.create(**validated_data)
        
        # Handle image file uploads
        if question_image_file:
            instance.question_image = question_image_file
        if explanation_image_file:
            instance.explanation_image = explanation_image_file
        
        instance.save()
        return instance
    
    def update(self, instance, validated_data):
        """Handle file uploads during updates"""
        # Extract write-only file fields
        question_image_file = validated_data.pop('question_image_file', None)
        explanation_image_file = validated_data.pop('explanation_image_file', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle image file uploads
        if question_image_file:
            instance.question_image = question_image_file
        if explanation_image_file:
            instance.explanation_image = explanation_image_file
        
        instance.save()
        return instance


class MockExamSubjectSerializer(serializers.ModelSerializer):
    questions = MockExamQuestionSerializer(many=True, read_only=True)
    question_count = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    
    class Meta:
        model = MockExamSubject
        fields = ['id', 'mock_exam', 'subject_name', 'description', 'subject_icon',
                  'num_questions', 'time_allocation_minutes', 'marks_per_question', 'order',
                  'questions', 'question_count', 'total_marks', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_question_count(self, obj):
        return obj.get_question_count()
    
    def get_total_marks(self, obj):
        return obj.get_total_marks()


class MockExamFeeSerializer(serializers.ModelSerializer):
    final_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = MockExamFee
        fields = ['id', 'mock_exam', 'fee_amount', 'currency', 'discount_percentage',
                  'promo_code', 'final_amount', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_final_amount(self, obj):
        return str(obj.get_final_amount())


class CustomMockExamListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list view"""
    subject_count = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    fee = MockExamFeeSerializer(read_only=True)
    
    class Meta:
        model = CustomMockExam
        fields = ['id', 'title', 'description', 'difficulty_level', 'total_duration_minutes',
                  'total_marks', 'passing_marks', 'is_published', 'subject_area', 'exam_year',
                  'total_attempts', 'avg_score', 'subject_count', 'total_questions', 'fee', 'created_at']
        read_only_fields = ['id', 'created_at', 'total_attempts', 'avg_score']
    
    def get_subject_count(self, obj):
        return obj.get_subject_count()
    
    def get_total_questions(self, obj):
        return obj.get_total_questions()


class CustomMockExamDetailSerializer(serializers.ModelSerializer):
    """Complete serializer with all nested data"""
    subjects = MockExamSubjectSerializer(many=True, read_only=True)
    fee = MockExamFeeSerializer(read_only=True)
    subject_count = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomMockExam
        fields = ['id', 'admin', 'title', 'description', 'instructions', 'total_duration_minutes',
                  'total_marks', 'passing_marks', 'difficulty_level', 'status', 'is_published',
                  'is_active', 'is_streaming', 'external_platform', 'external_exam_id', 'external_exam_url',
                  'subject_area', 'exam_year', 'language', 'total_attempts', 'avg_score',
                  'subjects', 'fee', 'subject_count', 'total_questions', 'created_at', 'updated_at']
        read_only_fields = ['id', 'admin', 'created_at', 'updated_at', 'total_attempts', 'avg_score']
    
    def get_subject_count(self, obj):
        return obj.get_subject_count()
    
    def get_total_questions(self, obj):
        return obj.get_total_questions()


class MockExamResultSerializer(serializers.ModelSerializer):
    question = MockExamQuestionSerializer(read_only=True)
    selected_option = MockExamOptionSerializer(read_only=True)
    
    class Meta:
        model = MockExamResult
        fields = ['id', 'attempt', 'question', 'selected_option', 'student_answer_text',
                  'is_correct', 'marks_obtained', 'time_spent_seconds', 'attempted',
                  'marked_for_review', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class MockExamAttemptListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list view"""
    mock_exam_title = serializers.CharField(source='mock_exam.title', read_only=True)
    mock_exam = serializers.PrimaryKeyRelatedField(
        queryset=CustomMockExam.objects.all(),
        write_only=True,
        required=True
    )
    
    class Meta:
        model = MockExamAttempt
        fields = ['id', 'mock_exam', 'mock_exam_title', 'start_time', 'end_time',
                  'status', 'obtained_marks', 'total_marks', 'percentage', 'grade',
                  'passed', 'time_spent_seconds']
        read_only_fields = ['id', 'mock_exam_title', 'start_time', 'end_time', 'status', 
                           'obtained_marks', 'percentage', 'grade', 'passed']


class MockExamAttemptDetailSerializer(serializers.ModelSerializer):
    """Complete serializer with results"""
    mock_exam = CustomMockExamDetailSerializer(read_only=True)
    results = MockExamResultSerializer(many=True, read_only=True)
    
    class Meta:
        model = MockExamAttempt
        fields = ['id', 'user', 'mock_exam', 'start_time', 'end_time', 'time_spent_seconds',
                  'status', 'is_submitted', 'total_marks', 'obtained_marks', 'percentage',
                  'grade', 'passed', 'device_type', 'results',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'start_time', 'end_time',
                           'status', 'is_submitted', 'obtained_marks', 'percentage', 'grade', 
                           'passed', 'device_type', 'results', 'time_spent_seconds']


class MockExamActivityLogSerializer(serializers.ModelSerializer):
    admin_username = serializers.CharField(source='admin.username', read_only=True)
    mock_exam_title = serializers.CharField(source='mock_exam.title', read_only=True)
    
    class Meta:
        model = MockExamActivityLog
        fields = ['id', 'admin', 'admin_username', 'mock_exam', 'mock_exam_title', 'action',
                  'description', 'change_details', 'affected_students', 'created_at']
        read_only_fields = fields


class MockExamExternalPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockExamExternalPlatform
        fields = ['id', 'platform_name', 'platform_type', 'description', 'platform_url',
                  'api_key', 'api_secret', 'api_endpoint', 'is_active', 'sync_enabled',
                  'last_sync_time', 'webhook_url', 'auth_headers', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_sync_time']
        extra_kwargs = {
            'api_key': {'write_only': True},
            'api_secret': {'write_only': True},
        }


class MockExamActivityOverviewSerializer(serializers.Serializer):
    """Serializer for admin activity overview dashboard"""
    total_mock_exams = serializers.IntegerField()
    published_exams = serializers.IntegerField()
    draft_exams = serializers.IntegerField()
    total_students_attempted = serializers.IntegerField()
    total_attempts = serializers.IntegerField()
    avg_completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    avg_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    most_attempted_exam = serializers.CharField()
    recent_attempts = MockExamAttemptListSerializer(many=True)
    subject_wise_attempts = serializers.DictField()
    hourly_attempts = serializers.ListField()  # For charts
