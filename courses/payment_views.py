import hmac
import hashlib
import json
import os

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.conf import settings
from django.utils import timezone

from .models import Payment, Course, Diploma, Enrollment, DiplomaEnrollment, PaystackSubAccount, FlutterwaveSubAccount
from .paystack_utils import PaystackClient, naira_to_kobo, calculate_split, generate_payment_reference, PaystackError
from .flutterwave_utils import FlutterwaveClient, FlutterwaveError, generate_payment_reference as generate_flutterwave_reference
from .serializers import PaymentSerializer
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class InitiatePaymentView(APIView):
    """Initiate Paystack payment for courses and diplomas."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Initiate payment.
        Body: {
            "item_type": "course" or "diploma",
            "item_id": <course_id or diploma_id>,
            "amount": <amount in Naira>
        }
        """
        user = request.user
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        amount = request.data.get('amount')

        if not all([item_type, item_id, amount]):
            return Response({'detail': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({'detail': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

            # Get the item (course or diploma)
            if item_type == 'course':
                item = Course.objects.get(id=item_id)
                kind = Payment.KIND_COURSE
            elif item_type == 'diploma':
                item = Diploma.objects.get(id=item_id)
                kind = Payment.KIND_DIPLOMA
            else:
                return Response({'detail': 'Invalid item_type'}, status=status.HTTP_400_BAD_REQUEST)

            # Calculate split
            from decimal import Decimal
            amount_decimal = Decimal(str(amount))
            platform_fee, creator_amount = calculate_split(amount_decimal, platform_percentage=5)

            # Generate payment reference
            payment_reference = generate_payment_reference()

            # Create payment record
            payment_data = {
                'user': user,
                'amount': amount,
                'kind': kind,
                'platform_fee': platform_fee,
                'creator_amount': creator_amount,
                'paystack_reference': payment_reference,
                'status': Payment.PENDING,
            }

            if item_type == 'course':
                payment_data['course'] = item
            else:
                payment_data['diploma'] = item

            payment = Payment.objects.create(**payment_data)

            # Initialize Paystack payment
            try:
                client = PaystackClient()
                metadata = {
                    'payment_id': payment.id,
                    'item_type': item_type,
                    'item_id': item_id,
                    'user_id': user.id,
                }
                
                # Build callback URL for redirect after Paystack payment
                frontend_base = os.getenv('FRONTEND_URL') or 'http://localhost:5173'
                callback_url = f"{frontend_base}/payment/verify"
                
                paystack_data = client.initialize_payment(
                    email=user.email,
                    amount=naira_to_kobo(amount),
                    reference=payment_reference,
                    metadata=metadata,
                    callback_url=callback_url
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
        """Verify payment by reference."""
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            
            if payment.user != request.user:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

            try:
                client = PaystackClient()
                transaction_data = client.verify_payment(reference)

                # Update payment status
                if transaction_data.get('status') == 'success':
                    with transaction.atomic():
                        payment.status = Payment.SUCCESS
                        payment.verified_at = timezone.now()
                        payment.save()

                        # Create enrollment
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


class PaystackWebhookView(APIView):
    """Paystack webhook for confirming payments."""
    permission_classes = [AllowAny]

    def post(self, request):
        """Handle Paystack webhook."""
        secret = os.getenv('paystack_test_secret_key') or settings.PAYSTACK_SECRET_KEY
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        raw_body = request.body

        # Verify signature
        computed = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature):
            logger.warning("Invalid Paystack webhook signature")
            return Response({'detail': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = json.loads(raw_body.decode('utf-8'))
            event = data.get('event')
            payload = data.get('data', {})

            if event == 'charge.success':
                reference = payload.get('reference')
                
                try:
                    payment = Payment.objects.get(paystack_reference=reference)
                    
                    with transaction.atomic():
                        payment.status = Payment.SUCCESS
                        payment.verified_at = timezone.now()
                        payment.save()

                        # Create enrollment based on payment kind
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

                        logger.info(f"Payment {reference} verified via webhook")

                except Payment.DoesNotExist:
                    logger.warning(f"Payment with reference {reference} not found")

            return Response({'status': 'ok'}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            logger.error("Invalid webhook payload")
            return Response({'detail': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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


class SubAccountViewSet(viewsets.ViewSet):
    """ViewSet for managing Paystack sub-accounts."""
    permission_classes = [IsAuthenticated]

    def create(self, request):
        """Create or update sub-account for user."""
        user = request.user
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        account_name = request.data.get('account_name')

        if not all([bank_code, account_number, account_name]):
            return Response({'detail': 'Missing required fields: bank_code, account_number, account_name'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = PaystackClient()
            
            # Validate account_number is numeric and 10 digits
            if not account_number.isdigit() or len(account_number) != 10:
                return Response({'detail': 'Account number must be 10 digits'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate bank_code exists in Paystack's bank list to avoid invalid bank codes
            try:
                banks = client.list_banks()
                valid_codes = {str(b.get('code')) for b in banks}
                provided = str(bank_code).strip()

                # Try common normalizations: zfill to 3 digits, and strip leading zeros
                candidates = {provided, provided.zfill(3), str(int(provided)) if provided.isdigit() else provided}
                matched = None
                for c in candidates:
                    if c in valid_codes:
                        matched = c
                        break

                if matched:
                    # normalize bank_code to the matched canonical value
                    bank_code = matched
                else:
                    # Do not reject immediately — allow resolve to run which gives the authoritative Paystack error.
                    logger.warning(f"Provided bank code '{bank_code}' not found in Paystack list; proceeding to resolve for authoritative error.")
            except PaystackError:
                # If Paystack list_banks fails, continue and allow resolve to catch invalid combos
                logger.warning('Could not validate bank code against Paystack list; continuing to resolve.')
            
            # Create sub-account with all required and optional fields
            subaccount_data = client.create_subaccount(
                business_name=account_name,
                settlement_bank=bank_code,
                account_number=account_number,
                account_holder_name=account_name,
                description=f'Sub-account for {account_name}',
                primary_contact_email=user.email,
                primary_contact_name=f'{user.first_name} {user.last_name}' if user.first_name or user.last_name else user.username,
                mobile=getattr(user, 'phone', '') or '',
            )

            # Save sub-account to database
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
        """Get user's sub-account."""
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
        """Get sub-account details."""
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


# ==================== FLUTTERWAVE INTEGRATION ====================

class InitiateFlutterwavePaymentView(APIView):
    """Initiate Flutterwave payment for courses and diplomas."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Initiate Flutterwave payment.
        Body: {
            "item_type": "course" or "diploma",
            "item_id": <course_id or diploma_id>,
            "amount": <amount in NGN>
        }
        """
        user = request.user
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        amount = request.data.get('amount')

        if not all([item_type, item_id, amount]):
            return Response({'detail': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({'detail': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

            # Get the item (course or diploma)
            if item_type == 'course':
                item = Course.objects.get(id=item_id)
                kind = Payment.KIND_COURSE
            elif item_type == 'diploma':
                item = Diploma.objects.get(id=item_id)
                kind = Payment.KIND_DIPLOMA
            else:
                return Response({'detail': 'Invalid item_type'}, status=status.HTTP_400_BAD_REQUEST)

            # Calculate split
            from decimal import Decimal
            amount_decimal = Decimal(str(amount))
            platform_fee, creator_amount = calculate_split(amount_decimal, platform_percentage=5)

            # Generate Flutterwave payment reference
            payment_reference = generate_flutterwave_reference()

            # Create payment record
            payment_data = {
                'user': user,
                'amount': amount,
                'kind': kind,
                'platform_fee': platform_fee,
                'creator_amount': creator_amount,
                'flutterwave_reference': payment_reference,
                'payment_provider': Payment.PROVIDER_FLUTTERWAVE,
                'status': Payment.PENDING,
            }

            if item_type == 'course':
                payment_data['course'] = item
            else:
                payment_data['diploma'] = item

            payment = Payment.objects.create(**payment_data)

            # Initialize Flutterwave payment
            try:
                client = FlutterwaveClient()
                metadata = {
                    'payment_id': payment.id,
                    'item_type': item_type,
                    'item_id': item_id,
                    'user_id': user.id,
                }
                
                # Build callback URL for redirect after Flutterwave payment
                frontend_base = os.getenv('FRONTEND_URL') or 'http://localhost:5173'
                callback_url = f"{frontend_base}/payment/flutterwave/verify"
                
                flutterwave_data = client.initialize_payment(
                    email=user.email,
                    amount=amount,
                    reference=payment_reference,
                    metadata=metadata,
                    callback_url=callback_url,
                    full_name=f'{user.first_name} {user.last_name}' if user.first_name or user.last_name else user.username,
                    phone_number=getattr(user, 'phone', '') or ''
                )

                return Response({
                    'payment_id': payment.id,
                    'reference': payment_reference,
                    'link': flutterwave_data.get('link'),
                    'authorization_url': flutterwave_data.get('link'),  # For compatibility
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
        """Verify payment by reference."""
        try:
            payment = Payment.objects.get(flutterwave_reference=reference)
            
            if payment.user != request.user:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

            try:
                client = FlutterwaveClient()
                transaction_data = client.verify_payment_by_reference(reference)

                # Update payment status
                if transaction_data.get('status') == 'successful':
                    with transaction.atomic():
                        payment.status = Payment.SUCCESS
                        payment.flutterwave_transaction_id = transaction_data.get('id')
                        payment.verified_at = timezone.now()
                        payment.save()

                        # Create enrollment
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
    """Handle Flutterwave webhook for payment updates."""
    permission_classes = [AllowAny]

    def post(self, request):
        """Process Flutterwave webhook."""
        try:
            # Get the raw body for signature verification
            body = request.body
            flutterwave_secret = os.getenv('FLUTTERWAVE_SECRET_KEY') or settings.FLUTTERWAVE_SECRET_KEY
            
            # Flutterwave sends signature in X-Flutterwave-Signature header
            signature = request.META.get('HTTP_X_FLUTTERWAVE_SIGNATURE', '')
            
            # Compute expected signature (Flutterwave uses SHA256)
            expected_signature = hashlib.sha256((body + flutterwave_secret).encode()).hexdigest()
            
            # Verify signature
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid Flutterwave webhook signature")
                return Response({'detail': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
            
            payload = request.data
            
            if payload.get('event') == 'charge.completed':
                data = payload.get('data', {})
                reference = data.get('tx_ref')
                
                try:
                    payment = Payment.objects.get(flutterwave_reference=reference)
                    
                    with transaction.atomic():
                        if data.get('status') == 'successful':
                            payment.status = Payment.SUCCESS
                            payment.flutterwave_transaction_id = data.get('id')
                        else:
                            payment.status = Payment.FAILED
                        
                        payment.verified_at = timezone.now()
                        payment.save()

                        # Create enrollment if successful
                        if payment.status == Payment.SUCCESS:
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

                        logger.info(f"Flutterwave payment {reference} processed via webhook")

                except Payment.DoesNotExist:
                    logger.warning(f"Payment with reference {reference} not found")

            return Response({'status': 'ok'}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            logger.error("Invalid webhook payload")
            return Response({'detail': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FlutterwaveSubAccountViewSet(viewsets.ViewSet):
    """ViewSet for managing Flutterwave sub-accounts."""
    permission_classes = [IsAuthenticated]

    def create(self, request):
        """Create or update Flutterwave sub-account for user."""
        user = request.user
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        account_name = request.data.get('account_name')
        business_email = request.data.get('business_email')

        if not all([bank_code, account_number, account_name, business_email]):
            return Response({'detail': 'Missing required fields: bank_code, account_number, account_name, business_email'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = FlutterwaveClient()
            
            # Validate account_number is numeric
            if not account_number.isdigit():
                return Response({'detail': 'Account number must contain only digits'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify account with Flutterwave before creating subaccount
            logger.info(f"Verifying account: {account_number}, Bank Code: {bank_code}")
            try:
                verified_account = client.verify_bank_account(account_number, bank_code)
                account_holder_name = verified_account.get('account_name', account_name)
                logger.info(f"Account verified successfully: {account_holder_name}")
            except FlutterwaveError as e:
                logger.warning(f"Account verification warning: {str(e)}")
                # If running in test mode, allow creating subaccounts despite verification failures
                if client.is_test_mode():
                    logger.info("Flutterwave client in TEST mode — proceeding despite verification failure.")
                    account_holder_name = account_name
                else:
                    # In live mode, surface verification errors to the client
                    logger.error(f"Account verification failed in LIVE mode: {str(e)}")
                    return Response({'detail': f'Failed to verify account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            # Create Flutterwave sub-account (or skip in test mode if provider validation fails)
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
                # In test mode, allow saving the subaccount locally even if Flutterwave creation fails
                if client.is_test_mode():
                    logger.info("Flutterwave client in TEST mode — saving subaccount locally despite provider failure.")
                    subaccount_id = f"TEST_{user.id}_{timezone.now().timestamp()}"
                else:
                    # In live mode, surface creation errors to the client
                    logger.error(f"Flutterwave subaccount creation failed in LIVE mode: {str(e)}")
                    return Response({'detail': f'Failed to create sub-account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            # Save sub-account to database
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
        """Get user's Flutterwave sub-account."""
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
        """Get Flutterwave sub-account details."""
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
        """
        Get list of banks from Flutterwave.
        """
        try:
            client = FlutterwaveClient()
            banks = client.list_banks()
            
            # Return simplified bank list
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
            # Return verification data directly to frontend
            return Response({'detail': 'Account verified', 'data': verified}, status=status.HTTP_200_OK)
        except FlutterwaveError as e:
            logger.warning(f"Flutterwave account verification failed: {str(e)}")
            return Response({'detail': f'Failed to verify account: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error verifying account: {str(e)}")
            return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)