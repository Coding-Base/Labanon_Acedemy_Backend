from rest_framework import viewsets, permissions, status, filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from django.core.mail import send_mail
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.db import models
import uuid
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse, FileResponse
from .models import Institution, Course, Module, Lesson, Enrollment, CartItem, Diploma, DiplomaEnrollment, Portfolio, PortfolioGalleryItem, Certificate
from .serializers import InstitutionSerializer, CourseSerializer, ModuleSerializer, LessonSerializer, EnrollmentSerializer, CartItemSerializer, DiplomaSerializer, DiplomaEnrollmentSerializer, PortfolioSerializer, PortfolioGalleryItemSerializer, CertificateSerializer
from .permissions import IsCreatorOrTeacherOrAdmin
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .serializers import PaymentSerializer
from .models import Payment
from django.conf import settings
from django.utils.text import slugify
import random
from users.permissions import IsMasterAdmin
import string
import os

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
        """Allow master admin to see all courses"""
        # Master admin can see all
        if IsMasterAdmin().has_permission(self.request, self):
            return Course.objects.all().order_by('-created_at')
        # Others see all (for read-only access via permission class)
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
        serializer.save(creator=self.request.user, slug=slug)


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        course = serializer.validated_data.get('course')
        if course and course.creator != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied('You do not own this course')
        serializer.save()


class LessonViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        module = serializer.validated_data.get('module')
        if module and module.course.creator != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied('You do not own this module/course')
        serializer.save()


class LessonMediaUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'detail': 'No file provided'}, status=400)

        ext = upload.name.split('.')[-1]
        name = f"lessons/{uuid.uuid4().hex}.{ext}"
        saved_name = default_storage.save(name, upload)

        # default_storage.url may return absolute url (cloudinary) or relative path (filesystem)
        try:
            url = default_storage.url(saved_name)
        except Exception:
            url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"

        # If url is relative (starts with '/'), ensure absolute by prefixing SITE_URL
        if url.startswith('/') and getattr(settings, 'SITE_URL', None):
            url = f"{settings.SITE_URL.rstrip('/')}{url}"

        return JsonResponse({'name': saved_name, 'url': url})


class CourseImageUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, IsAuthenticated]
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

        # If url is relative (starts with '/'), ensure absolute by prefixing SITE_URL
        if url.startswith('/') and getattr(settings, 'SITE_URL', None):
            url = f"{settings.SITE_URL.rstrip('/')}{url}"

        # optionally attach image to a course if course_id passed
        course_id = request.data.get('course_id') or request.POST.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
                # store absolute url so frontend gets a working link regardless of storage
                course.image = url
                course.save()
            except Course.DoesNotExist:
                pass

        return JsonResponse({'name': saved_name, 'url': url})


class InstitutionViewSet(viewsets.ModelViewSet):
    queryset = Institution.objects.all().order_by('-created_at')
    serializer_class = InstitutionSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'owner__username']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Return ordered queryset"""
        return Institution.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_institution(self, request):
        """Get the current user's institution"""
        try:
            institution = Institution.objects.get(owner=request.user)
            serializer = self.get_serializer(institution)
            return Response(serializer.data)
        except Institution.DoesNotExist:
            return Response(
                {'detail': 'You do not have an institution account'},
                status=status.HTTP_404_NOT_FOUND
            )


