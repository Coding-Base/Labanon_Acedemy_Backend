from rest_framework import viewsets, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.db.models import Q, Count
from rest_framework.exceptions import ValidationError
from datetime import timedelta
import random
import csv
import io
import json
import re

from .models import Country, ExamFolder, FolderExam, FolderSubject, Question, QuestionAssignment, Choice, Exam, ExamAttempt, Subject, StudentAnswer
from .permissions import CanManageExamLibrary
from .serializers import (
    CountrySerializer, ExamFolderSerializer, QuestionSerializer, ChoiceSerializer, ExamSerializer,
    ExamAttemptListSerializer, ExamAttemptDetailSerializer,
    ExamAttemptCreateSerializer, StudentAnswerSerializer,
    SubmitAnswerSerializer, SubjectSerializer
)
from .math_utils import format_math_question
from users.permissions import IsMasterAdmin
from courses.models import ActivationUnlock


def detect_year_from_text(text: str) -> str:
    """Extract a 4-digit exam year (1980-2035) from text or identifier."""
    if not text:
        return None
    matches = re.findall(r'\b(19[89]\d|20[0-3]\d)\b', str(text))
    if matches:
        return str(matches[0])
    return None


def detect_question_year(question) -> str:
    """
    Detect the most appropriate year for a question from text or explanation.
    Never falls back to upload date (created_at) to avoid corrupting question years.
    """
    y = detect_year_from_text(getattr(question, 'text', ''))
    if y:
        return y
    y = detect_year_from_text(getattr(question, 'explanation', ''))
    if y:
        return y
    return None


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


def student_visible_queryset(queryset):
    """Apply the shared publication and availability rules for student content."""
    now = timezone.now()
    return queryset.filter(
        is_visible=True,
    ).filter(
        Q(available_from__isnull=True) | Q(available_from__lte=now)
    ).filter(
        Q(status='published') | Q(status='scheduled', available_from__lte=now)
    ).filter(
        Q(available_until__isnull=True) | Q(available_until__gt=now)
    )


def student_visible_window_filter():
    now = timezone.now()
    return (
        Q(is_visible=True)
        & (Q(available_from__isnull=True) | Q(available_from__lte=now))
        & (Q(status='published') | Q(status='scheduled', available_from__lte=now))
        & (Q(available_until__isnull=True) | Q(available_until__gt=now))
    )


class ExamLibraryView(APIView):
    """Return the published, tag-filterable folder library for the student portal."""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        country_ids = [value for value in request.query_params.get('country', '').split(',') if value]
        year = request.query_params.get('year', '').strip()
        exam_type = request.query_params.get('exam_type', '').strip()
        institution = request.query_params.get('institution', '').strip()
        provider = request.query_params.get('provider', '').strip()
        subject_query = request.query_params.get('subject', '').strip()
        difficulty = request.query_params.get('difficulty', '').strip()
        visible = student_visible_window_filter()
        countries = Country.objects.filter(visible).order_by('sort_order', 'name')
        folders = list(
            ExamFolder.objects.filter(visible)
            .select_related('country', 'parent').prefetch_related('country_tags')
            .order_by('sort_order', 'name')
        )
        folder_ids = [folder.id for folder in folders]
        exam_links = list(
            FolderExam.objects.filter(folder_id__in=folder_ids, exam__in=Exam.objects.filter(visible))
            .select_related('exam').prefetch_related('exam__subjects__questions')
            .annotate(attempt_count=Count('exam__attempts'))
            .order_by('sort_order', 'created_at')
        )
        legacy_folder_exams = list(
            Exam.objects.filter(visible, folder_id__in=folder_ids)
            .prefetch_related('subjects__questions')
            .annotate(attempt_count=Count('attempts'))
            .order_by('sort_order', 'title')
        )
        subject_links = list(
            FolderSubject.objects.filter(folder_id__in=folder_ids, subject__exam__in=Exam.objects.filter(visible))
            .select_related('subject__exam').prefetch_related('subject__questions')
            .order_by('sort_order', 'created_at')
        )

        if country_ids:
            selected_country_ids = {int(value) for value in country_ids if value.isdigit()}
        else:
            selected_country_ids = set()

        def matches_exam(exam, extra_subjects=()):
            values = [exam.title, exam.description, exam.institution, exam.provider, exam.exam_type, exam.year, exam.difficulty]
            values.extend(subject.name for subject in exam.subjects.all())
            values.extend(subject.name for subject in extra_subjects)
            haystack = ' '.join(str(value or '') for value in values).lower()
            if query and query.lower() not in haystack:
                return False
            if year and exam.year != year:
                return False
            if exam_type and exam.exam_type.lower() != exam_type.lower():
                return False
            if institution and institution.lower() not in exam.institution.lower():
                return False
            if provider and provider.lower() not in exam.provider.lower():
                return False
            if difficulty and exam.difficulty.lower() != difficulty.lower():
                return False
            if subject_query and not any(subject_query.lower() in subject.name.lower() for subject in exam.subjects.all()):
                return False
            return True

        full_exams_by_folder = {}
        subject_links_by_folder = {}
        for link in exam_links:
            if matches_exam(link.exam):
                full_exams_by_folder.setdefault(link.folder_id, {})[link.exam_id] = link.exam
        for exam in legacy_folder_exams:
            if matches_exam(exam):
                full_exams_by_folder.setdefault(exam.folder_id, {})[exam.id] = exam
        for link in subject_links:
            if matches_exam(link.subject.exam, [link.subject]):
                subject_links_by_folder.setdefault(link.folder_id, []).append(link)

        children_by_parent = {}
        for folder in folders:
            children_by_parent.setdefault(folder.parent_id, []).append(folder)

        def build_folder(folder):
            children = []
            for child in children_by_parent.get(folder.id, []):
                child_data = build_folder(child)
                if child_data:
                    children.append(child_data)
            folder_tags = list(folder.country_tags.all())
            if not folder_tags and folder.country_id:
                folder_tags = [folder.country]
            tag_matches = not selected_country_ids or bool({tag.id for tag in folder_tags} & selected_country_ids)
            folder_text = ' '.join([folder.name, folder.description, *[tag.name for tag in folder_tags]]).lower()
            folder_matches = bool(query and query.lower() in folder_text)
            full_exams = list(full_exams_by_folder.get(folder.id, {}).values()) if tag_matches else []
            selected_links = subject_links_by_folder.get(folder.id, []) if tag_matches else []
            if not (folder_matches and tag_matches or full_exams or selected_links or children):
                return None
            full_exam_ids = {exam.id for exam in full_exams}
            subject_entries = [
                {
                    'id': link.id,
                    'subject': SubjectSerializer(link.subject, context={'request': request}).data,
                    'exam': ExamSerializer(link.subject.exam, context={'request': request}).data,
                    'sort_order': link.sort_order,
                }
                for link in selected_links if link.subject.exam_id not in full_exam_ids
            ]
            data = {
                **ExamFolderSerializer(folder, context={'request': request}).data,
                'children': children,
                'exams': [ExamSerializer(exam, context={'request': request}).data for exam in full_exams],
                'subject_entries': subject_entries,
            }
            return data

        result = [build_folder(folder) for folder in children_by_parent.get(None, [])]
        result = [folder for folder in result if folder]
        return Response({
            'results': result,
            'folders': result,
            'countries': CountrySerializer(countries, many=True, context={'request': request}).data,
            'query': query,
        })


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticatedOrReadOnly()]
        return [CanManageExamLibrary()]

    def get_queryset(self):
        queryset = super().get_queryset().order_by('sort_order', 'name')
        if self.request.method in permissions.SAFE_METHODS and not CanManageExamLibrary().has_permission(self.request, self):
            return queryset.filter(student_visible_window_filter())
        return queryset

    def perform_destroy(self, instance):
        if instance.tagged_folders.exists() or instance.legacy_folders.exists():
            instance.status = 'archived'
            instance.is_visible = False
            instance.save(update_fields=['status', 'is_visible', 'updated_at'])
        else:
            instance.delete()


