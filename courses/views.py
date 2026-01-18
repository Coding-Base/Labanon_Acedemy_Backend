from rest_framework import viewsets, permissions, status, filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from django.core.mail import send_mail
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Sum, Count, Q
from django.http import JsonResponse, FileResponse
from django.utils import timezone
from django.conf import settings
from django.utils.text import slugify
import uuid
import random
import string
import os

from users.permissions import IsMasterAdmin
from users.models import User
from .models import (
    Institution, Course, Module, Lesson, Enrollment, CartItem, 
    Diploma, DiplomaEnrollment, Portfolio, PortfolioGalleryItem, 
    Certificate, Payment, GospelVideo
)
from .serializers import (
    InstitutionSerializer, CourseSerializer, ModuleSerializer, 
    LessonSerializer, EnrollmentSerializer, CartItemSerializer, 
    DiplomaSerializer, DiplomaEnrollmentSerializer, PortfolioSerializer, 
    PortfolioGalleryItemSerializer, CertificateSerializer, PaymentSerializer,
    GospelVideoSerializer
)
from .permissions import IsCreatorOrTeacherOrAdmin
from rest_framework.decorators import action
from rest_framework.response import Response

# --- NEW PERMISSION CLASS ---
class IsInstitutionOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an institution to edit it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user or request.user.is_staff


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by('-created_at')
    serializer_class = CourseSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'description', 'creator__username', 'institution__name']
    filterset_fields = ['published', 'price', 'institution', 'creator']
    ordering_fields = ['created_at', 'price', 'title']

    def get_queryset(self):
        return Course.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        title = serializer.validated_data.get('title', '')
        base_slug = slugify(title) or 'course'
        slug = base_slug
        i = 0
        while Course.objects.filter(slug=slug).exists():
            i += 1
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            slug = f"{base_slug}-{suffix}"
        
        # Automatically link the user's institution if they have one
        institution = Institution.objects.filter(owner=self.request.user).first()
        
        serializer.save(
            creator=self.request.user, 
            slug=slug,
            institution=institution 
        )

class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by('order') # Added order_by
    serializer_class = ModuleSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        course = serializer.validated_data.get('course')
        if course and course.creator != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied('You do not own this course')
        serializer.save()

class LessonViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.all().order_by('order') # Added order_by
    serializer_class = LessonSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        module = serializer.validated_data.get('module')
        if module and module.course.creator != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied('You do not own this module/course')
        serializer.save()

class LessonMediaUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'detail': 'No file provided'}, status=400)
        ext = upload.name.split('.')[-1]
        name = f"lessons/{uuid.uuid4().hex}.{ext}"
        saved_name = default_storage.save(name, upload)
        try:
            url = default_storage.url(saved_name)
        except Exception:
            url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
        if url.startswith('/') and getattr(settings, 'SITE_URL', None):
            url = f"{settings.SITE_URL.rstrip('/')}{url}"
        return JsonResponse({'name': saved_name, 'url': url})

class CourseImageUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'detail': 'No file provided'}, status=400)
        ext = upload.name.split('.')[-1]
        name = f"courses/{uuid.uuid4().hex}.{ext}"
        saved_name = default_storage.save(name, upload)
        try:
            url = default_storage.url(saved_name)
        except Exception:
            url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
        if url.startswith('/') and getattr(settings, 'SITE_URL', None):
            url = f"{settings.SITE_URL.rstrip('/')}{url}"
        
        course_id = request.data.get('course_id') or request.POST.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
                course.image = url
                course.save()
            except Course.DoesNotExist:
                pass
        return JsonResponse({'name': saved_name, 'url': url})

class InstitutionViewSet(viewsets.ModelViewSet):
    queryset = Institution.objects.all().order_by('-created_at')
    serializer_class = InstitutionSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstitutionOwnerOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'owner__username']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Institution.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_institution(self, request):
        """Get the current user's institution"""
        institution = Institution.objects.filter(owner=request.user).first()
        
        if institution:
            serializer = self.get_serializer(institution)
            return Response(serializer.data)
        else:
            return Response(
                {'detail': 'You do not have an institution account'},
                status=status.HTTP_404_NOT_FOUND
            )

