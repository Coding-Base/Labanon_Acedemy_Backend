from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import CourseViewSet, InstitutionViewSet, EnrollmentViewSet, ModuleViewSet, LessonViewSet, PaymentViewSet, CartItemViewSet
from .payment_views import InitiateUnlockView, PaystackWebhookView
from .views import LessonMediaUploadView
from .views import CourseImageUploadView

router = DefaultRouter()
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'institutions', InstitutionViewSet, basename='institution')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'modules', ModuleViewSet, basename='module')
router.register(r'lessons', LessonViewSet, basename='lesson')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'cart', CartItemViewSet, basename='cart')

urlpatterns = router.urls

urlpatterns += [
	# unlock initiation (user-triggered)
	path('unlock/initiate/', InitiateUnlockView.as_view(), name='initiate-unlock'),
	# paystack webhook
	path('payments/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),
	# lesson media upload
	# lesson media upload (non-conflicting path)
	path('uploads/lessons/media/', LessonMediaUploadView.as_view(), name='lesson-upload-media'),
	# course image upload (non-conflicting path)
	path('uploads/courses/image/', CourseImageUploadView.as_view(), name='course-upload-image'),
]