class ExamFolderViewSet(viewsets.ModelViewSet):
    queryset = ExamFolder.objects.select_related('country', 'parent').all()
    serializer_class = ExamFolderSerializer
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticatedOrReadOnly()]
        return [CanManageExamLibrary()]

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('country_tags').order_by('sort_order', 'name')
        if self.request.method in permissions.SAFE_METHODS and not CanManageExamLibrary().has_permission(self.request, self):
            return queryset.filter(student_visible_window_filter())
        country_id = self.request.query_params.get('country')
        parent_id = self.request.query_params.get('parent')
        if country_id:
            queryset = queryset.filter(Q(country_tags__id=country_id) | Q(country_id=country_id)).distinct()
        if parent_id == 'root':
            queryset = queryset.filter(parent__isnull=True)
        elif parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        return queryset

    @action(detail=True, methods=['get'])
    def contents(self, request, pk=None):
        folder = self.get_object()
        children = self.get_queryset().filter(parent=folder).order_by('sort_order', 'name')
        exam_links = FolderExam.objects.filter(folder=folder).select_related('exam').prefetch_related('exam__subjects__questions').order_by('sort_order', 'created_at')
        subject_links = FolderSubject.objects.filter(folder=folder).select_related('subject__exam').prefetch_related('subject__questions').order_by('sort_order', 'created_at')
        if not CanManageExamLibrary().has_permission(request, self):
            exam_links = exam_links.filter(exam__in=Exam.objects.filter(student_visible_window_filter()))
            subject_links = subject_links.filter(subject__exam__in=Exam.objects.filter(student_visible_window_filter()))
        return Response({
            'folder': ExamFolderSerializer(folder, context={'request': request}).data,
            'children': ExamFolderSerializer(children, many=True, context={'request': request}).data,
            'exams': ExamSerializer([link.exam for link in exam_links], many=True, context={'request': request}).data,
            'exam_links': [{'id': link.id, 'exam': ExamSerializer(link.exam, context={'request': request}).data, 'sort_order': link.sort_order} for link in exam_links],
            'subject_links': [{'id': link.id, 'subject': SubjectSerializer(link.subject, context={'request': request}).data, 'exam': ExamSerializer(link.subject.exam, context={'request': request}).data, 'sort_order': link.sort_order} for link in subject_links],
        })

    @action(detail=True, methods=['get'], permission_classes=[CanManageExamLibrary])
    def available_content(self, request, pk=None):
        """Browse existing exams and their subjects before linking them to a folder."""
        self.get_object()
        query = request.query_params.get('q', '').strip()
        exams = Exam.objects.prefetch_related('subjects__questions').order_by('title')
        if query:
            exams = exams.filter(
                Q(title__icontains=query) | Q(description__icontains=query) |
                Q(institution__icontains=query) | Q(provider__icontains=query) |
                Q(subjects__name__icontains=query)
            ).distinct()
        return Response(ExamSerializer(exams, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def attach_exam(self, request, pk=None):
        folder = self.get_object()
        exam = get_object_or_404(Exam, pk=request.data.get('exam_id'))
        link, created = FolderExam.objects.get_or_create(
            folder=folder,
            exam=exam,
            defaults={'sort_order': folder.exam_links.count()},
        )
        return Response({'created': created, 'link_id': link.id, 'exam': ExamSerializer(exam, context={'request': request}).data}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def attach_subject(self, request, pk=None):
        folder = self.get_object()
        subject = get_object_or_404(Subject, pk=request.data.get('subject_id'))
        link, created = FolderSubject.objects.get_or_create(
            folder=folder,
            subject=subject,
            defaults={'sort_order': folder.subject_links.count()},
        )
        return Response({'created': created, 'link_id': link.id, 'subject': SubjectSerializer(subject, context={'request': request}).data}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def detach_exam(self, request, pk=None):
        folder = self.get_object()
        deleted, _ = FolderExam.objects.filter(folder=folder, exam_id=request.data.get('exam_id')).delete()
        if not deleted:
            return Response({'detail': 'This exam is not linked to the folder.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def detach_subject(self, request, pk=None):
        folder = self.get_object()
        deleted, _ = FolderSubject.objects.filter(folder=folder, subject_id=request.data.get('subject_id')).delete()
        if not deleted:
            return Response({'detail': 'This subject is not linked to the folder.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def publish(self, request, pk=None):
        folder = self.get_object()
        folder.status = 'published'
        folder.is_visible = True
        folder.status_before_archive = ''
        folder.save(update_fields=['status', 'is_visible', 'status_before_archive', 'updated_at'])
        return Response(self.get_serializer(folder).data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def unpublish(self, request, pk=None):
        folder = self.get_object()
        folder.status = 'draft'
        folder.is_visible = False
        folder.save(update_fields=['status', 'is_visible', 'updated_at'])
        return Response(self.get_serializer(folder).data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def archive(self, request, pk=None):
        folder = self.get_object()
        if folder.status != 'archived':
            folder.status_before_archive = folder.status
        folder.status = 'archived'
        folder.is_visible = False
        folder.save(update_fields=['status', 'is_visible', 'status_before_archive', 'updated_at'])
        return Response(self.get_serializer(folder).data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def unarchive(self, request, pk=None):
        folder = self.get_object()
        restored_status = folder.status_before_archive if folder.status_before_archive in {'draft', 'published', 'scheduled'} else 'draft'
        folder.status = restored_status
        folder.is_visible = restored_status in {'published', 'scheduled'}
        folder.status_before_archive = ''
        folder.save(update_fields=['status', 'is_visible', 'status_before_archive', 'updated_at'])
        return Response(self.get_serializer(folder).data)

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        items = request.data.get('items', [])
        if not isinstance(items, list):
            return Response({'detail': 'items must be an array'}, status=status.HTTP_400_BAD_REQUEST)
        item_ids = [item.get('id') for item in items]
        if len(item_ids) != len(set(item_ids)):
            return Response({'detail': 'items must not contain duplicate folder ids'}, status=status.HTTP_400_BAD_REQUEST)
        folders = list(self.get_queryset().filter(id__in=item_ids))
        if len(folders) != len(item_ids):
            return Response({'detail': 'One or more folders do not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        parent_ids = {folder.parent_id for folder in folders}
        if len(parent_ids) > 1:
            return Response({'detail': 'Folders can only be reordered with their siblings.'}, status=status.HTTP_400_BAD_REQUEST)
        by_id = {folder.id: folder for folder in folders}
        for item in items:
            folder = by_id.get(item.get('id'))
            if folder is not None:
                folder.sort_order = int(item.get('sort_order', 0))
                folder.updated_at = timezone.now()
        ExamFolder.objects.bulk_update(folders, ['sort_order', 'updated_at'])
        return Response(ExamFolderSerializer(folders, many=True, context={'request': request}).data)

    def perform_destroy(self, instance):
        # Folders are discovery containers only. Deleting a folder removes the
        # container and its FolderExam/FolderSubject links through cascade, but
        # must never delete or archive the underlying exams or subjects.
        instance.delete()


class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    @action(detail=False, methods=['get'])
    def popular(self, request):
        exams = self.get_queryset().order_by('-attempt_count', 'title')[:6]
        serializer = self.get_serializer(exams, many=True)
        return Response(serializer.data)

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticatedOrReadOnly()]
        return [CanManageExamLibrary()]

    def get_queryset(self):
        queryset = Exam.objects.select_related('folder__country').prefetch_related('subjects__questions').annotate(
            attempt_count=Count('attempts')
        )
        if self.request.method in permissions.SAFE_METHODS and not CanManageExamLibrary().has_permission(self.request, self):
            queryset = queryset.filter(student_visible_window_filter())
        return queryset.order_by('sort_order', 'title')

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.status = 'published'
        exam.is_visible = True
        exam.save(update_fields=['status', 'is_visible', 'updated_at'])
        return Response(self.get_serializer(exam).data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def schedule(self, request, pk=None):
        exam = self.get_object()
        available_from = request.data.get('available_from', exam.available_from)
        if not available_from:
            return Response({'available_from': 'A scheduled exam requires an availability date.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(exam, data={
            'status': 'scheduled',
            'is_visible': request.data.get('is_visible', True),
            'available_from': available_from,
            'available_until': request.data.get('available_until', exam.available_until),
        }, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def archive(self, request, pk=None):
        exam = self.get_object()
        exam.status = 'archived'
        exam.is_visible = False
        exam.save(update_fields=['status', 'is_visible', 'updated_at'])
        return Response(self.get_serializer(exam).data)

    @action(detail=True, methods=['get'], permission_classes=[CanManageExamLibrary])
    def preview(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def perform_destroy(self, instance):
        if instance.attempts.exists() or instance.subjects.exists():
            instance.status = 'archived'
            instance.is_visible = False
            instance.save(update_fields=['status', 'is_visible', 'updated_at'])
        else:
            instance.delete()

    @action(detail=True, methods=['get'])
    def subjects(self, request, pk=None):
        """Get all subjects for a specific exam"""
        exam = self.get_object()
        subjects = exam.subjects.all()
        serializer = SubjectSerializer(subjects, many=True)
        return Response(serializer.data)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticatedOrReadOnly()]
        return [CanManageExamLibrary()]

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Get all questions for a specific subject with pagination and optional year filter"""
        subject = self.get_object()
        questions = Question.objects.filter(
            Q(subject=subject) | Q(assignments__subject=subject)
        ).distinct()
        
        # Filter by year if specified
        year_filter = request.query_params.get('year')
        if year_filter == 'unassigned':
            questions = questions.filter(Q(year__isnull=True) | Q(year=''))
        elif year_filter:
            questions = questions.filter(year=year_filter)
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_questions = paginator.paginate_queryset(questions, request)
        serializer = QuestionSerializer(paginated_questions, many=True)
        
        return paginator.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def available_years(self, request, pk=None):
        """Get all distinct years for this subject.
        Unassigned questions are mapped to default '2021' for student visibility,
        while unassigned_count is reported for admin notifications.
        """
        subject = self.get_object()
        from django.db.models import Count, Q

        DEFAULT_FALLBACK_YEAR = "2021"

        explicit_year_data = list(
            Question.objects.filter(Q(subject=subject) | Q(assignments__subject=subject)).distinct()
            .exclude(Q(year__isnull=True) | Q(year=''))
            .values('year')
            .annotate(question_count=Count('id'))
            .order_by('-year')
        )

        unassigned_count = Question.objects.filter(Q(subject=subject) | Q(assignments__subject=subject)).filter(
            Q(year__isnull=True) | Q(year='')
        ).count()

        years_dict = {item['year']: item['question_count'] for item in explicit_year_data}
        if unassigned_count > 0:
            years_dict[DEFAULT_FALLBACK_YEAR] = years_dict.get(DEFAULT_FALLBACK_YEAR, 0) + unassigned_count

        student_years = [
            {'year': y, 'question_count': count}
            for y, count in sorted(years_dict.items(), key=lambda x: str(x[0]), reverse=True)
        ]

        return Response({
            'subject_id': subject.id,
            'subject_name': subject.name,
            'years': student_years,
            'explicit_years': [item['year'] for item in explicit_year_data],
            'total_questions': Question.objects.filter(Q(subject=subject) | Q(assignments__subject=subject)).distinct().count(),
            'unassigned_count': unassigned_count,
            'default_fallback_year': DEFAULT_FALLBACK_YEAR
        })

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def auto_assign_years(self, request, pk=None):
        """Auto-detect and assign years to all unassigned questions in this subject.
        Uses embedded year patterns in text/explanation or falls back to upload date (created_at).
        """
        subject = self.get_object()
        from django.db.models import Q
        unassigned_qs = subject.questions.filter(Q(year__isnull=True) | Q(year=''))
        total_unassigned = unassigned_qs.count()

        breakdown = {}
        updated_count = 0

        for q in unassigned_qs:
            detected_year = detect_question_year(q)
            if detected_year:
                q.year = detected_year
                q.save(update_fields=['year'])
                updated_count += 1
                breakdown[detected_year] = breakdown.get(detected_year, 0) + 1

        return Response({
            'message': f'Successfully upgraded and assigned {updated_count} question(s) to their respective years.',
            'subject_id': subject.id,
            'subject_name': subject.name,
            'total_processed': total_unassigned,
            'updated_count': updated_count,
            'breakdown': breakdown,
            'remaining_unassigned': subject.questions.filter(Q(year__isnull=True) | Q(year='')).count()
        }, status=status.HTTP_200_OK)


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticatedOrReadOnly()]
        return [CanManageExamLibrary()]

    @action(detail=True, methods=['post'], permission_classes=[CanManageExamLibrary])
    def assign_subjects(self, request, pk=None):
        """Attach a bank question to additional subjects without changing its owner."""
        question = self.get_object()
        subject_ids = request.data.get('subject_ids', [])
        if not isinstance(subject_ids, list):
            return Response({'detail': 'subject_ids must be an array'}, status=status.HTTP_400_BAD_REQUEST)
        subjects = list(Subject.objects.filter(id__in=subject_ids))
        if len(subjects) != len(set(subject_ids)):
            return Response({'detail': 'One or more subjects do not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        for subject in subjects:
            QuestionAssignment.objects.get_or_create(question=question, subject=subject)
        return Response({'question_id': question.id, 'subject_ids': [subject.id for subject in subjects]})

    @action(detail=True, methods=['post'])
    def update_choices(self, request, pk=None):
        """Update all choices for a question and set the correct answer.
        
        Expected payload:
        {
          "choices": [
            {"text": "Option A", "is_correct": false},
            {"text": "Option B", "is_correct": true},
            {"text": "Option C", "is_correct": false},
            {"text": "Option D", "is_correct": false}
          ],
          "text": "Updated question text (optional)",
          "explanation": "Updated explanation (optional)"
        }
        """
        question = self.get_object()
        choices_data = request.data.get('choices', [])
        question_text = request.data.get('text')
        explanation = request.data.get('explanation')

        # Validate choices
        if not choices_data or not isinstance(choices_data, list):
            return Response(
                {'detail': 'choices array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(choices_data) < 2:
            return Response(
                {'detail': 'At least 2 choices are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check that exactly one choice is marked as correct
        correct_count = sum(1 for c in choices_data if c.get('is_correct', False))
        if correct_count != 1:
            return Response(
                {'detail': 'Exactly one choice must be marked as correct'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check that all choices have text
        if not all(c.get('text', '').strip() for c in choices_data):
            return Response(
                {'detail': 'All choices must have non-empty text'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Update question text/explanation if provided
            if question_text:
                question.text = question_text.strip()
            if explanation is not None:
                question.explanation = explanation

            # Delete old choices
            question.choices.all().delete()

            # Create new choices
            for choice_data in choices_data:
                Choice.objects.create(
                    question=question,
                    text=choice_data.get('text', '').strip(),
                    is_correct=choice_data.get('is_correct', False)
                )

            # Save question
            question.save()

            serializer = self.get_serializer(question)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'detail': f'Error updating choices: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], permission_classes=[CanManageExamLibrary])
    def auto_assign_all_years(self, request):
        """Auto-detect and assign years to ALL unassigned questions across all subjects."""
        from django.db.models import Q
        unassigned_qs = Question.objects.filter(Q(year__isnull=True) | Q(year=''))
        total_unassigned = unassigned_qs.count()

        breakdown = {}
        updated_count = 0

        for q in unassigned_qs:
            detected_year = detect_question_year(q)
            if detected_year:
                q.year = detected_year
                q.save(update_fields=['year'])
                updated_count += 1
                breakdown[detected_year] = breakdown.get(detected_year, 0) + 1

        return Response({
            'message': f'Successfully upgraded and assigned {updated_count} question(s) across all subjects.',
            'total_processed': total_unassigned,
            'updated_count': updated_count,
            'breakdown': breakdown,
            'remaining_unassigned': Question.objects.filter(Q(year__isnull=True) | Q(year='')).count()
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[CanManageExamLibrary])
    def bulk_assign_year(self, request):
        """Bulk assign a specific year to a list of question IDs."""
        question_ids = request.data.get('question_ids', [])
        year = str(request.data.get('year', '')).strip()

        if not question_ids or not isinstance(question_ids, list):
            return Response({'detail': 'question_ids array is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not year:
            return Response({'detail': 'year is required'}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = Question.objects.filter(id__in=question_ids).update(year=year)
        return Response({
            'message': f'Successfully assigned year {year} to {updated_count} question(s).',
            'updated_count': updated_count,
            'year': year
        }, status=status.HTTP_200_OK)


class BulkQuestionUploadView(APIView):
    """Accept JSON bulk uploads of questions in the specified format.

    Expected payload:
    {
      "exam_id": "JAMB",  // or exam slug
      "subject": "Chemistry",  // subject name
      "year": 2024,
      "questions": [
        {
          "question_text": "...",
          "options": {
            "A": "...",
            "B": "...",
            "C": "...",
            "D": "..."
          },
          "correct_answer": "A",
          "explanation": "...",
          "subject": "Chemistry"
        },
        ...
      ]
    }
    Also supports CSV/Excel file upload via multipart/form-data.
    """
    permission_classes = [CanManageExamLibrary]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        # Check if file upload
        if 'file' in request.FILES:
            return self.handle_file_upload(request)
        
        return self.handle_json_upload(request)

    def handle_json_upload(self, request):
        data = request.data
        exam_id = data.get('exam_id')
        subject_name = data.get('subject')  # Top-level subject field
        year = data.get('year')
        questions_list = data.get('questions', [])

        if not exam_id:
            return Response(
                {'detail': 'exam_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not questions_list:
            return Response(
                {'detail': 'questions array is required and cannot be empty'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(questions_list, list):
            return Response(
                {'detail': 'questions must be an array'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # If subject is not provided at top level, check if first question has subject
        if not subject_name:
            for q in questions_list:
                if q.get('subject'):
                    subject_name = q.get('subject')
                    break

        if not subject_name:
            return Response(
                {'detail': 'subject is required (either at top-level or inside questions)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find exam by title or slug
        try:
            exam = Exam.objects.get(Q(title__iexact=exam_id) | Q(slug__iexact=exam_id))
        except Exam.DoesNotExist:
            return Response(
                {'detail': f'Exam "{exam_id}" not found. Please create the exam first.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Find the default subject
        try:
            subject = Subject.objects.get(exam=exam, name__iexact=subject_name)
        except Subject.DoesNotExist:
            return Response(
                {'detail': f'Subject "{subject_name}" not found under exam "{exam.title}". Please create the subject first.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return self.process_questions(questions_list, subject, year, request.user, exam)

    def handle_file_upload(self, request):
        file_obj = request.FILES['file']
        exam_id = request.data.get('exam_id')
        subject_name = request.data.get('subject')
        year = request.data.get('year')

        if not exam_id:
            return Response({'detail': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Find exam
        try:
            exam = Exam.objects.get(Q(title__iexact=exam_id) | Q(slug__iexact=exam_id))
        except Exam.DoesNotExist:
            return Response({'detail': f'Exam "{exam_id}" not found.'}, status=status.HTTP_404_NOT_FOUND)

        questions_list = []

        try:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)

            if file_obj.name.endswith('.csv'):
                decoded_file = file_obj.read().decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.DictReader(io_string)
                for row in reader:
                    # Clean dictionary with lowercased and stripped keys
                    cleaned_row = {
                        str(k).strip().lower(): str(v).strip() if v is not None else ''
                        for k, v in row.items() if k is not None
                    }

                    # Extract options (supports option_a, optiona, opt_a, a, etc.)
                    options = {}
                    for k, v in cleaned_row.items():
                        if not v:
                            continue
                        if k.startswith('option_') or k.startswith('option'):
                            opt_key = k.replace('option_', '').replace('option', '').strip().upper()
                            if opt_key and len(opt_key) <= 2:
                                options[opt_key] = v
                        elif k.startswith('opt_'):
                            opt_key = k.replace('opt_', '').strip().upper()
                            if opt_key and len(opt_key) <= 2:
                                options[opt_key] = v
                        elif k in ['a', 'b', 'c', 'd', 'e']:
                            options[k.upper()] = v

                    # Extract fields with multiple possible header names
                    q_text = (
                        cleaned_row.get('question_text') or 
                        cleaned_row.get('question') or 
                        cleaned_row.get('text') or ''
                    )
                    correct_ans = (
                        cleaned_row.get('correct_answer') or 
                        cleaned_row.get('answer') or 
                        cleaned_row.get('correct') or ''
                    )
                    q_year = (
                        cleaned_row.get('year') or 
                        cleaned_row.get('exam_year') or 
                        cleaned_row.get('session') or ''
                    )
                    q_subject = (
                        cleaned_row.get('subject') or 
                        cleaned_row.get('subject_name') or ''
                    )

                    q_image = (
                        cleaned_row.get('image_url') or 
                        cleaned_row.get('image') or 
                        cleaned_row.get('question_image') or 
                        cleaned_row.get('img') or ''
                    )
                    questions_list.append({
                        'question_text': q_text,
                        'options': options,
                        'correct_answer': correct_ans,
                        'explanation': cleaned_row.get('explanation', '') or cleaned_row.get('solution', ''),
                        'image': q_image,
                        'id': cleaned_row.get('id', ''),
                        'year': q_year,
                        'subject': q_subject
                    })
            elif file_obj.name.endswith('.xlsx') or file_obj.name.endswith('.xls'):
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(file_obj)
                    ws = wb.active
                    headers = [str(cell.value).strip().lower() if cell.value else '' for cell in ws[1]]
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        row_dict = dict(zip(headers, row))
                        # Similar logic for excel
                        options = {}
                        for k, v in row_dict.items():
                            if not v:
                                continue
                            if k.startswith('option_') or k.startswith('option'):
                                opt_key = k.replace('option_', '').replace('option', '').strip().upper()
                                if opt_key:
                                    options[opt_key] = str(v).strip()
                            elif k in ['a', 'b', 'c', 'd', 'e']:
                                options[k.upper()] = str(v).strip()

                        q_image = str(
                            row_dict.get('image_url') or 
                            row_dict.get('image') or 
                            row_dict.get('question_image') or 
                            row_dict.get('img') or ''
                        ).strip()
                        questions_list.append({
                            'question_text': str(row_dict.get('question_text') or row_dict.get('question') or ''),
                            'options': options,
                            'correct_answer': str(row_dict.get('correct_answer') or row_dict.get('answer') or ''),
                            'explanation': str(row_dict.get('explanation') or ''),
                            'image': q_image,
                            'id': str(row_dict.get('id') or ''),
                            'year': str(row_dict.get('year') or ''),
                            'subject': str(row_dict.get('subject') or '')
                        })
                except ImportError:
                    return Response({'detail': 'openpyxl library not installed for Excel support'}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({'detail': f'Error processing file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Determine subject if not specified at top level
        if not subject_name:
            for q in questions_list:
                if q.get('subject'):
                    subject_name = q.get('subject')
                    break

        if not subject_name:
            return Response({'detail': 'subject is required (either in request parameters or in file rows)'}, status=status.HTTP_400_BAD_REQUEST)

        # Find subject
        try:
            subject = Subject.objects.get(exam=exam, name__iexact=subject_name)
        except Subject.DoesNotExist:
            return Response({'detail': f'Subject "{subject_name}" not found.'}, status=status.HTTP_404_NOT_FOUND)

        return self.process_questions(questions_list, subject, year, request.user, exam)

    def process_questions(self, questions_list, subject, year, user, exam):
        created_questions = []
        errors = []
        years_summary = {}

        if not questions_list:
            return Response({
                'success': 0,
                'total': 0,
                'created': [],
                'errors': ['No valid questions found in the upload'],
                'exam': exam.title,
                'year': year
            }, status=status.HTTP_400_BAD_REQUEST)

        for idx, q_data in enumerate(questions_list, 1):
            try:
                question_text = q_data.get('question_text', '').strip()
                options = q_data.get('options', {})
                correct_answer = str(q_data.get('correct_answer', '')).strip().upper()
                explanation = q_data.get('explanation', '').strip()
                question_id = q_data.get('id', f'Question {idx}')

                # Validate question_text
                if not question_text:
                    errors.append(f"{question_id}: Question text is required")
                    continue

                # Validate options
                if not options or not isinstance(options, dict):
                    errors.append(f"{question_id}: Options must be a dictionary with at least 2 options")
                    continue

                if len(options) < 2:
                    errors.append(f"{question_id}: At least 2 options are required (got {len(options)})")
                    continue

                # Filter empty options
                options = {k: v for k, v in options.items() if v and str(v).strip()}
                if len(options) < 2:
                    errors.append(f"{question_id}: At least 2 non-empty options are required")
                    continue

                # Validate correct_answer
                if not correct_answer:
                    errors.append(f"{question_id}: correct_answer is required")
                    continue

                if correct_answer not in options:
                    errors.append(f"{question_id}: correct_answer '{correct_answer}' must be one of {list(options.keys())}")
                    continue

                # Determine question year:
                # 1. Per-question year (from JSON question or CSV row)
                # 2. Top-level year argument
                # 3. Detect from text or explanation
                # 4. If none, leave as None (unassigned)
                q_year = str(q_data.get('year') or year or '').strip()
                if not q_year:
                    q_year = detect_year_from_text(question_text) or detect_year_from_text(explanation) or None
                else:
                    q_year = q_year if q_year else None

                # Determine target subject (supports per-question subject override)
                target_subject = subject
                q_subject_name = q_data.get('subject')
                if q_subject_name and str(q_subject_name).strip().lower() != subject.name.lower():
                    try:
                        target_subject = Subject.objects.get(exam=exam, name__iexact=str(q_subject_name).strip())
                    except Subject.DoesNotExist:
                        target_subject = subject

                # Extract optional image URL or path
                q_image_val = str(q_data.get('image') or q_data.get('image_url') or q_data.get('question_image') or '').strip()
                if q_image_val and not (q_image_val.startswith(('http://', 'https://', '//')) or q_image_val.startswith('cbt_questions/')):
                    # Clean/ignore invalid string values
                    if not q_image_val.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                        q_image_val = ''

                # Create question with determined year, subject, and optional image
                question = Question.objects.create(
                    subject=target_subject,
                    text=question_text,
                    image=q_image_val if q_image_val else None,
                    year=q_year,
                    explanation=explanation,
                    creator=user
                )

                # Create choices
                for option_key, option_text in options.items():
                    is_correct = str(option_key).upper() == correct_answer
                    Choice.objects.create(
                        question=question,
                        text=str(option_text).strip(),
                        is_correct=is_correct
                    )

                created_questions.append({
                    'id': question.id,
                    'text': question_text[:50] + '...' if len(question_text) > 50 else question_text,
                    'year': q_year,
                    'subject': target_subject.name
                })
                years_summary[q_year] = years_summary.get(q_year, 0) + 1

            except Exception as e:
                errors.append(f"{q_data.get('id', f'Question {idx}')}: {str(e)}")

        if not created_questions:
            return Response({
                'success': 0,
                'total': len(questions_list),
                'created': [],
                'errors': errors,
                'exam': exam.title,
                'year': year
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': len(created_questions),
            'total': len(questions_list),
            'created': created_questions,
            'years_summary': years_summary,
            'errors': errors if errors else None,
            'exam': exam.title,
            'default_subject': subject.name
        }, status=status.HTTP_201_CREATED)


class StartExamView(APIView):
    """Start a new exam attempt (single or multi-subject) and return the questions for that exam"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data
        exam_id = data.get('exam')
        
        # Check if this is a multi-subject or single-subject exam
        subjects_config = data.get('subjects_config')
        
        # Single-subject (backward compatibility)
        if not subjects_config:
            subject_id = data.get('subject')
            num_questions = data.get('num_questions')
            time_limit_minutes = data.get('time_limit_minutes')
            year = data.get('year')
            test_name = None
            
            if not all([exam_id, subject_id, num_questions, time_limit_minutes]):
                return Response(
                    {'detail': 'exam, subject, num_questions, and time_limit_minutes are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            exam = get_object_or_404(Exam, pk=exam_id)
            subject = get_object_or_404(Subject, pk=subject_id)
            subjects_data = [{'subject_id': subject_id, 'num_questions': num_questions, 'year': year}]
        
        # Multi-subject exam
        else:
            test_name = data.get('test_name')
            time_limit_minutes = data.get('time_limit_minutes')
            
            if not all([exam_id, subjects_config, time_limit_minutes, test_name]):
                return Response(
                    {'detail': 'exam, subjects_config, time_limit_minutes, and test_name are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not isinstance(subjects_config, list) or len(subjects_config) == 0:
                return Response(
                    {'detail': 'subjects_config must be a non-empty array'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            exam = get_object_or_404(Exam, pk=exam_id)
            subject = None  # NULL for multi-subject exams
            subjects_data = subjects_config
        
        # Validate all subjects exist and gather question data
        total_num_questions = 0
        all_selected_questions = []
        subjects_info = []
        is_trial_attempt = False
        
        # Check if user has an unlock for this exam or active Pro plan
        has_unlock = False
        if request.user.is_authenticated:
            try:
                from courses.subscription_views import user_has_exam_access
                has_unlock = user_has_exam_access(request.user, exam_id)
            except Exception:
                has_unlock = ActivationUnlock.objects.filter(
                    user=request.user, 
                    exam_identifier=str(exam_id),
                    is_active=True
                ).exists() or getattr(request.user, 'is_unlocked', False)
        
        # If no unlock, check if they can use free trial (max 5 attempts per exam)
        if not has_unlock:
            trial_attempts_count = ExamAttempt.objects.filter(
                user=request.user,
                exam_id=exam_id,
                is_trial_attempt=True
            ).count()
            
            if trial_attempts_count >= exam.free_trial_attempts:
                return Response(
                    {
                        'detail': 'You have exhausted your free trial attempts for this exam.',
                        'trial_attempts_used': trial_attempts_count,
                        'trial_attempts_limit': exam.free_trial_attempts,
                        'message': f'Free trial limited to {exam.free_trial_attempts} attempts. Unlock this exam to continue practicing.',
                        'action': 'Unlock Exam'
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Mark this as a trial attempt
            is_trial_attempt = True
        
        # For multi-subject exams: verify student has selected these subjects in their unlock (if they have one)
        if subjects_config and exam_id and has_unlock:
            unlock = ActivationUnlock.objects.filter(user=request.user, exam_identifier=str(exam_id), is_active=True).first()
            if unlock:
                allowed_subject_ids = set(unlock.selected_exam_subjects.values_list('id', flat=True))
                requested_subject_ids = set(cfg.get('subject_id') for cfg in subjects_config)
                
                # If unlock has no selected subjects (legacy or full unlock), allow access to ALL exam subjects
                if not allowed_subject_ids:
                    allowed_subject_ids = set(exam.subjects.values_list('id', flat=True))
                
                # Check if all requested subjects are in allowed subjects
                if not requested_subject_ids.issubset(allowed_subject_ids):
                    allowed_subject_names = list(exam.subjects.filter(id__in=allowed_subject_ids).values_list('name', flat=True))
                    return Response(
                        {
                            'detail': 'You do not have access to all requested subjects.',
                            'available_subjects': allowed_subject_names,
                            'message': f'You have unlocked access to: {", ".join(allowed_subject_names)}. Please select only from these subjects.',
                            'action': 'Go back and reselect your subjects from the available options.'
                        },
                        status=status.HTTP_403_FORBIDDEN
                    )
            # If no specific unlock record exists but has_unlock is True (e.g. Pro subscriber), they have access to all subjects!
        
        for subject_config in subjects_data:
            subject_id = subject_config.get('subject_id')
            num_questions = subject_config.get('num_questions')
            year = subject_config.get('year')
            
            if not subject_id or not num_questions:
                return Response(
                    {'detail': 'Each subject config must have subject_id and num_questions'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            subject_obj = get_object_or_404(Subject, pk=subject_id)
            all_questions = Question.objects.filter(
                Q(subject=subject_obj) | Q(assignments__subject=subject_obj)
            ).distinct()

            DEFAULT_FALLBACK_YEAR = "2021"
            if year and str(year).strip().lower() != 'simulate':
                selected_year = str(year).strip()
                if selected_year == DEFAULT_FALLBACK_YEAR:
                    # Include explicit 2021 AND unassigned questions
                    all_questions = all_questions.filter(
                        Q(year=DEFAULT_FALLBACK_YEAR) | Q(year__isnull=True) | Q(year='')
                    )
                else:
                    all_questions = all_questions.filter(year=selected_year)
            # If year is "simulate", None, or empty, keep all_questions (full random sample)

            num_questions = min(int(num_questions), all_questions.count())
            
            # Cap questions per subject for free trial attempts
            if is_trial_attempt and exam.free_trial_questions_per_subject > 0:
                num_questions = min(num_questions, exam.free_trial_questions_per_subject)
            
            if num_questions < 1:
                year_msg = f' for year {year}' if (year and str(year).strip().lower() != 'simulate') else ''
                return Response(
                    {'detail': f'Not enough questions in subject {subject_obj.name}{year_msg}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            selected_questions = random.sample(list(all_questions), num_questions)
            all_selected_questions.extend(selected_questions)
            total_num_questions += num_questions
            
            subjects_info.append({
                'subject_id': subject_obj.id,
                'name': subject_obj.name,
                'num_questions': num_questions,
                'year': year or 'simulate'
            })

        # Create exam attempt
        exam_attempt = ExamAttempt.objects.create(
            user=request.user,
            exam=exam,
            subject=subject,  # NULL for multi-subject
            test_name=test_name,
            num_questions=total_num_questions,
            time_limit_minutes=int(time_limit_minutes),
            started_at=timezone.now(),
            is_trial_attempt=is_trial_attempt
        )

        # Create student answer records for each question
        for question in all_selected_questions:
            StudentAnswer.objects.create(
                exam_attempt=exam_attempt,
                question=question,
                subject=question.subject
            )

        # Return exam attempt details
        response_data = {
            'exam_attempt_id': exam_attempt.id,
            'test_name': test_name or exam.title,
            'exam_title': exam.title,
            'subjects': subjects_info,
            'num_questions': total_num_questions,
            'time_limit_minutes': time_limit_minutes,
            'started_at': exam_attempt.started_at,
            'is_trial_attempt': is_trial_attempt
        }
        
        # Add trial attempt info if this is a trial
        if is_trial_attempt:
            trial_attempts = ExamAttempt.objects.filter(
                user=request.user,
                exam_id=exam_id,
                is_trial_attempt=True
            ).count()
            response_data['trial_attempts_used'] = trial_attempts
            response_data['trial_attempts_remaining'] = exam.free_trial_attempts - trial_attempts
            response_data['trial_attempts_limit'] = exam.free_trial_attempts
            response_data['trial_message'] = f'Free trial: {trial_attempts}/{exam.free_trial_attempts} attempts used'
        
        return Response(response_data, status=status.HTTP_201_CREATED)


class SubmitAnswerView(APIView):
    """Submit an answer for a specific question in an exam attempt"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, exam_attempt_id):
        data = request.data
        question_id = data.get('question_id')
        choice_id = data.get('choice_id')

        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)
        question = get_object_or_404(Question, pk=question_id)

        try:
            student_answer = StudentAnswer.objects.get(
                exam_attempt=exam_attempt,
                question=question
            )
        except StudentAnswer.DoesNotExist:
            return Response(
                {'detail': 'This question is not part of this exam attempt'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the selected choice
        if choice_id:
            choice = get_object_or_404(Choice, pk=choice_id)
            student_answer.selected_choice = choice
            student_answer.is_correct = choice.is_correct
        else:
            student_answer.selected_choice = None
            student_answer.is_correct = False

        student_answer.answered_at = timezone.now()
        student_answer.save()

        return Response({
            'id': student_answer.id,
            'question_id': question.id,
            'is_correct': student_answer.is_correct
        })


class SubmitExamView(APIView):
    """Submit/complete an exam attempt and calculate the score"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, exam_attempt_id):
        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)

        if exam_attempt.is_submitted:
            return Response(
                {'detail': 'This exam has already been submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate score
        student_answers = exam_attempt.student_answers.all()
        correct_count = student_answers.filter(is_correct=True).count()
        total_count = student_answers.count()
        
        exam_attempt.score = correct_count
        exam_attempt.is_submitted = True
        exam_attempt.submitted_at = timezone.now()
        
        # Calculate time taken
        time_taken = exam_attempt.submitted_at - exam_attempt.started_at
        exam_attempt.time_taken_seconds = int(time_taken.total_seconds())
        
        exam_attempt.save()

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'score': exam_attempt.score,
            'total_questions': total_count,
            'percentage': round((correct_count / total_count) * 100, 2) if total_count > 0 else 0,
            'submitted_at': exam_attempt.submitted_at,
            'time_taken_seconds': exam_attempt.time_taken_seconds
        })


class ExamAttemptViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return ExamAttempt.objects.none()

        if self.action in ['retrieve', 'resume']:
            return ExamAttempt.objects.filter(user=user)

        status = self.request.query_params.get('status', 'submitted')
        if status == 'in_progress':
            return ExamAttempt.objects.filter(
                user=user, is_submitted=False
            ).order_by('-started_at')
        return ExamAttempt.objects.filter(
            user=user, is_submitted=True
        ).order_by('-submitted_at')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ExamAttemptDetailSerializer
        return ExamAttemptListSerializer

    @action(detail=True, methods=['get'])
    def resume(self, request, pk=None):
        """Resume an active (unsubmitted) exam attempt"""
        from django.shortcuts import get_object_or_404
        from django.utils import timezone
        from django.db.models import Count
        from rest_framework import status

        exam_attempt = get_object_or_404(ExamAttempt, pk=pk, user=request.user)

        if exam_attempt.is_submitted:
            return Response(
                {'error': 'This exam has already been submitted and cannot be resumed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate time remaining
        elapsed_seconds = int((timezone.now() - exam_attempt.started_at).total_seconds())
        total_limit_seconds = exam_attempt.time_limit_minutes * 60
        remaining_seconds = max(0, total_limit_seconds - elapsed_seconds)

        # If time has fully expired, auto-submit the exam
        if remaining_seconds <= 0 and total_limit_seconds > 0:
            exam_attempt.is_submitted = True
            exam_attempt.submitted_at = timezone.now()
            exam_attempt.time_taken_seconds = total_limit_seconds
            # Calculate final score
            student_answers = exam_attempt.student_answers.all()
            correct_count = student_answers.filter(is_correct=True).count()
            exam_attempt.score = float(correct_count)
            exam_attempt.save()

            return Response({
                'expired': True,
                'is_submitted': True,
                'exam_attempt_id': exam_attempt.id,
                'error': 'The time limit for this exam has expired. The exam has been automatically submitted.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Group questions in this attempt by subject to reconstruct subjectConfigs
        distinct_subjects = exam_attempt.student_answers.values(
            'subject_id', 'subject__name'
        ).annotate(count=Count('id')).order_by('subject_id')

        subjects_data = []
        for item in distinct_subjects:
            s_id = item['subject_id']
            s_name = item['subject__name'] or (exam_attempt.subject.name if exam_attempt.subject else 'Subject')
            q_count = item['count']
            if s_id:
                subjects_data.append({
                    'subject_id': s_id,
                    'subject_name': s_name,
                    'num_questions': q_count
                })

        if not subjects_data and exam_attempt.subject:
            subjects_data.append({
                'subject_id': exam_attempt.subject.id,
                'subject_name': exam_attempt.subject.name,
                'num_questions': exam_attempt.num_questions
            })

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'test_name': exam_attempt.test_name or (exam_attempt.subject.name if exam_attempt.subject else exam_attempt.exam.title),
            'exam_title': exam_attempt.exam.title,
            'time_limit_minutes': exam_attempt.time_limit_minutes,
            'time_remaining_seconds': remaining_seconds,
            'subject_configs': subjects_data,
            'is_trial_attempt': exam_attempt.is_trial_attempt,
            'started_at': exam_attempt.started_at,
            'num_questions': exam_attempt.num_questions
        })

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get detailed performance report for a specific exam attempt"""
        exam_attempt = self.get_object()
        
        student_answers = exam_attempt.student_answers.all()
        wrong_answers = student_answers.exclude(is_correct=True)

        wrong_answers_data = []
        for answer in wrong_answers:
            correct_choice = answer.question.choices.filter(is_correct=True).first()
            wrong_answers_data.append({
                'question_id': answer.question.id,
                'question_text': answer.question.text,
                'question_image': resolve_question_image_url(answer.question, request),
                'user_answer': answer.selected_choice.text if answer.selected_choice else 'Not answered',
                'correct_answer': correct_choice.text if correct_choice else 'N/A',
                'explanation': getattr(answer.question, 'explanation', 'No explanation available')
            })

        serializer = ExamAttemptDetailSerializer(exam_attempt, context={'request': request})
        data = serializer.data
        data['wrong_answers'] = wrong_answers_data

        return Response(data)


class ExamAttemptListView(APIView):
    """List all submitted exam attempts for the current user with pagination"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        page = request.query_params.get('page', 1)
        page_size = 10

        attempts = ExamAttempt.objects.filter(
            user=user, 
            is_submitted=True
        ).order_by('-submitted_at')

        total_count = attempts.count()
        start = (int(page) - 1) * page_size
        end = start + page_size

        paginated_attempts = attempts[start:end]
        serializer = ExamAttemptListSerializer(paginated_attempts, many=True)

        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': serializer.data
        })


def resolve_question_image_url(question, request=None):
    """Safely resolve an absolute URL for a question's image, supporting Cloudinary, remote URLs, and local files."""
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

class GetExamQuestionsView(APIView):
    """Get paginated questions for an active exam attempt, optionally filtered by subject"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exam_attempt_id):
        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)
        page = int(request.query_params.get('page', 1))
        subject_id = request.query_params.get('subject')
        page_size = 10

        # Filter student answers by subject if specified
        student_answers = exam_attempt.student_answers.all()
        if subject_id:
            student_answers = student_answers.filter(subject_id=int(subject_id))
        
        student_answers = student_answers.order_by('id')
        total_count = student_answers.count()
        
        start = (page - 1) * page_size
        end = start + page_size

        paginated_answers = student_answers[start:end]

        questions_data = []
        for answer in paginated_answers:
            question = answer.question
            questions_data.append({
                'id': question.id,
                'text': format_math_question(question.text),
                'image': resolve_question_image_url(question, request),
                'choices': [
                    {'id': c.id, 'text': format_math_question(c.text)}
                    for c in question.choices.all()
                ],
                'user_answer_id': answer.selected_choice.id if answer.selected_choice else None,
                'is_answered': answer.selected_choice is not None,
                'year': question.year
            })

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'page': page,
            'page_size': page_size,
            'total_questions': total_count,
            'total_pages': (total_count + page_size - 1) // page_size,
            'questions': questions_data
        })


class ExamProgressView(APIView):
    """Get progress/navigation data for an active exam (which questions answered, organized by subject)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exam_attempt_id):
        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)
        
        student_answers = exam_attempt.student_answers.all().order_by('id')
        
        # Always return progress array for backward compatibility
        progress = []
        for idx, answer in enumerate(student_answers, 1):
            progress.append({
                'question_number': idx,
                'question_id': answer.question.id,
                'is_answered': answer.selected_choice is not None,
                'is_correct': answer.is_correct
            })

        # For multi-subject exams, also return subject-level progress
        subject_progress = []
        if exam_attempt.test_name:  # Multi-subject exam
            # Group by subject
            from django.db.models import Count, Q
            subjects_in_attempt = exam_attempt.student_answers.values('subject_id', 'subject__name').distinct()
            
            for subject_data in subjects_in_attempt:
                subject_id = subject_data['subject_id']
                subject_name = subject_data['subject__name']
                
                subject_answers = exam_attempt.student_answers.filter(subject_id=subject_id)
                answered_count = subject_answers.filter(selected_choice__isnull=False).count()
                total_count = subject_answers.count()
                
                subject_progress.append({
                    'subject_id': subject_id,
                    'subject_name': subject_name,
                    'answered_count': answered_count,
                    'total_questions': total_count
                })

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'total_questions': exam_attempt.num_questions,
            'answered_count': student_answers.filter(selected_choice__isnull=False).count(),
            'progress': progress,
            'subject_progress': subject_progress
        })


class AnalyticsView(APIView):
    """Get CBT analytics for admin dashboard"""
    permission_classes = [IsMasterAdmin]

    def get(self, request):
        from django.db.models import Count, Avg, F
        
        # Get total exam attempts
        total_attempts = ExamAttempt.objects.count()
        
        # Get average score
        avg_score = ExamAttempt.objects.aggregate(avg=Avg('score'))['avg'] or 0
        
        # Get subjects with attempt counts
        subjects_data = Subject.objects.annotate(
            attempt_count=Count('attempts', distinct=True),
            avg_score=Avg('attempts__score')
        ).values('name', 'attempt_count', 'avg_score').order_by('-attempt_count')
        
        # Get today's attempts
        today = timezone.now().date()
        today_attempts = ExamAttempt.objects.filter(
            started_at__date=today
        ).count()
        
        # Compute pass rate (default pass threshold 50%)
        PASS_THRESHOLD = getattr(settings, 'CBT_PASS_THRESHOLD', 50)
        passed_attempts = ExamAttempt.objects.filter(score__gte=PASS_THRESHOLD).count()
        pass_rate = (passed_attempts / total_attempts) if total_attempts > 0 else 0

        # Average time taken (seconds -> minutes)
        avg_time_seconds = ExamAttempt.objects.aggregate(avg_time=Avg('time_taken_seconds'))['avg_time']
        avg_time_minutes = (float(avg_time_seconds) / 60.0) if avg_time_seconds is not None else None

        # Active students (unique users who attempted)
        active_students = ExamAttempt.objects.values('user').distinct().count()

        # Top scorers (top attempts by score)
        top_attempts_qs = ExamAttempt.objects.filter(score__isnull=False).select_related('user', 'exam', 'subject').order_by('-score', '-submitted_at')[:10]
        top_scorers = []
        for a in top_attempts_qs:
            top_scorers.append({
                'id': a.id,
                'user_id': a.user_id,
                'name': getattr(a.user, 'username', None) or getattr(a.user, 'full_name', None) or str(a.user_id),
                'exam': a.exam.title if a.exam else None,
                'subject': a.subject.name if a.subject else None,
                'score': float(a.score) if a.score is not None else None,
                'date': a.submitted_at.isoformat() if a.submitted_at else (a.finished_at.isoformat() if a.finished_at else a.started_at.isoformat())
            })

        top_subject = None
        if len(subjects_data) > 0:
            top_subject = subjects_data[0]['name']

        return Response({
            'total_attempts': total_attempts,
            'total_exams': Exam.objects.count(),
            'average_score': float(avg_score),
            'today_attempts': today_attempts,
            'subjects': list(subjects_data[:10]),  # Top 10 subjects
            'passed_attempts': passed_attempts,
            'pass_rate': float(pass_rate),
            'average_time_seconds': float(avg_time_seconds) if avg_time_seconds is not None else None,
            'average_time_minutes': float(avg_time_minutes) if avg_time_minutes is not None else None,
            'active_students_count': active_students,
            'top_scorers': top_scorers,
            'top_subject': top_subject,
        })

class StudentLeaderboardView(APIView):
    """Get student leaderboard based on exam scores"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Avg, Max
        
        limit = int(request.query_params.get('limit', 50))
        
        # Get top students by average score
        students_stats = ExamAttempt.objects.filter(
            is_submitted=True
        ).values('user__id', 'user__username').annotate(
            avg_score=Avg('score'),
            high_score=Max('score'),
            attempts_count=Count('id', distinct=True)
        ).order_by('-avg_score', '-high_score')[:limit]
        
        # Convert to response format
        leaderboard_data = [
            {
                'id': stats['user__id'],
                'username': stats['user__username'],
                'avg_score': float(stats['avg_score'] or 0),
                'high_score': float(stats['high_score'] or 0),
                'attempts_count': stats['attempts_count']
            }
            for stats in students_stats
        ]
        
        return Response(leaderboard_data)
