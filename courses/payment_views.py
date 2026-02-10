import hmac
import hashlib
import json
import os
import logging
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .webhook_verification import (
    PaystackWebhookVerifier, FlutterwaveWebhookVerifier, PaymentReconciliation,
    WebhookVerificationError
)
from rest_framework import status, viewsets
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.core.mail import send_mail
from django.template.loader import render_to_string # Although we build string manually here for simplicity, good practice is templates

from .models import (
    Payment, Course, Diploma, Enrollment, DiplomaEnrollment,
    PaystackSubAccount, FlutterwaveSubAccount, ActivationFee, ActivationUnlock
)
from .models import Visit
from .serializers import VisitSerializer
from django.db.models import Count
from .models import PaymentSplitConfig
from .paystack_utils import PaystackClient, naira_to_kobo, calculate_split, generate_payment_reference, PaystackError
from .flutterwave_utils import FlutterwaveClient, FlutterwaveError, generate_payment_reference as generate_flutterwave_reference
from .serializers import PaymentSerializer
try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Metric, Dimension, RunReportRequest
    GA_CLIENT_AVAILABLE = True
except Exception:
    GA_CLIENT_AVAILABLE = False

logger = logging.getLogger(__name__)


class TrackPageView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data or {}
        path = data.get('page_path') or data.get('path') or ''
        full_url = data.get('full_url') or data.get('url') or ''
        referrer = data.get('referrer') or ''
        utm_source = data.get('utm_source') or ''
        utm_medium = data.get('utm_medium') or ''
        utm_campaign = data.get('utm_campaign') or ''
        utm_term = data.get('utm_term') or ''
        utm_content = data.get('utm_content') or ''
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))

        session_id = data.get('session_id') or None
        try:
            visit = Visit.objects.create(
                path=path[:1024], full_url=full_url[:2048], referrer=referrer[:2048],
                utm_source=utm_source[:255], utm_medium=utm_medium[:255], utm_campaign=utm_campaign[:255],
                utm_term=utm_term[:255], utm_content=utm_content[:255], user_agent=user_agent[:1024], ip_address=(ip or '')[:45],
                session_id=session_id[:128] if session_id else None
            )
            # mark landing if no previous visit in this session
            try:
                if visit.session_id:
                    prev = Visit.objects.filter(session_id=visit.session_id).exclude(id=visit.id).order_by('created_at').first()
                    if not prev:
                        visit.is_landing = True
                        visit.save(update_fields=['is_landing'])
                else:
                    # heuristics: consider landing when referrer empty or external
                    if not visit.referrer:
                        visit.is_landing = True
                        visit.save(update_fields=['is_landing'])
            except Exception:
                pass

            # attempt geo enrichment if geoip2 is available and IP present
            try:
                if visit.ip_address:
                    import geoip2.database
                    dbpath = getattr(settings, 'GEOIP_DB_PATH', None)
                    if dbpath:
                        try:
                            reader = geoip2.database.Reader(dbpath)
                            rec = reader.city(visit.ip_address)
                            visit.country = rec.country.name
                            visit.region = rec.subdivisions.most_specific.name
                            visit.city = rec.city.name
                            visit.save(update_fields=['country','region','city'])
                        except Exception:
                            pass
            except Exception:
                pass

            return Response({'detail': 'ok', 'id': visit.id})
        except Exception as e:
            logger.exception('Failed to record visit')
            return Response({'detail': 'error', 'error': str(e)}, status=500)


class ReferrerStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'permission denied'}, status=403)

        # Top UTM sources
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        qs = Visit.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)

        sources = list(qs.values('utm_source').annotate(count=Count('id')).order_by('-count')[:50])
        referrers = list(qs.values('referrer').annotate(count=Count('id')).order_by('-count')[:200])

        # Optionally return CSV when requested
        fmt = request.query_params.get('format')
        if fmt == 'csv':
            import csv
            from django.http import HttpResponse
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="referrers.csv"'
            writer = csv.writer(response)
            writer.writerow(['type', 'value', 'count'])
            for s in sources:
                writer.writerow(['utm_source', s.get('utm_source') or '(none)', s.get('count')])
            for r in referrers:
                writer.writerow(['referrer', r.get('referrer') or '(direct)', r.get('count')])
            return response

        return Response({'utm_sources': sources, 'referrers': referrers})


