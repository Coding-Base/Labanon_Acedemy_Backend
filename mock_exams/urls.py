from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for viewsets
router = DefaultRouter()

# Admin endpoints
router.register(r'admin/exams', views.MasterAdminMockExamViewSet, basename='admin-mock-exams')
router.register(r'admin/subjects', views.MockExamSubjectViewSet, basename='admin-mock-subjects')
router.register(r'admin/questions', views.MockExamQuestionViewSet, basename='admin-mock-questions')
router.register(r'admin/options', views.MockExamOptionViewSet, basename='admin-mock-options')
router.register(r'admin/fees', views.MockExamFeeViewSet, basename='admin-mock-fees')
router.register(r'admin/platforms', views.MockExamExternalPlatformViewSet, basename='admin-mock-platforms')
router.register(r'admin/activity-logs', views.MockExamActivityLogViewSet, basename='admin-mock-activity-logs')

# Student endpoints
router.register(r'student/exams', views.StudentMockExamViewSet, basename='student-mock-exams')
router.register(r'student/attempts', views.MockExamAttemptViewSet, basename='student-mock-attempts')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
]
