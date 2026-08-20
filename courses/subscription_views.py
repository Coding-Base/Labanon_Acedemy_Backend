import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import os
from .models import Payment, ActivationUnlock, ActivationFee, ProPlan, UserSubscription, SubscriptionResetLog
from cbt.models import Exam
from .paystack_utils import PaystackClient, naira_to_kobo, generate_payment_reference, PaystackError

logger = logging.getLogger(__name__)


# ==========================================
# ACCESS CONTROL HELPER
# ==========================================

def user_has_exam_access(user, exam_identifier):
    """
    Determines if a user has access to a specific CBT Exam.
    
    Access is granted if:
    1. User is staff or superuser
    2. User has global `is_unlocked` bypass
    3. User has an active Pro subscription that covers this exam
    4. User has an active, non-revoked `ActivationUnlock` for this exam
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_staff or user.is_superuser or getattr(user, 'is_unlocked', False):
        return True

    now = timezone.now()

    # 1. Check active Pro subscription
    active_sub = UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.STATUS_ACTIVE,
        end_date__gt=now
    ).select_related('plan').first()

    if active_sub and active_sub.plan:
        plan = active_sub.plan
        if plan.all_exams_unlocked:
            return True
        # Check specific exam inclusion
        from cbt.models import Exam
        try:
            if str(exam_identifier).isdigit():
                exam_obj = Exam.objects.filter(id=int(exam_identifier)).first()
            else:
                exam_obj = Exam.objects.filter(slug=str(exam_identifier)).first()
            if exam_obj and plan.included_exams.filter(id=exam_obj.id).exists():
                return True
        except Exception as e:
            logger.error(f"Error checking plan exam inclusion: {e}")

    # 2. Check active ActivationUnlock
    unlock = ActivationUnlock.objects.filter(
        user=user,
        exam_identifier=str(exam_identifier),
        is_active=True
    ).first()

    if unlock:
        if unlock.expires_at is None or unlock.expires_at > now:
            return True

    return False


# ==========================================
# MASTER ADMIN VIEWS
# ==========================================

class AdminActivationsListView(APIView):
    """
    Lists all activation payments & unlocks for Master Admin.
    Provides filtering, search, and summary metrics.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        exam = request.GET.get('exam', '').strip()
        search = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', 'all').strip() # 'all', 'active', 'revoked'
        months = request.GET.get('months_older_than', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 25))

        qs = ActivationUnlock.objects.select_related('user', 'payment').all().order_by('-activated_at')

        # Filters
        if exam and exam != 'all':
            qs = qs.filter(exam_identifier=exam)

        if search:
            qs = qs.filter(
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(exam_identifier__icontains=search)
            )

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'revoked':
            qs = qs.filter(is_active=False)

        now = timezone.now()
        if months.isdigit():
            threshold_date = now - timedelta(days=int(months) * 30)
            qs = qs.filter(activated_at__lt=threshold_date)

        # Global metrics across all unlocks
        all_unlocks = ActivationUnlock.objects.all()
        total_activations = all_unlocks.count()
        active_count = all_unlocks.filter(is_active=True).count()
        revoked_count = all_unlocks.filter(is_active=False).count()
        
        nine_mos_ago = now - timedelta(days=9 * 30)
        older_than_9_mos = all_unlocks.filter(is_active=True, activated_at__lt=nine_mos_ago).count()

        # Total revenue from activation payments
        activation_payments = Payment.objects.filter(kind__in=[Payment.KIND_UNLOCK, 'unlock'], status=Payment.SUCCESS)
        total_revenue = activation_payments.aggregate(total=Sum('amount'))['total'] or 0

        # Pagination
        total_items = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        page_items = qs[start:end]

        data = []
        for item in page_items:
            age_days = (now - item.activated_at).days
            age_months = round(age_days / 30.0, 1)

            # Get human exam title if available
            exam_title = item.exam_identifier or "General"
            exam_obj = item.get_exam()
            if exam_obj:
                exam_title = exam_obj.title

            data.append({
                'id': item.id,
                'user_id': item.user.id,
                'username': item.user.username,
                'email': item.user.email,
                'full_name': f"{item.user.first_name} {item.user.last_name}".strip() or item.user.username,
                'exam_identifier': item.exam_identifier,
                'exam_title': exam_title,
                'amount': float(item.payment.amount) if item.payment else 0.0,
                'currency': item.payment.currency if item.payment else 'NGN',
                'activated_at': item.activated_at.isoformat(),
                'is_active': item.is_active,
                'revoked_at': item.revoked_at.isoformat() if item.revoked_at else None,
                'revocation_reason': item.revocation_reason,
                'age_months': age_months,
                'age_days': age_days,
            })

        return Response({
            'metrics': {
                'total_activations': total_activations,
                'active_unlocks': active_count,
                'revoked_unlocks': revoked_count,
                'older_than_9_months': older_than_9_mos,
                'total_revenue': float(total_revenue),
            },
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_items': total_items,
                'total_pages': max(1, (total_items + page_size - 1) // page_size),
            },
            'results': data,
        })