class EnrollmentViewSet(viewsets.ModelViewSet):
    queryset = Enrollment.objects.all().order_by('-purchased_at') # Added order_by default
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # FIX: Added .order_by('-purchased_at') to ensure consistent pagination
        return Enrollment.objects.filter(user=self.request.user).order_by('-purchased_at')

    def perform_create(self, serializer):
        course = serializer.validated_data.get('course')
        user = self.request.user
        enrollment = serializer.save(user=user)
        if course and float(course.price) == 0:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            Payment.objects.create(
                user=user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )

    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        enrollment = self.get_object()
        if enrollment.purchased:
            return Response({'detail': 'Already purchased'}, status=status.HTTP_400_BAD_REQUEST)

        course = enrollment.course
        amount = float(course.price)

        if amount == 0:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            Payment.objects.create(
                user=request.user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )
            return Response({'detail': 'Enrollment completed (free course)'} , status=status.HTTP_200_OK)

        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)

        payment = Payment.objects.create(
            user=request.user,
            course=course,
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )

        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"
        serializer = PaymentSerializer(payment)
        return Response({'payment': serializer.data, 'payment_url': fake_payment_url})

class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all().order_by('-created_at')
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params

        # 1. Master Admin sees everything
        if IsMasterAdmin().has_permission(self.request, self):
            qs = Payment.objects.all().order_by('-created_at')
            if params.get('status'):
                qs = qs.filter(status=params.get('status'))
            return qs

        # 2. Filter by Tutor
        tutor_param = params.get('tutor')
        status_param = params.get('status')
        
        if tutor_param:
            try:
                tutor_id = int(tutor_param)
                if user.id == tutor_id:
                    qs = Payment.objects.filter(
                        Q(course__creator__id=tutor_id) | Q(diploma__creator__id=tutor_id)
                    ).order_by('-created_at')
                    if status_param:
                        qs = qs.filter(status=status_param)
                    return qs
            except (TypeError, ValueError):
                pass
            return Payment.objects.none()

        # 3. Filter by Institution
        institution_param = params.get('course__institution') or params.get('diploma__institution')
        if institution_param:
            try:
                institution_id = int(institution_param)
                Institution.objects.get(id=institution_id, owner=user)
                
                qs = Payment.objects.filter(
                    Q(course__institution__id=institution_id) | Q(diploma__institution__id=institution_id)
                ).order_by('-created_at')
                
                if status_param:
                    qs = qs.filter(status=status_param)
                return qs
            except (Institution.DoesNotExist, TypeError, ValueError):
                return Payment.objects.none()

        # 4. Default: User's own purchases
        qs = Payment.objects.filter(user=user).order_by('-created_at')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=False, methods=['get'], permission_classes=[IsMasterAdmin])
    def admin_list(self, request):
        queryset = Payment.objects.all().order_by('-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsMasterAdmin])
    def stats(self, request):
        total_revenue = Payment.objects.filter(status=Payment.SUCCESS).aggregate(total=Sum('amount'))['total'] or 0
        total_transactions = Payment.objects.filter(status=Payment.SUCCESS).count()
        platform_commission = Payment.objects.filter(status=Payment.SUCCESS).aggregate(total=Sum('platform_fee'))['total'] or 0
        pending_payouts = Payment.objects.filter(status=Payment.PENDING).aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'total_revenue': float(total_revenue),
            'total_transactions': total_transactions,
            'platform_commission': float(platform_commission),
            'pending_payouts': float(pending_payouts)
        })

class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.all().order_by('-added_at')
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).order_by('-added_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        cart_item = self.get_object()
        course = cart_item.course
        amount = float(course.price)

        if amount == 0:
            enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            Payment.objects.create(
                user=request.user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )
            cart_item.delete()
            return Response({'detail': 'Enrolled (free course)'} , status=status.HTTP_200_OK)

        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)
        payment = Payment.objects.create(
            user=request.user,
            course=course,
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )

        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"
        serializer = PaymentSerializer(payment)
        return Response({'payment': serializer.data, 'payment_url': fake_payment_url})

    @action(detail=False, methods=['post'])
    def checkout_all(self, request):
        items = self.get_queryset()
        payments = []
        for item in items:
            course = item.course
            amount = float(course.price)
            if amount == 0:
                enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
                enrollment.purchased = True
                enrollment.purchased_at = timezone.now()
                enrollment.save()
                Payment.objects.create(
                    user=request.user,
                    course=course,
                    amount=0,
                    platform_fee=0,
                    kind=Payment.KIND_COURSE,
                    status=Payment.SUCCESS,
                )
                item.delete()
            else:
                commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
                platform_fee = float(amount) * float(commission)
                payment = Payment.objects.create(
                    user=request.user,
                    course=course,
                    amount=amount,
                    platform_fee=platform_fee,
                    status=Payment.PENDING,
                    kind=Payment.KIND_COURSE,
                )
                payments.append({'payment_id': payment.id, 'payment_url': f"https://pay.example.com/checkout/{payment.id}", 'course': course.id})

        return Response({'payments': payments})