class EnrollmentViewSet(viewsets.ModelViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Enrollment.objects.filter(user=self.request.user)

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
        """Return queryset based on requester and optional query params.

        - Default: payments where `user` is the current user (purchases made by the user)
        - If `tutor` query param is provided and matches the requesting user id,
          return payments for courses created by that tutor (optionally filtered by status).
        - Master admin may access all payments via `admin_list` or unrestricted admin access.
        """
        user = self.request.user
        params = self.request.query_params

        # If requester is master admin, return all payments (admin_list action handles pagination separately)
        try:
            if IsMasterAdmin().has_permission(self.request, self):
                qs = Payment.objects.all().order_by('-created_at')
                status_param = params.get('status')
                if status_param:
                    qs = qs.filter(status=status_param)
                return qs
        except Exception:
            # If permission helper fails for any reason, fall back to safe behavior
            pass

        # If tutor query param provided, allow tutor to view payments for their courses
        tutor_param = params.get('tutor')
        status_param = params.get('status')
        if tutor_param:
            try:
                tutor_id = int(tutor_param)
            except (TypeError, ValueError):
                return Payment.objects.none()

            # only allow if requester is the same tutor
            if user.is_authenticated and user.id == tutor_id:
                # Get payments for courses AND diplomas created by this tutor
                from django.db.models import Q
                qs = Payment.objects.filter(
                    Q(course__creator__id=tutor_id) | Q(diploma__creator__id=tutor_id)
                ).order_by('-created_at')
                if status_param:
                    qs = qs.filter(status=status_param)
                return qs
            # not authorized
            return Payment.objects.none()

        # If institution filtering requested (for institution dashboards)
        institution_param = params.get('course__institution') or params.get('diploma__institution')
        if institution_param:
            try:
                institution_id = int(institution_param)
            except (TypeError, ValueError):
                return Payment.objects.none()

            # Check if requester owns the institution
            try:
                inst = Institution.objects.get(id=institution_id, owner=user)
            except Institution.DoesNotExist:
                return Payment.objects.none()

            # Return payments for courses AND diplomas from this institution
            from django.db.models import Q
            qs = Payment.objects.filter(
                Q(course__institution__id=institution_id) | Q(diploma__institution__id=institution_id)
            ).order_by('-created_at')
            if status_param:
                qs = qs.filter(status=status_param)
            return qs

        # Default behavior: return payments where current user is the buyer
        qs = Payment.objects.filter(user=user).order_by('-created_at')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=False, methods=['get'], permission_classes=[IsMasterAdmin])
    def admin_list(self, request):
        """Get all payments for admin - paginated list"""
        queryset = Payment.objects.all().order_by('-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsMasterAdmin])
    def stats(self, request):
        """Get payment statistics for admin dashboard"""
        from django.db.models import Sum, Count, Q
        
        total_revenue = Payment.objects.filter(status=Payment.SUCCESS).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        total_transactions = Payment.objects.filter(status=Payment.SUCCESS).count()
        
        platform_commission = Payment.objects.filter(status=Payment.SUCCESS).aggregate(
            total=Sum('platform_fee')
        )['total'] or 0
        
        pending_payouts = Payment.objects.filter(status=Payment.PENDING).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
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
    """Viewset for managing diplomas (onsite learning programs)."""
    queryset = Diploma.objects.all().order_by('-created_at')
    serializer_class = DiplomaSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'description', 'institution__name']
    filterset_fields = ['institution', 'published', 'creator']
    ordering_fields = ['created_at', 'price']

    def get_permissions(self):
        """Anyone can view published diplomas, but only creator/institution can edit."""
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Filter by user if not master admin."""
        if IsMasterAdmin().has_permission(self.request, self):
            return Diploma.objects.all().order_by('-created_at')
        if self.request.user.is_authenticated:
            return Diploma.objects.filter(
                models.Q(creator=self.request.user) | models.Q(published=True)
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
        """Get diplomas created by the current user."""
        diplomas = self.get_queryset().filter(creator=request.user)
        serializer = self.get_serializer(diplomas, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        """Enroll user in a diploma."""
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
    """Viewset for diploma enrollments."""
    serializer_class = DiplomaEnrollmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if IsMasterAdmin().has_permission(self.request, self):
            return DiplomaEnrollment.objects.all()
        return DiplomaEnrollment.objects.filter(
            models.Q(user=user) | models.Q(diploma__creator=user)
        )

    def perform_create(self, serializer):
        """Automatically set the user to the current user."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        """Handle payment for diploma enrollment."""
        from django.utils import timezone
        enrollment = self.get_object()
        
        if enrollment.purchased:
            return Response({'detail': 'Already purchased'}, status=status.HTTP_400_BAD_REQUEST)

        diploma = enrollment.diploma
        amount = float(diploma.price)

        if amount == 0:
            # Free diploma
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            return Response({'detail': 'Enrollment completed (free program)', 'enrolled': True}, status=status.HTTP_200_OK)

        # For paid diplomas, create a fake payment URL (same pattern as courses)
        # In production, integrate with your payment provider
        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)

        # Create a payment record
        payment = Payment.objects.create(
            user=request.user,
            course=diploma,  # Note: this might need a diploma field, using course for now
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )

        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"
        return Response({'payment_url': fake_payment_url}, status=status.HTTP_200_OK)


class PortfolioViewSet(viewsets.ModelViewSet):
    """Viewset for managing institution portfolios."""
    queryset = Portfolio.objects.all()
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Users see own portfolio or public portfolios."""
        from django.db.models import Q
        user = self.request.user
        if IsMasterAdmin().has_permission(self.request, self):
            return Portfolio.objects.all()
        return Portfolio.objects.filter(Q(institution__owner=user) | Q(published=True))

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def by_token(self, request):
        """Get portfolio by public token (public endpoint)."""
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
        """Publish a portfolio."""
        portfolio = self.get_object()
        if portfolio.institution.owner != request.user and not IsMasterAdmin().has_permission(request, self):
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        portfolio.published = True
        portfolio.save()
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Unpublish a portfolio."""
        portfolio = self.get_object()
        if portfolio.institution.owner != request.user and not IsMasterAdmin().has_permission(request, self):
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        portfolio.published = False
        portfolio.save()
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)


class PortfolioGalleryItemViewSet(viewsets.ModelViewSet):
    """Viewset for portfolio gallery items."""
    serializer_class = PortfolioGalleryItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter by portfolio."""
        portfolio_id = self.request.query_params.get('portfolio')
        if portfolio_id:
            return PortfolioGalleryItem.objects.filter(portfolio_id=portfolio_id).order_by('order')
        return PortfolioGalleryItem.objects.all()


