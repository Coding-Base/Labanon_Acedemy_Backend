#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lep_backend.settings')
django.setup()

from courses.models import ActivationFee

print("=== ACTIVATION FEES CONFIGURED ===\n")

# Check for exam fees
exam_fees = ActivationFee.objects.filter(type='exam')
print(f"Global Exam Fees: {exam_fees.count()}")
for fee in exam_fees:
    print(f"  - {fee.currency} {fee.amount}")

# Check for specific exam fees
specific_exam_fees = ActivationFee.objects.exclude(exam_identifier__isnull=True).exclude(exam_identifier='')
print(f"\nExam-Specific Fees: {specific_exam_fees.count()}")
for fee in specific_exam_fees:
    print(f"  - {fee.exam_identifier}: {fee.currency} {fee.amount}")

# Check for interview fees
interview_fees = ActivationFee.objects.filter(type='interview')
print(f"\nInterview Fees: {interview_fees.count()}")
for fee in interview_fees:
    print(f"  - Subject {fee.subject_id}: {fee.currency} {fee.amount}")

# Check for account fees
account_fees = ActivationFee.objects.filter(type='account')
print(f"\nAccount Activation Fees: {account_fees.count()}")
for fee in account_fees:
    print(f"  - {fee.account_role}: {fee.currency} {fee.amount}")

print(f"\n=== TOTAL: {ActivationFee.objects.count()} fees configured ===")

if ActivationFee.objects.count() == 0:
    print("\n⚠️  NO FEES CONFIGURED! Students cannot unlock exams.")
    print("\nFix: Add activation fees in Admin Dashboard:")
    print("  1. Go to Master Admin Dashboard")
    print("  2. Find 'Payment Settings'")
    print("  3. Add a global fee for exam type")
