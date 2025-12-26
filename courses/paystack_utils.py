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
            logger.error(f"Paystack API error: {str(e)}, Status: {e.response.status_code if hasattr(e, 'response') and e.response else 'N/A'}, Response: {error_body}")
            raise PaystackError(f"Paystack API error: {str(e)}")
    
    def initialize_payment(self, email, amount, reference, metadata=None, callback_url=None):
        """
        Initialize payment transaction.
        
        Args:
            email (str): Customer email
            amount (int): Amount in kobo (₦100 = 10000 kobo)
            reference (str): Unique reference for this transaction
            metadata (dict): Additional metadata to send with transaction
            callback_url (str): URL to redirect to after payment (Paystack will append ?reference=xxx)
        
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
            data['mobile'] = mobile
        
        logger.debug(f"Paystack subaccount request data: {data}")
        response = self._request('POST', '/subaccount', data)
        if not response.get('status'):
            error_msg = response.get('message', 'Failed to create sub-account')
            logger.error(f"Paystack subaccount error: {error_msg}, Response: {response}")
            raise PaystackError(error_msg)
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
