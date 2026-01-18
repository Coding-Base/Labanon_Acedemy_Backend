"""
Management command to reconcile pending payments.

This command checks pending payments older than a specified number of minutes
and verifies their status with the payment gateways. It's designed to be run
periodically (e.g., via cron job or scheduler) to recover payments that timed
out during verification but were actually successful on the gateway.

Usage:
    python manage.py reconcile_payments
    python manage.py reconcile_payments --minutes-old 10
    python manage.py reconcile_payments --minutes-old 5 --verbose
"""

from django.core.management.base import BaseCommand
from courses.webhook_verification import PaymentReconciliation


class Command(BaseCommand):
    help = 'Reconcile pending payments with payment gateways to recover timed-out transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes-old',
            type=int,
            default=5,
            help='Only reconcile payments older than this many minutes (default: 5)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each payment checked',
        )

    def handle(self, *args, **options):
        minutes_old = options['minutes_old']
        verbose = options['verbose']

        if minutes_old < 1:
            self.stdout.write(self.style.ERROR('Error: --minutes-old must be at least 1'))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting payment reconciliation (checking payments older than {minutes_old} minutes)...'
            )
        )

        # Run reconciliation
        results = PaymentReconciliation.reconcile_pending_payments(minutes_old)

        # Display results
        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Reconciliation completed!\n')
        )

        self.stdout.write(f'Total payments checked: {results["total_checked"]}')
        self.stdout.write(
            self.style.SUCCESS(f'Paystack payments updated: {results["paystack_updated"]}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Flutterwave payments updated: {results["flutterwave_updated"]}')
        )

        # Show detailed information if verbose
        if verbose and results['details']:
            self.stdout.write('\nDetailed results:')
            self.stdout.write('-' * 80)
            for detail in results['details']:
                if detail.get('status') == 'updated':
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Payment {detail['payment_id']} ({detail['reference']}): "
                            f"{detail['action']}"
                        )
                    )
                elif detail.get('status') == 'acknowledged':
                    self.stdout.write(
                        f"• Payment {detail['payment_id']} ({detail['reference']}): "
                        f"{detail['action']}"
                    )
                elif detail.get('status') == 'error':
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Payment {detail['payment_id']}: {detail.get('message', 'Unknown error')}"
                        )
                    )

        # Show errors if any
        if results['errors']:
            self.stdout.write(self.style.WARNING(f'\n⚠ {len(results["errors"])} errors encountered:'))
            for error in results['errors']:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        self.stdout.write('\n')
