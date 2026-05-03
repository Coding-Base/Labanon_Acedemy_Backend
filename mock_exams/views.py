from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, Avg, F, Max, Sum
from django.utils import timezone
from datetime import timedelta
import logging
from django.db import transaction

from .models import (
    CustomMockExam, MockExamSubject, MockExamQuestion, MockExamOption,
    MockExamFee, MockExamAttempt, MockExamResult, MockExamActivityLog,
    MockExamExternalPlatform
)
from .serializers import (
    CustomMockExamDetailSerializer, CustomMockExamListSerializer,
    MockExamSubjectSerializer, MockExamQuestionSerializer, MockExamOptionSerializer,
    MockExamFeeSerializer, MockExamAttemptListSerializer, MockExamAttemptDetailSerializer,
    MockExamResultSerializer, MockExamActivityLogSerializer, MockExamExternalPlatformSerializer,
    MockExamActivityOverviewSerializer
)
from courses.models import ActivationUnlock


logger = logging.getLogger(__name__)


class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class MasterAdminMockExamViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Master Admin to manage Mock Exams.
    Admin-only access with full CRUD operations.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'subject_area']
    ordering_fields = ['created_at', 'title', 'total_attempts']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return CustomMockExam.objects.prefetch_related('subjects', 'attempts').all()
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CustomMockExamDetailSerializer
        return CustomMockExamListSerializer
    
    def perform_create(self, serializer):
        """Create exam and log activity"""
        exam = serializer.save(admin=self.request.user)
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=exam,
            action='create_exam',
            description=f"Created mock exam: {exam.title}",
            change_details={'title': exam.title, 'duration': exam.total_duration_minutes}
        )
        logger.info(f"Admin {self.request.user.username} created mock exam: {exam.title}")
    
    def perform_update(self, serializer):
        """Update exam and log activity"""
        old_instance = CustomMockExam.objects.get(pk=self.kwargs['pk'])
        exam = serializer.save()
        
        changes = {}
        if old_instance.title != exam.title:
            changes['title'] = {'old': old_instance.title, 'new': exam.title}
        if old_instance.total_duration_minutes != exam.total_duration_minutes:
            changes['duration'] = {'old': old_instance.total_duration_minutes, 'new': exam.total_duration_minutes}
        if old_instance.total_marks != exam.total_marks:
            changes['marks'] = {'old': old_instance.total_marks, 'new': exam.total_marks}
        
        if changes:
            MockExamActivityLog.objects.create(
                admin=self.request.user,
                mock_exam=exam,
                action='update_exam',
                description=f"Updated mock exam: {exam.title}",
                change_details=changes
            )
        logger.info(f"Admin {self.request.user.username} updated mock exam: {exam.title}")
    
    def perform_destroy(self, instance):
        """Delete exam and log activity"""
        title = instance.title
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=instance,
            action='delete_exam',
            description=f"Deleted mock exam: {title}",
            affected_students=instance.attempts.count()
        )
        logger.info(f"Admin {self.request.user.username} deleted mock exam: {title}")
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish exam to make it available to students"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'📢 Publish action called for exam {pk}')
        
        exam = self.get_object()
        logger.info(f'  Exam: {exam.title}')
        
        # Validate exam has subjects and questions
        subject_count = exam.subjects.count()
        logger.info(f'  Subject count: {subject_count}')
        if subject_count == 0:
            logger.warning('  ❌ No subjects found!')
            return Response({'error': 'Exam must have at least one subject'}, status=status.HTTP_400_BAD_REQUEST)
        
        total_questions = sum(subj.questions.count() for subj in exam.subjects.all())
        logger.info(f'  Total questions: {total_questions}')
        if total_questions == 0:
            logger.warning('  ❌ No questions found!')
            return Response({'error': 'Exam must have at least one question'}, status=status.HTTP_400_BAD_REQUEST)
        
        exam.is_published = True
        exam.status = 'published'
        exam.save()
        logger.info(f'  ✅ Exam published successfully')
        
        MockExamActivityLog.objects.create(
            admin=request.user,
            mock_exam=exam,
            action='publish_exam',
            description=f"Published mock exam: {exam.title}"
        )
        
        return Response({'status': 'exam published', 'exam_id': exam.id}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive exam to hide from students"""
        exam = self.get_object()
        exam.is_published = False
        exam.status = 'archived'
        exam.save()
        
        MockExamActivityLog.objects.create(
            admin=request.user,
            mock_exam=exam,
            action='archive_exam',
            description=f"Archived mock exam: {exam.title}"
        )
        
        return Response({'status': 'exam archived'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def activity_overview(self, request):
        """Get admin dashboard overview with activity stats"""
        total_exams = CustomMockExam.objects.count()
        published_exams = CustomMockExam.objects.filter(is_published=True).count()
        draft_exams = CustomMockExam.objects.filter(status='draft').count()
        
        all_attempts = MockExamAttempt.objects.all()
        total_students = all_attempts.values('user').distinct().count()
        total_attempts = all_attempts.count()
        
        completed_attempts = all_attempts.filter(status='completed').count()
        completion_rate = (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0
        
        avg_score = all_attempts.filter(status='completed').aggregate(Avg('percentage'))['percentage__avg'] or 0
        
        # Most attempted exam
        most_attempted = CustomMockExam.objects.annotate(
            attempt_count=Count('attempts')
        ).order_by('-attempt_count').first()
        
        # Recent attempts
        recent_attempts = MockExamAttempt.objects.select_related(
            'user', 'mock_exam'
        ).order_by('-start_time')[:5]
        
        # Subject-wise attempts - convert to dict
        subject_attempts_list = list(
            MockExamSubject.objects.annotate(
                attempt_count=Count('mock_exam__attempts')
            ).values('subject_name', 'attempt_count')
        )
        
        data = {
            'total_mock_exams': total_exams,
            'published_exams': published_exams,
            'draft_exams': draft_exams,
            'total_students_attempted': total_students,
            'total_attempts': total_attempts,
            'avg_completion_rate': completion_rate,
            'avg_score': avg_score,
            'most_attempted_exam': most_attempted.title if most_attempted else None,
            'recent_attempts': MockExamAttemptListSerializer(recent_attempts, many=True).data,
            'subject_wise_attempts': {'data': subject_attempts_list},
            'hourly_attempts': [],
        }
        
        serializer = MockExamActivityOverviewSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MockExamSubjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing subjects within mock exams.
    Supports both nested (/admin/exams/<id>/subjects/) and flat (/admin/subjects/?mock_exam=<id>) endpoints.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = MockExamSubjectSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'created_at']
    ordering = ['order']
    
    def get_queryset(self):
        # Support both nested and flat routing
        exam_id = self.kwargs.get('exam_id') or self.request.query_params.get('mock_exam')
        if exam_id:
            return MockExamSubject.objects.filter(mock_exam_id=exam_id)
        return MockExamSubject.objects.all()
    
    def perform_create(self, serializer):
        # Get exam from either nested param or request data
        exam_id = self.kwargs.get('exam_id') or self.request.data.get('mock_exam')
        exam = CustomMockExam.objects.get(id=exam_id)
        subject = serializer.save(mock_exam=exam)
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=exam,
            action='add_subject',
            description=f"Added subject: {subject.subject_name}",
            change_details={'subject_name': subject.subject_name}
        )


class MockExamQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing questions within subjects.
    Supports both nested (/admin/subjects/<id>/questions/) and flat (/admin/questions/?subject=<id>) endpoints.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = MockExamQuestionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'difficulty', 'created_at']
    ordering = ['order']
    
    def get_queryset(self):
        # Support both nested and flat routing
        subject_id = self.kwargs.get('subject_id') or self.request.query_params.get('subject')
        if subject_id:
            return MockExamQuestion.objects.filter(subject_id=subject_id).prefetch_related('options')
        return MockExamQuestion.objects.all().prefetch_related('options')
    
    def perform_create(self, serializer):
        # Get subject from either nested param or request data
        subject_id = self.kwargs.get('subject_id') or self.request.data.get('subject')
        subject = MockExamSubject.objects.get(id=subject_id)
        question = serializer.save(subject=subject)
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=subject.mock_exam,
            action='add_question',
            description=f"Added question in {subject.subject_name}",
            change_details={'question_type': question.question_type}
        )


class MockExamOptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing options for questions.
    Options are AUTO-CREATED when question is created (A, B, C, D).
    This endpoint mainly updates existing options (PATCH) or retrieves them (GET).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = MockExamOptionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order']
    ordering = ['order']
    
    def get_queryset(self):
        """Get options for a specific question or all options"""
        question_id = self.kwargs.get('question_id') or self.request.query_params.get('question')
        if question_id:
            return MockExamOption.objects.filter(question_id=question_id)
        return MockExamOption.objects.all()
    
    def create(self, request, *args, **kwargs):
        """
        DISABLED: Options are auto-created when question is created.
        Users should PATCH to update option_text and is_correct fields.
        """
        return Response(
            {"detail": "Options are auto-created when a question is created. Use PATCH to update them."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def perform_update(self, serializer):
        """Allow updates to existing options (filling in text, marking correct)"""
        serializer.save()


class StudentMockExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for students to browse and access mock exams.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'subject_area', 'subjects__subject_name']
    ordering_fields = ['created_at', 'total_attempts', 'total_marks']
    ordering = ['-created_at']
    
    def get_queryset(self):
        # Only show published exams
        return CustomMockExam.objects.filter(
            is_published=True,
            is_active=True
        ).prefetch_related('subjects', 'fee').all()
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CustomMockExamDetailSerializer
        return CustomMockExamListSerializer
    
    @action(detail=True, methods=['post'])
    def check_unlock_status(self, request, pk=None):
        """Check if student needs to unlock the exam or can take it free"""
        exam = self.get_object()
        user = request.user
        
        # Check 1: User has global unlock (is_unlocked=True)
        if getattr(user, 'is_unlocked', False):
            return Response({
                'unlocked': True,
                'reason': 'global_unlock',
                'message': 'You have full access to mock exams'
            }, status=status.HTTP_200_OK)
        
        # Check 2: User has any existing ActivationUnlock record (CBT exams or mock exams)
        if ActivationUnlock.objects.filter(user=user).exists():
            return Response({
                'unlocked': True,
                'reason': 'existing_unlock',
                'message': 'You have previously unlocked exams. Mock exams are free for you.'
            }, status=status.HTTP_200_OK)
        
        # Check 2.5: User has specifically unlocked this mock exam
        mock_exam_unlock = ActivationUnlock.objects.filter(
            user=user,
            exam_identifier=f"mock_exam_{exam.id}"
        ).exists()
        if mock_exam_unlock:
            return Response({
                'unlocked': True,
                'reason': 'mock_exam_unlock',
                'message': 'You have unlocked this mock exam.'
            }, status=status.HTTP_200_OK)
        
        # Check 3: Exam is free
        if not hasattr(exam, 'fee') or exam.fee.fee_amount == 0:
            return Response({
                'unlocked': True,
                'reason': 'free_exam',
                'message': 'This exam is free'
            }, status=status.HTTP_200_OK)
        
        # Check 4: User needs to unlock (paid exam)
        return Response({
            'unlocked': False,
            'reason': 'requires_payment',
            'fee_amount': float(exam.fee.fee_amount),
            'currency': exam.fee.currency,
            'message': f"This exam requires unlock payment of {exam.fee.currency} {exam.fee.fee_amount}"
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def start_attempt(self, request, pk=None):
        """Start a new mock exam attempt"""
        exam = self.get_object()
        user = request.user
        
        # Verify access
        check = self.check_unlock_status(request, pk)
        if check.status_code == 200 and not check.data.get('unlocked'):
            return Response({'error': 'You must unlock this exam first'}, status=status.HTTP_403_FORBIDDEN)
        
        # Create attempt record
        attempt = MockExamAttempt.objects.create(
            user=user,
            mock_exam=exam,
            device_type=request.data.get('device_type', 'unknown'),
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Calculate total marks
        total_marks = sum(subj.get_total_marks() for subj in exam.subjects.all())
        attempt.total_marks = total_marks
        attempt.save()
        
        # Create result records for all questions
        for subject in exam.subjects.all():
            for question in subject.questions.all():
                MockExamResult.objects.create(
                    attempt=attempt,
                    question=question
                )
        
        serializer = MockExamAttemptDetailSerializer(attempt)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def my_attempts(self, request):
        """Get student's past attempts"""
        attempts = MockExamAttempt.objects.filter(
            user=request.user,
            status__in=['completed', 'submitted']
        ).order_by('-start_time')
        
        page = self.paginate_queryset(attempts)
        if page is not None:
            serializer = MockExamAttemptListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = MockExamAttemptListSerializer(attempts, many=True)
        return Response(serializer.data)


class MockExamFeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing mock exam fees (admin only).
    """
    queryset = MockExamFee.objects.select_related('mock_exam')
    serializer_class = MockExamFeeSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def perform_create(self, serializer):
        """Log fee creation"""
        fee = serializer.save()
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=fee.mock_exam,
            action='create_fee',
            description=f"Created fee for {fee.mock_exam.title}"
        )
    
    def perform_update(self, serializer):
        """Log fee update"""
        fee = serializer.save()
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=fee.mock_exam,
            action='update_fee',
            description=f"Updated fee for {fee.mock_exam.title}"
        )


class MockExamExternalPlatformViewSet(viewsets.ModelViewSet):
    """
    ViewSet for configuring external exam platforms (admin only).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = MockExamExternalPlatform.objects.all()
    serializer_class = MockExamExternalPlatformSerializer
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test connection to external platform"""
        platform = self.get_object()
        try:
            # TODO: Implement actual connection test
            return Response({'status': 'connection_ok'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'connection_failed', 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def sync_exams(self, request, pk=None):
        """Sync exams from external platform"""
        platform = self.get_object()
        try:
            # TODO: Implement actual sync logic
            platform.last_sync_time = timezone.now()
            platform.save()
            return Response({'status': 'sync_completed'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'sync_failed', 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MockExamActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing activity logs (admin only).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = MockExamActivityLog.objects.select_related('admin', 'mock_exam').order_by('-created_at')
    serializer_class = MockExamActivityLogSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'action']
    ordering = ['-created_at']


class MockExamAttemptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student mock exam attempts.
    Allows creating, retrieving, updating, and submitting attempts.
    """
    serializer_class = MockExamAttemptListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-start_time']

    def get_queryset(self):
        """Students see only their own attempts; admins see all"""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return MockExamAttempt.objects.select_related('user', 'mock_exam').all()
        return MockExamAttempt.objects.select_related('user', 'mock_exam').filter(user=user)

    def get_serializer_class(self):
        """Use detail serializer for retrieve, list serializer for list"""
        if self.action == 'retrieve':
            return MockExamAttemptDetailSerializer
        return MockExamAttemptListSerializer

    def perform_create(self, serializer):
        """Set current user and calculate total marks when creating attempt"""
        # Get the mock_exam from validated data (it's there because of source='mock_exam')
        mock_exam = serializer.validated_data.get('mock_exam')
        
        # Calculate total marks from exam questions (through subjects relationship)
        total_marks = 0
        if mock_exam:
            # Sum marks across all questions in all subjects
            total_marks = mock_exam.subjects.aggregate(
                total=Sum('questions__marks')
            )['total'] or 0
        
        # Save with current user and calculated total marks
        serializer.save(user=self.request.user, total_marks=total_marks)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit exam attempt with student answers and calculate score.
        Expects: {answers: {question_id: option_id}, time_spent_seconds: int}
        """
        attempt = self.get_object()
        
        # Check if already submitted
        if attempt.is_submitted:
            return Response(
                {'detail': 'Exam has already been submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        answers = request.data.get('answers', {})  # {question_id: option_id}
        time_spent = request.data.get('time_spent_seconds', 0)
        
        # Calculate score by checking correct answers
        obtained_marks = 0
        for question_id, selected_option_id in answers.items():
            try:
                # Check if selected option is correct and belongs to the question
                option = MockExamOption.objects.get(
                    id=selected_option_id,
                    question_id=question_id,
                    is_correct=True
                )
                # Get marks for this question
                question = MockExamQuestion.objects.get(id=question_id)
                obtained_marks += question.marks
            except (MockExamOption.DoesNotExist, MockExamQuestion.DoesNotExist):
                # Wrong answer or invalid option, no marks awarded
                pass
        
        # Store answers as JSON, calculate percentage and grade
        percentage = (obtained_marks / attempt.total_marks * 100) if attempt.total_marks > 0 else 0
        
        # Simple grading: A=90+, B=80-89, C=70-79, D=60-69, F=below 60
        if percentage >= 90:
            grade = 'A'
        elif percentage >= 80:
            grade = 'B'
        elif percentage >= 70:
            grade = 'C'
        elif percentage >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        passed = percentage >= 50  # 50% to pass
        
        # Update attempt
        attempt.answers = answers
        attempt.obtained_marks = obtained_marks
        attempt.percentage = percentage
        attempt.grade = grade
        attempt.passed = passed
        attempt.is_submitted = True
        attempt.status = 'submitted'
        attempt.end_time = timezone.now()
        attempt.time_spent_seconds = time_spent
        attempt.save()
        
        # Log the activity
        MockExamActivityLog.objects.create(
            admin=request.user,
            action='SUBMIT',
            mock_exam=attempt.mock_exam,
            description=f"Student {request.user.username} submitted attempt with score {obtained_marks}/{attempt.total_marks}"
        )
        
        serializer = MockExamAttemptDetailSerializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)
