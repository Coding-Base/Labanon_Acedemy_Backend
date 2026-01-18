"""
Webhook verification utilities for secure payment status reconciliation.
This module handles verification and processing of webhooks from payment gateways.
"""

import hmac
import hashlib
import json
import os
import logging
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payment, Enrollment, DiplomaEnrollment, ActivationUnlock
from .paystack_utils import PaystackClient
from .flutterwave_utils import FlutterwaveClient

logger = logging.getLogger(__name__)


class WebhookVerificationError(Exception):
    """Raised when webhook verification fails."""
    pass


class PaystackWebhookVerifier:
    """Handles Paystack webhook signature verification and processing."""
    
    @staticmethod
    def verify_signature(body: bytes, signature: str) -> bool:
        """
        Verify Paystack webhook signature.
        
        Args:
            body: Raw request body
            signature: Signature from X-Paystack-Signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        secret = os.getenv('paystack_test_secret_key') or settings.PAYSTACK_SECRET_KEY
        computed = hmac.new(secret.encode('utf-8'), body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed, signature)
    
    @staticmethod
    def process_webhook(data: dict) -> dict:
        """
        Process Paystack webhook data and update payment status.
        
        Args:
            data: Webhook payload
            
        Returns:
            Dictionary with processing result
        """
        event = data.get('event')
        payload = data.get('data', {})
        
        if event == 'charge.success':
            reference = payload.get('reference')
            return PaystackWebhookVerifier._handle_charge_success(reference, payload)
        
        elif event == 'charge.failed':
            reference = payload.get('reference')
            return PaystackWebhookVerifier._handle_charge_failed(reference)
        
        return {'status': 'ignored', 'event': event}
    
    @staticmethod
    @staticmethod
    def _handle_charge_success(reference: str, payload: dict) -> dict:
        """Handle charge.success webhook event."""
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            
            # Track webhook receipt
            previous_status = payment.status
            payment.webhook_attempts += 1
            payment.webhook_received = True
            payment.webhook_received_at = timezone.now()
            
            if payment.status != Payment.SUCCESS:
                with transaction.atomic():
                    payment.status = Payment.SUCCESS
                    payment.verified_at = timezone.now()
                    
                    # Extract gateway fee from webhook payload (in kobo, convert to Naira)
                    gateway_fee_kobo = payload.get('fees', 0)
                    payment.gateway_fee = gateway_fee_kobo / 100  # Convert from kobo to Naira
                    payment.net_amount = payload.get('net', 0) / 100  # Convert from kobo to Naira
                    
                    payment.save()
                    
                    # Create enrollments based on payment kind
                    PaystackWebhookVerifier._create_enrollments(payment)
                    
                logger.info(
                    f"Payment {reference} status updated via webhook: "
                    f"{previous_status} → {payment.status} | Gateway fee: ₦{payment.gateway_fee}"
                )
                return {
                    'status': 'success',
                    'reference': reference,
                    'action': 'updated',
                    'previous_status': previous_status
                }
            else:
                # Update gateway fee even if payment already successful
                if payload.get('fees'):
                    payment.gateway_fee = payload.get('fees', 0) / 100
                    payment.net_amount = payload.get('net', 0) / 100
                payment.save()
                logger.info(f"Webhook received for already successful payment {reference}")
                return {
                    'status': 'success',
                    'reference': reference,
                    'action': 'acknowledged',
                    'message': 'Payment already successful'
                }
        
        except Payment.DoesNotExist:
            logger.warning(f"Webhook received for non-existent payment reference: {reference}")
            return {
                'status': 'error',
                'reference': reference,
                'message': 'Payment not found'
            }
        except Exception as e:
            logger.error(f"Error processing charge.success webhook for {reference}: {str(e)}")
            return {
                'status': 'error',
                'reference': reference,
                'message': str(e)
            }
    
    @staticmethod
    def _handle_charge_failed(reference: str) -> dict:
        """Handle charge.failed webhook event."""
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            previous_status = payment.status
            payment.webhook_attempts += 1
            payment.webhook_received_at = timezone.now()
            
            if payment.status != Payment.FAILED:
                payment.status = Payment.FAILED
                payment.save()
                logger.info(
                    f"Payment {reference} marked as failed via webhook: "
                    f"{previous_status} → FAILED"
                )
                return {
                    'status': 'success',
                    'reference': reference,
                    'action': 'marked_failed'
                }
            else:
                logger.info(f"Webhook received for already failed payment {reference}")
                return {
                    'status': 'success',
                    'reference': reference,
                    'action': 'acknowledged'
                }
        except Payment.DoesNotExist:
            logger.warning(f"Webhook received for non-existent payment reference: {reference}")
            return {'status': 'error', 'message': 'Payment not found'}
        except Exception as e:
            logger.error(f"Error processing charge.failed webhook for {reference}: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def _create_enrollments(payment: Payment):
        """Create necessary enrollments based on payment kind."""
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
            PaystackWebhookVerifier._handle_unlock_payment(payment)


class FlutterwaveWebhookVerifier:
    """Handles Flutterwave webhook signature verification and processing."""
    
    @staticmethod
    def verify_signature(body: bytes, signature: str) -> bool:
        """
        Verify Flutterwave webhook signature.
        
        Args:
            body: Raw request body (JSON string)
            signature: Signature from x-flutterwave-signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        flutterwave_secret = os.getenv('FLUTTERWAVE_SECRET_KEY') or settings.FLUTTERWAVE_SECRET_KEY
        expected_signature = hashlib.sha256((body + flutterwave_secret).encode()).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    
    @staticmethod
    def process_webhook(data: dict) -> dict:
        """
        Process Flutterwave webhook data and update payment status.
        
        Args:
            data: Webhook payload
            
        Returns:
            Dictionary with processing result
        """
        event = data.get('event')
        
        if event == 'charge.completed':
            payload = data.get('data', {})
            reference = payload.get('tx_ref')
            return FlutterwaveWebhookVerifier._handle_charge_completed(reference, payload)
        
        return {'status': 'ignored', 'event': event}
    
    @staticmethod
    @staticmethod
    def _handle_charge_completed(reference: str, payload: dict) -> dict:
        """Handle charge.completed webhook event."""
        try:
            payment = Payment.objects.get(flutterwave_reference=reference)
            
            previous_status = payment.status
            payment.webhook_attempts += 1
            payment.webhook_received_at = timezone.now()
            
            charge_status = payload.get('status')
            
            if charge_status == 'successful':
                if payment.status != Payment.SUCCESS:
                    with transaction.atomic():
                        payment.status = Payment.SUCCESS
                        payment.flutterwave_transaction_id = payload.get('id')
                        payment.verified_at = timezone.now()
                        payment.webhook_received = True
                        
                        # Extract gateway fee from Flutterwave webhook
                        # Flutterwave: charged_amount - amount = gateway fee
                        amount = payload.get('amount', 0)
                        charged_amount = payload.get('charged_amount', 0)
                        payment.gateway_fee = max(0, charged_amount - amount)
                        payment.net_amount = amount
                        
                        payment.save()
                        
                        # Create enrollments
                        FlutterwaveWebhookVerifier._create_enrollments(payment)
                    
                    logger.info(
                        f"Payment {reference} status updated via webhook: "
                        f"{previous_status} → SUCCESS | Gateway fee: ₦{payment.gateway_fee}"
                    )
                    return {
                        'status': 'success',
                        'reference': reference,
                        'action': 'updated',
                        'previous_status': previous_status
                    }
                else:
                    # Update gateway fee even if already successful
                    amount = payload.get('amount', 0)
                    charged_amount = payload.get('charged_amount', 0)
                    if charged_amount > 0:
                        payment.gateway_fee = max(0, charged_amount - amount)
                        payment.net_amount = amount
                    payment.webhook_received = True
                    payment.save()
                    logger.info(f"Webhook received for already successful payment {reference}")
                    return {
                        'status': 'success',
                        'reference': reference,
                        'action': 'acknowledged'
                    }
            
            elif charge_status in ['failed', 'cancelled']:
                if payment.status != Payment.FAILED:
                    payment.status = Payment.FAILED
                    payment.webhook_received = True
                    payment.save()
                    logger.info(
                        f"Payment {reference} marked as failed via webhook: {charge_status}"
                    )
                return {
                    'status': 'success',
                    'reference': reference,
                    'action': 'marked_failed'
                }
        
        except Payment.DoesNotExist:
            logger.warning(f"Webhook received for non-existent payment reference: {reference}")
            return {'status': 'error', 'message': 'Payment not found'}
        except Exception as e:
            logger.error(f"Error processing charge.completed webhook for {reference}: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def _create_enrollments(payment: Payment):
        """Create necessary enrollments based on payment kind."""
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
            FlutterwaveWebhookVerifier._handle_unlock_payment(payment)


class PaymentReconciliation:
    """
    Payment reconciliation service to recover payments that may have timed out
    during verification but were actually successful on the gateway.
    """
    
    @staticmethod
    def reconcile_pending_payments(minutes_old: int = 5) -> dict:
        """
        Check pending payments that are older than specified minutes.
        This handles cases where verification timed out but payment succeeded.
        
        Args:
            minutes_old: Only reconcile payments older than this many minutes
            
        Returns:
            Dictionary with reconciliation results
        """
        cutoff_time = timezone.now() - timedelta(minutes=minutes_old)
        
        pending_payments = Payment.objects.filter(
            status=Payment.PENDING,
            created_at__lt=cutoff_time
        ).select_related('user', 'course', 'diploma')
        
        results = {
            'total_checked': 0,
            'paystack_updated': 0,
            'flutterwave_updated': 0,
            'already_successful': 0,
            'confirmed_failed': 0,
            'errors': [],
            'details': []
        }
        
        for payment in pending_payments:
            results['total_checked'] += 1
            
            try:
                if payment.payment_provider == Payment.PROVIDER_PAYSTACK:
                    result = PaymentReconciliation._reconcile_paystack_payment(payment)
                elif payment.payment_provider == Payment.PROVIDER_FLUTTERWAVE:
                    result = PaymentReconciliation._reconcile_flutterwave_payment(payment)
                else:
                    result = {'status': 'error', 'message': 'Unknown provider'}
                
                results['details'].append({
                    'payment_id': payment.id,
                    'reference': payment.paystack_reference or payment.flutterwave_reference,
                    **result
                })
                
                if result.get('status') == 'updated':
                    if payment.payment_provider == Payment.PROVIDER_PAYSTACK:
                        results['paystack_updated'] += 1
                    else:
                        results['flutterwave_updated'] += 1
                    logger.info(
                        f"Payment {payment.id} reconciled: {result.get('action')}"
                    )
                
            except Exception as e:
                error_msg = f"Payment {payment.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"Reconciliation error: {error_msg}")
        
        logger.info(
            f"Payment reconciliation complete: {results['paystack_updated']} Paystack, "
            f"{results['flutterwave_updated']} Flutterwave updated"
        )
        
        return results
    
    @staticmethod
    def _reconcile_paystack_payment(payment: Payment) -> dict:
        """Check Paystack payment status and update if successful."""
        try:
            if not payment.paystack_reference:
                return {'status': 'error', 'message': 'No Paystack reference'}
            
            client = PaystackClient()
            transaction_data = client.verify_payment(payment.paystack_reference)
            
            if transaction_data.get('status') == 'success':
                # Gateway says payment succeeded
                if payment.status == Payment.SUCCESS:
                    return {
                        'status': 'acknowledged',
                        'action': 'already_successful',
                        'gateway_status': 'success'
                    }
                
                # Update payment to success
                with transaction.atomic():
                    payment.status = Payment.SUCCESS
                    payment.verified_at = timezone.now()
                    payment.webhook_received = True  # Mark as reconciled
                    
                    # Extract gateway fee from Paystack reconciliation
                    gateway_fee_kobo = transaction_data.get('fees', 0)
                    payment.gateway_fee = gateway_fee_kobo / 100
                    payment.net_amount = transaction_data.get('net', 0) / 100
                    
                    payment.save()
                    
                    # Create enrollments
                    PaystackWebhookVerifier._create_enrollments(payment)
                
                return {
                    'status': 'updated',
                    'action': 'recovered_from_timeout',
                    'gateway_status': 'success'
                }
            else:
                # Gateway says payment failed
                if payment.status != Payment.FAILED:
                    payment.status = Payment.FAILED
                    payment.save()
                    return {
                        'status': 'updated',
                        'action': 'confirmed_failed',
                        'gateway_status': transaction_data.get('status', 'failed')
                    }
                return {
                    'status': 'acknowledged',
                    'action': 'already_failed',
                    'gateway_status': transaction_data.get('status', 'failed')
                }
        
        except Exception as e:
            logger.error(f"Paystack reconciliation error for payment {payment.id}: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    @staticmethod
    def _reconcile_flutterwave_payment(payment: Payment) -> dict:
        """Check Flutterwave payment status and update if successful."""
        try:
            if not payment.flutterwave_reference:
                return {'status': 'error', 'message': 'No Flutterwave reference'}
            
            client = FlutterwaveClient()
            transaction_data = client.verify_payment_by_reference(payment.flutterwave_reference)
            
            if transaction_data.get('status') == 'successful':
                # Gateway says payment succeeded
                if payment.status == Payment.SUCCESS:
                    return {
                        'status': 'acknowledged',
                        'action': 'already_successful',
                        'gateway_status': 'successful'
                    }
                
                # Update payment to success
                with transaction.atomic():
                    payment.status = Payment.SUCCESS
                    payment.flutterwave_transaction_id = transaction_data.get('id')
                    payment.verified_at = timezone.now()
                    payment.webhook_received = True  # Mark as reconciled
                    
                    # Extract gateway fee from Flutterwave reconciliation
                    amount = transaction_data.get('amount', 0)
                    charged_amount = transaction_data.get('charged_amount', 0)
                    payment.gateway_fee = max(0, charged_amount - amount)
                    payment.net_amount = amount
                    
                    payment.save()
                    
                    # Create enrollments
                    FlutterwaveWebhookVerifier._create_enrollments(payment)
                
                return {
                    'status': 'updated',
                    'action': 'recovered_from_timeout',
                    'gateway_status': 'successful'
                }
            else:
                # Gateway says payment failed
                if payment.status != Payment.FAILED:
                    payment.status = Payment.FAILED
                    payment.save()
                    return {
                        'status': 'updated',
                        'action': 'confirmed_failed',
                        'gateway_status': transaction_data.get('status', 'failed')
                    }
                return {
                    'status': 'acknowledged',
                    'action': 'already_failed',
                    'gateway_status': transaction_data.get('status', 'failed')
                }
        
        except Exception as e:
            logger.error(f"Flutterwave reconciliation error for payment {payment.id}: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }


# Helper functions for unlock payment handling
def _handle_unlock_payment(payment: Payment):
    """Create activation unlock records for unlock kind payments."""
    try:
        meta = None
        if payment.provider_reference:
            try:
                meta = json.loads(payment.provider_reference)
            except Exception:
                meta = None
        
        if meta and isinstance(meta, dict):
            activation = meta.get('activation') or meta
            
            exam_identifier = activation.get('exam_id') if activation else None
            subject_id = activation.get('subject_id') if activation else None
            
            if exam_identifier or subject_id:
                ActivationUnlock.objects.get_or_create(
                    user=payment.user,
                    exam_identifier=str(exam_identifier) if exam_identifier else None,
                    subject_id=int(subject_id) if subject_id else None,
                    defaults={'payment': payment}
                )
            
            # Mark account unlocked if activation_type == 'account'
            activation_type = activation.get('activation_type') if activation else None
            if activation_type == 'account':
                payment.user.is_unlocked = True
                payment.user.save()
    except Exception as e:
        logger.error(f"Failed to create activation unlock for payment {payment.id}: {str(e)}")


# Assign helper to verifier classes
PaystackWebhookVerifier._handle_unlock_payment = staticmethod(_handle_unlock_payment)
FlutterwaveWebhookVerifier._handle_unlock_payment = staticmethod(_handle_unlock_payment)
