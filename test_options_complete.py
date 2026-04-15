#!/usr/bin/env python
"""
Standalone test: Create exam → subject → question → 3 options.
Verifies that option_letter increments correctly (A, B, C).
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lep_backend.settings')
django.setup()

from django.core.management import call_command
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from mock_exams.models import CustomMockExam, MockExamSubject, MockExamQuestion, MockExamOption

print("=" * 80)
print("STEP 1: Run migrations")
print("=" * 80)
try:
    call_command('migrate', 'mock_exams', verbosity=2)
    print("✅ Migrations applied successfully\n")
except Exception as e:
    print(f"⚠️ Migration issue: {e}\n")

print("=" * 80)
print("STEP 2: Setup test data")
print("=" * 80)
User = get_user_model()
admin, created = User.objects.get_or_create(
    username='ci_test_admin',
    defaults={'email': 'ci@example.com', 'is_staff': True, 'is_superuser': True}
)
admin.set_password('pass')
admin.save()
print(f"✅ Admin user: {admin.username}\n")

exam, created = CustomMockExam.objects.get_or_create(
    admin=admin,
    title='CI Test Exam',
    defaults={'description': 'CI test'}
)
print(f"✅ Exam: {exam.title}\n")

subject, created = MockExamSubject.objects.get_or_create(
    mock_exam=exam,
    subject_name='CI Subject'
)
print(f"✅ Subject: {subject.subject_name}\n")

question, created = MockExamQuestion.objects.get_or_create(
    subject=subject,
    question_text='CI Q1',
    defaults={'question_type': 'multiple_choice'}
)
print(f"✅ Question: {question.question_text}\n")

MockExamOption.objects.filter(question=question).delete()
print("✅ Cleaned up old options\n")

print("=" * 80)
print("STEP 3: Test adding 3 options via API")
print("=" * 80)
client = APIClient()
client.force_authenticate(user=admin)

test_options = [
    {'option_text': 'Option A', 'is_correct': True},
    {'option_text': 'Option B', 'is_correct': False},
    {'option_text': 'Option C', 'is_correct': False},
]

for i, opt_data in enumerate(test_options, 1):
    resp = client.post(
        '/api/mock-exams/admin/options/',
        {'question': question.id, **opt_data},
        format='json'
    )
    if resp.status_code == 201:
        letter = resp.data.get('option_letter', '?')
        order = resp.data.get('order', '?')
        print(f"✅ Option {i}: Status {resp.status_code} | Letter '{letter}' | Order {order}")
    else:
        print(f"❌ Option {i}: Status {resp.status_code}")
        print(f"   Error: {resp.data}")

print("\n" + "=" * 80)
print("STEP 4: Verify final DB state")
print("=" * 80)
opts = list(
    MockExamOption.objects.filter(question=question)
    .order_by('order')
    .values('id', 'order', 'option_letter', 'option_text')
)

print(f"\nTotal options created: {len(opts)}\n")
for opt in opts:
    print(f"  Order {opt['order']}: Letter '{opt['option_letter']}' - {opt['option_text']}")

print("\n" + "=" * 80)
if len(opts) == 3 and [o['option_letter'] for o in opts] == ['A', 'B', 'C']:
    print("✅✅✅ SUCCESS! All 3 options created with correct letters (A, B, C)")
    sys.exit(0)
else:
    print("❌ FAILED! Expected 3 options with letters A, B, C")
    sys.exit(1)
