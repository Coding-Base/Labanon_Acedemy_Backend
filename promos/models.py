from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


def generate_code():
    return uuid.uuid4().hex[:8].upper()


class PromoCode(models.Model):
    """Promo/discount codes usable across payments.

    - `amount`: either a fixed currency amount or a percentage (ctrl by `is_percentage`).
    - `max_uses`: optional limit for how many times the code can be consumed.
    - `uses`: counter of times consumed.
    - `expires_at`: optional expiry datetime.
    - `applicable_to`: optional tag to restrict use (e.g. 'exam', 'activation', 'all').
    """
    code = models.CharField(max_length=32, unique=True, default=generate_code)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount or percentage value')
    is_percentage = models.BooleanField(default=False)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    applicable_to = models.CharField(max_length=32, default='all', help_text='Optional: restriction tag')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({'%' if self.is_percentage else ''}{self.amount})"

    def is_expired(self):
        if self.expires_at and timezone.now() >= self.expires_at:
            return True
        return False

    def is_usable(self):
        if not self.active:
            return False
        if self.is_expired():
            return False
        if self.max_uses is not None and self.uses >= self.max_uses:
            return False
        return True

    def compute_discount(self, total_amount):
        """Return Decimal discount applied for given total_amount."""
        from decimal import Decimal
        total = Decimal(str(total_amount))
        amt = Decimal(str(self.amount))
        if self.is_percentage:
            discount = (total * amt / Decimal('100')).quantize(Decimal('0.01'))
        else:
            discount = min(amt, total)
        return discount

    def consume(self):
        if self.max_uses is not None and self.uses >= self.max_uses:
            raise ValueError('Promo exhausted')
        self.uses += 1
        # If we've reached max uses, deactivate
        if self.max_uses is not None and self.uses >= self.max_uses:
            self.active = False
        self.save()
