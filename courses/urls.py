from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    CourseViewSet, InstitutionViewSet, EnrollmentViewSet, ModuleViewSet, 
    LessonViewSet, PaymentViewSet, CartItemViewSet, DiplomaViewSet, 
    DiplomaEnrollmentViewSet, PortfolioViewSet, PortfolioGalleryItemViewSet,
    CertificateViewSet, SignatureView, LogoView
)
from .payment_views import (
    InitiateUnlockView, PaystackWebhookView, InitiatePaymentView, 
    VerifyPaymentView, SubAccountViewSet,
    InitiateFlutterwavePaymentView, VerifyFlutterwavePaymentView, 
	FlutterwaveWebhookView, FlutterwaveSubAccountViewSet, FlutterwaveListBanksView, FlutterwaveVerifyAccountView
)
from .views import LessonMediaUploadView
from .views import CourseImageUploadView

# Custom payment endpoints MUST be defined before router to take precedence
urlpatterns = [
	# Signature and logo endpoints for certificates
	path('signature/', SignatureView.as_view(), name='signature'),
	path('logo/', LogoView.as_view(), name='logo'),
	# Paystack Payment endpoints
	path('payments/initiate/', InitiatePaymentView.as_view(), name='initiate-payment'),
	path('payments/verify/<str:reference>/', VerifyPaymentView.as_view(), name='verify-payment'),
	path('payments/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),
	# Flutterwave Payment endpoints
	path('payments/flutterwave/initiate/', InitiateFlutterwavePaymentView.as_view(), name='initiate-flutterwave-payment'),
	path('payments/flutterwave/verify/<str:reference>/', VerifyFlutterwavePaymentView.as_view(), name='verify-flutterwave-payment'),
	path('payments/flutterwave/webhook/', FlutterwaveWebhookView.as_view(), name='flutterwave-webhook'),
	path('payments/flutterwave/list-banks/', FlutterwaveListBanksView.as_view(), name='flutterwave-list-banks'),
	path('payments/flutterwave/verify-account/', FlutterwaveVerifyAccountView.as_view(), name='flutterwave-verify-account'),
	# unlock initiation (user-triggered)
	path('unlock/initiate/', InitiateUnlockView.as_view(), name='initiate-unlock'),
	# lesson media upload
    path('lessons/upload-media/', LessonMediaUploadView.as_view(), name='lesson-media-upload'),
    path('courses/upload-image/', CourseImageUploadView.as_view(), name='course-image-upload'),
]

router = DefaultRouter()
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'institutions', InstitutionViewSet, basename='institution')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'modules', ModuleViewSet, basename='module')
router.register(r'lessons', LessonViewSet, basename='lesson')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'cart', CartItemViewSet, basename='cart')
router.register(r'diplomas', DiplomaViewSet, basename='diploma')
router.register(r'diploma-enrollments', DiplomaEnrollmentViewSet, basename='diploma-enrollment')
router.register(r'portfolios', PortfolioViewSet, basename='portfolio')
router.register(r'portfolio-gallery', PortfolioGalleryItemViewSet, basename='portfolio-gallery')
router.register(r'certificates', CertificateViewSet, basename='certificate')
router.register(r'subaccounts', SubAccountViewSet, basename='subaccount')
router.register(r'flutterwave-subaccounts', FlutterwaveSubAccountViewSet, basename='flutterwave-subaccount')

urlpatterns += router.urls