from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, Avg, F, Max, Sum
from django.utils import timezone
from datetime import timedelta
import logging
import requests
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
        return CustomMockExam.objects.prefetch_related('subjects__questions__options', 'attempts').all()
    
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
        logger.info(f'📢 Publish action called for exam {pk}')
        
        exam = self.get_object()
        logger.info(f'  Exam: {exam.title}')
        
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
        logger.info('  ✅ Exam published successfully')
        
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
        
        # Subject-wise attempts
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
        exam_id = self.kwargs.get('exam_id') or self.request.query_params.get('mock_exam')
        if exam_id:
            return MockExamSubject.objects.filter(mock_exam_id=exam_id)
        return MockExamSubject.objects.all()
    
    def perform_create(self, serializer):
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
        subject_id = self.kwargs.get('subject_id') or self.request.query_params.get('subject')
        if subject_id:
            return MockExamQuestion.objects.filter(subject_id=subject_id).prefetch_related('options')
        return MockExamQuestion.objects.all().prefetch_related('options')
    
    def perform_create(self, serializer):
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
    This endpoint mainly updates existing options (PATCH/PUT) or retrieves them (GET).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = MockExamOptionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order']
    ordering = ['order']
    
    def get_queryset(self):
        question_id = self.kwargs.get('question_id') or self.request.query_params.get('question')
        if question_id:
            return MockExamOption.objects.filter(question_id=question_id)
        return MockExamOption.objects.all()
    
    def create(self, request, *args, **kwargs):
        """
        DISABLED: Options are auto-created when question is created.
        Users should PATCH/PUT to update option_text and is_correct fields.
        """
        return Response(
            {"detail": "Options are auto-created when a question is created. Use PATCH/PUT to update them."},
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
        return CustomMockExam.objects.filter(
            is_published=True,
            is_active=True
        ).prefetch_related('subjects', 'fee').all()
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CustomMockExamDetailSerializer
        return CustomMockExamListSerializer
    
    @action(detail=True, methods=['post', 'get'])
    def check_unlock_status(self, request, pk=None):
        """Check if student needs to unlock the exam or can take it free"""
        exam = self.get_object()
        user = request.user
        
        # Check 0: Admin / superuser bypass
        if user.is_staff or user.is_superuser:
            return Response({
                'unlocked': True,
                'reason': 'admin_access',
                'message': 'Admin access granted for mock exam'
            }, status=status.HTTP_200_OK)

        # Check 1: User has global unlock (is_unlocked=True)
        if getattr(user, 'is_unlocked', False):
            return Response({
                'unlocked': True,
                'reason': 'global_unlock',
                'message': 'You have full access to mock exams'
            }, status=status.HTTP_200_OK)
        
        # Check 1.5: Active Pro subscription
        try:
            from courses.subscription_models import UserSubscription
            sub = UserSubscription.objects.filter(
                user=user,
                status=UserSubscription.STATUS_ACTIVE,
                end_date__gt=timezone.now()
            ).select_related('plan').first()
            if sub and (not sub.plan or sub.plan.allow_mock_exams):
                return Response({
                    'unlocked': True,
                    'reason': 'pro_subscription',
                    'message': 'Full access via your active Pro plan'
                }, status=status.HTTP_200_OK)
        except Exception:
            pass

        # Check 2: User has any existing active ActivationUnlock record (CBT exams or mock exams)
        if ActivationUnlock.objects.filter(user=user, is_active=True).exists():
            return Response({
                'unlocked': True,
                'reason': 'existing_unlock',
                'message': 'You have previously unlocked exams. Mock exams are free for you.'
            }, status=status.HTTP_200_OK)
        
        # Check 2.5: User has specifically unlocked this mock exam
        mock_exam_unlock = ActivationUnlock.objects.filter(
            user=user,
            exam_identifier=f"mock_exam_{exam.id}",
            is_active=True
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
        final_amt = float(exam.fee.get_final_amount())
        return Response({
            'unlocked': False,
            'reason': 'requires_payment',
            'fee_amount': float(exam.fee.fee_amount),
            'final_amount': final_amt,
            'currency': exam.fee.currency,
            'message': f"This exam requires unlock payment of {exam.fee.currency} {final_amt:.2f}"
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """Unlock a mock exam for the student"""
        exam = self.get_object()
        user = request.user
        
        unlock_record, created = ActivationUnlock.objects.get_or_create(
            user=user,
            exam_identifier=f"mock_exam_{exam.id}",
            defaults={'is_active': True}
        )
        if not unlock_record.is_active:
            unlock_record.is_active = True
            unlock_record.save(update_fields=['is_active'])
            
        return Response({
            'status': 'success',
            'unlocked': True,
            'message': f"Successfully unlocked {exam.title}"
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
                MockExamResult.objects.get_or_create(
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
    
    def create(self, request, *args, **kwargs):
        """Upsert fee if mock_exam fee already exists"""
        mock_exam_id = request.data.get('mock_exam')
        if mock_exam_id:
            existing_fee = MockExamFee.objects.filter(mock_exam_id=mock_exam_id).first()
            if existing_fee:
                serializer = self.get_serializer(existing_fee, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(serializer.data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Log fee creation"""
        fee = serializer.save()
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=fee.mock_exam,
            action='set_fee',
            description=f"Set fee for {fee.mock_exam.title} ({fee.currency} {fee.fee_amount})"
        )
    
    def perform_update(self, serializer):
        """Log fee update"""
        fee = serializer.save()
        MockExamActivityLog.objects.create(
            admin=self.request.user,
            mock_exam=fee.mock_exam,
            action='update_fee',
            description=f"Updated fee for {fee.mock_exam.title} ({fee.currency} {fee.fee_amount})"
        )


class MockExamExternalPlatformViewSet(viewsets.ModelViewSet):
    """
    ViewSet for configuring external exam platforms (admin only).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = MockExamExternalPlatform.objects.all()
    serializer_class = MockExamExternalPlatformSerializer

    def _resolve_url(self, platform):
        """
        Resolve outbound URL:
        If api_endpoint starts with http:// or https://, use api_endpoint directly.
        Otherwise, safely join platform_url.rstrip('/') and api_endpoint.lstrip('/').
        """
        api_endpoint = (platform.api_endpoint or '').strip()
        platform_url = (platform.platform_url or '').strip()

        if api_endpoint.startswith('http://') or api_endpoint.startswith('https://'):
            return api_endpoint

        if platform_url:
            if api_endpoint:
                return f"{platform_url.rstrip('/')}/{api_endpoint.lstrip('/')}"
            return platform_url

        return api_endpoint

    def _get_headers(self, platform):
        """Build request authentication headers"""
        headers = {
            'Accept': 'application/json',
        }
        if platform.api_key:
            headers['Authorization'] = f'Bearer {platform.api_key}'
            headers['X-API-Key'] = platform.api_key
        if platform.api_secret:
            headers['X-API-Secret'] = platform.api_secret

        if platform.auth_headers and isinstance(platform.auth_headers, dict):
            headers.update(platform.auth_headers)

        return headers

    def _execute_test_connection(self, request, pk=None):
        """Core logic for testing external platform connectivity"""
        platform = self.get_object()
        target_url = self._resolve_url(platform)

        if not target_url:
            return Response({
                'status': 'error',
                'message': 'Connection failed: No valid platform URL or API endpoint configured'
            }, status=status.HTTP_400_BAD_REQUEST)

        headers = self._get_headers(platform)

        try:
            response = requests.get(target_url, headers=headers, timeout=10)
        except requests.exceptions.Timeout:
            return Response({
                'status': 'error',
                'message': 'Connection failed: Request timed out after 10 seconds'
            }, status=status.HTTP_502_BAD_GATEWAY)
        except requests.exceptions.RequestException as e:
            return Response({
                'status': 'error',
                'message': f'Connection failed: {str(e)}'
            }, status=status.HTTP_502_BAD_GATEWAY)

        if 200 <= response.status_code <= 299:
            return Response({
                'status': 'success',
                'message': 'Connection test successful!',
                'http_status': response.status_code
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'error',
                'message': f'Connection failed: External server returned HTTP {response.status_code}',
                'http_status': response.status_code
            }, status=status.HTTP_502_BAD_GATEWAY)

    def _execute_sync_exams(self, request, pk=None):
        """Core logic for syncing/streaming exams from external platform"""
        platform = self.get_object()

        # 1. Verify that platform.is_active and platform.sync_enabled are True
        if not platform.is_active or not platform.sync_enabled:
            return Response({
                'status': 'error',
                'message': 'Sync failed: Platform is inactive or sync is disabled'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Resolve target URL
        target_url = self._resolve_url(platform)
        if not target_url:
            return Response({
                'status': 'error',
                'message': 'Sync failed: No valid platform URL or API endpoint configured'
            }, status=status.HTTP_400_BAD_REQUEST)

        headers = self._get_headers(platform)

        # 3. Send outbound GET request
        try:
            response = requests.get(target_url, headers=headers, timeout=15)
        except requests.exceptions.Timeout:
            return Response({
                'status': 'error',
                'message': 'Sync failed: Request timed out after 15 seconds'
            }, status=status.HTTP_502_BAD_GATEWAY)
        except requests.exceptions.RequestException as e:
            return Response({
                'status': 'error',
                'message': f'Sync failed: {str(e)}'
            }, status=status.HTTP_502_BAD_GATEWAY)

        if not (200 <= response.status_code <= 299):
            return Response({
                'status': 'error',
                'message': f'Sync failed: External platform returned HTTP {response.status_code}',
                'http_status': response.status_code
            }, status=status.HTTP_502_BAD_GATEWAY)

        # 4. Parse JSON
        try:
            payload = response.json()
        except ValueError:
            return Response({
                'status': 'error',
                'message': 'Sync failed: Invalid JSON response from external platform'
            }, status=status.HTTP_502_BAD_GATEWAY)

        if isinstance(payload, dict) and payload.get('status') == 'error':
            return Response({
                'status': 'error',
                'message': f"External platform error: {payload.get('message', 'Unknown error')}"
            }, status=status.HTTP_400_BAD_REQUEST)

        # 5. Extract exam entries
        exam_entries = []
        if isinstance(payload, list):
            exam_entries = payload
        elif isinstance(payload, dict):
            if 'exams' in payload and isinstance(payload['exams'], list):
                exam_entries = payload['exams']
            elif 'exam' in payload and isinstance(payload['exam'], dict):
                exam_entries = [{
                    'exam': payload['exam'],
                    'questions': payload.get('questions', [])
                }]
            elif 'title' in payload:
                exam_entries = [{
                    'exam': payload,
                    'questions': payload.get('questions', [])
                }]
            else:
                exam_entries = [payload]

        synced_exams_count = 0
        synced_questions_count = 0

        with transaction.atomic():
            for item in exam_entries:
                if 'exam' in item and isinstance(item['exam'], dict):
                    exam_data = item['exam']
                    questions_data = item.get('questions') or exam_data.get('questions', [])
                else:
                    exam_data = item
                    questions_data = item.get('questions', [])

                title = (exam_data.get('title') or '').strip()
                external_id = str(exam_data.get('external_id') or exam_data.get('id') or '').strip()
                if not title:
                    ext_title_id = external_id or f"exam_{synced_exams_count + 1}"
                    title = f"{platform.platform_name} Mock Exam {ext_title_id}"

                duration = int(exam_data.get('duration') or exam_data.get('total_duration_minutes') or 60)
                duration = max(5, min(480, duration))

                total_marks = int(exam_data.get('total_marks') or 100)
                passing_marks = int(exam_data.get('passing_marks') or (total_marks // 2))
                is_active = bool(exam_data.get('is_active', True))
                category = (exam_data.get('category') or exam_data.get('subject_area') or platform.platform_name).strip()
                difficulty = exam_data.get('difficulty_level') or exam_data.get('difficulty') or 'medium'
                if difficulty not in ['easy', 'medium', 'hard', 'mixed']:
                    difficulty = 'medium'
                instructions = exam_data.get('instructions') or f"Instructions for {title}"
                description = exam_data.get('description') or f"Mock exam streamed from {platform.platform_name}"

                mock_exam = None
                if external_id:
                    mock_exam = CustomMockExam.objects.filter(
                        external_platform=platform,
                        external_exam_id=external_id
                    ).first()

                if not mock_exam:
                    mock_exam = CustomMockExam.objects.filter(title=title).first()

                if mock_exam:
                    mock_exam.title = title
                    mock_exam.description = description
                    mock_exam.instructions = instructions
                    mock_exam.total_duration_minutes = duration
                    mock_exam.total_marks = total_marks
                    mock_exam.passing_marks = passing_marks
                    mock_exam.difficulty_level = difficulty
                    mock_exam.subject_area = category
                    mock_exam.is_streaming = True
                    mock_exam.external_platform = platform
                    if external_id:
                        mock_exam.external_exam_id = external_id
                    mock_exam.external_exam_url = target_url
                    mock_exam.is_published = is_active
                    mock_exam.is_active = is_active
                    mock_exam.status = 'published' if is_active else 'draft'
                    mock_exam.save()
                else:
                    mock_exam = CustomMockExam.objects.create(
                        admin=request.user if (request.user and request.user.is_authenticated) else None,
                        title=title,
                        description=description,
                        instructions=instructions,
                        total_duration_minutes=duration,
                        total_marks=total_marks,
                        passing_marks=passing_marks,
                        difficulty_level=difficulty,
                        subject_area=category,
                        is_streaming=True,
                        external_platform=platform,
                        external_exam_id=external_id or None,
                        external_exam_url=target_url,
                        is_published=is_active,
                        is_active=is_active,
                        status='published' if is_active else 'draft',
                    )

                # Ensure default fee exists
                MockExamFee.objects.get_or_create(
                    mock_exam=mock_exam,
                    defaults={'fee_amount': 0, 'currency': 'NGN', 'discount_percentage': 0}
                )

                synced_exams_count += 1

                # Group questions by subject
                if questions_data and isinstance(questions_data, list):
                    questions_by_subj = {}
                    for q in questions_data:
                        if not isinstance(q, dict):
                            continue
                        s_name = (q.get('subject') or q.get('subject_name') or category or 'General').strip()
                        questions_by_subj.setdefault(s_name, []).append(q)

                    time_per_subj = max(5, duration // max(1, len(questions_by_subj)))

                    for subj_idx, (s_name, s_questions) in enumerate(questions_by_subj.items()):
                        subject_obj, _ = MockExamSubject.objects.get_or_create(
                            mock_exam=mock_exam,
                            subject_name=s_name,
                            defaults={
                                'order': subj_idx,
                                'num_questions': max(1, len(s_questions)),
                                'time_allocation_minutes': time_per_subj,
                                'marks_per_question': 1,
                            }
                        )
                        subject_obj.num_questions = max(1, len(s_questions))
                        subject_obj.time_allocation_minutes = time_per_subj
                        subject_obj.order = subj_idx
                        subject_obj.save()

                        for q_idx, q_item in enumerate(s_questions):
                            q_text = (q_item.get('question') or q_item.get('question_text') or '').strip()
                            if not q_text:
                                continue

                            q_marks = int(q_item.get('marks') or 1)
                            q_explanation = (q_item.get('explanation') or '').strip()
                            q_answer = str(q_item.get('answer') or '').strip().upper()
                            q_diff = q_item.get('difficulty') or difficulty
                            if q_diff not in ['easy', 'medium', 'hard']:
                                q_diff = 'medium'

                            q_obj = MockExamQuestion.objects.filter(
                                subject=subject_obj,
                                question_text=q_text
                            ).first()

                            if not q_obj:
                                q_obj = MockExamQuestion.objects.create(
                                    subject=subject_obj,
                                    question_text=q_text,
                                    question_type='multiple_choice',
                                    difficulty=q_diff,
                                    marks=max(1, q_marks),
                                    explanation=q_explanation,
                                    order=q_idx,
                                )
                            else:
                                q_obj.marks = max(1, q_marks)
                                q_obj.explanation = q_explanation
                                q_obj.difficulty = q_diff
                                q_obj.order = q_idx
                                q_obj.save()

                            synced_questions_count += 1

                            raw_options = q_item.get('options') or []
                            existing_options = {opt.option_letter.upper(): opt for opt in q_obj.options.all()}
                            letters_used = set()

                            for opt_idx, opt_data in enumerate(raw_options):
                                if isinstance(opt_data, str):
                                    opt_letter = chr(65 + opt_idx)
                                    opt_text = opt_data.strip()
                                    is_corr = (opt_letter == q_answer)
                                elif isinstance(opt_data, dict):
                                    opt_letter = str(opt_data.get('key') or opt_data.get('letter') or chr(65 + opt_idx)).strip().upper()
                                    opt_text = str(opt_data.get('text') or opt_data.get('option_text') or '').strip()
                                    is_corr = bool(opt_data.get('is_correct') or (opt_letter == q_answer))
                                else:
                                    continue

                                letters_used.add(opt_letter)

                                if opt_letter in existing_options:
                                    opt = existing_options[opt_letter]
                                    opt.option_text = opt_text
                                    opt.is_correct = is_corr
                                    opt.order = opt_idx
                                    opt.save()
                                else:
                                    MockExamOption.objects.create(
                                        question=q_obj,
                                        option_letter=opt_letter,
                                        option_text=opt_text,
                                        is_correct=is_corr,
                                        order=opt_idx,
                                    )

                            for letter, opt in existing_options.items():
                                if letter not in letters_used and (not opt.option_text or not opt.option_text.strip()):
                                    opt.delete()

        # Update last_sync_time
        platform.last_sync_time = timezone.now()
        platform.save(update_fields=['last_sync_time'])

        # Log activity
        MockExamActivityLog.objects.create(
            admin=request.user if (request.user and request.user.is_authenticated) else None,
            action='sync_platform',
            description=f"Synced {synced_exams_count} exam(s) and {synced_questions_count} question(s) from {platform.platform_name}",
            change_details={
                'platform': platform.platform_name,
                'synced_exams': synced_exams_count,
                'synced_questions': synced_questions_count,
            }
        )

        return Response({
            'status': 'success',
            'message': f"Successfully synced {synced_exams_count} exam(s) and {synced_questions_count} question(s) from {platform.platform_name}!",
            'synced_exams': synced_exams_count,
            'synced_questions': synced_questions_count,
            'last_sync_time': platform.last_sync_time.isoformat(),
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='test-connection')
    def test_connection(self, request, pk=None):
        """Test connection to external platform (kebab-case URL)"""
        return self._execute_test_connection(request, pk)

    @action(detail=True, methods=['post'], url_path='test_connection')
    def test_connection_alias(self, request, pk=None):
        """Test connection to external platform (snake_case alias)"""
        return self._execute_test_connection(request, pk)

    @action(detail=True, methods=['post'], url_path='sync-exams')
    def sync_exams(self, request, pk=None):
        """Sync exams from external platform (kebab-case URL)"""
        return self._execute_sync_exams(request, pk)

    @action(detail=True, methods=['post'], url_path='sync_exams')
    def sync_exams_alias(self, request, pk=None):
        """Sync exams from external platform (snake_case alias)"""
        return self._execute_sync_exams(request, pk)


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
        mock_exam = serializer.validated_data.get('mock_exam')
        total_marks = 0
        if mock_exam:
            total_marks = mock_exam.total_marks or mock_exam.subjects.aggregate(
                total=Sum('questions__marks')
            )['total'] or 0

        attempt = serializer.save(user=self.request.user, total_marks=total_marks)

        # Pre-populate MockExamResult records for all questions
        if mock_exam:
            for subject in mock_exam.subjects.all():
                for question in subject.questions.all():
                    MockExamResult.objects.get_or_create(
                        attempt=attempt,
                        question=question
                    )

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """Get results for this attempt"""
        attempt = self.get_object()
        serializer = MockExamAttemptDetailSerializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit exam attempt with student answers and calculate score.
        Expects: {answers: {question_id: option_id}, time_spent: int} or time_spent_seconds
        """
        attempt = self.get_object()

        if attempt.is_submitted:
            return Response(
                {'detail': 'Exam has already been submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        answers = request.data.get('answers', {})  # {question_id: option_id}
        time_spent = request.data.get('time_spent_seconds') or request.data.get('time_spent', 0)

        obtained_marks = 0

        # Score answers and update MockExamResult records
        for question_id_str, selected_option_id in answers.items():
            try:
                question_id = int(question_id_str)
                question = MockExamQuestion.objects.get(id=question_id)
                selected_option = MockExamOption.objects.filter(
                    id=selected_option_id,
                    question=question
                ).first()

                is_correct = bool(selected_option and selected_option.is_correct)
                q_marks = question.marks if is_correct else 0
                obtained_marks += q_marks

                MockExamResult.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        'selected_option': selected_option,
                        'is_correct': is_correct,
                        'marks_obtained': q_marks,
                        'attempted': bool(selected_option_id),
                    }
                )
            except Exception as e:
                logger.warning(f"Error scoring question {question_id_str}: {e}")

        # Compute percentage and grade
        total_marks = attempt.total_marks or (attempt.mock_exam.total_marks if attempt.mock_exam else 100) or 1
        percentage = (obtained_marks / total_marks * 100) if total_marks > 0 else 0
        passing_marks = (attempt.mock_exam.passing_marks if attempt.mock_exam else (total_marks * 0.5)) or (total_marks * 0.5)
        passed = obtained_marks >= passing_marks

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

        attempt.obtained_marks = obtained_marks
        attempt.percentage = percentage
        attempt.grade = grade
        attempt.passed = passed
        attempt.is_submitted = True
        attempt.status = 'completed'
        attempt.end_time = timezone.now()
        attempt.time_spent_seconds = time_spent
        attempt.save()

        # Update exam overall statistics
        if attempt.mock_exam:
            exam = attempt.mock_exam
            completed_attempts = MockExamAttempt.objects.filter(mock_exam=exam, status='completed')
            exam.total_attempts = completed_attempts.count()
            avg_score = completed_attempts.aggregate(Avg('percentage'))['percentage__avg'] or 0
            exam.avg_score = avg_score
            exam.save(update_fields=['total_attempts', 'avg_score'])

        serializer = MockExamAttemptDetailSerializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)
