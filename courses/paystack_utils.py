"""
Paystack integration utilities for payment processing and sub-account management.
"""
import requests
import os
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = 'https://api.paystack.co'
PAYSTACK_SECRET_KEY = os.getenv('paystack_test_secret_key') or settings.PAYSTACK_SECRET_KEY


class PaystackError(Exception):
    """Custom exception for Paystack API errors."""
    pass


class PaystackClient:
    """Client for interacting with Paystack API."""
    
    def __init__(self, secret_key=None):
        self.secret_key = secret_key or PAYSTACK_SECRET_KEY
        self.base_url = PAYSTACK_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def _request(self, method, endpoint, data=None):
        """Make HTTP request to Paystack API."""
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=self.headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=self.headers)
            else:
                raise PaystackError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_body = ''
            try:
                error_body = e.response.json() if hasattr(e, 'response') and e.response is not None else {}
            except:
                error_body = str(e)
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 'N/A'
            logger.error(f"Paystack API error: {str(e)}, Status: {status_code}, Response: {error_body}")
            # Raise with the parsed response body when available to help debugging
            raise PaystackError(f"Paystack API error: Status {status_code}, Response: {error_body}")
    
    def initialize_payment(self, email, amount, reference, metadata=None, callback_url=None, recipient_code=None, split_code=None):
        """
        Initialize payment transaction.
        
        Args:
            email (str): Customer email
            amount (int): Amount in kobo (₦100 = 10000 kobo)
            reference (str): Unique reference for this transaction
            metadata (dict): Additional metadata to send with transaction
            callback_url (str): URL to redirect to after payment (Paystack will append ?reference=xxx)
            recipient_code (str): Recipient code for split payment (for paying a sub-account)
            split_code (str): Split code for distributing payment among multiple accounts
        
        Returns:
            dict: Response with authorization_url and access_code
        """
        data = {
            'email': email,
            'amount': amount,
            'reference': reference,
        }
        if metadata:
            data['metadata'] = metadata
        if callback_url:
            data['callback_url'] = callback_url
        if recipient_code:
            data['recipient'] = recipient_code
        if split_code:
            data['split_code'] = split_code
        
        response = self._request('POST', '/transaction/initialize', data)
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Failed to initialize payment'))
        return response.get('data', {})
    
    def verify_payment(self, reference):
        """
        Verify a payment transaction.
        
        Args:
            reference (str): The payment reference to verify
        
        Returns:
            dict: Transaction details if successful
        """
        response = self._request('GET', f'/transaction/verify/{reference}')
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Failed to verify payment'))
        return response.get('data', {})
    
    def create_subaccount(self, business_name, settlement_bank, account_number, 
                         account_holder_name, percentage_charge=0, description='', 
                         primary_contact_email='', primary_contact_name='', mobile=''):
        """
        Create a Paystack sub-account for a tutor/institution.
        
        Args:
            business_name (str): Name of the tutor/institution
            settlement_bank (str): Bank code (e.g., '011' for First Bank)
            account_number (str): Bank account number
            account_holder_name (str): Account holder name
            percentage_charge (float): Percentage to charge for payments (default 0)
            description (str): Description of the business
            primary_contact_email (str): Primary contact email
            primary_contact_name (str): Primary contact name
            mobile (str): Mobile number
        
        Returns:
            dict: Response with subaccount_code if successful
        """
        # Attempt to resolve the bank account first to catch invalid account details
        try:
            resolved = self.resolve_bank_account(account_number, settlement_bank)
        except PaystackError as e:
            logger.error(f"Bank account resolution failed: {e}")
            raise PaystackError(f"Account details are invalid: {e}")

        # If Paystack returned an account_name, verify it matches the provided account holder name
        account_name = resolved.get('account_name') if isinstance(resolved, dict) else None
        def _norm(s: str) -> str:
            return ' '.join(s.split()).lower() if isinstance(s, str) else ''

        if account_name and account_holder_name:
            if _norm(account_name) != _norm(account_holder_name):
                logger.error(f"Resolved account name '{account_name}' does not match provided account holder name '{account_holder_name}'")
                raise PaystackError(f"Account name does not match bank records: resolved='{account_name}' provided='{account_holder_name}'")

        data = {
            'business_name': business_name,
            'settlement_bank': settlement_bank,
            'account_number': account_number,
            'account_holder_name': account_holder_name,
            'percentage_charge': float(percentage_charge),
        }
        
        # Add optional fields if provided
        if description:
            data['description'] = description
        if primary_contact_email:
            data['primary_contact_email'] = primary_contact_email
        if primary_contact_name:
            data['primary_contact_name'] = primary_contact_name
        if mobile:
            # Paystack expects primary contact phone under 'primary_contact_phone'
            data['primary_contact_phone'] = mobile
        
        logger.debug(f"Paystack subaccount request data: {data}")
        response = self._request('POST', '/subaccount', data)
        if not response.get('status'):
            error_msg = response.get('message', 'Failed to create sub-account')
            logger.error(f"Paystack subaccount error: {error_msg}, Response: {response}")
            # Surface the full response to help debugging (validation errors etc.)
            raise PaystackError(f"{error_msg}: {response}")
        return response.get('data', {})

    def resolve_bank_account(self, account_number, bank_code):
        """
        Resolve a bank account using Paystack's resolve endpoint to validate account number and bank code.

        Returns the `data` dict on success (contains `account_name`), or raises PaystackError on failure.
        """
        if not account_number or not bank_code:
            raise PaystackError("Missing account number or bank code for account resolution")

        # Paystack expects query params `account_number` and `bank_code`
        endpoint = f"/bank/resolve?account_number={account_number}&bank_code={bank_code}"
        response = self._request('GET', endpoint)
        if not response.get('status'):
            logger.error(f"Paystack resolve failed: {response}")
            raise PaystackError(response.get('message', 'Failed to resolve bank account'))
        return response.get('data', {})
    
    def update_subaccount(self, id_or_code, data):
        """
        Update a sub-account.
        
        Args:
            id_or_code (str): Sub-account ID or code
            data (dict): Data to update
        
        Returns:
            dict: Updated sub-account details
        """
        response = self._request('PUT', f'/subaccount/{id_or_code}', data)
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Failed to update sub-account'))
        return response.get('data', {})
    
    def get_subaccount(self, id_or_code):
        """
        Get sub-account details.
        
        Args:
            id_or_code (str): Sub-account ID or code
        
        Returns:
            dict: Sub-account details
        """
        response = self._request('GET', f'/subaccount/{id_or_code}')
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Sub-account not found'))
        return response.get('data', {})
    
    def list_banks(self, country='NG'):
        """
        List available banks.
        
        Args:
            country (str): Country code (default 'NG' for Nigeria)
        
        Returns:
            list: List of available banks with codes
        """
        response = self._request('GET', f'/bank?country={country}')
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Failed to fetch banks'))
        return response.get('data', [])
    
    def create_split(self, name, type='percentage', currency='NGN', subaccounts=None):
        """
        Create a payment split (for distributing payments among multiple accounts).
        
        Args:
            name (str): Name of the split
            type (str): 'percentage' or 'flat'
            currency (str): Currency code
            subaccounts (list): List of dicts with 'subaccount' and 'share' keys
        
        Returns:
            dict: Split details
        """
        data = {
            'name': name,
            'type': type,
            'currency': currency,
        }
        if subaccounts:
            data['subaccounts'] = subaccounts
        
        response = self._request('POST', '/split', data)
        if not response.get('status'):
            raise PaystackError(response.get('message', 'Failed to create split'))
        return response.get('data', {})


def kobo_to_naira(kobo):
    """Convert kobo to Naira."""
    return Decimal(str(kobo)) / Decimal('100')


def naira_to_kobo(naira):
    """Convert Naira to kobo."""
    return int(Decimal(str(naira)) * Decimal('100'))


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
    """Generate a unique payment reference."""
    import uuid
    return f"PAY_{uuid.uuid4().hex[:12].upper()}"