class AdminResetActivationsView(APIView):
    """
    Executes or previews bulk reset of student exam subscriptions.
    Allows specifying an exam and duration threshold (e.g. older than 9 months).
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        exam_identifier = request.data.get('exam_identifier', 'all').strip()
        months_threshold = int(request.data.get('months_threshold', 9))
        dry_run = bool(request.data.get('dry_run', False))
        custom_cutoff = request.data.get('cutoff_date')
        reason = request.data.get('reason', f'Admin bulk reset for subscriptions older than {months_threshold} months').strip()

        now = timezone.now()
        if custom_cutoff:
            try:
                cutoff_date = timezone.datetime.fromisoformat(custom_cutoff)
                if timezone.is_naive(cutoff_date):
                    cutoff_date = timezone.make_aware(cutoff_date)
            except Exception:
                cutoff_date = now - timedelta(days=months_threshold * 30)
        else:
            cutoff_date = now - timedelta(days=months_threshold * 30)

        # Target active unlocks older than cutoff
        qs = ActivationUnlock.objects.filter(
            is_active=True,
            activated_at__lt=cutoff_date
        )

        if exam_identifier and exam_identifier != 'all':
            qs = qs.filter(exam_identifier=exam_identifier)

        affected_count = qs.count()

        # Preview mode
        if dry_run:
            sample = []
            for item in qs.select_related('user')[:10]:
                sample.append({
                    'id': item.id,
                    'username': item.user.username,
                    'email': item.user.email,
                    'exam_identifier': item.exam_identifier,
                    'activated_at': item.activated_at.isoformat(),
                    'age_months': round((now - item.activated_at).days / 30.0, 1),
                })

            return Response({
                'dry_run': True,
                'affected_count': affected_count,
                'cutoff_date': cutoff_date.isoformat(),
                'months_threshold': months_threshold,
                'exam_identifier': exam_identifier,
                'sample_users': sample,
            })

        # Real Execution mode
        exam_title = "All Exams"
        if exam_identifier != 'all':
            from cbt.models import Exam
            exam_obj = Exam.objects.filter(slug=exam_identifier).first() or Exam.objects.filter(id=exam_identifier if str(exam_identifier).isdigit() else 0).first()
            if exam_obj:
                exam_title = exam_obj.title
            else:
                exam_title = exam_identifier

        # Batch update
        updated_rows = qs.update(
            is_active=False,
            revoked_at=now,
            revocation_reason=reason
        )

        # Create audit log
        log_entry = SubscriptionResetLog.objects.create(
            admin_user=request.user,
            exam_identifier=exam_identifier,
            exam_title=exam_title,
            months_threshold=months_threshold,
            cutoff_date=cutoff_date,
            affected_users_count=updated_rows,
            reason=reason
        )

        logger.info(f"Admin {request.user.username} reset {updated_rows} unlocks for exam '{exam_identifier}' older than {months_threshold} mos.")

        return Response({
            'success': True,
            'message': f"Successfully reset {updated_rows} user subscription(s) for {exam_title}.",
            'affected_count': updated_rows,
            'log_id': log_entry.id,
            'cutoff_date': cutoff_date.isoformat(),
        })


class AdminResetLogsView(APIView):
    """Returns audit history of subscription reset actions."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        logs = SubscriptionResetLog.objects.select_related('admin_user').all().order_by('-created_at')[:50]
        data = []
        for l in logs:
            data.append({
                'id': l.id,
                'admin': l.admin_user.username if l.admin_user else "System",
                'exam_identifier': l.exam_identifier,
                'exam_title': l.exam_title,
                'months_threshold': l.months_threshold,
                'cutoff_date': l.cutoff_date.isoformat(),
                'affected_users_count': l.affected_users_count,
                'reason': l.reason,
                'created_at': l.created_at.isoformat(),
            })
        return Response({'results': data})


