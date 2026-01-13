from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ExamViewSet, QuestionViewSet, SubjectViewSet, ExamAttemptViewSet, 
    BulkQuestionUploadView, StartExamView, SubmitAnswerView, SubmitExamView,
    ExamAttemptListView, GetExamQuestionsView, ExamProgressView, AnalyticsView,
    StudentLeaderboardView
)

router = DefaultRouter()
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'attempts', ExamAttemptViewSet, basename='attempt')

urlpatterns = router.urls + [
    # CBT Exam Flow Endpoints
    path('start-exam/', StartExamView.as_view(), name='start-exam'),
    path('attempts/<int:exam_attempt_id>/submit-answer/', SubmitAnswerView.as_view(), name='submit-answer'),
    path('attempts/<int:exam_attempt_id>/submit/', SubmitExamView.as_view(), name='submit-exam'),
    path('attempts/<int:exam_attempt_id>/questions/', GetExamQuestionsView.as_view(), name='get-exam-questions'),
    path('attempts/<int:exam_attempt_id>/progress/', ExamProgressView.as_view(), name='exam-progress'),
    path('attempt-list/', ExamAttemptListView.as_view(), name='attempt-list'),
    # Admin Endpoints
    path('bulk-upload/', BulkQuestionUploadView.as_view(), name='bulk-upload'),
    path('analytics/', AnalyticsView.as_view(), name='analytics'),
    path('leaderboard/', StudentLeaderboardView.as_view(), name='student-leaderboard'),
]
