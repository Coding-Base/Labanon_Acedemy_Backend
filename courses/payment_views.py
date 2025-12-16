import hmac
import hashlib
import json
import os

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .models import Payment, Course
from django.utils import timezone


class InitiateUnlockView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # create a Payment entry for unlocking account and return a payment_url
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

        # In production call Paystack initialize endpoint. For now return fake url.
        payment_url = f"https://paystack.example.com/checkout/{payment.id}"
        return Response({'payment_id': payment.id, 'payment_url': payment_url})


class PaystackWebhookView(APIView):
    # Paystack posts without auth; verify using signature header
    permission_classes = [AllowAny]

    def post(self, request):
        secret = os.environ.get('PAYSTACK_SECRET') or ''
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        raw_body = request.body

        # verify signature
        computed = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature):
            return Response({'detail': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        data = json.loads(raw_body.decode('utf-8'))
        # Paystack sends event type, and data includes reference, amount, status
        event = data.get('event')
        payload = data.get('data', {})
        reference = payload.get('reference')

        # Here we assume we stored provider_reference as the external reference when initiating
        try:
            payment = Payment.objects.get(provider_reference=reference)
        except Payment.DoesNotExist:
            return Response({'detail': 'payment not found'}, status=status.HTTP_404_NOT_FOUND)

        # mark success/failure
        status_str = payload.get('status')
        if status_str == 'success':
            payment.status = Payment.SUCCESS
            payment.save()
            # if unlock payment, mark user unlocked
            if payment.kind == Payment.KIND_UNLOCK:
                user = payment.user
                user.is_unlocked = True
                user.save()
            # if course purchase, mark enrollment (simple handling)
            if payment.kind == Payment.KIND_COURSE and payment.course:
                from .models import Enrollment

                Enrollment.objects.update_or_create(
                    user=payment.user,
                    course=payment.course,
                    defaults={'purchased': True, 'purchased_at': timezone.now()},
                )

            return Response({'status': 'ok'})

        payment.status = Payment.FAILED
        payment.save()
        return Response({'status': 'failed'})