class DiplomaViewSet(viewsets.ModelViewSet):
    queryset = Diploma.objects.all().order_by('-created_at')
    serializer_class = DiplomaSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'description', 'institution__name']
    filterset_fields = ['institution', 'published', 'creator']
    ordering_fields = ['created_at', 'price']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if IsMasterAdmin().has_permission(self.request, self):
            return Diploma.objects.all().order_by('-created_at')
        if self.request.user.is_authenticated:
            return Diploma.objects.filter(
                Q(creator=self.request.user) | Q(published=True)
            ).order_by('-created_at')
        return Diploma.objects.filter(published=True).order_by('-created_at')

    def perform_create(self, serializer):
        title = serializer.validated_data.get('title', '')
        base_slug = slugify(title) or 'diploma'
        slug = base_slug
        i = 0
        while Diploma.objects.filter(slug=slug).exists():
            i += 1
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            slug = f"{base_slug}-{suffix}"
        serializer.save(creator=self.request.user, slug=slug)

    @action(detail=False, methods=['get'])
    def my_diplomas(self, request):
        diplomas = self.get_queryset().filter(creator=request.user)
        serializer = self.get_serializer(diplomas, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        diploma = self.get_object()
        enrollment, created = DiplomaEnrollment.objects.get_or_create(
            user=request.user,
            diploma=diploma,
            defaults={'purchased': True, 'purchased_at': timezone.now()}
        )
        if not created:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
        serializer = DiplomaEnrollmentSerializer(enrollment)
        return Response(serializer.data)

class DiplomaEnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = DiplomaEnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if IsMasterAdmin().has_permission(self.request, self):
            return DiplomaEnrollment.objects.all().order_by('-purchased_at') # Added order_by
        return DiplomaEnrollment.objects.filter(
            Q(user=user) | Q(diploma__creator=user)
        ).order_by('-purchased_at') # Added order_by

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        enrollment = self.get_object()
        if enrollment.purchased:
            return Response({'detail': 'Already purchased'}, status=status.HTTP_400_BAD_REQUEST)
        diploma = enrollment.diploma
        amount = float(diploma.price)
        if amount == 0:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            return Response({'detail': 'Enrollment completed (free program)', 'enrolled': True}, status=status.HTTP_200_OK)
        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)
        payment = Payment.objects.create(
            user=request.user,
            course=diploma, 
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )
        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"
        return Response({'payment_url': fake_payment_url}, status=status.HTTP_200_OK)

