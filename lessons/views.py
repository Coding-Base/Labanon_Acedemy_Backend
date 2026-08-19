# backend/lessons/views.py
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils import timezone
import json

from users.permissions import IsMasterAdmin
from .models import Category, Subject, LessonSubfolder, Topic, LessonContent, StudentLessonProgress, LessonSearch
from .serializers import (
    CategorySerializer, SubjectSerializer, LessonSubfolderSerializer, TopicSerializer, LessonContentSerializer,
    StudentLessonProgressSerializer, LessonSearchSerializer,
    SubjectFolderSerializer, TopicDetailSerializer
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for lesson categories.
    - Master admin can create/update/delete categories
    - Everyone can list active categories
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    pagination_class = None  # Categories are few, no pagination needed
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['order', 'name', 'created_at']
    ordering = ['order', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        # Admin sees all categories including inactive; public only active
        if self.request.user.is_authenticated and (
            self.request.user.is_staff or
            (hasattr(self.request.user, 'is_master_admin') and self.request.user.is_master_admin)
        ):
            return Category.objects.all().order_by('order', 'name')
        return Category.objects.filter(is_active=True).order_by('order', 'name')


class SubjectViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Subjects
    - Admin can create/update/delete subjects
    - Everyone can list subjects
    """
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]  # Allow authenticated users
        else:
            permission_classes = [permissions.AllowAny]

        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        # Mark manually created subjects
        serializer.save(is_custom=True)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def folder_view(self, request, pk=None):
        """Get subject with all its topics (folder view)"""
        try:
            subject = Subject.objects.get(pk=pk)
            serializer = SubjectFolderSerializer(subject)
            return Response(serializer.data)
        except Subject.DoesNotExist:
            return Response({'detail': 'Subject not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def list_subjects_with_topics(self, request):
        """Get all subjects with their topics (for student folder view)"""
        subjects = Subject.objects.prefetch_related('subfolders__topics__lessons').all()
        serializer = SubjectFolderSerializer(subjects, many=True)
        return Response(serializer.data)


class LessonSubfolderViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for lesson subfolders/departments under a subject/folder.
    """
    queryset = LessonSubfolder.objects.select_related('subject').all()
    serializer_class = LessonSubfolderSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['name', 'description', 'subject__name']
    filterset_fields = ['subject']
    ordering_fields = ['name', 'order', 'created_at']
    ordering = ['subject', 'order', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        serializer.save(is_custom=True)


class TopicViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Topics
    - Admin can create/update/delete topics
    - Everyone can list topics
    """
    queryset = Topic.objects.select_related('subject', 'subfolder').all()
    serializer_class = TopicSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['name', 'description', 'subject__name', 'subfolder__name']
    filterset_fields = ['subject', 'subfolder']
    ordering_fields = ['name', 'order', 'created_at']
    ordering = ['order', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]  # Allow authenticated users
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        serializer.save(is_custom=True)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def detail_view(self, request, pk=None):
        """Get topic with all its lessons"""
        try:
            topic = Topic.objects.get(pk=pk)
            serializer = TopicDetailSerializer(topic)
            return Response(serializer.data)
        except Topic.DoesNotExist:
            return Response({'detail': 'Topic not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], permission_classes=[IsMasterAdmin])
    def by_subject(self, request):
        """Get topics for a specific subject"""
        subject_id = request.query_params.get('subject_id')
        if not subject_id:
            return Response({'detail': 'subject_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        topics = Topic.objects.filter(subject_id=subject_id).select_related('subject', 'subfolder').order_by('order', 'name')
        serializer = TopicSerializer(topics, many=True)
        return Response(serializer.data)


class LessonContentViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Lesson Content
    - Admin can create/update/delete lessons
    - Students can view published lessons
    """
    queryset = LessonContent.objects.filter(is_published=True)
    serializer_class = LessonContentSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'content', 'tags', 'topic__name', 'topic__subfolder__name', 'topic__subject__name']
    filterset_fields = ['topic', 'topic__subfolder', 'topic__subject', 'is_published']
    ordering_fields = ['order', 'created_at', 'published_date']
    ordering = ['order', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]  # Allow authenticated users
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        if isinstance(self.request.user, type) or not self.request.user.is_authenticated:
            # Anonymous user - show only published
            return LessonContent.objects.select_related('topic__subject', 'topic__subfolder').filter(is_published=True).order_by('order', 'created_at')
        
        # Authenticated user - show all if admin, only published otherwise
        if self.request.user.is_staff or (hasattr(self.request.user, 'is_master_admin') and self.request.user.is_master_admin):
            return LessonContent.objects.select_related('topic__subject', 'topic__subfolder').all().order_by('order', 'created_at')
        
        return LessonContent.objects.select_related('topic__subject', 'topic__subfolder').filter(is_published=True).order_by('order', 'created_at')

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_as_viewed(self, request, pk=None):
        """Mark lesson as viewed by student"""
        try:
            lesson = LessonContent.objects.get(pk=pk)
            progress, created = StudentLessonProgress.objects.get_or_create(
                student=request.user,
                lesson=lesson
            )
            progress.is_viewed = True
            progress.first_viewed_at = progress.first_viewed_at or timezone.now()
            progress.save()
            
            serializer = StudentLessonProgressSerializer(progress)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except LessonContent.DoesNotExist:
            return Response({'detail': 'Lesson not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_as_completed(self, request, pk=None):
        """Mark lesson as completed by student"""
        try:
            lesson = LessonContent.objects.get(pk=pk)
            time_spent = request.data.get('time_spent_seconds', 0)
            
            progress, created = StudentLessonProgress.objects.get_or_create(
                student=request.user,
                lesson=lesson
            )
            progress.is_completed = True
            progress.is_viewed = True
            progress.completed_at = progress.completed_at or timezone.now()
            progress.time_spent_seconds = max(progress.time_spent_seconds, int(time_spent))
            progress.save()
            
            serializer = StudentLessonProgressSerializer(progress)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except LessonContent.DoesNotExist:
            return Response({'detail': 'Lesson not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_progress(self, request):
        """Get student's lesson progress"""
        progress = StudentLessonProgress.objects.filter(student=request.user).order_by('-updated_at')
        page = self.paginate_queryset(progress)
        if page is not None:
            serializer = StudentLessonProgressSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = StudentLessonProgressSerializer(progress, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def search(self, request):
        """Search lessons by title, tag, topic, subfolder, or subject"""
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'detail': 'Search query is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Track the search
        results = LessonContent.objects.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__icontains=query) |
            Q(topic__name__icontains=query) |
            Q(topic__subfolder__name__icontains=query) |
            Q(topic__subject__name__icontains=query),
            is_published=True
        ).select_related('topic__subject', 'topic__subfolder').distinct()
        
        if request.user.is_authenticated:
            LessonSearch.objects.create(
                student=request.user,
                search_query=query,
                results_count=results.count()
            )
        
        page = self.paginate_queryset(results)
        if page is not None:
            serializer = LessonContentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = LessonContentSerializer(results, many=True)
        return Response(serializer.data)


class StudentLessonProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Track student progress on lessons (read-only for everyone)
    Students can only see their own progress
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StudentLessonProgressSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    filterset_fields = ['is_viewed', 'is_completed']
    ordering_fields = ['updated_at', 'completed_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        # Students only see their own progress
        return StudentLessonProgress.objects.filter(student=self.request.user)


class LessonAnalyticsAPIView(viewsets.ViewSet):
    """Analytics endpoints for lesson usage"""
    permission_classes = [IsMasterAdmin]

    @action(detail=False, methods=['get'])
    def subject_stats(self, request):
        """Get statistics about subjects and topics"""
        subjects = Subject.objects.all()
        stats = []
        for subject in subjects:
            topics_count = subject.topics.count()
            lessons_count = LessonContent.objects.filter(topic__subject=subject, is_published=True).count()
            views = StudentLessonProgress.objects.filter(lesson__topic__subject=subject, is_viewed=True).count()
            
            stats.append({
                'subject_id': subject.id,
                'subject_name': subject.name,
                'subfolders_count': subject.subfolders.count(),
                'topics_count': topics_count,
                'lessons_count': lessons_count,
                'total_views': views,
                'created_at': subject.created_at
            })
        
        return Response(stats)

    @action(detail=False, methods=['get'])
    def student_engagement(self, request):
        """Get student engagement metrics"""
        total_students = StudentLessonProgress.objects.values('student').distinct().count()
        viewed_lessons = StudentLessonProgress.objects.filter(is_viewed=True).count()
        completed_lessons = StudentLessonProgress.objects.filter(is_completed=True).count()
        
        return Response({
            'total_students_engaged': total_students,
            'total_views': viewed_lessons,
            'total_completions': completed_lessons,
            'avg_views_per_student': round(viewed_lessons / total_students, 2) if total_students > 0 else 0
        })

    @action(detail=False, methods=['get'])
    def top_lessons(self, request):
        """Get top 10 most viewed lessons"""
        from django.db.models import Count
        
        lessons = LessonContent.objects.annotate(
            view_count=Count('student_progress', filter=Q(student_progress__is_viewed=True))
        ).order_by('-view_count')[:10]
        
        serializer = LessonContentSerializer(lessons, many=True)
        return Response(serializer.data)