class SignatureView(APIView):
    """
    View to serve the platform signature image.
    Used by the certificate generator on the frontend.
    """
    def get(self, request):
        """Serve the signature image from backend root directory."""
        signature_path = os.path.join(settings.BASE_DIR, 'signature.png')
        
        if os.path.exists(signature_path):
            return FileResponse(
                open(signature_path, 'rb'),
                content_type='image/png',
                as_attachment=False
            )
        else:
            return Response(
                {'detail': 'Signature image not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class LogoView(APIView):
    """
    View to serve the platform logo image.
    Used by the certificate generator on the frontend.
    """
    def get(self, request):
        """Serve the logo image from backend root directory."""
        logo_path = os.path.join(settings.BASE_DIR, 'labanonlogo.png')
        
        if os.path.exists(logo_path):
            return FileResponse(
                open(logo_path, 'rb'),
                content_type='image/png',
                as_attachment=False
            )
        else:
            return Response(
                {'detail': 'Logo image not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Viewset for retrieving and managing certificates.
    - Users can view their own certificates
    - Admin/staff can view all certificates
    """
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    search_fields = ['course__title', 'certificate_id']
    ordering_fields = ['created_at', 'issue_date', 'completion_date']
    ordering = ['-created_at']

    def get_queryset(self):
        """Users see only their own certificates. Admin sees all."""
        user = self.request.user
        if user.is_staff:
            return Certificate.objects.all().order_by('-created_at')
        return Certificate.objects.filter(user=user).order_by('-created_at')

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_certificate(self, request):
        """
        Create a new certificate for a course completion.
        Expects: course_id, completion_date (optional)
        """
        course_id = request.data.get('course_id')
        completion_date = request.data.get('completion_date')
        
        if not course_id:
            return Response(
                {'detail': 'course_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {'detail': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user has purchased and completed the course
        try:
            enrollment = Enrollment.objects.get(user=request.user, course=course, purchased=True)
        except Enrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course or have not purchased it'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if certificate already exists
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
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_downloaded(self, request, pk=None):
        """Mark certificate as downloaded and increment download count."""
        certificate = self.get_object()
        
        # Verify user owns this certificate
        if certificate.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        certificate.mark_downloaded()
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)

    @staticmethod
    def _generate_certificate_id():
        """Generate a unique certificate ID."""
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"CERT-{timestamp}-{random_suffix}"
    


class TutorApplicationView(APIView):
    """
    Handles requests for private tutors.
    Sends an email to the admin with details and a confirmation email to the user.
    """
    permission_classes = [AllowAny]  # Allow public access

    def post(self, request):
        data = request.data
        
        # Extract fields
        full_name = data.get('fullName')
        email = data.get('email')
        phone = data.get('whatsappNumber')
        country = data.get('country')
        subject = data.get('subject')
        address = data.get('address')
        info = data.get('additionalInfo', 'N/A')

        # Basic Validation
        if not all([full_name, email, phone, country, subject, address]):
             return Response(
                 {'detail': 'Please fill in all required fields.'}, 
                 status=status.HTTP_400_BAD_REQUEST
             )

        # 1. Prepare Email to Admin (Platform Owner)
        admin_subject = f"NEW TUTOR REQUEST: {subject} - {full_name}"
        admin_message = f"""
        You have received a new request for a private tutor.

        APPLICANT DETAILS
        ------------------
        Name: {full_name}
        Email: {email}
        WhatsApp: {phone}
        Country: {country}
        Residential Address: {address}

        REQUEST DETAILS
        ----------------
        Subject/Course: {subject}
        Additional Info: {info}

        ACTION REQUIRED
        ----------------
        Please contact the user via WhatsApp or Email to proceed.
        """

        # 2. Prepare Confirmation Email to User
        user_subject = "Request Received - Lebanon Academy"
        user_message = f"""
        Dear {full_name},

        Thank you for choosing Lebanon Academy.

        We have received your request for a private tutor in "{subject}". 
        
        Our team is currently reviewing your details to match you with the best available expert. We will reach out to you shortly via WhatsApp or Email to finalize the arrangements.

        Best regards,
        The Lebanon Academy Team
        """

        try:
            # Send to Admin
            # Ensure ADMIN_EMAIL is set in your settings.py or .env, otherwise hardcode or use a default
            admin_email = getattr(settings, 'ADMIN_EMAIL', settings.DEFAULT_FROM_EMAIL)
            
            send_mail(
                admin_subject,
                admin_message,
                settings.DEFAULT_FROM_EMAIL, # From
                [admin_email],               # To Admin
                fail_silently=False,
            )
            
            # Send to User
            send_mail(
                user_subject,
                user_message,
                settings.DEFAULT_FROM_EMAIL, # From
                [email],                     # To User
                fail_silently=True,          # Don't crash if user email is invalid
            )
            
            return Response({'detail': 'Application submitted successfully'}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return Response(
                {'detail': 'Application received, but failed to send notification emails. We will contact you.'}, 
                status=status.HTTP_200_OK # Return 200 so frontend shows success even if email service hiccups
            )