class PortfolioViewSet(viewsets.ModelViewSet):
    queryset = Portfolio.objects.all().order_by('-created_at') # Added order_by default
    serializer_class = PortfolioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if IsMasterAdmin().has_permission(self.request, self):
            return Portfolio.objects.all().order_by('-created_at') # Added order_by
            
        return Portfolio.objects.filter(institution__owner=user).order_by('-created_at') # Added order_by

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def by_token(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({'detail': 'Token required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            portfolio = Portfolio.objects.get(public_token=token, published=True)
            serializer = self.get_serializer(portfolio)
            return Response(serializer.data)
        except Portfolio.DoesNotExist:
            return Response({'detail': 'Portfolio not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        portfolio = self.get_object()
        if portfolio.institution.owner != request.user and not IsMasterAdmin().has_permission(request, self):
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        portfolio.published = True
        portfolio.save()
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        portfolio = self.get_object()
        if portfolio.institution.owner != request.user and not IsMasterAdmin().has_permission(request, self):
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        portfolio.published = False
        portfolio.save()
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)

class PortfolioGalleryItemViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioGalleryItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        portfolio_id = self.request.query_params.get('portfolio')
        if portfolio_id:
            return PortfolioGalleryItem.objects.filter(portfolio_id=portfolio_id).order_by('order')
        return PortfolioGalleryItem.objects.all().order_by('order')

class SignatureView(APIView):
    def get(self, request):
        signature_path = os.path.join(settings.BASE_DIR, 'signature.png')
        if os.path.exists(signature_path):
            return FileResponse(open(signature_path, 'rb'), content_type='image/png', as_attachment=False)
        else:
            return Response({'detail': 'Signature image not found'}, status=status.HTTP_404_NOT_FOUND)

class LogoView(APIView):
    def get(self, request):
        logo_path = os.path.join(settings.BASE_DIR, 'labanonlogo.png')
        if os.path.exists(logo_path):
            return FileResponse(open(logo_path, 'rb'), content_type='image/png', as_attachment=False)
        else:
            return Response({'detail': 'Logo image not found'}, status=status.HTTP_404_NOT_FOUND)

class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CertificateSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    search_fields = ['course__title', 'certificate_id']
    ordering_fields = ['created_at', 'issue_date', 'completion_date']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Certificate.objects.all().order_by('-created_at')
        return Certificate.objects.filter(user=user).order_by('-created_at')

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def create_certificate(self, request):
        course_id = request.data.get('course_id')
        completion_date = request.data.get('completion_date')
        if not course_id:
            return Response({'detail': 'course_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({'detail': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            enrollment = Enrollment.objects.get(user=request.user, course=course, purchased=True)
        except Enrollment.DoesNotExist:
            return Response({'detail': 'You are not enrolled in this course or have not purchased it'}, status=status.HTTP_403_FORBIDDEN)
        
        certificate, created = Certificate.objects.get_or_create(
            user=request.user,
            course=course,
            enrollment=enrollment,
            defaults={
                'certificate_id': self._generate_certificate_id(),
                'completion_date': completion_date if completion_date else timezone.now().date()
            }
        )
        serializer = self.get_serializer(certificate)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def mark_downloaded(self, request, pk=None):
        certificate = self.get_object()
        if certificate.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        certificate.mark_downloaded()
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)

    @staticmethod
    def _generate_certificate_id():
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"CERT-{timestamp}-{random_suffix}"

class TutorApplicationView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        data = request.data
        full_name = data.get('fullName')
        email = data.get('email')
        phone = data.get('whatsappNumber')
        country = data.get('country')
        subject = data.get('subject')
        level = data.get('academicLevel', 'N/A')
        address = data.get('address')
        info = data.get('additionalInfo', 'N/A')

        if not all([full_name, email, phone, country, subject, address]):
             return Response({'detail': 'Please fill in all required fields.'}, status=status.HTTP_400_BAD_REQUEST)

        style_container = "font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 0; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;"
        style_header = "background-color: #16a34a; padding: 20px; text-align: center; color: white;"
        style_body = "padding: 20px; color: #333; line-height: 1.6;"
        style_footer = "background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #6b7280; border-top: 1px solid #e0e0e0;"
        style_table = "width: 100%; border-collapse: collapse; margin-top: 10px;"
        style_th = "text-align: left; padding: 8px; background-color: #f3f4f6; border-bottom: 1px solid #e5e7eb; font-weight: bold; width: 35%;"
        style_td = "padding: 8px; border-bottom: 1px solid #e5e7eb;"

        admin_subject = f"New Tutor Request: {subject} - {full_name}"
        admin_html_message = f"""
        <div style="{style_container}">
            <div style="{style_header}"><h2 style="margin:0;">New Tutor Request</h2></div>
            <div style="{style_body}">
                <p><strong>You have received a new application.</strong></p>
                <table style="{style_table}">
                    <tr><td style="{style_th}">Applicant Name</td><td style="{style_td}">{full_name}</td></tr>
                    <tr><td style="{style_th}">Email</td><td style="{style_td}"><a href="mailto:{email}" style="color:#16a34a;">{email}</a></td></tr>
                    <tr><td style="{style_th}">WhatsApp</td><td style="{style_td}">{phone}</td></tr>
                    <tr><td style="{style_th}">Level/Class</td><td style="{style_td}">{level}</td></tr>
                    <tr><td style="{style_th}">Subject</td><td style="{style_td}">{subject}</td></tr>
                    <tr><td style="{style_th}">Country</td><td style="{style_td}">{country}</td></tr>
                    <tr><td style="{style_th}">Address</td><td style="{style_td}">{address}</td></tr>
                </table>
                <br>
                <div style="background-color: #f0fdf4; padding: 15px; border-left: 4px solid #16a34a; border-radius: 4px;"><strong>Additional Info:</strong><br>{info}</div>
                <br><p>Please contact the applicant via WhatsApp or Email to proceed.</p>
            </div>
            <div style="{style_footer}">&copy; {timezone.now().year} LightHub Academy Admin System</div>
        </div>"""
        
        admin_plain_message = f"New Tutor Request Received.\nName: {full_name}\nEmail: {email}\nPhone: {phone}\nLevel: {level}\nSubject: {subject}\nLocation: {country}, {address}\nAdditional Info: {info}"
        
        user_subject = "Request Received - LightHub Academy"
        user_html_message = f"""
        <div style="{style_container}">
            <div style="{style_header}"><h2 style="margin:0;">Request Received</h2></div>
            <div style="{style_body}">
                <p>Dear <strong>{full_name}</strong>,</p>
                <p>Thank you for choosing <strong>LightHub Academy</strong>.</p>
                <p>We have successfully received your request for a private tutor in <strong>{subject}</strong>.</p>
                <p>Our team is currently reviewing your details to match you with the best available expert. We will reach out to you shortly via <strong>WhatsApp</strong> or <strong>Email</strong> to finalize the arrangements.</p>
                <br><p>Best regards,<br><strong>The LightHub Academy Team</strong></p>
            </div>
            <div style="{style_footer}">&copy; {timezone.now().year} LightHub Academy. All rights reserved.<br><a href="https://lebanonacademy.ng" style="color: #16a34a; text-decoration: none;">Visit Website</a></div>
        </div>"""
        user_plain_message = f"Dear {full_name},\nThank you for choosing LightHub Academy. We have received your request for a tutor in {subject}.\nWe will contact you shortly via WhatsApp or Email.\nBest regards,\nThe LightHub Academy Team"

        try:
            admin_email = getattr(settings, 'ADMIN_EMAIL', settings.DEFAULT_FROM_EMAIL)
            send_mail(subject=admin_subject, message=admin_plain_message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[admin_email], fail_silently=False, html_message=admin_html_message)
            send_mail(subject=user_subject, message=user_plain_message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email], fail_silently=True, html_message=user_html_message)
            return Response({'detail': 'Application submitted successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return Response({'detail': 'Application received, but failed to send notification emails. We will contact you.'}, status=status.HTTP_200_OK)


class TutorsLeaderboardView(APIView):
    """Get tutors leaderboard based on course sales and performance"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Avg
        
        limit = int(request.query_params.get('limit', 50))
        
        # Get top tutors by total enrollments (sales)
        tutors_stats = User.objects.filter(
            role='tutor'
        ).annotate(
            total_enrollments=Count('courses__enrollments', distinct=True),
            courses_count=Count('courses', distinct=True),
            avg_rating=Avg('courses__reviews__rating')
        ).order_by('-total_enrollments', '-courses_count')[:limit]
        
        # Convert to response format
        leaderboard_data = [
            {
                'id': tutor.id,
                'username': tutor.username,
                'name': f"{tutor.first_name} {tutor.last_name}".strip() or tutor.username,
                'sales': tutor.total_enrollments or 0,
                'courses_created': tutor.courses_count or 0,
                'rating': float(tutor.avg_rating or 4.0)
            }
            for tutor in tutors_stats
        ]
        
        return Response(leaderboard_data)


class GospelVideoViewSet(viewsets.ModelViewSet):
    """Manage gospel videos - only Master Admin can create/edit/delete"""
    queryset = GospelVideo.objects.all()
    serializer_class = GospelVideoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """Only master admin can create/update/delete; all authenticated users can view"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsMasterAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return GospelVideo.objects.all().order_by('-updated_at')

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def current(self, request):
        """Get the currently active gospel video"""
        gospel = GospelVideo.get_active()
        if gospel:
            serializer = self.get_serializer(gospel)
            return Response(serializer.data)
        return Response(None)

