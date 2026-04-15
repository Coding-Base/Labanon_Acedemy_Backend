from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from mock_exams.models import (
    CustomMockExam, MockExamSubject, MockExamQuestion, 
    MockExamOption, MockExamFee
)
from datetime import timedelta
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate mock exams with test data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to populate mock exam data...'))

        # Get or create admin user
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f'Created admin user'))
        else:
            self.stdout.write(self.style.WARNING(f'Admin user already exists'))

        # Create sample mock exams
        exam_data = [
            {
                'title': 'JAMB Practice Exam 1',
                'description': 'JAMB UTME examination practice test 1',
                'subject_area': 'General Studies',
                'difficulty_level': 'medium',
                'total_duration_minutes': 120,
                'total_marks': 100,
                'passing_marks': 70,
                'status': 'draft',
                'is_published': False,
            },
            {
                'title': 'WAEC Sample Exam 2023',
                'description': 'WAEC SSCE practice examination',
                'subject_area': 'English Language',
                'difficulty_level': 'hard',
                'total_duration_minutes': 180,
                'total_marks': 120,
                'passing_marks': 80,
                'status': 'published',
                'is_published': True,
            },
            {
                'title': 'NECO Diagnostic Test',
                'description': 'NECO entrance examination diagnostic',
                'subject_area': 'Mathematics',
                'difficulty_level': 'easy',
                'total_duration_minutes': 90,
                'total_marks': 80,
                'passing_marks': 60,
                'status': 'published',
                'is_published': True,
            },
        ]

        exams = []
        for exam_info in exam_data:
            exam, created = CustomMockExam.objects.get_or_create(
                title=exam_info['title'],
                defaults={
                    'admin': admin_user,
                    **exam_info
                }
            )
            exams.append(exam)
            status_text = 'Created' if created else 'Already exists'
            self.stdout.write(self.style.SUCCESS(f'{status_text}: {exam.title}'))

        # Create subjects for each exam
        subjects_data = {
            exams[0]: ['English', 'Mathematics', 'Physics'],  # JAMB exam
            exams[1]: ['Literature', 'Grammar', 'Comprehension'],  # WAEC
            exams[2]: ['Algebra', 'Geometry', 'Calculus'],  # NECO
        }

        subjects = {}
        for exam, subject_names in subjects_data.items():
            for subject_name in subject_names:
                subject, created = MockExamSubject.objects.get_or_create(
                    mock_exam=exam,
                    subject_name=subject_name,
                    defaults={
                        'order': subject_names.index(subject_name),
                    }
                )
                subjects[f"{exam.id}_{subject_name}"] = subject
                status_text = 'Created' if created else 'Already exists'
                self.stdout.write(self.style.SUCCESS(f'  {status_text}: {subject_name}'))

        # Create questions for subjects
        questions_data = [
            {
                'question_text': 'What is the capital of Nigeria?',
                'question_type': 'MCQ',
                'marks': 1,
                'options': [
                    {'text': 'Lagos', 'is_correct': False},
                    {'text': 'Abuja', 'is_correct': True},
                    {'text': 'Ibadan', 'is_correct': False},
                    {'text': 'Kano', 'is_correct': False},
                ]
            },
            {
                'question_text': 'Solve: 2x + 5 = 15',
                'question_type': 'MCQ',
                'marks': 2,
                'options': [
                    {'text': 'x = 5', 'is_correct': True},
                    {'text': 'x = 10', 'is_correct': False},
                    {'text': 'x = -5', 'is_correct': False},
                    {'text': 'x = 3', 'is_correct': False},
                ]
            },
            {
                'question_text': 'True or False: Water boils at 100°C at sea level',
                'question_type': 'TrueOrFalse',
                'marks': 1,
                'options': [
                    {'text': 'True', 'is_correct': True},
                    {'text': 'False', 'is_correct': False},
                ]
            },
        ]

        question_count = 0
        for exam in exams[:1]:  # Add questions to first exam for now
            exam_subjects = MockExamSubject.objects.filter(mock_exam=exam)
            for subject in exam_subjects:
                for q_data in questions_data[:2]:
                    question, created = MockExamQuestion.objects.get_or_create(
                        subject=subject,
                        question_text=q_data['question_text'],
                        defaults={
                            'question_type': q_data['question_type'],
                            'marks': q_data['marks'],
                        }
                    )
                    if created:
                        # Create options
                        for idx, option_data in enumerate(q_data['options']):
                            MockExamOption.objects.get_or_create(
                                question=question,
                                text=option_data['text'],
                                defaults={
                                    'is_correct': option_data['is_correct'],
                                    'order': idx,
                                }
                            )
                        question_count += 1
                        self.stdout.write(self.style.SUCCESS(f'    Created question: {question.question_text[:50]}...'))

        # Create fees for exams
        fees_data = [
            {'exam': exams[0], 'amount': 2500, 'currency': 'NGN', 'discount_percent': 0},
            {'exam': exams[1], 'amount': 3500, 'currency': 'NGN', 'discount_percent': 10},
            {'exam': exams[2], 'amount': 1500, 'currency': 'NGN', 'discount_percent': 5},
        ]

        for fee_data in fees_data:
            fee, created = MockExamFee.objects.get_or_create(
                mock_exam=fee_data['exam'],
                defaults={
                    'fee_amount': fee_data['amount'],
                    'currency': fee_data['currency'],
                    'discount_percentage': fee_data['discount_percent'],
                }
            )
            status_text = 'Created' if created else 'Already exists'
            self.stdout.write(self.style.SUCCESS(f'{status_text} fee: ₦{fee.amount} for {fee.exam.title}'))

        self.stdout.write(self.style.SUCCESS('✓ Mock exam data population completed successfully!'))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Quick Start:'))
        self.stdout.write('1. Create a superuser: python manage.py createsuperuser')
        self.stdout.write('2. Open admin: http://localhost:8000/admin/')
        self.stdout.write('3. Test APIs: http://localhost:8000/api/mock-exams/')
