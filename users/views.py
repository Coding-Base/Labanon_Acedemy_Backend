from rest_framework import generics, permissions, status, viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import User
from .models import Review
from .serializers import UserSerializer, RegisterSerializer, StudentDetailSerializer, TutorDetailSerializer, InstitutionDetailSerializer, VerificationStatusSerializer
from .permissions import IsMasterAdmin
from .verification import get_user_verification_status
from courses.models import Course, Enrollment, Payment
from cbt.models import ExamAttempt
from .models import TrialConfig
from .serializers import TrialConfigSerializer
from .serializers import ReviewSerializer
from rest_framework.permissions import IsAdminUser

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = user.role
        data = {'role': role, 'username': user.username}

        if role == User.TUTOR:
            courses_qs = Course.objects.filter(creator=user)
            courses_count = courses_qs.count()
            sales = Payment.objects.filter(course__in=courses_qs, status=Payment.SUCCESS).aggregate(total=Sum('amount'))['total'] or 0
            students = Enrollment.objects.filter(course__in=courses_qs, purchased=True).values('user').distinct().count()
            data.update({'courses_count': courses_count, 'sales_total': float(sales), 'students_count': students})
            
            # Add tutor verification status
            try:
                from courses.models import TutorVerificationDocument
                # Check if all documents are approved
                tutor_docs = TutorVerificationDocument.objects.filter(tutor=user)
                if tutor_docs.exists():
                    # If any document is rejected, overall status is rejected
                    if tutor_docs.filter(status=TutorVerificationDocument.STATUS_REJECTED).exists():
                        data['verification_status'] = 'rejected'
                        # Get rejection reason from the rejected document's review_notes
                        rejected_doc = tutor_docs.filter(status=TutorVerificationDocument.STATUS_REJECTED).first()
                        data['rejection_reason'] = rejected_doc.review_notes if rejected_doc else 'Documents need revision'
                    # If all are approved
                    elif tutor_docs.filter(status=TutorVerificationDocument.STATUS_APPROVED).count() == tutor_docs.count():
                        data['verification_status'] = 'approved'
                        data['rejection_reason'] = None
                    # Otherwise pending
                    else:
                        data['verification_status'] = 'pending'
                        data['rejection_reason'] = None
                else:
                    data['verification_status'] = None
                    data['rejection_reason'] = None
            except ImportError:
                data['verification_status'] = None
                data['rejection_reason'] = None

        elif role == User.STUDENT:
            enrollments = Enrollment.objects.filter(user=user)
            enroll_count = enrollments.count()
            attempts = ExamAttempt.objects.filter(user=user)
            attempts_count = attempts.count()
            avg_score = attempts.aggregate(avg=Sum('score'))['avg'] if attempts_count else None
            data.update({'enrollments_count': enroll_count, 'attempts_count': attempts_count, 'avg_score': float(avg_score) if avg_score else None})

        elif role == User.INSTITUTION:
            inst_qs = user.owned_institutions.all()
            inst_count = inst_qs.count()
            
            courses_qs = Course.objects.filter(institution__in=inst_qs)
            courses_count = courses_qs.count()
            
            student_ids = set()
            course_students = Enrollment.objects.filter(course__institution__in=inst_qs).values_list('user', flat=True)
            student_ids.update(course_students)
            
            try:
                from courses.models import DiplomaEnrollment
                diploma_students = DiplomaEnrollment.objects.filter(diploma__institution__in=inst_qs).values_list('user', flat=True)
                student_ids.update(diploma_students)
            except ImportError:
                pass

            data.update({
                'institutions_count': inst_count, 
                'courses_count': courses_count, 
                'students_count': len(student_ids)
            })
            
            # Add institution verification status
            try:
                from courses.models import Institution
                inst = Institution.objects.filter(owner=user).first()
                if inst:
                    data['verification_status'] = inst.verification_status
                    data['rejection_reason'] = inst.rejection_reason if inst.verification_status == 'rejected' else None
                else:
                    data['verification_status'] = None
                    data['rejection_reason'] = None
            except ImportError:
                data['verification_status'] = None
                data['rejection_reason'] = None

        else:  # researcher or admin
            users_count = User.objects.count()
            courses_count = Course.objects.count()
            payments_total = Payment.objects.filter(status=Payment.SUCCESS).aggregate(total=Sum('amount'))['total'] or 0
            data.update({'users_count': users_count, 'courses_count': courses_count, 'payments_total': float(payments_total)})

        return Response(data)


