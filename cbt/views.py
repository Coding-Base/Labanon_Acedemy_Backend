from rest_framework import viewsets, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import random

from .models import Question, Choice, Exam, ExamAttempt, Subject, StudentAnswer
from .serializers import (
    QuestionSerializer, ChoiceSerializer, ExamSerializer, 
    ExamAttemptListSerializer, ExamAttemptDetailSerializer,
    ExamAttemptCreateSerializer, StudentAnswerSerializer,
    SubmitAnswerSerializer, SubjectSerializer
)
from users.permissions import IsMasterAdmin


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

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

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Get all questions for a specific subject"""
        subject = self.get_object()
        questions = subject.questions.all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


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
          "subject": "Chemistry"  // optional, can override via top-level subject
        },
        ...
      ]
    }
    """
    permission_classes = [IsMasterAdmin]

    def post(self, request):
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

        if not subject_name:
            return Response(
                {'detail': 'subject is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not questions_list:
            return Response(
                {'detail': 'questions array is required'},
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

        # Find the subject
        try:
            subject = Subject.objects.get(exam=exam, name__iexact=subject_name)
        except Subject.DoesNotExist:
            return Response(
                {'detail': f'Subject "{subject_name}" not found under exam "{exam.title}". Please create the subject first.'},
                status=status.HTTP_404_NOT_FOUND
            )

        created_questions = []
        errors = []

        for q_data in questions_list:
            try:
                question_text = q_data.get('question_text')
                options = q_data.get('options', {})
                correct_answer = q_data.get('correct_answer')
                explanation = q_data.get('explanation', '')
                question_id = q_data.get('id', '')

                if not question_text:
                    errors.append(f"Question {question_id}: question_text is required")
                    continue

                if not options or len(options) < 2:
                    errors.append(f"Question {question_id}: At least 2 options are required")
                    continue

                if not correct_answer:
                    errors.append(f"Question {question_id}: correct_answer is required")
                    continue

                # Create question
                question = Question.objects.create(
                    subject=subject,
                    text=question_text,
                    year=str(year) if year else None,
                    creator=request.user
                )

                # Create choices
                for option_key, option_text in options.items():
                    is_correct = option_key.upper() == correct_answer.upper()
                    Choice.objects.create(
                        question=question,
                        text=option_text,
                        is_correct=is_correct
                    )

                created_questions.append({
                    'id': question.id,
                    'text': question_text[:50] + '...' if len(question_text) > 50 else question_text
                })

            except Exception as e:
                errors.append(f"Question {q_data.get('id', 'unknown')}: {str(e)}")

        return Response({
            'success': len(created_questions),
            'total': len(questions_list),
            'created': created_questions,
            'errors': errors if errors else None,
            'exam': exam.title,
            'year': year
        }, status=status.HTTP_201_CREATED)


class StartExamView(APIView):
    """Start a new exam attempt and return the questions for that exam"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data
        exam_id = data.get('exam')
        subject_id = data.get('subject')
        num_questions = data.get('num_questions')
        time_limit_minutes = data.get('time_limit_minutes')

        if not all([exam_id, subject_id, num_questions, time_limit_minutes]):
            return Response(
                {'detail': 'exam, subject, num_questions, and time_limit_minutes are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        exam = get_object_or_404(Exam, pk=exam_id)
        subject = get_object_or_404(Subject, pk=subject_id)

        # Get random questions from the subject
        all_questions = subject.questions.all()
        num_questions = min(int(num_questions), all_questions.count())
        
        if num_questions < 1:
            return Response(
                {'detail': 'Not enough questions in this subject'},
                status=status.HTTP_400_BAD_REQUEST
            )

        selected_questions = random.sample(list(all_questions), num_questions)

        # Create exam attempt
        exam_attempt = ExamAttempt.objects.create(
            user=request.user,
            exam=exam,
            subject=subject,
            num_questions=num_questions,
            time_limit_minutes=int(time_limit_minutes),
            started_at=timezone.now()
        )

        # Create student answer records for each question
        for question in selected_questions:
            StudentAnswer.objects.create(
                exam_attempt=exam_attempt,
                question=question
            )

        # Return exam attempt details with paginated questions
        questions = [
            {
                'id': q.id,
                'text': q.text,
                'choices': [
                    {'id': c.id, 'text': c.text}
                    for c in q.choices.all()
                ]
            }
            for q in selected_questions
        ]

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'exam_title': exam.title,
            'subject_name': subject.name,
            'num_questions': num_questions,
            'time_limit_minutes': time_limit_minutes,
            'started_at': exam_attempt.started_at,
            'questions': questions
        }, status=status.HTTP_201_CREATED)


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
        return ExamAttempt.objects.filter(user=self.request.user, is_submitted=True).order_by('-submitted_at')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ExamAttemptDetailSerializer
        return ExamAttemptListSerializer

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get detailed performance report for a specific exam attempt"""
        exam_attempt = self.get_object()
        
        student_answers = exam_attempt.student_answers.all()
        wrong_answers = student_answers.filter(is_correct=False)

        wrong_answers_data = []
        for answer in wrong_answers:
            correct_choice = answer.question.choices.filter(is_correct=True).first()
            wrong_answers_data.append({
                'question_id': answer.question.id,
                'question_text': answer.question.text,
                'user_answer': answer.selected_choice.text if answer.selected_choice else 'Not answered',
                'correct_answer': correct_choice.text if correct_choice else 'N/A',
                'explanation': getattr(answer.question, 'explanation', 'No explanation available')
            })

        serializer = ExamAttemptDetailSerializer(exam_attempt)
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


class GetExamQuestionsView(APIView):
    """Get paginated questions for an active exam attempt"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exam_attempt_id):
        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)
        page = int(request.query_params.get('page', 1))
        page_size = 10

        student_answers = exam_attempt.student_answers.all().order_by('question_id')
        total_count = student_answers.count()
        
        start = (page - 1) * page_size
        end = start + page_size

        paginated_answers = student_answers[start:end]

        questions_data = []
        for answer in paginated_answers:
            question = answer.question
            questions_data.append({
                'id': question.id,
                'text': question.text,
                'choices': [
                    {'id': c.id, 'text': c.text}
                    for c in question.choices.all()
                ],
                'user_answer_id': answer.selected_choice.id if answer.selected_choice else None,
                'is_answered': answer.selected_choice is not None
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
    """Get progress/navigation data for an active exam (which questions answered)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exam_attempt_id):
        exam_attempt = get_object_or_404(ExamAttempt, pk=exam_attempt_id, user=request.user)
        
        student_answers = exam_attempt.student_answers.all().order_by('question_id')
        
        progress = []
        for idx, answer in enumerate(student_answers, 1):
            progress.append({
                'question_number': idx,
                'question_id': answer.question.id,
                'is_answered': answer.selected_choice is not None,
                'is_correct': answer.is_correct
            })

        return Response({
            'exam_attempt_id': exam_attempt.id,
            'total_questions': exam_attempt.num_questions,
            'answered_count': student_answers.filter(selected_choice__isnull=False).count(),
            'progress': progress
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
        
        return Response({
            'total_attempts': total_attempts,
            'total_exams': Exam.objects.count(),
            'average_score': float(avg_score),
            'today_attempts': today_attempts,
            'subjects': list(subjects_data[:10])  # Top 10 subjects
        })




