from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from cbt.models import Question, Subject
import re


def detect_year_from_text(text: str) -> str:
    """Extract a 4-digit exam year (1980-2035) from text or identifier."""
    if not text:
        return None
    matches = re.findall(r'\b(19[89]\d|20[0-3]\d)\b', str(text))
    if matches:
        return str(matches[0])
    return None


def detect_question_year(question) -> str:
    """
    Detect the most appropriate year for a question:
    1. Check question.text for embedded year pattern
    2. Check question.explanation for embedded year pattern
    3. Fallback to question.created_at.year (upload timestamp)
    4. Fallback to current year
    """
    y = detect_year_from_text(getattr(question, 'text', ''))
    if y:
        return y
    y = detect_year_from_text(getattr(question, 'explanation', ''))
    if y:
        return y
    if hasattr(question, 'created_at') and question.created_at:
        return str(question.created_at.year)
    return str(timezone.now().year)


class Command(BaseCommand):
    help = 'Automatically detect and upgrade unassigned questions by assigning them to their respective years.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate detection and show what would be updated without saving changes.',
        )
        parser.add_argument(
            '--subject-id',
            type=int,
            help='Limit auto-assignment to a specific subject ID.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        subject_id = options.get('subject_id')

        self.stdout.write(f"\n=== Auto-Assign Question Years{' (DRY RUN)' if dry_run else ''} ===\n")

        query = Q(year__isnull=True) | Q(year='')
        if subject_id:
            query &= Q(subject_id=subject_id)

        unassigned_qs = Question.objects.filter(query).select_related('subject', 'subject__exam')
        total_unassigned = unassigned_qs.count()

        if total_unassigned == 0:
            self.stdout.write(self.style.SUCCESS("All questions already have assigned years. Nothing to update!"))
            return

        self.stdout.write(f"Found {total_unassigned} unassigned question(s) to process.\n")

        breakdown = {}
        updated_count = 0

        for q in unassigned_qs:
            detected_year = detect_question_year(q)
            breakdown[detected_year] = breakdown.get(detected_year, 0) + 1
            updated_count += 1

            if not dry_run:
                q.year = detected_year
                q.save(update_fields=['year'])

        self.stdout.write(self.style.SUCCESS(f"\nProcessed {updated_count} question(s):"))
        for year, count in sorted(breakdown.items(), key=lambda x: str(x[0]), reverse=True):
            self.stdout.write(f"  * Year {year}: {count} question(s)")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run completed. No database changes were saved. Run without --dry-run to apply."))
        else:
            self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Successfully updated all questions!"))
