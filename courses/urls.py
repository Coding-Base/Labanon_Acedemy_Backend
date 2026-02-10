from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    CourseViewSet, InstitutionViewSet, EnrollmentViewSet, ModuleViewSet, 
    LessonViewSet, PaymentViewSet, CartItemViewSet, DiplomaViewSet, 
    DiplomaEnrollmentViewSet, PortfolioViewSet, PortfolioGalleryItemViewSet,
    CertificateViewSet, SignatureView, LogoView, TutorApplicationView,
    AdminSignatureView,
    LessonMediaUploadView, CourseImageUploadView, TutorsLeaderboardView,
    GospelVideoViewSet,
    ModuleQuizViewSet, QuizQuestionViewSet, QuizOptionViewSet, ModuleQuizAttemptViewSet
)
from .payment_views import (
    InitiateUnlockView, PaystackWebhookView, InitiatePaymentView, 
    VerifyPaymentView, SubAccountViewSet, ActivationFeeView, ActivationStatusView, AdminActivationFeeView, AdminAnalyticsView,
    TrackPageView, ReferrerStatsView, DailyAnalyticsView,
    PaymentSplitConfigView,
    InitiateFlutterwavePaymentView, VerifyFlutterwavePaymentView, 
    FlutterwaveWebhookView, FlutterwaveSubAccountViewSet, 
    FlutterwaveListBanksView, FlutterwaveVerifyAccountView, PaymentReconciliationView
)

# Custom payment endpoints MUST be defined before router to take precedence
urlpatterns = [
    # Signature and logo endpoints for certificates
    path('signature/', SignatureView.as_view(), name='signature'),
    path('admin/signature/', AdminSignatureView.as_view(), name='admin-signature'),
    path('logo/', LogoView.as_view(), name='logo'),

    # Paystack Payment endpoints
    path('payments/initiate/', InitiatePaymentView.as_view(), name='initiate-payment'),
    path('payments/verify/<str:reference>/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('payments/activation-fee/', ActivationFeeView.as_view(), name='activation-fee'),
    path('payments/activation-status/', ActivationStatusView.as_view(), name='activation-status'),
    path('payments/admin/activation-fees/', AdminActivationFeeView.as_view(), name='admin-activation-fees'),
    path('payments/admin/activation-fees/<int:fee_id>/', AdminActivationFeeView.as_view(), name='admin-activation-fee-detail'),
    path('payments/admin/split-config/', PaymentSplitConfigView.as_view(), name='admin-split-config'),
    path('analytics/admin/summary/', AdminAnalyticsView.as_view(), name='admin-analytics-summary'),
    path('analytics/daily/', DailyAnalyticsView.as_view(), name='daily-analytics'),
    path('analytics/track/', TrackPageView.as_view(), name='analytics-track'),
    path('analytics/referrers/', ReferrerStatsView.as_view(), name='analytics-referrers'),
    path('payments/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),

    # Flutterwave Payment endpoints
    path('payments/flutterwave/initiate/', InitiateFlutterwavePaymentView.as_view(), name='initiate-flutterwave-payment'),
    path('payments/flutterwave/verify/<str:reference>/', VerifyFlutterwavePaymentView.as_view(), name='verify-flutterwave-payment'),
    path('payments/flutterwave/webhook/', FlutterwaveWebhookView.as_view(), name='flutterwave-webhook'),
    path('payments/flutterwave/list-banks/', FlutterwaveListBanksView.as_view(), name='flutterwave-list-banks'),
    path('payments/flutterwave/verify-account/', FlutterwaveVerifyAccountView.as_view(), name='flutterwave-verify-account'),

    # Payment reconciliation endpoint (admin only)
    path('payments/admin/reconcile/', PaymentReconciliationView.as_view(), name='reconcile-payments'),

    # Unlock initiation (user-triggered)
    path('unlock/initiate/', InitiateUnlockView.as_view(), name='initiate-unlock'),

    # Media Uploads
    path('lessons/upload-media/', LessonMediaUploadView.as_view(), name='lesson-media-upload'),
    
    # FIX: Added this specific route to match your InstitutionPortfolio frontend call
    path('course-image-upload/', CourseImageUploadView.as_view(), name='course-image-upload-root'),
    path('courses/upload-image/', CourseImageUploadView.as_view(), name='course-image-upload'),

    # Tutor Application
    path('online-tutorial-for-student-application/', TutorApplicationView.as_view(), name='online-tutorial-for-student-application'),
    
    # Leaderboard
    path('tutors/leaderboard/', TutorsLeaderboardView.as_view(), name='tutors-leaderboard'),
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
router.register(r'gospel-videos', GospelVideoViewSet, basename='gospel-video')
router.register(r'module-quizzes', ModuleQuizViewSet, basename='module-quiz')
router.register(r'quiz-questions', QuizQuestionViewSet, basename='quiz-question')
router.register(r'quiz-options', QuizOptionViewSet, basename='quiz-option')
router.register(r'quiz-attempts', ModuleQuizAttemptViewSet, basename='quiz-attempt')

urlpatterns += router.urls