class AdminProPlanView(APIView):
    """CRUD operations for Pro subscription tiers."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        plans = ProPlan.objects.prefetch_related('included_exams').all().order_by('order', 'price_ngn')
        available_exams = list(Exam.objects.all().order_by('title').values('id', 'title', 'slug', 'description'))
        data = []
        for p in plans:
            sub_count = p.subscriptions.filter(status=UserSubscription.STATUS_ACTIVE).count()
            data.append({
                'id': p.id,
                'name': p.name,
                'slug': p.slug,
                'description': p.description,
                'price_ngn': float(p.price_ngn),
                'price_usd': float(p.price_usd),
                'billing_interval_days': p.billing_interval_days,
                'all_exams_unlocked': p.all_exams_unlocked,
                'included_exams': list(p.included_exams.values('id', 'title', 'slug')),
                'allow_mock_exams': p.allow_mock_exams,
                'allow_materials_download': p.allow_materials_download,
                'material_download_limit': p.material_download_limit,
                'features_list': p.features_list or [],
                'badge': p.badge,
                'is_active': p.is_active,
                'order': p.order,
                'active_subscribers_count': sub_count,
                'created_at': p.created_at.isoformat(),
            })
        return Response({'results': data, 'available_exams': available_exams})

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'Plan name is required'}, status=status.HTTP_400_BAD_REQUEST)

        slug = request.data.get('slug') or slugify(name)
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while ProPlan.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        price_ngn = Decimal(str(request.data.get('price_ngn', 3500.0)))
        price_usd = Decimal(str(request.data.get('price_usd', 5.0)))
        interval = int(request.data.get('billing_interval_days', 30))
        all_exams = bool(request.data.get('all_exams_unlocked', True))
        allow_mock = bool(request.data.get('allow_mock_exams', True))
        allow_materials = bool(request.data.get('allow_materials_download', True))
        material_limit = int(request.data.get('material_download_limit', 0))
        badge = request.data.get('badge', '').strip() or None
        features = request.data.get('features_list', [])
        description = request.data.get('description', '').strip()
        order = int(request.data.get('order', 0))

        plan = ProPlan.objects.create(
            name=name,
            slug=slug,
            description=description,
            price_ngn=price_ngn,
            price_usd=price_usd,
            billing_interval_days=interval,
            all_exams_unlocked=all_exams,
            allow_mock_exams=allow_mock,
            allow_materials_download=allow_materials,
            material_download_limit=material_limit,
            features_list=features,
            badge=badge,
            order=order,
            is_active=True
        )

        exam_ids = request.data.get('included_exam_ids', [])
        if exam_ids and not all_exams:
            plan.included_exams.set(exam_ids)

        return Response({'success': True, 'id': plan.id, 'slug': plan.slug}, status=status.HTTP_201_CREATED)


class AdminProPlanDetailView(APIView):
    """Retrieve, update, or archive a specific Pro Plan."""
    permission_classes = [IsAdminUser]

    def put(self, request, plan_id):
        try:
            plan = ProPlan.objects.get(id=plan_id)
        except ProPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            plan.name = request.data['name'].strip()
        if 'description' in request.data:
            plan.description = request.data['description'].strip()
        if 'price_ngn' in request.data:
            plan.price_ngn = Decimal(str(request.data['price_ngn']))
        if 'price_usd' in request.data:
            plan.price_usd = Decimal(str(request.data['price_usd']))
        if 'billing_interval_days' in request.data:
            plan.billing_interval_days = int(request.data['billing_interval_days'])
        if 'all_exams_unlocked' in request.data:
            plan.all_exams_unlocked = bool(request.data['all_exams_unlocked'])
        if 'allow_mock_exams' in request.data:
            plan.allow_mock_exams = bool(request.data['allow_mock_exams'])
        if 'allow_materials_download' in request.data:
            plan.allow_materials_download = bool(request.data['allow_materials_download'])
        if 'material_download_limit' in request.data:
            plan.material_download_limit = int(request.data['material_download_limit'])
        if 'features_list' in request.data:
            plan.features_list = request.data['features_list']
        if 'badge' in request.data:
            plan.badge = request.data['badge'].strip() or None
        if 'is_active' in request.data:
            plan.is_active = bool(request.data['is_active'])
        if 'order' in request.data:
            plan.order = int(request.data['order'])

        if 'included_exam_ids' in request.data:
            plan.included_exams.set(request.data['included_exam_ids'])

        plan.save()
        return Response({'success': True, 'id': plan.id})

    def delete(self, request, plan_id):
        try:
            plan = ProPlan.objects.get(id=plan_id)
        except ProPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        # Soft delete / toggle active
        plan.is_active = False
        plan.save()
        return Response({'success': True, 'message': 'Plan deactivated'})


class AdminSubscribersView(APIView):
    """Lists all student Pro subscribers."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.GET.get('status', 'all')
        search = request.GET.get('search', '').strip()

        qs = UserSubscription.objects.select_related('user', 'plan', 'last_payment').all()

        if status_filter != 'all':
            qs = qs.filter(status=status_filter)

        if search:
            qs = qs.filter(
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search)
            )

        now = timezone.now()
        data = []
        for s in qs[:100]:
            data.append({
                'id': s.id,
                'user_id': s.user.id,
                'username': s.user.username,
                'email': s.user.email,
                'full_name': f"{s.user.first_name} {s.user.last_name}".strip() or s.user.username,
                'plan_name': s.plan.name if s.plan else "Custom Pro",
                'plan_id': s.plan.id if s.plan else None,
                'status': s.status,
                'start_date': s.start_date.isoformat(),
                'end_date': s.end_date.isoformat(),
                'auto_renew': s.auto_renew,
                'days_remaining': s.days_remaining(),
                'card_last4': s.card_last4,
                'card_brand': s.card_brand,
                'last_payment_amount': float(s.last_payment.amount) if s.last_payment else None,
                'created_at': s.created_at.isoformat(),
            })

        return Response({
            'total_subscribers': UserSubscription.objects.count(),
            'active_subscribers': UserSubscription.objects.filter(status=UserSubscription.STATUS_ACTIVE, end_date__gt=now).count(),
            'results': data
        })


