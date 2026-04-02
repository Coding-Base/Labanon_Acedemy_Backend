"""
Verification status checking utilities for tutors and institutions.
Checks ComplianceSubmission, TutorVerificationDocument, VerificationDocument, 
and Institution.verification_status to determine if an account is verified.
"""

from django.utils import timezone
from datetime import datetime


def get_user_verification_status(user):
    """
    Returns verification status for a user.
    
    Returns dict:
    {
        'role': str,
        'is_verified': bool,
        'verification_status': str,  # 'pending', 'approved', 'rejected', 'not_applicable'
        'reason': str,
        'verified_at': datetime or None,
    }
    
    For tutors: Checks ComplianceSubmission and TutorVerificationDocument
    For institutions: Checks Institution.verification_status
    For others: Always verified (no restrictions)
    """
    
    from courses.models import (
        ComplianceSubmission, 
        TutorVerificationDocument, 
        VerificationDocument,
        Institution
    )
    
    result = {
        'role': user.role,
        'is_verified': True,
        'verification_status': 'not_applicable',
        'reason': '',
        'verified_at': None,
    }
    
    # TUTOR VERIFICATION CHECK
    if user.role == 'tutor':
        # Check 1: ComplianceSubmission for tutor
        compliance_submission = ComplianceSubmission.objects.filter(
            tutor=user,
            entity_type='tutor',
            status='approved'
        ).first()
        
        if compliance_submission:
            result.update({
                'is_verified': True,
                'verification_status': 'approved',
                'reason': 'Your account is verified and you can publish courses',
                'verified_at': compliance_submission.approved_at if hasattr(compliance_submission, 'approved_at') else timezone.now()
            })
            return result
        
        # Check 2: TutorVerificationDocument status
        approved_docs = TutorVerificationDocument.objects.filter(
            tutor=user,
            status='approved'
        )
        
        if approved_docs.exists():
            result.update({
                'is_verified': True,
                'verification_status': 'approved',
                'reason': 'Your account is verified and you can publish courses',
                'verified_at': approved_docs.first().reviewed_at or timezone.now()
            })
            return result
        
        # Check for rejected documents
        rejected_docs = TutorVerificationDocument.objects.filter(
            tutor=user,
            status='rejected'
        )
        
        if rejected_docs.exists():
            rejected_doc = rejected_docs.first()
            result.update({
                'is_verified': False,
                'verification_status': 'rejected',
                'reason': rejected_doc.review_notes or 'Your documents were rejected. Please resubmit with corrections.'
            })
            return result
        
        # Otherwise pending
        result.update({
            'is_verified': False,
            'verification_status': 'pending',
            'reason': 'Your account is pending verification. Complete your compliance submission to publish courses.'
        })
        return result
    
    # INSTITUTION VERIFICATION CHECK
    elif user.role == 'institution':
        # Check Institution.verification_status
        institution = Institution.objects.filter(owner=user).first()
        
        if institution:
            if institution.verification_status == 'approved':
                result.update({
                    'is_verified': True,
                    'verification_status': 'approved',
                    'reason': 'Your institution is verified and you can publish courses',
                    'verified_at': institution.verified_at
                })
                return result
            
            elif institution.verification_status == 'rejected':
                result.update({
                    'is_verified': False,
                    'verification_status': 'rejected',
                    'reason': institution.rejection_reason or 'Your institution was rejected for verification. Please contact support.'
                })
                return result
            
            # Otherwise pending
            result.update({
                'is_verified': False,
                'verification_status': 'pending',
                'reason': 'Your institution is pending verification. Complete your compliance submission to publish courses.'
            })
            return result
        
        # No institution found (shouldn't happen)
        result.update({
            'is_verified': False,
            'verification_status': 'pending',
            'reason': 'Your institution information was not found. Please contact support.'
        })
        return result
    
    # OTHER ROLES (student, researcher, admin, etc.) - always verified
    else:
        result.update({
            'is_verified': True,
            'verification_status': 'not_applicable',
            'reason': 'Verification not required for your account type'
        })
        return result
