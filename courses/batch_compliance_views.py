"""
Batch Compliance Submission Views
Handles folder-based submission system where multiple documents are grouped together
"""
import logging
import uuid
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

from .models import (
    Institution, ComplianceSubmission, VerificationDocument, 
    TutorVerificationDocument
)
from .compliance_serializers import ComplianceSubmissionSerializer
from users.models import User

logger = logging.getLogger(__name__)


def send_verification_email(user, subject, template_content):
    """Helper function to send verification-related emails."""
    try:
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f9fafb; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; }}
                .header {{ background-color: #16a34a; padding: 20px; text-align: center; color: #ffffff; }}
                .header h2 {{ margin: 0; font-size: 24px; font-weight: 600; }}
                .content {{ padding: 30px; color: #374151; line-height: 1.6; }}
                .footer {{ background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
                .btn {{ display: inline-block; padding: 10px 20px; background-color: #16a34a; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 10px; }}
                .alert-box {{ background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; border-radius: 4px; margin: 15px 0; }}
                .success-box {{ background-color: #d1fae5; border-left: 4px solid #10b981; padding: 15px; border-radius: 4px; margin: 15px 0; }}
                .error-box {{ background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; border-radius: 4px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{subject}</h2>
                </div>
                <div class="content">
                    {template_content}
                </div>
                <div class="footer">
                    &copy; {timezone.now().year} LightHub Academy. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """
        
        send_mail(
            subject=subject,
            message="",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False


class ComplianceBatchSubmissionView(APIView):
    """
    Submit multiple documents as a single compliance folder.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Submit a batch of compliance documents.
        
        Expected payload:
        {
            "entity_type": "tutor" or "institution",
            "entity_id": id (optional for tutor, required for institution),
            "contact_name": "Name",
            "contact_email": "email@example.com",
            "contact_phone": "+234...",
            "comments": "Optional comments",
            "documents": [
                {
                    "document_type": "id_card",
                    "document_name": "My ID",
                    "document_link": "https://drive.google.com/..."
                },
                ...
            ]
        }
        """
        try:
            entity_type = request.data.get('entity_type')
            entity_id = request.data.get('entity_id')
            contact_name = request.data.get('contact_name', '')
            contact_email = request.data.get('contact_email', '')
            contact_phone = request.data.get('contact_phone', '')
            comments = request.data.get('comments', '')
            documents = request.data.get('documents', [])
            
            # Validate required fields
            if entity_type not in ['tutor', 'institution']:
                return Response(
                    {'detail': 'entity_type must be "tutor" or "institution"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not documents or len(documents) == 0:
                return Response(
                    {'detail': 'At least one document must be provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not contact_name or not contact_email:
                return Response(
                    {'detail': 'contact_name and contact_email are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate and get entity
            if entity_type == 'tutor':
                entity = request.user  # Current user must be the tutor
                tutor_entity = request.user
                institution_entity = None
            else:  # institution
                try:
                    institution_entity = Institution.objects.get(id=entity_id, owner=request.user)
                    tutor_entity = None
                except Institution.DoesNotExist:
                    return Response(
                        {'detail': 'Institution not found or you do not have permission'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Create compliance submission folder
            with transaction.atomic():
                submission_id = f"{entity_type.upper()}{uuid.uuid4().hex[:12].upper()}"
                
                submission = ComplianceSubmission.objects.create(
                    submission_id=submission_id,
                    entity_type=entity_type,
                    tutor=tutor_entity,
                    institution=institution_entity,
                    contact_name=contact_name,
                    contact_email=contact_email,
                    contact_phone=contact_phone,
                    comments=comments,
                    status=ComplianceSubmission.STATUS_PENDING
                )
                
                # Create documents and link them to the submission
                for idx, doc_data in enumerate(documents):
                    document_type = doc_data.get('document_type')
                    document_name = doc_data.get('document_name')
                    document_link = doc_data.get('document_link')
                    document_file = doc_data.get('document_file')
                    
                    # Validate document
                    if not document_type or not document_name:
                        return Response(
                            {'detail': f'Document {idx + 1} missing type or name'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    if not document_link and not document_file:
                        return Response(
                            {'detail': f'Document {idx + 1} must have either link or file'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Create document linked to submission
                    if entity_type == 'tutor':
                        TutorVerificationDocument.objects.create(
                            tutor=tutor_entity,
                            submission=submission,
                            document_type=document_type,
                            document_name=document_name,
                            document_file=document_link or document_file,
                            status=TutorVerificationDocument.STATUS_PENDING
                        )
                    else:  # institution
                        VerificationDocument.objects.create(
                            institution=institution_entity,
                            submission=submission,
                            document_type=document_type,
                            document_name=document_name,
                            document_file=document_link or document_file,
                            status=VerificationDocument.STATUS_PENDING
                        )
                
                # Notify admin about new submission
                admin_users = User.objects.filter(is_staff=True, is_superuser=True)
                entity_name = tutor_entity.username if entity_type == 'tutor' else institution_entity.name
                
                for admin in admin_users:
                    try:
                        email_content = f"""
                        <p>Hello Admin,</p>
                        <p>A new compliance submission folder has been submitted.</p>
                        <div class="alert-box">
                            <p><strong>Submission ID:</strong> {submission.submission_id}</p>
                            <p><strong>Entity:</strong> {entity_name}</p>
                            <p><strong>Type:</strong> {entity_type.upper()}</p>
                            <p><strong>Contact:</strong> {contact_name} ({contact_email})</p>
                            <p><strong>Documents:</strong> {len(documents)} file(s)</p>
                            <p><strong>Submitted At:</strong> {submission.submitted_at.strftime('%d %b %Y, %I:%M %p')}</p>
                        </div>
                        <p>Please log in to the verification dashboard to review this submission folder.</p>
                        <center><a href="{settings.FRONTEND_URL}/admin/verification" class="btn">Review Submission</a></center>
                        """
                        send_verification_email(
                            admin,
                            f"New Compliance Submission: {entity_name}",
                            email_content
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin: {str(e)}")
            
            return Response(
                {
                    'detail': 'Compliance submission folder created successfully',
                    'submission_id': submission.submission_id,
                    'id': submission.id
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error submitting compliance batch: {str(e)}", exc_info=True)
            return Response(
                {'detail': f'Error submitting compliance folder: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ComplianceFolderDashboardView(APIView):
    """
    Dashboard view for tutor/institution to see their compliance submissions.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all compliance submissions for the current user."""
        try:
            user = request.user
            
            # Get tutor submissions
            if user.is_tutor or True:  # Everyone can be a tutor
                tutor_submissions = ComplianceSubmission.objects.filter(
                    tutor=user,
                    entity_type=ComplianceSubmission.ENTITY_TYPE_TUTOR
                ).order_by('-submitted_at')
                
                data = ComplianceSubmissionSerializer(tutor_submissions, many=True).data
                
                # Add institution submissions if user owns an institution
                institutions = Institution.objects.filter(owner=user)
                for institution in institutions:
                    inst_submissions = ComplianceSubmission.objects.filter(
                        institution=institution,
                        entity_type=ComplianceSubmission.ENTITY_TYPE_INSTITUTION
                    ).order_by('-submitted_at')
                    data.extend(ComplianceSubmissionSerializer(inst_submissions, many=True).data)
                
                return Response(data, status=status.HTTP_200_OK)
            
            return Response([], status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error loading compliance folders: {str(e)}")
            return Response(
                {'detail': 'Error loading submissions'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VerificationFolderAdminDashboardView(APIView):
    """
    Admin dashboard view for reviewing compliance submission folders.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all compliance submission folders for admin review."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            status_filter = request.query_params.get('status', 'pending')
            
            if status_filter == 'all':
                submissions = ComplianceSubmission.objects.order_by('-submitted_at')
            else:
                submissions = ComplianceSubmission.objects.filter(
                    status=status_filter
                ).order_by('-submitted_at')
            
            data = ComplianceSubmissionSerializer(submissions, many=True).data
            
            return Response({
                'submissions': data,
                'stats': {
                    'pending': ComplianceSubmission.objects.filter(
                        status=ComplianceSubmission.STATUS_PENDING
                    ).count(),
                    'approved': ComplianceSubmission.objects.filter(
                        status=ComplianceSubmission.STATUS_APPROVED
                    ).count(),
                    'rejected': ComplianceSubmission.objects.filter(
                        status=ComplianceSubmission.STATUS_REJECTED
                    ).count(),
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error loading admin dashboard: {str(e)}")
            return Response(
                {'detail': 'Error loading dashboard'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ApproveComplianceFolderView(APIView):
    """Approve a compliance submission folder."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, submission_id):
        """Approve an entire compliance submission folder."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            reason = request.data.get('reason', '')
            
            submission = ComplianceSubmission.objects.get(id=submission_id)
            
            with transaction.atomic():
                # Update all documents in the submission
                submission.get_all_documents().update(
                    status='approved',
                    reviewed_by=request.user,
                    reviewed_at=timezone.now()
                )
                
                # Update submission
                submission.status = ComplianceSubmission.STATUS_APPROVED
                submission.reviewed_by = request.user
                submission.reviewed_at = timezone.now()
                submission.review_notes = reason
                submission.save()
                
                # Update entity verification status
                if submission.entity_type == ComplianceSubmission.ENTITY_TYPE_TUTOR:
                    user = submission.tutor
                    # Mark user as verified tutor (would need additional field in User model)
                    if hasattr(user, 'is_verified_tutor'):
                        user.is_verified_tutor = True
                        user.save()
                    
                    email_content = f"""
                    <p>Hello {user.first_name or user.username},</p>
                    <p><strong>Congratulations!</strong> Your compliance verification has been approved.</p>
                    <div class="success-box">
                        <p>All {submission.get_all_documents().count()} documents in your submission have been verified and approved.</p>
                        <p>You can now:</p>
                        <ul>
                            <li>Publish courses</li>
                            <li>Receive payments for enrollments</li>
                            <li>Access all platform features</li>
                        </ul>
                    </div>
                    """
                    recipient = user
                
                else:  # institution
                    institution = submission.institution
                    institution.verification_status = Institution.VERIFICATION_APPROVED
                    institution.verified_by = request.user
                    institution.verified_at = timezone.now()
                    institution.save()
                    
                    email_content = f"""
                    <p>Hello {institution.owner.first_name or institution.owner.username},</p>
                    <p><strong>Congratulations!</strong> Your institution <strong>{institution.name}</strong> has been verified and approved.</p>
                    <div class="success-box">
                        <p>All {submission.get_all_documents().count()} documents in your submission have been verified and approved.</p>
                        <p>Your institution is now fully active and can:</p>
                        <ul>
                            <li>Publish courses to the marketplace</li>
                            <li>Receive payments for course enrollments</li>
                            <li>Access all institutional features</li>
                        </ul>
                    </div>
                    """
                    recipient = institution.owner
                
                # Send approval email
                send_verification_email(
                    recipient,
                    "Compliance Verification Approved ✓",
                    email_content
                )
            
            return Response(
                {'detail': 'Compliance submission approved successfully'},
                status=status.HTTP_200_OK
            )
        
        except ComplianceSubmission.DoesNotExist:
            return Response(
                {'detail': 'Submission not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error approving submission: {str(e)}")
            return Response(
                {'detail': 'Error approving submission'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RejectComplianceFolderView(APIView):
    """Reject a compliance submission folder."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, submission_id):
        """Reject an entire compliance submission folder."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            reason = request.data.get('reason', 'Please resubmit with corrections')
            
            if not reason:
                return Response(
                    {'detail': 'Rejection reason is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            submission = ComplianceSubmission.objects.get(id=submission_id)
            
            with transaction.atomic():
                # Update all documents in the submission
                submission.get_all_documents().update(
                    status='rejected',
                    reviewed_by=request.user,
                    reviewed_at=timezone.now(),
                    review_notes=reason
                )
                
                # Update submission
                submission.status = ComplianceSubmission.STATUS_REJECTED
                submission.reviewed_by = request.user
                submission.reviewed_at = timezone.now()
                submission.review_notes = reason
                submission.save()
                
                # Send rejection email
                if submission.entity_type == ComplianceSubmission.ENTITY_TYPE_TUTOR:
                    recipient = submission.tutor
                    entity_name = recipient.username
                else:
                    recipient = submission.institution.owner
                    entity_name = submission.institution.name
                
                email_content = f"""
                <p>Hello,</p>
                <p>Thank you for submitting your compliance verification documents. Unfortunately, we are unable to approve your submission at this time.</p>
                <div class="error-box">
                    <p><strong>Reason for Rejection:</strong></p>
                    <p>{reason}</p>
                </div>
                <p>Please review the feedback above and resubmit your documents with the necessary corrections. You can submit an updated compliance folder from your dashboard.</p>
                <p>If you have questions, please contact our support team.</p>
                """
                
                send_verification_email(
                    recipient,
                    "Compliance Verification - Action Required",
                    email_content
                )
            
            return Response(
                {'detail': 'Compliance submission rejected successfully'},
                status=status.HTTP_200_OK
            )
        
        except ComplianceSubmission.DoesNotExist:
            return Response(
                {'detail': 'Submission not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error rejecting submission: {str(e)}")
            return Response(
                {'detail': 'Error rejecting submission'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