class AdminGrantProView(APIView):
    """Allows Master Admin to manually grant complimentary Pro access to a student."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        user_id = request.data.get('user_id')
        plan_id = request.data.get('plan_id')
        days = int(request.data.get('days', 30))
        notes = request.data.get('notes', 'Granted by admin').strip()

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            student = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        plan = None
        if plan_id:
            plan = ProPlan.objects.filter(id=plan_id).first()
        if not plan:
            plan = ProPlan.objects.filter(is_active=True).first()

        now = timezone.now()
        # Check existing subscription
        existing = UserSubscription.objects.filter(user=student, status=UserSubscription.STATUS_ACTIVE).first()
        if existing and existing.end_date > now:
            existing.end_date = existing.end_date + timedelta(days=days)
            existing.notes = f"{existing.notes}\nExtended by {days} days on {now.strftime('%Y-%m-%d')}: {notes}"
            existing.save()
            sub = existing
        else:
            sub = UserSubscription.objects.create(
                user=student,
                plan=plan,
                status=UserSubscription.STATUS_ACTIVE,
                start_date=now,
                end_date=now + timedelta(days=days),
                auto_renew=False,
                notes=f"Granted by admin {request.user.username}: {notes}"
            )

        return Response({
            'success': True,
            'message': f"Granted {days} days of Pro access to {student.username}.",
            'end_date': sub.end_date.isoformat()
        })


# ==========================================
# STUDENT PRO VIEWS
# ==========================================

class StudentProPlansView(APIView):
    """Returns active Pro plans for public/student checkout display."""
    permission_classes = [AllowAny]

    def get(self, request):
        plans = ProPlan.objects.filter(is_active=True).prefetch_related('included_exams').order_by('order', 'price_ngn')
        data = []
        for p in plans:
            data.append({
                'id': p.id,
                'name': p.name,
                'slug': p.slug,
                'description': p.description,
                'price_ngn': float(p.price_ngn),
                'price_usd': float(p.price_usd),
                'billing_interval_days': p.billing_interval_days,
                'all_exams_unlocked': p.all_exams_unlocked,
                'included_exams': list(p.included_exams.values('id', 'title', 'slug')),
                'allow_mock_exams': p.allow_mock_exams,
                'allow_materials_download': p.allow_materials_download,
                'material_download_limit': p.material_download_limit,
                'features_list': p.features_list or [
                    "Full access to all JAMB, WAEC, NECO & GCE exams",
                    "Unlimited timed CBT practice tests & instant scoring",
                    "Full access to Custom Mock Exam sessions",
                    "Unlimited PDF study materials & syllabus downloads",
                    "In-depth performance analytics & leaderboard ranking",
                    "24/7 Priority student support"
                ],
                'badge': p.badge,
            })
        return Response({'plans': data})


class StudentSubscriptionStatusView(APIView):
    """Returns the current student's Pro status and subscription details."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        sub = UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.STATUS_ACTIVE,
            end_date__gt=now
        ).select_related('plan').first()

        if sub:
            return Response({
                'is_pro': True,
                'subscription': {
                    'id': sub.id,
                    'plan_name': sub.plan.name if sub.plan else "Pro Member",
                    'plan_slug': sub.plan.slug if sub.plan else "pro",
                    'start_date': sub.start_date.isoformat(),
                    'end_date': sub.end_date.isoformat(),
                    'days_remaining': sub.days_remaining(),
                    'auto_renew': sub.auto_renew,
                    'card_last4': sub.card_last4,
                    'card_brand': sub.card_brand,
                    'all_exams_unlocked': sub.plan.all_exams_unlocked if sub.plan else True,
                    'included_exams': list(sub.plan.included_exams.values('id', 'title', 'slug')) if (sub.plan and not sub.plan.all_exams_unlocked) else [],
                    'allow_mock_exams': sub.plan.allow_mock_exams if sub.plan else True,
                    'allow_materials_download': sub.plan.allow_materials_download if sub.plan else True,
                    'material_download_limit': sub.plan.material_download_limit if sub.plan else 0,
                    'features_list': sub.plan.features_list if sub.plan else [],
                }
            })

        return Response({
            'is_pro': False,
            'subscription': None
        })