class VerificationStatusView(APIView):
    """
    Returns current user's verification status.
    For tutors/institutions, checks ComplianceSubmission and document status.
    For others, always verified (no restrictions).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        verification_status = get_user_verification_status(user)
        serializer = VerificationStatusSerializer(verification_status)
        return Response(serializer.data)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Admin user listing / detail / delete/update endpoints for master admin with search, filter and pagination."""
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsMasterAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['id', 'username', 'email']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on user role"""
        role = self.request.query_params.get('role')
        
        if role == 'student':
            return StudentDetailSerializer
        elif role == 'tutor':
            return TutorDetailSerializer
        elif role == 'institution':
            return InstitutionDetailSerializer
        
        return UserSerializer
    
    def partial_update(self, request, *args, **kwargs):
        """Handle PATCH updates for admin-managed fields that may live on related models.
        Frontend sends verification_status, custom_share_percentage, rejection_reason, verified_by for institutions
        and verification_status/custom_share for tutors. Apply changes to related models accordingly.
        """
        user = self.get_object()
        data = request.data or {}
        print(f"[DEBUG] partial_update called for user {user.id} ({user.role}) with data: {data}")

        # Institutions: apply fields to Institution model
        if user.role == User.INSTITUTION or request.query_params.get('role') == 'institution':
            try:
                from courses.models import Institution
                inst = Institution.objects.filter(owner=user).first()
                if not inst:
                    print(f"[DEBUG] No Institution found for user {user.id}")
                    return Response({'detail': 'Institution profile not found for user.'}, status=400)

                changed = False
                if 'verification_status' in data:
                    inst.verification_status = data.get('verification_status')
                    if data.get('verification_status') == Institution.VERIFICATION_APPROVED:
                        inst.verified_by = request.user
                        inst.verified_at = timezone.now()
                    print(f"[DEBUG] Updated verification_status to {inst.verification_status}")
                    changed = True
                if 'custom_share_percentage' in data:
                    inst.custom_share_percentage = data.get('custom_share_percentage')
                    print(f"[DEBUG] Updated custom_share_percentage to {inst.custom_share_percentage}")
                    changed = True
                if 'rejection_reason' in data:
                    inst.rejection_reason = data.get('rejection_reason') or ''
                    print(f"[DEBUG] Updated rejection_reason")
                    changed = True
                if changed:
                    inst.save()
                    print(f"[DEBUG] Institution saved successfully: {inst.id}")

                # Return serialized user (read-only details reflect related institution fields via serializer methods)
                serializer = self.get_serializer(user)
                print(f"[DEBUG] Returning Institution user data")
                return Response(serializer.data)
            except Exception as e:
                print(f"[ERROR] Exception in institution update: {str(e)}")
                import traceback
                traceback.print_exc()
                return Response({'detail': f'Error updating institution: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Tutors: try to update verification records if model exists
        if user.role == User.TUTOR or request.query_params.get('role') == 'tutor':
            try:
                from courses.models import TutorVerificationDocument
                if 'verification_status' in data:
                    # create or update a verification document for record-keeping
                    doc = TutorVerificationDocument.objects.filter(tutor=user).order_by('-reviewed_at').first()
                    if not doc:
                        doc = TutorVerificationDocument.objects.create(tutor=user, status=data.get('verification_status'))
                    else:
                        doc.status = data.get('verification_status')
                    doc.reviewed_by = request.user
                    doc.reviewed_at = timezone.now()
                    if 'rejection_reason' in data:
                        doc.rejection_reason = data.get('rejection_reason') or ''
                    doc.save()
                    print(f"[DEBUG] Tutor verification document saved")

                serializer = self.get_serializer(user)
                print(f"[DEBUG] Returning Tutor user data")
                return Response(serializer.data)
            except Exception as e:
                print(f"[ERROR] Exception in tutor update: {str(e)}")
                import traceback
                traceback.print_exc()
                return Response({'detail': f'Error updating tutor: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Fallback to default behavior for other updates that map directly to User fields
        print(f"[DEBUG] Using default behavior for User field updates")
        return super().partial_update(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """Endpoint to change user password."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not old_password or not new_password or not confirm_password:
            return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(old_password):
            return Response({'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({'error': 'New passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters long'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)


class ProfileUpdateView(APIView):
    """Endpoint to update user profile information."""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        user = request.user
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')

        if email and email != user.email:
            if User.objects.filter(email=email).exists():
                return Response({'error': 'Email already in use'}, status=status.HTTP_400_BAD_REQUEST)
            user.email = email

        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name

        user.save()

        return Response({
            'message': 'Profile updated successfully',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """
    User requests a password reset link via email.
    """
    permission_classes = [] 

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'message': 'If an account exists with this email, a reset link has been sent.'})

        # Generate Token & UID
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Build Link
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
        
        # --- HTML Email Template ---
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f9fafb; margin: 0; padding: 0; }}
                .container {{ max-width: 500px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; overflow: hidden; }}
                .header {{ background-color: #16a34a; padding: 20px; text-align: center; }}
                .header h2 {{ color: #ffffff; margin: 0; font-size: 20px; }}
                .content {{ padding: 30px; color: #374151; line-height: 1.6; }}
                .btn {{ display: inline-block; padding: 12px 24px; background-color: #16a34a; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 20px; text-align: center; }}
                .footer {{ background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset</h2>
                </div>
                <div class="content">
                    <p>Hello <strong>{user.username}</strong>,</p>
                    <p>We received a request to reset your password for your Lighthub Academy account.</p>
                    <p>Click the button below to choose a new password:</p>
                    <center><a href="{reset_link}" class="btn">Reset Password</a></center>
                    <p style="margin-top: 30px; font-size: 13px; color: #6b7280;">If you did not request this change, please ignore this email. Your password will remain unchanged.</p>
                </div>
                <div class="footer">
                    &copy; {settings.DEFAULT_FROM_EMAIL.split('<')[0].strip()} Security Team.
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text fallback
        plain_message = f"""
        Hello {user.username},
        
        You requested a password reset. Please click the link below to set a new password:
        {reset_link}
        
        If you did not request this, please ignore this email.
        """
        
        try:
            send_mail(
                subject="Reset Your Password - Lighthub Academy",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False
            )
        except Exception as e:
            # Log error but don't crash to avoid leaking system info
            print(f"Email Error: {e}")
            return Response({'error': 'Failed to send email. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'message': 'If an account exists with this email, a reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    """
    User submits new password with UID and Token.
    """
    permission_classes = []

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')

        if not all([uidb64, token, new_password]):
            return Response({'error': 'Missing data'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid link'}, status=status.HTTP_400_BAD_REQUEST)

        if default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.is_active = True 
            user.save()
            return Response({'message': 'Password reset successful. You can now login.'})
        
        return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)


class TrialDaysView(APIView):
    """Endpoint for getting trial days setting (public read) and updating it (admin-only)."""

    def get_permissions(self):
        """Allow public read access to trial config; restrict writes to admin."""
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [IsMasterAdmin()]

    def get(self, request):
        obj, _ = TrialConfig.objects.get_or_create(pk=1)
        return Response({'trial_days': obj.trial_days})

    def post(self, request):
        days = request.data.get('trial_days')
        try:
            days = int(days)
            if days <= 0:
                raise ValueError()
        except Exception:
            return Response({'error': 'Invalid trial_days'}, status=status.HTTP_400_BAD_REQUEST)

        obj, _ = TrialConfig.objects.get_or_create(pk=1)
        obj.trial_days = days
        obj.save()
        return Response({'trial_days': obj.trial_days})

    def put(self, request):
        return self.post(request)


class ReviewsPublicView(generics.ListCreateAPIView):
    """Public endpoint to list approved reviews and allow creating new reviews."""
    serializer_class = ReviewSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # Show all reviews to admin users (accessed under /api/admin/ with admin token)
        user = getattr(self.request, 'user', None)
        try:
            if user and user.is_authenticated and (getattr(user, 'is_staff', False) or getattr(user, 'role', None) == 'admin'):
                return Review.objects.all().order_by('-created_at')
        except Exception:
            pass
        # Otherwise only show approved reviews publicly
        return Review.objects.filter(is_approved=True).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save()


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Detail view: public can GET only approved reviews; admin can manage any review."""
    serializer_class = ReviewSerializer
    queryset = Review.objects.all()

    def get_permissions(self):
        # Admin users may GET/PUT/DELETE; anonymous/public only GET approved
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsMasterAdmin()]

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        # If not approved and requester is not admin, return 404 to hide it
        if not obj.is_approved and not (request.user and getattr(request.user, 'is_staff', False)):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return super().retrieve(request, *args, **kwargs)