class DailyAnalyticsView(APIView):
    """Return daily breakdown of visits, payments, and revenue."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Sum
        from datetime import datetime, timedelta
        import json

        if not request.user.is_staff:
            return Response({'detail': 'permission denied'}, status=403)

        start = request.query_params.get('start')
        end = request.query_params.get('end')
        
        # Default to last 30 days
        if not end:
            end_date = timezone.now()
        else:
            try:
                end_date = datetime.fromisoformat(end)
            except:
                end_date = timezone.now()
        
        if not start:
            start_date = end_date - timedelta(days=30)
        else:
            try:
                start_date = datetime.fromisoformat(start)
            except:
                start_date = end_date - timedelta(days=30)

        # Aggregate visits by date
        daily_visits = Visit.objects.filter(
            created_at__date__gte=start_date.date(),
            created_at__date__lte=end_date.date()
        ).extra(
            select={'date': 'DATE(created_at)'}
        ).values('date').annotate(
            views=Count('id'),
            landing_views=Count('id', filter=Q(is_landing=True))
        ).order_by('date')

        # Aggregate payments by date
        daily_payments = Payment.objects.filter(
            created_at__date__gte=start_date.date(),
            created_at__date__lte=end_date.date(),
            status=Payment.COMPLETE
        ).extra(
            select={'date': 'DATE(created_at)'}
        ).values('date').annotate(
            transactions=Count('id'),
            revenue=Sum('amount'),
            platform_fee=Sum('platform_fee'),
            creator_amount=Sum('creator_amount')
        ).order_by('date')

        # Merge data by date
        daily_data = {}
        for visit in daily_visits:
            date_str = str(visit['date'])
            if date_str not in daily_data:
                daily_data[date_str] = {}
            daily_data[date_str].update({
                'date': date_str,
                'views': visit['views'],
                'landing_views': visit['landing_views']
            })

        for payment in daily_payments:
            date_str = str(payment['date'])
            if date_str not in daily_data:
                daily_data[date_str] = {'date': date_str}
            daily_data[date_str].update({
                'transactions': payment['transactions'],
                'revenue': float(payment['revenue'] or 0),
                'platform_fee': float(payment['platform_fee'] or 0),
                'creator_amount': float(payment['creator_amount'] or 0)
            })

        # Sort and fill in missing metrics with 0
        daily_list = sorted(daily_data.values(), key=lambda x: x['date'])
        for item in daily_list:
            item.setdefault('views', 0)
            item.setdefault('landing_views', 0)
            item.setdefault('transactions', 0)
            item.setdefault('revenue', 0)
            item.setdefault('platform_fee', 0)
            item.setdefault('creator_amount', 0)

        # Calculate totals
        totals = {
            'views': sum(d['views'] for d in daily_list),
            'landing_views': sum(d['landing_views'] for d in daily_list),
            'transactions': sum(d['transactions'] for d in daily_list),
            'revenue': sum(d['revenue'] for d in daily_list),
            'platform_fee': sum(d['platform_fee'] for d in daily_list),
            'creator_amount': sum(d['creator_amount'] for d in daily_list)
        }

        # Optionally return CSV
        fmt = request.query_params.get('format')
        if fmt == 'csv':
            import csv
            from django.http import HttpResponse
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="daily_analytics.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Page Views', 'Landing Views', 'Transactions', 'Revenue', 'Platform Fee', 'Creator Amount'])
            for item in daily_list:
                writer.writerow([
                    item['date'],
                    item['views'],
                    item['landing_views'],
                    item['transactions'],
                    f"${item['revenue']:.2f}",
                    f"${item['platform_fee']:.2f}",
                    f"${item['creator_amount']:.2f}"
                ])
            return response

        return Response({'daily': daily_list, 'totals': totals})

# ==================== EMAIL HELPER FUNCTION ====================

def send_successful_payment_emails(payment):
    """
    Sends 3 HTML emails upon successful payment:
    1. To Student (Receipt)
    2. To Creator (Notification)
    3. To Admin (Alert)
    """
    try:
        # 1. Determine Item Details (Course or Diploma)
        item_title = "Unknown Item"
        creator_email = None
        creator_name = "Creator"
        
        if payment.kind == Payment.KIND_COURSE and payment.course:
            item_title = payment.course.title
            if payment.course.creator:
                creator_email = payment.course.creator.email
                creator_name = payment.course.creator.username
        elif payment.kind == Payment.KIND_DIPLOMA and payment.diploma:
            item_title = payment.diploma.title
            if payment.diploma.creator:
                creator_email = payment.diploma.creator.email
                creator_name = payment.diploma.creator.username

        # Format Data
        amount_formatted = f"NGN {payment.amount:,.2f}"
        reference = payment.paystack_reference or payment.flutterwave_reference
        date_str = timezone.now().strftime('%d %b %Y, %I:%M %p')
        
        # --- HTML TEMPLATE BASE ---
        def get_html_template(title, body_content):
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f9fafb; margin: 0; padding: 0; }}
                    .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; }}
                    .header {{ background-color: #16a34a; padding: 20px; text-align: center; color: #ffffff; }}
                    .header h2 {{ margin: 0; font-size: 24px; font-weight: 600; }}
                    .content {{ padding: 30px; color: #374151; line-height: 1.6; }}
                    .details-box {{ background-color: #f3f4f6; border-radius: 6px; padding: 15px; margin: 20px 0; border-left: 4px solid #16a34a; }}
                    .details-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }}
                    .label {{ font-weight: 600; color: #4b5563; }}
                    .value {{ color: #111827; }}
                    .footer {{ background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
                    .btn {{ display: inline-block; padding: 10px 20px; background-color: #16a34a; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>{title}</h2>
                    </div>
                    <div class="content">
                        {body_content}
                    </div>
                    <div class="footer">
                        &copy; {timezone.now().year} LightHub Academy. All rights reserved.
                    </div>
                </div>
            </body>
            </html>
            """

        # --- 1. Email to Student ---
        student_body = f"""
            <p>Hello <strong>{payment.user.first_name or payment.user.username}</strong>,</p>
            <p>Thank you for your purchase! We are excited to have you onboard.</p>
            <div class="details-box">
                <div class="details-row"><span class="label">Item:</span> <span class="value">{item_title}</span></div>
                <div class="details-row"><span class="label">Amount Paid:</span> <span class="value">{amount_formatted}</span></div>
                <div class="details-row"><span class="label">Reference:</span> <span class="value">{reference}</span></div>
                <div class="details-row"><span class="label">Date:</span> <span class="value">{date_str}</span></div>
            </div>
            <p>You can now access your course directly from your dashboard.</p>
            <center><a href="{settings.FRONTEND_URL}/dashboard" class="btn">Go to Dashboard</a></center>
        """
        
        send_mail(
            subject=f"Receipt: {item_title}",
            message=f"Payment received for {item_title}. Amount: {amount_formatted}", # Plain text fallback
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[payment.user.email],
            html_message=get_html_template("Payment Successful", student_body),
            fail_silently=True
        )

        # --- 2. Email to Course Creator ---
        if creator_email:
            creator_body = f"""
                <p>Hello <strong>{creator_name}</strong>,</p>
                <p>Great news! A new student has just enrolled in your course.</p>
                <div class="details-box">
                    <div class="details-row"><span class="label">Course:</span> <span class="value">{item_title}</span></div>
                    <div class="details-row"><span class="label">Student:</span> <span class="value">{payment.user.first_name} {payment.user.last_name}</span></div>
                    <div class="details-row"><span class="label">Total Paid:</span> <span class="value">{amount_formatted}</span></div>
                    <div class="details-row"><span class="label" style="color:#16a34a;">Your Earnings:</span> <span class="value" style="font-weight:bold;">NGN {payment.creator_amount:,.2f}</span></div>
                </div>
                
                <div class="details-box" style="background-color: #dbeafe; border-left-color: #0284c7;">
                    <p style="margin-top: 0; font-weight: 600; color: #0c4a6e;">Payment Settlement Timeline</p>
                    <p style="margin: 10px 0 15px; color: #1e40af; font-size: 14px;">Your earnings will be deposited within <strong>24-72 hours</strong> of this transaction. Here's what to expect:</p>
                    <ul style="margin: 10px 0; padding-left: 20px; font-size: 13px; color: #1e40af;">
                        <li><strong>Immediate:</strong> Payment verified and confirmed</li>
                        <li><strong>0-24 hours:</strong> Payment marked for settlement</li>
                        <li><strong>24-48 hours:</strong> Paystack processes the payout</li>
                        <li><strong>48-72 hours:</strong> Funds deposited in your bank account</li>
                    </ul>
                    <p style="margin: 10px 0 0; font-size: 12px; color: #1e40af;"><em>Note: Settlement times may vary based on your bank and payment gateway processing. Weekend and holiday deposits may take longer.</em></p>
                </div>
                
                <p>Keep up the excellent work providing value to students!</p>
            """
            
            send_mail(
                subject=f"New Enrollment: {item_title}",
                message=f"New student enrolled in {item_title}. Earnings: NGN {payment.creator_amount:,.2f}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[creator_email],
                html_message=get_html_template("New Student Enrollment", creator_body),
                fail_silently=True
            )

        # --- 3. Email to Platform Admin ---
        admin_body = f"""
            <p><strong>New Successful Transaction Detected.</strong></p>
            <div class="details-box">
                <div class="details-row"><span class="label">Item:</span> <span class="value">{item_title}</span></div>
                <div class="details-row"><span class="label">Buyer Email:</span> <span class="value">{payment.user.email}</span></div>
                <div class="details-row"><span class="label">Total Amount:</span> <span class="value">{amount_formatted}</span></div>
                <div class="details-row"><span class="label">Platform Fee:</span> <span class="value">NGN {payment.platform_fee:,.2f}</span></div>
                <div class="details-row"><span class="label">Creator Earning:</span> <span class="value">NGN {payment.creator_amount:,.2f}</span></div>
                <div class="details-row"><span class="label">Ref:</span> <span class="value">{reference}</span></div>
            </div>
        """
        
        admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@lebanonacademy.ng')
        send_mail(
            subject=f"Transaction Alert: {amount_formatted}",
            message=f"New transaction: {item_title} by {payment.user.email}. Amount: {amount_formatted}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_email],
            html_message=get_html_template("Transaction Alert", admin_body),
            fail_silently=True
        )

        logger.info(f"Sent styled payment emails for Payment ID {payment.id}")

    except Exception as e:
        logger.error(f"Failed to send payment emails for Payment ID {payment.id}: {str(e)}")


# ==================== VIEWS ====================

