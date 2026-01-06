"""
Flutterwave integration utilities for payment processing and sub-account management.
"""
import requests
import os
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
import logging
import json

logger = logging.getLogger(__name__)

FLUTTERWAVE_BASE_URL = 'https://api.flutterwave.com/v3'
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY') or settings.FLUTTERWAVE_SECRET_KEY
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY') or settings.FLUTTERWAVE_PUBLIC_KEY
FLUTTERWAVE_ENCRYPTION_KEY = os.getenv('Flutterwave_ENCRYPTION_KEY') or getattr(settings, 'FLUTTERWAVE_ENCRYPTION_KEY', '')


class FlutterwaveError(Exception):
    """Custom exception for Flutterwave API errors."""
    pass


class FlutterwaveClient:
    """Client for interacting with Flutterwave API."""
    
    def __init__(self, secret_key=None):
        self.secret_key = secret_key or FLUTTERWAVE_SECRET_KEY
        self.public_key = FLUTTERWAVE_PUBLIC_KEY
        self.base_url = FLUTTERWAVE_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }

    def is_test_mode(self):
        """Return True when using a Flutterwave test secret key."""
        try:
            return bool(self.secret_key and 'TEST' in str(self.secret_key).upper())
        except Exception:
            return False
    
    def _request(self, method, endpoint, data=None):
        """Make HTTP request to Flutterwave API."""
        url = f"{self.base_url}{endpoint}"
        # Verbose request/response logging (only when Django DEBUG enabled)
        try:
            if settings.DEBUG:
                logger.debug(f"Flutterwave request -> {method} {url} payload={json.dumps(data) if data is not None else None}")

            # Use a session that ignores environment proxies to avoid local dev proxy interception
            session = requests.Session()
            session.trust_env = False
            if method == 'GET':
                response = session.get(url, headers=self.headers, timeout=15)
            elif method == 'POST':
                response = session.post(url, json=data, headers=self.headers, timeout=15)
            elif method == 'PUT':
                response = session.put(url, json=data, headers=self.headers, timeout=15)
            else:
                raise FlutterwaveError(f"Unsupported HTTP method: {method}")

            # Try to parse JSON body, fallback to text
            try:
                body = response.json()
            except ValueError:
                body = response.text

            if settings.DEBUG:
                logger.debug(f"Flutterwave response <- status={response.status_code} body={body}")

            if not response.ok:
                # Non-2xx responses should raise a readable error
                raise FlutterwaveError(f"HTTP {response.status_code}: {body}")

            return body
        except requests.exceptions.RequestException as e:
            # Network-level errors
            resp = getattr(e, 'response', None)
            try:
                err_body = resp.json() if resp is not None else str(e)
            except Exception:
                err_body = resp.text if resp is not None else str(e)
            status_code = resp.status_code if resp is not None else 'N/A'
            logger.error(f"Flutterwave API request exception: {str(e)}, status={status_code}, body={err_body}")
            raise FlutterwaveError(f"Flutterwave API error: Status {status_code}, Response: {err_body}")
    
    def initialize_payment(self, email, amount, reference, metadata=None, callback_url=None, full_name='', phone_number=''):
        """
        Initialize payment transaction for Flutterwave.
        
        Args:
            email (str): Customer email
            amount (float): Amount in NGN (₦100)
            reference (str): Unique reference for this transaction
            metadata (dict): Additional metadata to send with transaction
            callback_url (str): URL to redirect to after payment
            full_name (str): Customer full name
            phone_number (str): Customer phone number
        
        Returns:
            dict: Response with link and payment data
        """
        data = {
            'tx_ref': reference,
            'amount': amount,
            'currency': 'NGN',
            'redirect_url': callback_url or '',
            'customer': {
                'email': email,
            }
        }
        
        if full_name:
            data['customer']['name'] = full_name
        if phone_number:
            data['customer']['phonenumber'] = phone_number
        
        if metadata:
            data['meta'] = metadata
        
        data['customizations'] = {
            'title': 'Lebanon Academy Payment',
            'description': 'Course/Diploma Purchase'
        }
        
        response = self._request('POST', '/payments', data)
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to initialize payment'))
        return response.get('data', {})
    
    def verify_payment(self, transaction_id):
        """
        Verify a payment transaction using transaction ID.
        
        Args:
            transaction_id (str or int): The Flutterwave transaction ID
        
        Returns:
            dict: Transaction details if successful
        """
        response = self._request('GET', f'/transactions/{transaction_id}/verify')
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to verify payment'))
        return response.get('data', {})
    
    def verify_payment_by_reference(self, reference):
        """
        Verify a payment using reference code.
        
        Args:
            reference (str): The payment reference code
        
        Returns:
            dict: Transaction details if successful
        """
        response = self._request('GET', f'/transactions/verify_by_reference?tx_ref={reference}')
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to verify payment'))
        return response.get('data', {})
    
    def create_subaccount(self, business_name, account_bank, account_number, 
                         account_holder_name, business_email=None, percentage_charge=0, country='NG',
                         meta=None):
        """
        Create a Flutterwave sub-account for a tutor/institution.
        
        Args:
            business_name (str): Name of the business
            account_bank (str): Bank code (3-character code like '050' for Fidelity)
            account_number (str): Bank account number
            account_holder_name (str): Account holder name
            business_email (str): Business email address (required by Flutterwave)
            percentage_charge (float): Percentage to charge (0-100)
            country (str): Country code (default 'NG')
            meta (dict): Additional metadata
        
        Returns:
            dict: Response with subaccount details including subaccount_id
        """
        data = {
            'account_bank': account_bank,
            'account_number': account_number,
            'business_name': business_name,
            'business_email': business_email or 'noreply@example.com',
            'split_type': 'percentage',
            'split_value': float(percentage_charge),
            'country': country,
        }
        
        if meta:
            data['meta'] = meta
        
        logger.debug(f"Flutterwave subaccount request data: {data}")
        response = self._request('POST', '/subaccounts', data)
        if response.get('status') != 'success':
            error_msg = response.get('message', 'Failed to create sub-account')
            logger.error(f"Flutterwave subaccount error: {error_msg}, Response: {response}")
            raise FlutterwaveError(f"{error_msg}: {response}")
        return response.get('data', {})
    
    def get_subaccount(self, subaccount_id):
        """
        Get sub-account details.
        
        Args:
            subaccount_id (int): Sub-account ID
        
        Returns:
            dict: Sub-account details
        """
        response = self._request('GET', f'/subaccounts/{subaccount_id}')
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Sub-account not found'))
        return response.get('data', {})
    
    def update_subaccount(self, subaccount_id, data):
        """
        Update a sub-account.
        
        Args:
            subaccount_id (int): Sub-account ID
            data (dict): Data to update
        
        Returns:
            dict: Updated sub-account details
        """
        response = self._request('PUT', f'/subaccounts/{subaccount_id}', data)
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to update sub-account'))
        return response.get('data', {})
    
    def list_banks(self, country='NG'):
        """
        List available banks.
        
        Args:
            country (str): Country code (default 'NG')
        
        Returns:
            list: List of available banks with codes
        """
        response = self._request('GET', f'/banks/{country}')
        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to fetch banks'))
        return response.get('data', [])
    
    def verify_bank_account(self, account_number, account_bank):
        """
        Verify bank account details using Flutterwave account resolution.
        
        Args:
            account_number (str): Bank account number
            account_bank (str): Bank code
        
        Returns:
            dict: Account details with account name
        """
        endpoint = f'/accounts/resolve?account_number={account_number}&account_bank={account_bank}'
        response = self._request('GET', endpoint)
        # Ensure we have a dict (some responses may come back as raw text)
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except Exception:
                logger.error(f"Unexpected non-JSON response from Flutterwave verify: {response}")
                # Raise the raw response to surface exact provider message to caller
                raise FlutterwaveError(response)

        if response.get('status') != 'success':
            raise FlutterwaveError(response.get('message', 'Failed to resolve account'))
        return response.get('data', {})


def ngn_to_float(naira):
    """Convert NGN to float."""
    return float(Decimal(str(naira)))


def calculate_split(total_amount, platform_percentage=5):
    """
    Calculate platform fee and creator amount.
    
    Args:
        total_amount (Decimal): Total payment amount
        platform_percentage (float): Platform fee percentage
    
    Returns:
        tuple: (platform_fee, creator_amount)
    """
    platform_fee = total_amount * Decimal(str(platform_percentage)) / Decimal('100')
    creator_amount = total_amount - platform_fee
    return platform_fee, creator_amount


def generate_payment_reference():
    """Generate a unique payment reference for Flutterwave."""
    import uuid
    return f"FLW_{uuid.uuid4().hex[:12].upper()}"
