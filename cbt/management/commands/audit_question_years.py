from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from cbt.models import Question, Subject

class Command(BaseCommand):
    help = 'Audit question year data across all subjects and report unassigned questions'

    def handle(self, *args, **options):
        self.stdout.write("\n=== CBT Question Year Audit Report ===\n")
        total_questions_all = 0
        total_unassigned_all = 0

        for subject in Subject.objects.select_related('exam').all().order_by('exam__title', 'name'):
            total = subject.questions.count()
            if total == 0:
                continue

            total_questions_all += total
            no_year = subject.questions.filter(
                Q(year__isnull=True) | Q(year='')
            ).count()
            total_unassigned_all += no_year

            year_breakdown = list(
                subject.questions
                .exclude(Q(year__isnull=True) | Q(year=''))
                .values('year')
                .annotate(count=Count('id'))
                .order_by('-year')
            )

            self.stdout.write(f"\n📚 {subject.exam.title} - {subject.name}")
            self.stdout.write(f"   Total: {total} questions")
            if no_year > 0:
                self.stdout.write(self.style.WARNING(f"   ⚠️ Unassigned (no year): {no_year} questions (will default to 2021 for students)"))
            else:
                self.stdout.write(self.style.SUCCESS(f"   ✅ All questions have years assigned"))

            for entry in year_breakdown:
                self.stdout.write(f"     • {entry['year']}: {entry['count']} questions")

        self.stdout.write("\n" + "="*45)
        self.stdout.write(f"Total Questions Across System: {total_questions_all}")
        if total_unassigned_all > 0:
            self.stdout.write(self.style.WARNING(f"Total Unassigned Questions: {total_unassigned_all} (defaulting to 2021)"))
        else:
            self.stdout.write(self.style.SUCCESS("All questions have assigned years!"))
        self.stdout.write("="*45 + "\n")