class InitiateSubscriptionPaymentView(APIView):
    """Initiates a Paystack checkout for a Pro subscription."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        currency = request.data.get('currency', 'NGN').upper()
        auto_renew = bool(request.data.get('auto_renew', True))

        try:
            plan = ProPlan.objects.get(id=plan_id, is_active=True)
        except ProPlan.DoesNotExist:
            return Response({'error': 'Selected plan is not available'}, status=status.HTTP_404_NOT_FOUND)

        amount = plan.price_usd if currency == 'USD' else plan.price_ngn

        # Create pending Payment record
        payment = Payment.objects.create(
            user=request.user,
            amount=amount,
            currency=currency,
            kind=Payment.KIND_SUBSCRIPTION,
            status=Payment.PENDING,
            payment_provider=Payment.PROVIDER_PAYSTACK,
            provider_reference=json.dumps({
                'plan_id': plan.id,
                'plan_name': plan.name,
                'auto_renew': auto_renew,
                'type': 'pro_subscription'
            })
        )

        frontend_base = getattr(settings, 'FRONTEND_URL', None) or os.getenv('FRONTEND_URL') or 'http://localhost:5173'
        ref = generate_payment_reference()
        payment.paystack_reference = ref
        payment.save()

        callback_url = f"{frontend_base}/payment/verify?reference={ref}&type=subscription"

        # Initialize with Paystack
        metadata = {
            'user_id': request.user.id,
            'email': request.user.email,
            'payment_id': payment.id,
            'plan_id': plan.id,
            'plan_slug': plan.slug,
            'auto_renew': auto_renew,
            'kind': Payment.KIND_SUBSCRIPTION
        }

        gateway_amount = naira_to_kobo(amount) if currency == 'NGN' else int(Decimal(str(amount)) * 100)

        try:
            client = PaystackClient()
            paystack_resp = client.initialize_payment(
                email=request.user.email,
                amount=gateway_amount,
                reference=ref,
                metadata=metadata,
                callback_url=callback_url,
                currency=currency
            )
        except PaystackError as e:
            payment.status = Payment.FAILED
            payment.save()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'authorization_url': paystack_resp.get('authorization_url'),
            'access_code': paystack_resp.get('access_code'),
            'reference': ref,
            'payment_id': payment.id,
        })


class VerifySubscriptionPaymentView(APIView):
    """Verifies payment with Paystack and activates the student's Pro subscription."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reference = request.data.get('reference')
        if not reference:
            return Response({'error': 'Reference is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Look up payment
        payment = Payment.objects.filter(paystack_reference=reference, user=request.user).first()
        if not payment:
            payment = Payment.objects.filter(id=reference if str(reference).isdigit() else 0, user=request.user).first()

        if not payment:
            return Response({'error': 'Payment record not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == Payment.SUCCESS:
            sub = UserSubscription.objects.filter(user=request.user, status=UserSubscription.STATUS_ACTIVE).first()
            return Response({
                'success': True,
                'message': 'Subscription is already active',
                'subscription': {
                    'plan_name': sub.plan.name if sub and sub.plan else "Pro",
                    'end_date': sub.end_date.isoformat() if sub else None,
                    'days_remaining': sub.days_remaining() if sub else 30
                }
            })

        # Verify with Paystack API
        try:
            client = PaystackClient()
            vdata = client.verify_payment(payment.paystack_reference or reference)
        except PaystackError as e:
            payment.status = Payment.FAILED
            payment.save()
            return Response({'error': f"Payment verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if not vdata or vdata.get('status') != 'success':
            payment.status = Payment.FAILED
            payment.save()
            return Response({'error': 'Payment verification failed or was declined'}, status=status.HTTP_400_BAD_REQUEST)

        payment.status = Payment.SUCCESS
        payment.verified_at = timezone.now()
        payment.gateway_fee = Decimal(str(vdata.get('fees', 0))) / Decimal('100')
        payment.save()

        # Extract plan from provider metadata
        plan = None
        auto_renew = True
        try:
            meta = json.loads(payment.provider_reference or '{}')
            plan_id = meta.get('plan_id')
            auto_renew = meta.get('auto_renew', True)
            if plan_id:
                plan = ProPlan.objects.filter(id=plan_id).first()
        except Exception:
            pass

        if not plan:
            plan = ProPlan.objects.filter(is_active=True).first()

        # Extract saved card authorization
        auth_data = vdata.get('authorization', {})
        auth_code = auth_data.get('authorization_code')
        last4 = auth_data.get('last4')
        brand = auth_data.get('brand')
        customer_code = vdata.get('customer', {}).get('customer_code')

        now = timezone.now()
        interval_days = plan.billing_interval_days if plan else 30
        end_date = now + timedelta(days=interval_days)

        # Check existing subscription to extend or create
        existing_sub = UserSubscription.objects.filter(user=request.user).first()
        if existing_sub:
            existing_sub.plan = plan
            existing_sub.status = UserSubscription.STATUS_ACTIVE
            existing_sub.start_date = now
            existing_sub.end_date = end_date
            existing_sub.auto_renew = auto_renew
            existing_sub.paystack_authorization_code = auth_code or existing_sub.paystack_authorization_code
            existing_sub.paystack_customer_code = customer_code or existing_sub.paystack_customer_code
            existing_sub.card_last4 = last4 or existing_sub.card_last4
            existing_sub.card_brand = brand or existing_sub.card_brand
            existing_sub.last_payment = payment
            existing_sub.save()
            sub = existing_sub
        else:
            sub = UserSubscription.objects.create(
                user=request.user,
                plan=plan,
                status=UserSubscription.STATUS_ACTIVE,
                start_date=now,
                end_date=end_date,
                auto_renew=auto_renew,
                paystack_authorization_code=auth_code,
                paystack_customer_code=customer_code,
                card_last4=last4,
                card_brand=brand,
                last_payment=payment
            )

        return Response({
            'success': True,
            'message': 'Pro Subscription activated successfully!',
            'subscription': {
                'plan_name': plan.name if plan else "Pro",
                'end_date': sub.end_date.isoformat(),
                'days_remaining': sub.days_remaining(),
                'auto_renew': sub.auto_renew
            }
        })


class ToggleAutoRenewView(APIView):
    """Allows student to turn auto-renewal on or off."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sub = UserSubscription.objects.filter(user=request.user, status=UserSubscription.STATUS_ACTIVE).first()
        if not sub:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)

        sub.auto_renew = not sub.auto_renew
        sub.save()

        return Response({
            'success': True,
            'auto_renew': sub.auto_renew,
            'message': f"Auto-renewal is now {'enabled' if sub.auto_renew else 'disabled'}."
        })


class CancelSubscriptionView(APIView):
    """Cancels student subscription so it will not renew at the end of cycle."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sub = UserSubscription.objects.filter(user=request.user, status=UserSubscription.STATUS_ACTIVE).first()
        if not sub:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)

        sub.auto_renew = False
        sub.status = UserSubscription.STATUS_CANCELLED
        sub.notes = f"{sub.notes}\nCancelled by user on {timezone.now().strftime('%Y-%m-%d')}"
        sub.save()

        return Response({
            'success': True,
            'message': f"Subscription cancelled. You will retain Pro access until {sub.end_date.strftime('%B %d, %Y')}."
        })