class InitiatePaymentView(APIView):
    """Initiate Paystack payment for courses and diplomas."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        amount = request.data.get('amount')
        requested_currency = request.data.get('currency')
        # Optional currency provided by frontend (ISO code)
        requested_currency = request.data.get('currency')

        # Basic required fields: item_type and amount. item_id is required
        # only for course/diploma item types. Allow item_id == 0 for
        # activation flows (frontend may send 0 as placeholder).
        if not item_type or amount is None:
            return Response({'detail': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

        if item_type in ('course', 'diploma') and (item_id is None or str(item_id).strip() == ''):
            return Response({'detail': 'Missing required fields: item_id required for course/diploma'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({'detail': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

            # Determine kind/item and support activation payments
            kind = None
            item = None
            activation_meta = None

            if item_type == 'course':
                item = Course.objects.get(id=item_id)
                kind = Payment.KIND_COURSE
            elif item_type == 'diploma':
                item = Diploma.objects.get(id=item_id)
                kind = Payment.KIND_DIPLOMA
            elif item_type == 'activation':
                kind = Payment.KIND_UNLOCK
                activation_meta = {
                    'activation_type': request.data.get('activation_type'),
                    'exam_id': request.data.get('exam_id') or request.data.get('item_id'),
                    'subject_id': request.data.get('subject_id'),
                    'activation_role': request.data.get('activation_role') or (request.data.get('activation') and request.data.get('activation').get('role')),
                }
            else:
                return Response({'detail': 'Invalid item_type'}, status=status.HTTP_400_BAD_REQUEST)

            amount_decimal = Decimal(str(amount))
            # Determine currency: frontend > activation fee (if any) > default
            currency = (requested_currency or '').strip().upper() if requested_currency else None
            if kind == Payment.KIND_UNLOCK:
                fee_currency = None
                try:
                    exam_id = request.data.get('exam_id') or request.data.get('item_id')
                    subject_id = request.data.get('subject_id')
                    activation_type = request.data.get('activation_type') or (request.data.get('activation') and request.data.get('activation').get('activation_type'))
                    # Support account activation fees per role
                    if activation_type == 'account':
                        activation_role = request.data.get('activation_role') or (request.data.get('activation') and request.data.get('activation').get('role'))
                        if activation_role:
                            fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT, account_role=activation_role).order_by('-updated_at').first()
                        else:
                            fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT).order_by('-updated_at').first()
                    elif subject_id:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_INTERVIEW, subject_id=subject_id).order_by('-updated_at').first()
                    elif exam_id:
                        fee = ActivationFee.objects.filter(exam_identifier=str(exam_id)).order_by('-updated_at').first()
                    else:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_EXAM).order_by('-updated_at').first()
                    if fee:
                        fee_currency = fee.currency
                except Exception:
                    fee_currency = None
                if not currency:
                    currency = (fee_currency or 'NGN').upper()
            else:
                if not currency:
                    currency = getattr(settings, 'DEFAULT_CURRENCY', 'NGN').upper()
            # Determine currency: frontend > activation fee (if any) > default
            currency = (requested_currency or '').strip().upper() if requested_currency else None
            if kind == Payment.KIND_UNLOCK:
                # Try to fetch configured activation fee when not provided (repeat block handles role/account)
                fee_currency = None
                try:
                    exam_id = request.data.get('exam_id') or request.data.get('item_id')
                    subject_id = request.data.get('subject_id')
                    activation_type = request.data.get('activation_type') or (request.data.get('activation') and request.data.get('activation').get('activation_type'))
                    if activation_type == 'account':
                        activation_role = request.data.get('activation_role') or (request.data.get('activation') and request.data.get('activation').get('role'))
                        if activation_role:
                            fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT, account_role=activation_role).order_by('-updated_at').first()
                        else:
                            fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT).order_by('-updated_at').first()
                    elif subject_id:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_INTERVIEW, subject_id=subject_id).order_by('-updated_at').first()
                    elif exam_id:
                        fee = ActivationFee.objects.filter(exam_identifier=str(exam_id)).order_by('-updated_at').first()
                    else:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_EXAM).order_by('-updated_at').first()
                    if fee:
                        fee_currency = fee.currency
                except Exception:
                    fee_currency = None
                if not currency:
                    currency = (fee_currency or 'NGN').upper()
            else:
                if not currency:
                    # default currency for payments
                    currency = getattr(settings, 'DEFAULT_CURRENCY', 'NGN').upper()
            # For activation payments platform receives full amount
            if kind == Payment.KIND_UNLOCK:
                platform_fee = amount_decimal
                creator_amount = Decimal('0.00')
            else:
                # Fetch the configured splits
                split_cfg = PaymentSplitConfig.get_solo()
                # If the item has an institution, use institution_share; otherwise tutor_share
                creator_share_percent = None
                if item_type == 'course' and isinstance(item, Course) and item.institution:
                    creator_share_percent = split_cfg.institution_share
                elif item_type == 'diploma' and isinstance(item, Diploma) and item.institution:
                    creator_share_percent = split_cfg.institution_share
                else:
                    creator_share_percent = split_cfg.tutor_share

                # Platform percentage is the remainder
                platform_percentage = Decimal('100.00') - Decimal(str(creator_share_percent))
                platform_fee, creator_amount = calculate_split(amount_decimal, platform_percentage=platform_percentage)

            payment_reference = generate_payment_reference()

            payment_data = {
                'user': user,
                # store major-unit decimal (e.g., Naira, USD) in Payment.amount
                'amount': amount_decimal,
                'currency': currency,
                'kind': kind,
                'platform_fee': platform_fee,
                'creator_amount': creator_amount,
                'paystack_reference': payment_reference,
                'status': Payment.PENDING,
            }

            if item_type == 'course':
                payment_data['course'] = item
            elif item_type == 'diploma':
                payment_data['diploma'] = item
            elif item_type == 'activation':
                # persist activation metadata for later processing
                try:
                    payment_data['provider_reference'] = json.dumps(activation_meta)
                except Exception:
                    payment_data['provider_reference'] = ''

            payment = Payment.objects.create(**payment_data)

            # --- Attribution: attach Visit to Payment if visit_id provided ---
            try:
                visit_id = request.data.get('visit_id') or (request.data.get('visit') and request.data.get('visit').get('id'))
                if visit_id:
                    try:
                        visit_obj = Visit.objects.filter(id=int(visit_id)).first()
                        if visit_obj:
                            payment.visit = visit_obj
                            payment.save(update_fields=['visit'])
                    except Exception:
                        # don't block payment initiation on bad visit id
                        logger.debug(f"Invalid visit_id provided for payment attribution: {visit_id}")
            except Exception:
                pass

            try:
                client = PaystackClient()
                metadata = {
                    'payment_id': payment.id,
                    'item_type': item_type,
                    'item_id': item_id,
                    'user_id': user.id,
                }
                if activation_meta:
                    metadata['activation'] = activation_meta

                frontend_base = os.getenv('FRONTEND_URL') or 'http://localhost:5173'
                callback_url = f"{frontend_base}/payment/verify"

                # For course/diploma payments, try to use tutor's sub-account for split payment
                recipient_code = None
                if kind in (Payment.KIND_COURSE, Payment.KIND_DIPLOMA):
                    creator = item.creator if item else None
                    if creator:
                        try:
                            subaccount = PaystackSubAccount.objects.get(user=creator)
                            if subaccount.subaccount_code:
                                recipient_code = subaccount.subaccount_code
                                # Store tutor info in payment for reference
                                payment.recipient_code = recipient_code
                                payment.save()
                        except PaystackSubAccount.DoesNotExist:
                            logger.warning(f"No Paystack sub-account found for course creator {creator.id}")

                # Convert amount to gateway subunits (Paystack expects kobo for NGN; others typically use cents)
                if currency == 'NGN':
                    gateway_amount = naira_to_kobo(amount_decimal)
                else:
                    gateway_amount = int((amount_decimal * Decimal('100')).to_integral_value())

                paystack_data = client.initialize_payment(
                    email=user.email,
                    amount=gateway_amount,
                    reference=payment_reference,
                    metadata=metadata,
                    callback_url=callback_url,
                    recipient_code=recipient_code,  # Use tutor's subaccount
                    currency=currency
                )

                return Response({
                    'payment_id': payment.id,
                    'reference': payment_reference,
                    'authorization_url': paystack_data.get('authorization_url'),
                    'access_code': paystack_data.get('access_code'),
                }, status=status.HTTP_201_CREATED)

            except PaystackError as e:
                payment.status = Payment.FAILED
                payment.save()
                logger.error(f"Paystack initialization failed: {str(e)}")
                return Response({'detail': f'Payment initialization failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        except (Course.DoesNotExist, Diploma.DoesNotExist):
            return Response({'detail': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyPaymentView(APIView):
    """Verify Paystack payment."""
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            
            if payment.user != request.user:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

            try:
                client = PaystackClient()
                transaction_data = client.verify_payment(reference)

                if transaction_data.get('status') == 'success':
                    # Only process if not already successful to avoid duplicates
                    if payment.status != Payment.SUCCESS:
                        with transaction.atomic():
                            payment.status = Payment.SUCCESS
                            payment.verified_at = timezone.now()
                            
                            # Extract gateway fee from Paystack response (in kobo, convert to Naira)
                            gateway_fee_kobo = transaction_data.get('fees', 0)
                            payment.gateway_fee = gateway_fee_kobo / 100  # Convert from kobo to Naira
                            payment.net_amount = transaction_data.get('net', 0) / 100  # Convert from kobo to Naira
                            
                            payment.save()

                            if payment.kind == Payment.KIND_COURSE and payment.course:
                                Enrollment.objects.update_or_create(
                                    user=payment.user,
                                    course=payment.course,
                                    defaults={'purchased': True, 'purchased_at': timezone.now()}
                                )
                            elif payment.kind == Payment.KIND_DIPLOMA and payment.diploma:
                                DiplomaEnrollment.objects.update_or_create(
                                    user=payment.user,
                                    diploma=payment.diploma,
                                    defaults={'purchased': True, 'purchased_at': timezone.now()}
                                )
                            # Activation unlocks are handled below using provider transaction metadata
                            elif payment.kind == Payment.KIND_UNLOCK:
                                # Create ActivationUnlock record based on provider metadata
                                try:
                                    meta = None
                                    if payment.provider_reference:
                                        try:
                                            meta = json.loads(payment.provider_reference)
                                        except Exception:
                                            meta = None

                                    tx_meta = transaction_data.get('metadata') or {}
                                    activation = None
                                    if isinstance(tx_meta, dict) and tx_meta.get('activation'):
                                        activation = tx_meta.get('activation')
                                    elif isinstance(tx_meta, dict) and tx_meta.get('activation_type'):
                                        # support providers that inline fields directly
                                        activation = tx_meta
                                    else:
                                        activation = meta

                                    exam_identifier = activation.get('exam_id') if activation else None
                                    subject_id = activation.get('subject_id') if activation else None

                                    # Support account-level activation: mark user as unlocked
                                    try:
                                        activation_type = activation.get('activation_type') if activation else None
                                        if activation_type == 'account':
                                            try:
                                                u = payment.user
                                                u.is_unlocked = True
                                                u.save()
                                                logger.info(f"User {u.id} marked as unlocked via account activation payment")
                                            except Exception as ue:
                                                logger.error(f"Failed to mark user unlocked: {str(ue)}")
                                    except Exception:
                                        logger.exception("Activation processing error")

                                    if exam_identifier or subject_id:
                                        ActivationUnlock.objects.get_or_create(
                                            user=payment.user,
                                            exam_identifier=str(exam_identifier) if exam_identifier else None,
                                            subject_id=int(subject_id) if subject_id else None,
                                            defaults={'payment': payment}
                                        )
                                    # Mark account unlocked if activation_type == 'account'
                                    try:
                                        activation_type = activation.get('activation_type') if activation else None
                                        if activation_type == 'account':
                                            try:
                                                u = payment.user
                                                u.is_unlocked = True
                                                u.save()
                                            except Exception as ue:
                                                logger.error(f"Failed to mark user unlocked: {str(ue)}")
                                    except Exception:
                                        pass
                                        # also handle account-level activation via presence of activation_type
                                        try:
                                            if activation and activation.get('activation_type') == 'account':
                                                u = payment.user
                                                u.is_unlocked = True
                                                u.save()
                                        except Exception as e:
                                            logger.error(f"Failed to mark user unlocked: {str(e)}")
                                except Exception as e:
                                    logger.error(f"Failed to create activation unlock: {str(e)}")
                        
                        # Send Emails (Outside atomic block usually, but inside view is fine)
                        send_successful_payment_emails(payment)

                else:
                    payment.status = Payment.FAILED
                    payment.save()

                serializer = PaymentSerializer(payment)
                return Response(serializer.data, status=status.HTTP_200_OK)

            except PaystackError as e:
                logger.error(f"Payment verification error: {str(e)}")
                return Response({'detail': f'Verification failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        except Payment.DoesNotExist:
            return Response({'detail': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)


class ActivationFeeView(APIView):
    """Return activation fee for exam or interview subject.

    Query params:
    - type: 'exam' or 'interview' (default 'exam')
    - exam: exam identifier (id or slug)
    - subject: subject id (for interview)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        fee_type = request.query_params.get('type', 'exam')
        exam = request.query_params.get('exam')
        subject = request.query_params.get('subject')
        account_role = request.query_params.get('account_role')

        try:
            # Priority: subject-specific, exam-specific, then default global fee for type
            if subject:
                fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_INTERVIEW, subject_id=subject).order_by('-updated_at').first()
            elif exam:
                fee = ActivationFee.objects.filter(exam_identifier=str(exam)).order_by('-updated_at').first()
            else:
                if fee_type == ActivationFee.TYPE_ACCOUNT or fee_type == 'account':
                    if account_role:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT, account_role=account_role).order_by('-updated_at').first()
                    else:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_ACCOUNT).order_by('-updated_at').first()
                else:
                    fee = ActivationFee.objects.filter(type=fee_type).order_by('-updated_at').first()

            if not fee:
                return Response({'amount': None}, status=status.HTTP_200_OK)

            return Response({'amount': float(fee.amount), 'currency': fee.currency}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Failed to fetch activation fee: {str(e)}")
            return Response({'detail': 'Error fetching fee'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAnalyticsView(APIView):
    """Proxy view for admin to fetch Google Analytics (GA4) reports via service account."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response({'detail': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        if not GA_CLIENT_AVAILABLE:
            return Response({'detail': 'Google Analytics client not installed on server'}, status=status.HTTP_501_NOT_IMPLEMENTED)

        from django.conf import settings

        property_id = getattr(settings, 'GA4_PROPERTY_ID', None)
        service_account_file = getattr(settings, 'GA_SERVICE_ACCOUNT_FILE', None)
        if not property_id or not service_account_file:
            return Response({'detail': 'GA4_PROPERTY_ID or GA_SERVICE_ACCOUNT_FILE not configured'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = BetaAnalyticsDataClient.from_service_account_file(service_account_file)
            prop = f"properties/{property_id}"

            # Summary report: users, activeUsers, sessions, screenPageViews over last 28 days
            summary_req = RunReportRequest(
                property=prop,
                date_ranges=[DateRange(start_date='28daysAgo', end_date='today')],
                metrics=[Metric(name='activeUsers'), Metric(name='totalUsers'), Metric(name='sessions'), Metric(name='screenPageViews')]
            )
            summary_resp = client.run_report(request=summary_req)

            summary = {}
            if summary_resp.rows:
                vals = summary_resp.rows[0].metric_values
                summary = {
                    'activeUsers': int(float(vals[0].value or 0)),
                    'totalUsers': int(float(vals[1].value or 0)),
                    'sessions': int(float(vals[2].value or 0)),
                    'screenPageViews': int(float(vals[3].value or 0)),
                }
            else:
                summary = {'activeUsers': 0, 'totalUsers': 0, 'sessions': 0, 'screenPageViews': 0}

            # Technologies: browsers and device categories (last 28 days)
            tech_req = RunReportRequest(
                property=prop,
                date_ranges=[DateRange(start_date='28daysAgo', end_date='today')],
                dimensions=[Dimension(name='browser'), Dimension(name='deviceCategory')],
                metrics=[Metric(name='activeUsers')],
                limit=50
            )
            tech_resp = client.run_report(request=tech_req)
            tech = {'browsers': [], 'devices': []}
            # Aggregate
            for row in tech_resp.rows:
                browser = row.dimension_values[0].value
                device = row.dimension_values[1].value
                users = int(float(row.metric_values[0].value or 0))
                tech['browsers'].append({'browser': browser, 'users': users})
                tech['devices'].append({'device': device, 'users': users})

            # Country distribution
            country_req = RunReportRequest(
                property=prop,
                date_ranges=[DateRange(start_date='28daysAgo', end_date='today')],
                dimensions=[Dimension(name='country')],
                metrics=[Metric(name='activeUsers')],
                limit=50
            )
            country_resp = client.run_report(request=country_req)
            countries = []
            for row in country_resp.rows:
                countries.append({'country': row.dimension_values[0].value, 'users': int(float(row.metric_values[0].value or 0))})

            # Timeseries: pageviews over last 28 days
            timeseries_req = RunReportRequest(
                property=prop,
                date_ranges=[DateRange(start_date='28daysAgo', end_date='today')],
                dimensions=[Dimension(name='date')],
                metrics=[Metric(name='screenPageViews')],
                limit=365
            )
            timeseries_resp = client.run_report(request=timeseries_req)
            timeseries = []
            for row in timeseries_resp.rows:
                date = row.dimension_values[0].value
                views = int(float(row.metric_values[0].value or 0))
                # GA returns date in YYYYMMDD, convert to YYYY-MM-DD
                if len(date) == 8 and date.isdigit():
                    date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
                timeseries.append({'date': date, 'views': views})

            return Response({'summary': summary, 'technology': tech, 'countries': countries, 'timeseries': timeseries})

        except Exception as e:
            logger.exception('Failed to fetch GA reports')
            return Response({'detail': f'Failed to fetch analytics: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ActivationStatusView(APIView):
    """Check whether current user has unlocked an exam or subject."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        exam = request.query_params.get('exam')
        subject = request.query_params.get('subject')

        try:
            user = request.user
            unlocked = False
            if subject:
                # Subject is requested: unlocked if either subject-specific unlock exists
                # OR the entire exam (exam_identifier) is unlocked for the user.
                q = Q(user=user, subject_id=subject)
                if exam:
                    q = q | Q(user=user, exam_identifier=str(exam))
                unlocked = ActivationUnlock.objects.filter(q).exists()
            elif exam:
                unlocked = ActivationUnlock.objects.filter(user=user, exam_identifier=str(exam)).exists()
            else:
                unlocked = False

            return Response({'unlocked': unlocked}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Activation status check failed: {str(e)}")
            return Response({'detail': 'Error checking status'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminActivationFeeView(APIView):
    """Simple admin API to list/create/update activation fees. Restricted to staff users."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        fees = ActivationFee.objects.all().order_by('-updated_at')
        data = []
        for f in fees:
            data.append({
                'id': f.id,
                'type': f.type,
                'exam_identifier': f.exam_identifier,
                'subject_id': f.subject_id,
                'account_role': f.account_role,
                'currency': f.currency,
                'amount': float(f.amount),
                'updated_at': f.updated_at,
                'updated_by': getattr(f.updated_by, 'username', None)
            })
        return Response({'results': data})

    def post(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        try:
            fid = request.data.get('id')
            ftype = request.data.get('type') or ActivationFee.TYPE_EXAM
            exam_identifier = request.data.get('exam_identifier')
            subject_id = request.data.get('subject_id')
            account_role = request.data.get('account_role')
            currency = request.data.get('currency') or 'NGN'
            amount = request.data.get('amount')

            if amount is None:
                return Response({'detail': 'amount required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # For account activation fees, require an explicit account_role (tutor or institution)
            if (ftype == ActivationFee.TYPE_ACCOUNT or ftype == 'account'):
                if not account_role:
                    return Response({'detail': 'account_role required for account activation fees'}, status=status.HTTP_400_BAD_REQUEST)
                if account_role not in (ActivationFee.ACCOUNT_ROLE_TUTOR, ActivationFee.ACCOUNT_ROLE_INSTITUTION):
                    return Response({'detail': 'invalid account_role'}, status=status.HTTP_400_BAD_REQUEST)

            if fid:
                fee = ActivationFee.objects.get(id=fid)
                fee.type = ftype
                fee.exam_identifier = exam_identifier
                fee.subject_id = subject_id
                fee.account_role = account_role
                fee.currency = currency
                fee.amount = Decimal(str(amount))
                fee.updated_by = request.user
                fee.save()
            else:
                fee = ActivationFee.objects.create(
                    type=ftype,
                    exam_identifier=exam_identifier,
                    subject_id=subject_id,
                    account_role=account_role,
                    currency=currency,
                    amount=Decimal(str(amount)),
                    updated_by=request.user
                )

            return Response({'id': fee.id, 'amount': float(fee.amount), 'currency': fee.currency})
        except Exception as e:
            logger.error(f"Admin activation fee error: {str(e)}")
            return Response({'detail': 'Error saving fee'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, fee_id=None):
        if not request.user.is_staff:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        try:
            if not fee_id:
                return Response({'detail': 'Fee id required'}, status=status.HTTP_400_BAD_REQUEST)
            fee = ActivationFee.objects.get(id=fee_id)
            fee.delete()
            return Response({'detail': 'deleted'})
        except ActivationFee.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Failed to delete activation fee: {str(e)}")
            return Response({'detail': 'Error deleting fee'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaystackWebhookView(APIView):
    """
    Paystack webhook for confirming payments.
    
    Receives real-time payment notifications from Paystack and updates payment status
    immediately, providing a safety net for cases where verification timeouts occur.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        
        # Verify webhook signature
        if not PaystackWebhookVerifier.verify_signature(raw_body, signature):
            logger.warning("Invalid Paystack webhook signature")
            return Response({'detail': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            data = json.loads(raw_body.decode('utf-8'))
            
            # Use webhook verifier to process the event
            result = PaystackWebhookVerifier.process_webhook(data)
            
            if result.get('status') == 'error':
                logger.error(f"Webhook processing error: {result.get('message')}")
                # Still return 200 to acknowledge receipt - Paystack will retry if we don't
                return Response({'status': 'ok', 'result': result}, status=status.HTTP_200_OK)
            
            # If payment was updated, send confirmation emails
            if result.get('action') == 'updated':
                try:
                    reference = result.get('reference')
                    payment = Payment.objects.get(paystack_reference=reference)
                    send_successful_payment_emails(payment)
                except Exception as e:
                    logger.error(f"Failed to send payment confirmation emails: {str(e)}")
            
            return Response({'status': 'ok', 'result': result}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            logger.error("Invalid webhook payload (JSON decode error)")
            return Response({'detail': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            # Return 200 to acknowledge even on error - Paystack will retry if needed
            return Response({'status': 'ok', 'error': str(e)}, status=status.HTTP_200_OK)


class InitiateUnlockView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        unlock_price = float(os.environ.get('UNLOCK_PRICE', 5000.00))
        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = unlock_price * float(commission)

        payment = Payment.objects.create(
            user=user,
            course=None,
            amount=unlock_price,
            platform_fee=platform_fee,
            kind=Payment.KIND_UNLOCK,
            status=Payment.PENDING,
        )

        payment_url = f"https://paystack.example.com/checkout/{payment.id}"
        return Response({'payment_id': payment.id, 'payment_url': payment_url})


class SubAccountViewSet(viewsets.ViewSet):
    """ViewSet for managing Paystack sub-accounts."""
    permission_classes = [IsAuthenticated]

    def create(self, request):
        user = request.user
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        account_name = request.data.get('account_name')

        if not all([bank_code, account_number, account_name]):
            return Response({'detail': 'Missing required fields: bank_code, account_number, account_name'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = PaystackClient()
            
            if not account_number.isdigit() or len(account_number) != 10:
                return Response({'detail': 'Account number must be 10 digits'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                banks = client.list_banks()
                valid_codes = {str(b.get('code')) for b in banks}
                provided = str(bank_code).strip()
                candidates = {provided, provided.zfill(3), str(int(provided)) if provided.isdigit() else provided}
                matched = None
                for c in candidates:
                    if c in valid_codes:
                        matched = c
                        break

                if matched:
                    bank_code = matched
                else:
                    logger.warning(f"Provided bank code '{bank_code}' not found in Paystack list; proceeding to resolve for authoritative error.")
            except PaystackError:
                logger.warning('Could not validate bank code against Paystack list; continuing to resolve.')
            
            # Use configured tutor share to set subaccount percentage_charge so Paystack can route splits correctly
            try:
                split_cfg = PaymentSplitConfig.get_solo()
                percentage_charge = float(split_cfg.tutor_share)
            except Exception:
                percentage_charge = 0

            subaccount_data = client.create_subaccount(
                business_name=account_name,
                settlement_bank=bank_code,
                account_number=account_number,
                account_holder_name=account_name,
                percentage_charge=percentage_charge,
                description=f'Sub-account for {account_name}',
                primary_contact_email=user.email,
                primary_contact_name=f'{user.first_name} {user.last_name}' if user.first_name or user.last_name else user.username,
                mobile=getattr(user, 'phone', '') or '',
            )

            subaccount = PaystackSubAccount.objects.update_or_create(
                user=user,
                defaults={
                    'bank_code': bank_code,
                    'account_number': account_number,
                    'account_name': account_name,
                    'subaccount_code': subaccount_data.get('subaccount_code'),
                    'is_active': True,
                }
            )

            return Response({
                'id': subaccount[0].id,
                'bank_code': bank_code,
                'account_number': account_number,
                'account_name': account_name,
                'subaccount_code': subaccount_data.get('subaccount_code'),
                'is_active': True,
            }, status=status.HTTP_201_CREATED)

        except PaystackError as e:
            logger.error(f"Sub-account creation error: {str(e)}")
            return Response({'detail': f'Failed to create sub-account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Sub-account error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request):
        try:
            subaccount = PaystackSubAccount.objects.get(user=request.user)
            return Response({
                'id': subaccount.id,
                'bank_code': subaccount.bank_code,
                'account_number': subaccount.account_number,
                'account_name': subaccount.account_name,
                'subaccount_code': subaccount.subaccount_code,
                'is_active': subaccount.is_active,
            })
        except PaystackSubAccount.DoesNotExist:
            return Response({'detail': 'No sub-account found'}, status=status.HTTP_404_NOT_FOUND)

    def retrieve(self, request, pk=None):
        try:
            subaccount = PaystackSubAccount.objects.get(id=pk, user=request.user)
            return Response({
                'id': subaccount.id,
                'bank_code': subaccount.bank_code,
                'account_number': subaccount.account_number,
                'account_name': subaccount.account_name,
                'subaccount_code': subaccount.subaccount_code,
                'is_active': subaccount.is_active,
                'created_at': subaccount.created_at,
            })
        except PaystackSubAccount.DoesNotExist:
            return Response({'detail': 'Sub-account not found'}, status=status.HTTP_404_NOT_FOUND)


class PaymentSplitConfigView(APIView):
    """Admin-only API to view and update payment split configuration."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            cfg = PaymentSplitConfig.get_solo()
            return Response({
                'tutor_share': float(cfg.tutor_share),
                'institution_share': float(cfg.institution_share),
                'updated_at': cfg.updated_at,
                'updated_by': getattr(cfg.updated_by, 'username', None)
            })
        except Exception as e:
            logger.error(f"Failed to fetch payment split config: {str(e)}")
            return Response({'detail': 'Error fetching config'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        try:
            tutor = request.data.get('tutor_share')
            institution = request.data.get('institution_share')
            if tutor is None or institution is None:
                return Response({'detail': 'Both tutor_share and institution_share required'}, status=status.HTTP_400_BAD_REQUEST)

            cfg = PaymentSplitConfig.get_solo()
            cfg.tutor_share = Decimal(str(tutor))
            cfg.institution_share = Decimal(str(institution))
            cfg.updated_by = request.user
            cfg.save()
            return Response({'detail': 'Updated', 'tutor_share': float(cfg.tutor_share), 'institution_share': float(cfg.institution_share)})
        except Exception as e:
            logger.error(f"Failed to update payment split config: {str(e)}")
            return Response({'detail': 'Error updating config'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FLUTTERWAVE INTEGRATION ====================

class InitiateFlutterwavePaymentView(APIView):
    """Initiate Flutterwave payment for courses and diplomas."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        amount = request.data.get('amount')
        requested_currency = request.data.get('currency')

        # For Flutterwave initiation require item_type and amount; require
        # item_id only for course/diploma (activation not supported here).
        if not item_type or amount is None:
            return Response({'detail': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

        if item_type in ('course', 'diploma') and (item_id is None or str(item_id).strip() == ''):
            return Response({'detail': 'Missing required fields: item_id required for course/diploma'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({'detail': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

            if item_type == 'course':
                item = Course.objects.get(id=item_id)
                kind = Payment.KIND_COURSE
            elif item_type == 'diploma':
                item = Diploma.objects.get(id=item_id)
                kind = Payment.KIND_DIPLOMA
            elif item_type == 'activation':
                # Support activation unlocks via Flutterwave as well
                kind = Payment.KIND_UNLOCK
                activation_meta = {
                    'activation_type': request.data.get('activation_type'),
                    'exam_id': request.data.get('exam_id') or request.data.get('item_id'),
                    'subject_id': request.data.get('subject_id'),
                }
            else:
                return Response({'detail': 'Invalid item_type'}, status=status.HTTP_400_BAD_REQUEST)

            amount_decimal = Decimal(str(amount))
            
            # Determine currency: frontend > activation fee (if any) > default
            currency = (requested_currency or '').strip().upper() if requested_currency else None
            if kind == Payment.KIND_UNLOCK:
                fee_currency = None
                try:
                    exam_id = request.data.get('exam_id') or request.data.get('item_id')
                    subject_id = request.data.get('subject_id')
                    if subject_id:
                        fee = ActivationFee.objects.filter(type=ActivationFee.TYPE_INTERVIEW, subject_id=subject_id).order_by('-updated_at').first()
                    elif exam_id:
                        fee = ActivationFee.objects.filter(exam_identifier=str(exam_id)).order_by('-updated_at').first()
                    else:
                        fee = ActivationFee.objects.filter(type='exam').order_by('-updated_at').first()
                    if fee:
                        fee_currency = fee.currency
                except Exception:
                    fee_currency = None
                if not currency:
                    currency = (fee_currency or 'NGN').upper()
            else:
                if not currency:
                    currency = getattr(settings, 'DEFAULT_CURRENCY', 'NGN').upper()
            
            if item_type == 'activation' or kind == Payment.KIND_UNLOCK:
                # platform receives full amount for unlocks
                platform_fee = amount_decimal
                creator_amount = Decimal('0.00')
            else:
                platform_fee, creator_amount = calculate_split(amount_decimal, platform_percentage=5)

            payment_reference = generate_flutterwave_reference()

            payment_data = {
                'user': user,
                'amount': amount_decimal,
                'currency': currency,
                'kind': kind,
                'platform_fee': platform_fee,
                'creator_amount': creator_amount,
                'flutterwave_reference': payment_reference,
                'payment_provider': Payment.PROVIDER_FLUTTERWAVE,
                'status': Payment.PENDING,
            }

            if item_type == 'course':
                payment_data['course'] = item
            elif item_type == 'diploma':
                payment_data['diploma'] = item
            if item_type == 'activation':
                try:
                    payment_data['provider_reference'] = json.dumps(activation_meta)
                except Exception:
                    payment_data['provider_reference'] = ''

            payment = Payment.objects.create(**payment_data)

            try:
                client = FlutterwaveClient()
                metadata = {
                    'payment_id': payment.id,
                    'item_type': item_type,
                    'item_id': item_id,
                    'user_id': user.id,
                }
                metadata['currency'] = currency
                if item_type == 'activation' and activation_meta:
                    metadata['activation'] = activation_meta
                
                frontend_base = os.getenv('FRONTEND_URL') or 'http://localhost:5173'
                callback_url = f"{frontend_base}/payment/flutterwave/verify"
                
                # For course/diploma payments, try to use tutor's sub-account for split payment
                subaccount_id = None
                if kind in (Payment.KIND_COURSE, Payment.KIND_DIPLOMA):
                    creator = item.creator if item else None
                    if creator:
                        try:
                            flutterwave_subaccount = FlutterwaveSubAccount.objects.get(user=creator)
                            if flutterwave_subaccount.subaccount_id:
                                subaccount_id = flutterwave_subaccount.subaccount_id
                                # Store tutor info in payment for reference
                                payment.recipient_code = str(subaccount_id)
                                payment.save()
                        except FlutterwaveSubAccount.DoesNotExist:
                            logger.warning(f"No Flutterwave sub-account found for course creator {creator.id}")
                
                flutterwave_data = client.initialize_payment(
                    email=user.email,
                    amount=float(amount_decimal),
                    reference=payment_reference,
                    metadata=metadata,
                    callback_url=callback_url,
                    full_name=f'{user.first_name} {user.last_name}' if user.first_name or user.last_name else user.username,
                    phone_number=getattr(user, 'phone', '') or '',
                    subaccount_id=subaccount_id,  # Use tutor's subaccount
                    currency=currency
                )
                

                return Response({
                    'payment_id': payment.id,
                    'reference': payment_reference,
                    'link': flutterwave_data.get('link'),
                    'authorization_url': flutterwave_data.get('link'),
                }, status=status.HTTP_201_CREATED)

            except FlutterwaveError as e:
                payment.status = Payment.FAILED
                payment.save()
                logger.error(f"Flutterwave initialization failed: {str(e)}")
                return Response({'detail': f'Payment initialization failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        except (Course.DoesNotExist, Diploma.DoesNotExist):
            return Response({'detail': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Flutterwave payment initiation error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyFlutterwavePaymentView(APIView):
    """Verify Flutterwave payment."""
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        try:
            payment = Payment.objects.get(flutterwave_reference=reference)
            
            if payment.user != request.user:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

            try:
                client = FlutterwaveClient()
                transaction_data = client.verify_payment_by_reference(reference)

                if transaction_data.get('status') == 'successful':
                    if payment.status != Payment.SUCCESS:
                        with transaction.atomic():
                            payment.status = Payment.SUCCESS
                            payment.flutterwave_transaction_id = transaction_data.get('id')
                            payment.verified_at = timezone.now()
                            
                            # Extract gateway fee from Flutterwave response
                            # Flutterwave charges: amount_charged - amount = gateway fee
                            amount = transaction_data.get('amount', 0)
                            charged_amount = transaction_data.get('charged_amount', 0)
                            payment.gateway_fee = max(0, charged_amount - amount)  # Ensure non-negative
                            payment.net_amount = amount
                            
                            payment.save()

                            if payment.kind == Payment.KIND_COURSE and payment.course:
                                Enrollment.objects.update_or_create(
                                    user=payment.user,
                                    course=payment.course,
                                    defaults={'purchased': True, 'purchased_at': timezone.now()}
                                )
                            elif payment.kind == Payment.KIND_DIPLOMA and payment.diploma:
                                DiplomaEnrollment.objects.update_or_create(
                                    user=payment.user,
                                    diploma=payment.diploma,
                                    defaults={'purchased': True, 'purchased_at': timezone.now()}
                                )
                            elif payment.kind == Payment.KIND_UNLOCK:
                                # Create ActivationUnlock record based on provider metadata
                                try:
                                    meta = None
                                    if payment.provider_reference:
                                        try:
                                            meta = json.loads(payment.provider_reference)
                                        except Exception:
                                            meta = None

                                    # Flutterwave may return metadata under 'meta' or 'data.meta'
                                    tx_meta = transaction_data.get('meta') or transaction_data.get('data', {}).get('meta') or transaction_data.get('metadata') or {}
                                    activation = None
                                    if isinstance(tx_meta, dict) and tx_meta.get('activation'):
                                        activation = tx_meta.get('activation')
                                    elif isinstance(tx_meta, dict) and tx_meta.get('activation_type'):
                                        activation = tx_meta
                                    else:
                                        activation = meta

                                    exam_identifier = activation.get('exam_id') if activation else None
                                    subject_id = activation.get('subject_id') if activation else None

                                    if exam_identifier or subject_id:
                                        ActivationUnlock.objects.get_or_create(
                                            user=payment.user,
                                            exam_identifier=str(exam_identifier) if exam_identifier else None,
                                            subject_id=int(subject_id) if subject_id else None,
                                            defaults={'payment': payment}
                                        )
                                except Exception as e:
                                    logger.error(f"Failed to create activation unlock (flutterwave verify): {str(e)}")
                                # Mark account unlocked if activation_type == 'account'
                                try:
                                    meta_for_account = None
                                    if payment.provider_reference:
                                        try:
                                            meta_for_account = json.loads(payment.provider_reference)
                                        except Exception:
                                            meta_for_account = None
                                    activation_check = None
                                    if isinstance(tx_meta, dict) and tx_meta.get('activation'):
                                        activation_check = tx_meta.get('activation')
                                    elif isinstance(tx_meta, dict) and tx_meta.get('activation_type'):
                                        activation_check = tx_meta
                                    else:
                                        activation_check = meta_for_account

                                    if activation_check and activation_check.get('activation_type') == 'account':
                                        try:
                                            u = payment.user
                                            u.is_unlocked = True
                                            u.save()
                                        except Exception as e:
                                            logger.error(f"Failed to mark user unlocked (flutterwave verify): {str(e)}")
                                except Exception:
                                    pass
                        
                        # Send Emails for Flutterwave Verification
                        send_successful_payment_emails(payment)

                    logger.info(f"Flutterwave payment {reference} verified")
                    return Response({
                        'status': 'success',
                        'payment_id': payment.id,
                        'amount': str(payment.amount),
                    })
                else:
                    payment.status = Payment.FAILED
                    payment.save()
                    return Response({'status': 'failed', 'detail': 'Payment verification failed'}, status=status.HTTP_400_BAD_REQUEST)

            except FlutterwaveError as e:
                logger.error(f"Flutterwave verification error: {str(e)}")
                return Response({'detail': f'Verification failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        except Payment.DoesNotExist:
            return Response({'detail': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FlutterwaveWebhookView(APIView):
    """
    Handle Flutterwave webhook for payment updates.
    
    Receives real-time payment notifications from Flutterwave and updates payment status
    immediately, providing a safety net for cases where verification timeouts occur.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            body = request.body
            signature = request.META.get('HTTP_X_FLUTTERWAVE_SIGNATURE', '')
            
            # Verify webhook signature
            if not FlutterwaveWebhookVerifier.verify_signature(body, signature) and not settings.DEBUG:
                logger.warning("Invalid Flutterwave webhook signature")
                # Don't fail - might be debug mode
            
            payload = request.data
            
            # Use webhook verifier to process the event
            result = FlutterwaveWebhookVerifier.process_webhook(payload)
            
            if result.get('status') == 'error':
                logger.error(f"Webhook processing error: {result.get('message')}")
                # Still return 200 to acknowledge receipt
                return Response({'status': 'ok', 'result': result}, status=status.HTTP_200_OK)
            
            # If payment was updated, send confirmation emails
            if result.get('action') == 'updated':
                try:
                    reference = result.get('reference')
                    payment = Payment.objects.get(flutterwave_reference=reference)
                    send_successful_payment_emails(payment)
                except Exception as e:
                    logger.error(f"Failed to send payment confirmation emails: {str(e)}")
            
            return Response({'status': 'ok', 'result': result}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            logger.error("Invalid webhook payload (JSON decode error)")
            return Response({'detail': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            # Return 200 to acknowledge even on error
            return Response({'status': 'ok', 'error': str(e)}, status=status.HTTP_200_OK)


class PaymentReconciliationView(APIView):
    """
    Admin endpoint to manually trigger payment reconciliation.
    
    This endpoint checks pending payments that are older than a specified time
    and verifies their status with the payment gateways. Useful for recovering
    payments that timed out during verification but were actually successful.
    
    Returns detailed reconciliation results including payments that were updated.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Require admin or staff permission
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {'detail': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Get reconciliation parameters
            minutes_old = int(request.data.get('minutes_old', 5))
            
            if minutes_old < 1:
                return Response(
                    {'detail': 'minutes_old must be at least 1'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Run reconciliation
            results = PaymentReconciliation.reconcile_pending_payments(minutes_old)
            
            logger.info(
                f"Admin {request.user.username} triggered payment reconciliation: "
                f"checked {results['total_checked']}, "
                f"Paystack updated {results['paystack_updated']}, "
                f"Flutterwave updated {results['flutterwave_updated']}"
            )
            
            return Response({
                'status': 'success',
                'message': 'Reconciliation completed',
                'results': results
            }, status=status.HTTP_200_OK)
        
        except ValueError as e:
            return Response(
                {'detail': f'Invalid parameter: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Payment reconciliation error: {str(e)}")
            return Response(
                {'detail': f'Reconciliation error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FlutterwaveSubAccountViewSet(viewsets.ViewSet):
    """ViewSet for managing Flutterwave sub-accounts."""
    permission_classes = [IsAuthenticated]

    def create(self, request):
        user = request.user
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        account_name = request.data.get('account_name')
        business_email = request.data.get('business_email')

        if not all([bank_code, account_number, account_name, business_email]):
            return Response({'detail': 'Missing required fields: bank_code, account_number, account_name, business_email'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = FlutterwaveClient()
            
            if not account_number.isdigit():
                return Response({'detail': 'Account number must contain only digits'}, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"Verifying account: {account_number}, Bank Code: {bank_code}")
            try:
                verified_account = client.verify_bank_account(account_number, bank_code)
                account_holder_name = verified_account.get('account_name', account_name)
                logger.info(f"Account verified successfully: {account_holder_name}")
            except FlutterwaveError as e:
                logger.warning(f"Account verification warning: {str(e)}")
                if client.is_test_mode():
                    logger.info("Flutterwave client in TEST mode — proceeding despite verification failure.")
                    account_holder_name = account_name
                else:
                    logger.error(f"Account verification failed in LIVE mode: {str(e)}")
                    return Response({'detail': f'Failed to verify account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            subaccount_id = None
            try:
                subaccount_data = client.create_subaccount(
                    business_name=account_name,
                    account_bank=bank_code,
                    account_number=account_number,
                    account_holder_name=account_holder_name,
                    business_email=business_email,
                    percentage_charge=0,
                    meta={
                        'user_id': user.id,
                        'user_email': user.email,
                        'created_date': str(timezone.now()),
                    }
                )
                subaccount_id = subaccount_data.get('subaccount_id') or subaccount_data.get('id')
                logger.info(f"Flutterwave subaccount created: {subaccount_id}")
            except FlutterwaveError as e:
                logger.warning(f"Flutterwave subaccount creation warning: {str(e)}")
                if client.is_test_mode():
                    logger.info("Flutterwave client in TEST mode — saving subaccount locally despite provider failure.")
                    subaccount_id = f"TEST_{user.id}_{timezone.now().timestamp()}"
                else:
                    logger.error(f"Flutterwave subaccount creation failed in LIVE mode: {str(e)}")
                    return Response({'detail': f'Failed to create sub-account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            subaccount = FlutterwaveSubAccount.objects.update_or_create(
                user=user,
                defaults={
                    'bank_code': bank_code,
                    'account_number': account_number,
                    'account_name': account_name,
                    'subaccount_id': subaccount_id,
                    'is_active': True,
                }
            )

            return Response({
                'id': subaccount[0].id,
                'bank_code': bank_code,
                'account_number': account_number,
                'account_name': account_name,
                'subaccount_id': subaccount_id,
                'is_active': True,
            }, status=status.HTTP_201_CREATED)

        except FlutterwaveError as e:
            logger.error(f"Flutterwave sub-account creation error: {str(e)}")
            return Response({'detail': f'Failed to create sub-account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Flutterwave sub-account error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request):
        try:
            subaccount = FlutterwaveSubAccount.objects.get(user=request.user)
            return Response({
                'id': subaccount.id,
                'bank_code': subaccount.bank_code,
                'account_number': subaccount.account_number,
                'account_name': subaccount.account_name,
                'subaccount_id': subaccount.subaccount_id,
                'is_active': subaccount.is_active,
            })
        except FlutterwaveSubAccount.DoesNotExist:
            return Response({'detail': 'No sub-account found'}, status=status.HTTP_404_NOT_FOUND)

    def retrieve(self, request, pk=None):
        try:
            subaccount = FlutterwaveSubAccount.objects.get(id=pk, user=request.user)
            return Response({
                'id': subaccount.id,
                'bank_code': subaccount.bank_code,
                'account_number': subaccount.account_number,
                'account_name': subaccount.account_name,
                'subaccount_id': subaccount.subaccount_id,
                'is_active': subaccount.is_active,
                'created_at': subaccount.created_at,
            })
        except FlutterwaveSubAccount.DoesNotExist:
            return Response({'detail': 'Sub-account not found'}, status=status.HTTP_404_NOT_FOUND)

class FlutterwaveListBanksView(APIView):
    """Get list of available banks for Flutterwave."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            client = FlutterwaveClient()
            banks = client.list_banks()
            
            bank_list = [
                {
                    'id': idx,
                    'code': bank.get('code'),
                    'name': bank.get('name')
                }
                for idx, bank in enumerate(banks, 1)
            ]
            
            return Response({
                'banks': bank_list,
                'total': len(bank_list)
            }, status=status.HTTP_200_OK)
        
        except FlutterwaveError as e:
            logger.error(f"Failed to fetch banks: {str(e)}")
            return Response({'detail': f'Failed to fetch banks: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching banks: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FlutterwaveVerifyAccountView(APIView):
    """Verify a bank account using Flutterwave account resolution endpoint."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        account_number = request.data.get('account_number')
        account_bank = request.data.get('account_bank') or request.data.get('bank_code')

        if not account_number or not account_bank:
            return Response({'detail': 'Missing required fields: account_number, account_bank'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = FlutterwaveClient()
            verified = client.verify_bank_account(account_number, account_bank)
            return Response({'detail': 'Account verified', 'data': verified}, status=status.HTTP_200_OK)
        except FlutterwaveError as e:
            logger.warning(f"Flutterwave account verification failed: {str(e)}")
            return Response({'detail': f'Failed to verify account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error verifying account: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)