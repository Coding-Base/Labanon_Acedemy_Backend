"""
Verification and Compliance Views for Institutions and Tutors
"""
import logging
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction

from .models import (
    Institution, VerificationDocument, TutorVerificationDocument, 
    LegalDocument, Course, ComplianceSubmission
)
from .serializers import (
    VerificationDocumentSerializer, TutorVerificationDocumentSerializer,
    LegalDocumentSerializer, InstitutionVerificationSerializer
)
from users.models import User

logger = logging.getLogger(__name__)


def send_verification_email(user, subject, template_content, institution_name=None):
    """
    Helper function to send verification-related emails.
    """
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
            message="",  # Plain text fallback
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Verification email sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False


# ==================== INSTITUTION VERIFICATION ====================

class InstitutionComplianceFormView(APIView):
    """
    Institution dashboard view for submitting verification documents.
    GET: List submitted documents and their status
    POST: Submit a new verification document
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all verification documents for the institution."""
        try:
            # Get institutions owned by this user
            institutions = Institution.objects.filter(owner=request.user)
            
            if not institutions.exists():
                return Response(
                    {'detail': 'You do not own any institution'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            documents_data = []
            for institution in institutions:
                documents = VerificationDocument.objects.filter(
                    institution=institution
                ).order_by('-submitted_at')
                
                documents_data.append({
                    'institution_id': institution.id,
                    'institution_name': institution.name,
                    'verification_status': institution.verification_status,
                    'verified_at': institution.verified_at,
                    'rejection_reason': institution.rejection_reason,
                    'documents': VerificationDocumentSerializer(documents, many=True).data
                })
            
            return Response(documents_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error retrieving compliance documents: {str(e)}")
            return Response(
                {'detail': 'Error retrieving documents'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Submit a new verification document (accepts either file or Google Drive link)."""
        try:
            institution_id = request.data.get('institution_id')
            document_type = request.data.get('document_type')
            document_file = request.data.get('document_file')
            document_link = request.data.get('document_link')  # Google Drive link
            document_name = request.data.get('document_name')
            
            # Validate required fields - must have either file or link
            if not all([institution_id, document_type, document_name]):
                return Response(
                    {'detail': 'Missing required fields: institution_id, document_type, document_name'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not document_file and not document_link:
                return Response(
                    {'detail': 'Must provide either document_file or document_link'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify institution ownership
            try:
                institution = Institution.objects.get(id=institution_id, owner=request.user)
            except Institution.DoesNotExist:
                return Response(
                    {'detail': 'Institution not found or you do not have permission'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Create document - save either file or link
            doc = VerificationDocument.objects.create(
                institution=institution,
                document_type=document_type,
                document_file=document_file or document_link,  # Save file or link
                document_name=document_name,
                status=VerificationDocument.STATUS_PENDING
            )
            
            # Send notification to admin
            admin_users = request.user.__class__.objects.filter(is_staff=True, is_superuser=True)
            for admin in admin_users:
                try:
                    email_content = f"""
                    <p>Hello Admin,</p>
                    <p>A new verification document has been submitted by <strong>{institution.name}</strong>.</p>
                    <div class="alert-box">
                        <p><strong>Institution:</strong> {institution.name}</p>
                        <p><strong>Owner Email:</strong> {institution.owner.email}</p>
                        <p><strong>Phone:</strong> {institution.phone or 'Not provided'}</p>
                        <p><strong>Document Type:</strong> {doc.get_document_type_display()}</p>
                        <p><strong>Submitted At:</strong> {doc.submitted_at.strftime('%d %b %Y, %I:%M %p')}</p>
                    </div>
                    <p>Please log in to the admin dashboard to review and approve/reject this document.</p>
                    <center><a href="{settings.FRONTEND_URL}/admin/compliance-verification" class="btn">Review Documents</a></center>
                    """
                    send_verification_email(
                        admin,
                        f"New Verification Document: {institution.name}",
                        email_content
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin about document submission: {str(e)}")
            
            return Response(
                {
                    'detail': 'Document submitted successfully. Your documents are under review.',
                    'document_id': doc.id
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error submitting verification document: {str(e)}")
            return Response(
                {'detail': 'Error submitting document'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== ADMIN VERIFICATION DASHBOARD ====================

class AdminComplianceDashboardView(APIView):
    """
    Admin dashboard view for reviewing institution and tutor verification documents.
    GET: List pending documents for review
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all pending verification documents."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Get pending institution documents
            pending_institution_docs = VerificationDocument.objects.filter(
                status=VerificationDocument.STATUS_PENDING
            ).select_related('institution', 'institution__owner').order_by('-submitted_at')
            
            # Get pending tutor documents
            pending_tutor_docs = TutorVerificationDocument.objects.filter(
                status=TutorVerificationDocument.STATUS_PENDING
            ).select_related('tutor').order_by('-submitted_at')
            
            # Get approved and rejected for reference
            approved_institution_docs = VerificationDocument.objects.filter(
                status=VerificationDocument.STATUS_APPROVED
            ).order_by('-reviewed_at')[:10]
            
            rejected_institution_docs = VerificationDocument.objects.filter(
                status=VerificationDocument.STATUS_REJECTED
            ).order_by('-reviewed_at')[:10]
            
            return Response({
                'pending_institution_documents': VerificationDocumentSerializer(
                    pending_institution_docs, many=True
                ).data,
                'pending_tutor_documents': TutorVerificationDocumentSerializer(
                    pending_tutor_docs, many=True
                ).data,
                'recent_approved_documents': VerificationDocumentSerializer(
                    approved_institution_docs, many=True
                ).data,
                'recent_rejected_documents': VerificationDocumentSerializer(
                    rejected_institution_docs, many=True
                ).data,
                'stats': {
                    'pending_institution': pending_institution_docs.count(),
                    'pending_tutor': pending_tutor_docs.count(),
                    'total_institutions': Institution.objects.count(),
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error retrieving compliance dashboard: {str(e)}")
            return Response(
                {'detail': 'Error retrieving dashboard data'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ApproveInstitutionVerificationView(APIView):
    """
    Admin endpoint to approve an institution's verification.
    Approves all documents and marks institution as verified.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Approve institution verification."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            institution_id = request.data.get('institution_id')
            custom_share_percentage = request.data.get('custom_share_percentage')
            
            if not institution_id:
                return Response(
                    {'detail': 'institution_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                institution = Institution.objects.get(id=institution_id)
                
                # Approve all pending documents
                docs = VerificationDocument.objects.filter(
                    institution=institution,
                    status=VerificationDocument.STATUS_PENDING
                )
                
                docs.update(
                    status=VerificationDocument.STATUS_APPROVED,
                    reviewed_by=request.user,
                    reviewed_at=timezone.now()
                )
                
                # Update institution verification status
                institution.verification_status = Institution.VERIFICATION_APPROVED
                institution.verified_by = request.user
                institution.verified_at = timezone.now()
                
                # Set custom share percentage if provided
                if custom_share_percentage:
                    try:
                        institution.custom_share_percentage = Decimal(str(custom_share_percentage))
                    except:
                        pass
                
                institution.save()
                
                # Send approval email to institution owner
                email_content = f"""
                <p>Hello {institution.owner.first_name or institution.owner.username},</p>
                <p><strong>Congratulations!</strong> Your institution <strong>{institution.name}</strong> has been verified and approved.</p>
                <div class="success-box">
                    <p><strong>Your account is now fully active!</strong></p>
                    <p>You can now:</p>
                    <ul>
                        <li>Publish courses to the marketplace</li>
                        <li>Receive payments for course enrollments</li>
                        <li>Access all institutional features</li>
                    </ul>
                </div>
                <p>Thank you for being part of our community. If you have any questions, please contact our support team.</p>
                <center><a href="{settings.FRONTEND_URL}/institution/dashboard" class="btn">Go to Dashboard</a></center>
                """
                
                send_verification_email(
                    institution.owner,
                    "Institution Verification Approved ✓",
                    email_content
                )
            
            return Response(
                {
                    'detail': 'Institution approved successfully',
                    'institution': InstitutionVerificationSerializer(institution).data
                },
                status=status.HTTP_200_OK
            )
        
        except Institution.DoesNotExist:
            return Response(
                {'detail': 'Institution not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error approving institution: {str(e)}")
            return Response(
                {'detail': 'Error approving institution'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RejectInstitutionVerificationView(APIView):
    """
    Admin endpoint to reject an institution's verification.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Reject institution verification."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            institution_id = request.data.get('institution_id')
            rejection_reason = request.data.get('rejection_reason')
            
            if not institution_id or not rejection_reason:
                return Response(
                    {'detail': 'institution_id and rejection_reason are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                institution = Institution.objects.get(id=institution_id)
                
                # Mark all pending documents as rejected
                docs = VerificationDocument.objects.filter(
                    institution=institution,
                    status=VerificationDocument.STATUS_PENDING
                )
                
                docs.update(
                    status=VerificationDocument.STATUS_REJECTED,
                    reviewed_by=request.user,
                    reviewed_at=timezone.now(),
                    review_notes=rejection_reason
                )
                
                # Update institution verification status
                institution.verification_status = Institution.VERIFICATION_REJECTED
                institution.verified_by = request.user
                institution.verified_at = timezone.now()
                institution.rejection_reason = rejection_reason
                institution.save()
                
                # Send rejection email to institution owner
                email_content = f"""
                <p>Hello {institution.owner.first_name or institution.owner.username},</p>
                <p>Thank you for submitting your institution verification documents. Unfortunately, we were unable to approve your application at this time.</p>
                <div class="error-box">
                    <p><strong>Reason for Rejection:</strong></p>
                    <p>{rejection_reason}</p>
                </div>
                <p>Please review the feedback above and resubmit your documents with the necessary corrections. You can submit updated documents from your institution dashboard.</p>
                <p>If you have any questions, please contact our support team.</p>
                <center><a href="{settings.FRONTEND_URL}/institution/dashboard" class="btn">Submit Updated Documents</a></center>
                """
                
                send_verification_email(
                    institution.owner,
                    "Institution Verification Update - Action Required",
                    email_content
                )
            
            return Response(
                {
                    'detail': 'Institution verification rejected',
                    'institution': InstitutionVerificationSerializer(institution).data
                },
                status=status.HTTP_200_OK
            )
        
        except Institution.DoesNotExist:
            return Response(
                {'detail': 'Institution not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error rejecting institution: {str(e)}")
            return Response(
                {'detail': 'Error rejecting institution'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== LEGAL DOCUMENTS ====================

class LegalDocumentListView(APIView):
    """
    Public endpoint for users to download legal documents.
    GET: List all active legal documents
    """
    permission_classes = [AllowAny]

    def get(self, request):
        """List all active legal documents."""
        try:
            documents = LegalDocument.objects.filter(is_active=True).order_by('-updated_at')
            return Response(
                LegalDocumentSerializer(documents, many=True).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error retrieving legal documents: {str(e)}")
            return Response(
                {'detail': 'Error retrieving documents'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminLegalDocumentView(APIView):
    """
    Admin endpoint for managing legal documents.
    GET: List all legal documents (including inactive)
    POST: Create/Update legal document
    DELETE: Delete legal document
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all legal documents (admin view)."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            documents = LegalDocument.objects.all().order_by('-updated_at')
            return Response(
                LegalDocumentSerializer(documents, many=True).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error retrieving legal documents: {str(e)}")
            return Response(
                {'detail': 'Error retrieving documents'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Create or update a legal document (admin only)."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            document_id = request.data.get('id')
            document_type = request.data.get('document_type')
            title = request.data.get('title')
            description = request.data.get('description')
            document_file = request.data.get('document_file')
            version = request.data.get('version', '1.0')
            is_active = request.data.get('is_active', True)
            
            if not all([document_type, title, document_file]):
                return Response(
                    {'detail': 'Missing required fields: document_type, title, document_file'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if document_id:
                # Update existing document
                doc = LegalDocument.objects.get(id=document_id)
            else:
                # Create new document
                doc = LegalDocument()
            
            doc.document_type = document_type
            doc.title = title
            doc.description = description
            doc.document_file = document_file
            doc.version = version
            doc.is_active = is_active
            doc.updated_by = request.user
            doc.save()
            
            return Response(
                LegalDocumentSerializer(doc).data,
                status=status.HTTP_201_CREATED if not document_id else status.HTTP_200_OK
            )
        
        except LegalDocument.DoesNotExist:
            return Response(
                {'detail': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error saving legal document: {str(e)}")
            return Response(
                {'detail': 'Error saving document'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request):
        """Delete a legal document (admin only)."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            document_id = request.data.get('id')
            if not document_id:
                return Response(
                    {'detail': 'id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            doc = LegalDocument.objects.get(id=document_id)
            doc.delete()
            
            return Response(
                {'detail': 'Document deleted successfully'},
                status=status.HTTP_200_OK
            )
        
        except LegalDocument.DoesNotExist:
            return Response(
                {'detail': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error deleting legal document: {str(e)}")
            return Response(
                {'detail': 'Error deleting document'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== TUTOR VERIFICATION ====================

class TutorComplianceFormView(APIView):
    """
    Tutor endpoint for submitting verification documents.
    GET: List submitted documents
    POST: Submit a new verification document
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all tutor verification documents."""
        try:
            documents = TutorVerificationDocument.objects.filter(
                tutor=request.user
            ).order_by('-submitted_at')
            
            return Response({
                'verification_status': getattr(request.user, 'verification_status', 'pending'),
                'documents': TutorVerificationDocumentSerializer(documents, many=True).data
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error retrieving tutor documents: {str(e)}")
            return Response(
                {'detail': 'Error retrieving documents'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Submit a new tutor verification document (accepts either file or Google Drive link)."""
        try:
            document_type = request.data.get('document_type')
            document_file = request.data.get('document_file')
            document_link = request.data.get('document_link')  # Google Drive link
            document_name = request.data.get('document_name')
            
            # Validate required fields - must have either file or link
            if not all([document_type, document_name]):
                return Response(
                    {'detail': 'Missing required fields: document_type, document_name'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not document_file and not document_link:
                return Response(
                    {'detail': 'Must provide either document_file or document_link'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create document - save either file or link
            doc = TutorVerificationDocument.objects.create(
                tutor=request.user,
                document_type=document_type,
                document_file=document_file or document_link,  # Save file or link
                document_name=document_name,
                status=TutorVerificationDocument.STATUS_PENDING
            )
            
            # Notify admin
            admin_users = request.user.__class__.objects.filter(is_staff=True, is_superuser=True)
            for admin in admin_users:
                try:
                    email_content = f"""
                    <p>Hello Admin,</p>
                    <p>A new tutor verification document has been submitted by <strong>{request.user.username}</strong>.</p>
                    <div class="alert-box">
                        <p><strong>Tutor:</strong> {request.user.get_full_name() or request.user.username}</p>
                        <p><strong>Email:</strong> {request.user.email}</p>
                        <p><strong>Document Type:</strong> {doc.get_document_type_display()}</p>
                        <p><strong>Submitted At:</strong> {doc.submitted_at.strftime('%d %b %Y, %I:%M %p')}</p>
                    </div>
                    <p>Please log in to review this document.</p>
                    """
                    send_verification_email(admin, f"New Tutor Verification Document", email_content)
                except Exception as e:
                    logger.error(f"Failed to notify admin: {str(e)}")
            
            return Response(
                {
                    'detail': 'Document submitted successfully',
                    'document_id': doc.id
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error submitting tutor document: {str(e)}")
            return Response(
                {'detail': 'Error submitting document'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== UNIFIED VERIFICATION APPROVAL/REJECTION ====================

class UnifiedVerificationApprovalView(APIView):
    """
    Unified admin endpoint to approve both institution and tutor verification.
    POST: Approve a submission (institution or tutor)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        """Approve verification submission (institution or tutor)."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            entity_type = request.data.get('entity_type')
            reason = request.data.get('reason', '')
            custom_share_percentage = request.data.get('custom_share_percentage')
            
            with transaction.atomic():
                if entity_type == 'institution':
                    # Approve institution
                    institution = Institution.objects.get(id=submission_id)
                    
                    # Approve all pending documents
                    docs = VerificationDocument.objects.filter(
                        institution=institution,
                        status=VerificationDocument.STATUS_PENDING
                    )
                    
                    docs.update(
                        status=VerificationDocument.STATUS_APPROVED,
                        reviewed_by=request.user,
                        reviewed_at=timezone.now()
                    )
                    
                    # Update institution verification status
                    institution.verification_status = Institution.VERIFICATION_APPROVED
                    institution.verified_by = request.user
                    institution.verified_at = timezone.now()
                    
                    if custom_share_percentage:
                        try:
                            institution.custom_share_percentage = Decimal(str(custom_share_percentage))
                        except:
                            pass
                    
                    institution.save()
                    
                    # Send approval email
                    email_content = f"""
                    <p>Hello {institution.owner.first_name or institution.owner.username},</p>
                    <p><strong>Congratulations!</strong> Your institution <strong>{institution.name}</strong> has been verified and approved.</p>
                    <div class="success-box">
                        <p><strong>Your account is now fully active!</strong></p>
                        <p>You can now:</p>
                        <ul>
                            <li>Publish courses to the marketplace</li>
                            <li>Receive payments for course enrollments</li>
                            <li>Access all institutional features</li>
                        </ul>
                    </div>
                    <p>Thank you for being part of our community. If you have any questions, please contact our support team.</p>
                    <center><a href="{settings.FRONTEND_URL}/institution/dashboard" class="btn">Go to Dashboard</a></center>
                    """
                    
                    send_verification_email(
                        institution.owner,
                        "Institution Verification Approved ✓",
                        email_content
                    )
                    
                    return Response(
                        {
                            'detail': 'Institution approved successfully',
                            'entity_type': 'institution',
                            'id': institution.id
                        },
                        status=status.HTTP_200_OK
                    )
                
                elif entity_type == 'tutor':
                    # Approve tutor
                    tutor = User.objects.get(id=submission_id)
                    
                    # Approve all pending documents
                    docs = TutorVerificationDocument.objects.filter(
                        tutor=tutor,
                        status=TutorVerificationDocument.STATUS_PENDING
                    )
                    
                    docs.update(
                        status=TutorVerificationDocument.STATUS_APPROVED,
                        reviewed_by=request.user,
                        reviewed_at=timezone.now()
                    )
                    
                    # Send approval email
                    email_content = f"""
                    <p>Hello {tutor.first_name or tutor.username},</p>
                    <p><strong>Congratulations!</strong> Your tutor verification has been approved.</p>
                    <div class="success-box">
                        <p><strong>Your account is now fully verified!</strong></p>
                        <p>You can now:</p>
                        <ul>
                            <li>Create and publish courses</li>
                            <li>Receive payments from course enrollments</li>
                            <li>Access all tutor features</li>
                        </ul>
                    </div>
                    <p>Thank you for being part of our community. If you have any questions, please contact our support team.</p>
                    <center><a href="{settings.FRONTEND_URL}/tutor/dashboard" class="btn">Go to Dashboard</a></center>
                    """
                    
                    send_verification_email(
                        tutor,
                        "Tutor Verification Approved ✓",
                        email_content
                    )
                    
                    return Response(
                        {
                            'detail': 'Tutor approved successfully',
                            'entity_type': 'tutor',
                            'id': tutor.id
                        },
                        status=status.HTTP_200_OK
                    )
                
                else:
                    return Response(
                        {'detail': 'Invalid entity_type. Must be "institution" or "tutor"'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        except Institution.DoesNotExist:
            return Response(
                {'detail': 'Institution not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except User.DoesNotExist:
            return Response(
                {'detail': 'Tutor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error approving verification: {str(e)}")
            return Response(
                {'detail': 'Error approving verification'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UnifiedVerificationRejectionView(APIView):
    """
    Unified admin endpoint to reject both institution and tutor verification.
    POST: Reject a submission (institution or tutor)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        """Reject verification submission (institution or tutor)."""
        if not request.user.is_staff:
            return Response(
                {'detail': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            entity_type = request.data.get('entity_type')
            reason = request.data.get('reason', '')
            
            if not reason:
                return Response(
                    {'detail': 'rejection_reason is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                if entity_type == 'institution':
                    # Reject institution
                    institution = Institution.objects.get(id=submission_id)
                    
                    # Mark all pending documents as rejected
                    docs = VerificationDocument.objects.filter(
                        institution=institution,
                        status=VerificationDocument.STATUS_PENDING
                    )
                    
                    docs.update(
                        status=VerificationDocument.STATUS_REJECTED,
                        reviewed_by=request.user,
                        reviewed_at=timezone.now(),
                        review_notes=reason
                    )
                    
                    # Update institution verification status
                    institution.verification_status = Institution.VERIFICATION_REJECTED
                    institution.verified_by = request.user
                    institution.verified_at = timezone.now()
                    institution.rejection_reason = reason
                    institution.save()
                    
                    # Send rejection email
                    email_content = f"""
                    <p>Hello {institution.owner.first_name or institution.owner.username},</p>
                    <p>Thank you for submitting your institution verification documents. Unfortunately, we were unable to approve your application at this time.</p>
                    <div class="error-box">
                        <p><strong>Reason for Rejection:</strong></p>
                        <p>{reason}</p>
                    </div>
                    <p>Please review the feedback above and resubmit your documents with the necessary corrections. You can submit updated documents from your institution dashboard.</p>
                    <p>If you have any questions, please contact our support team.</p>
                    <center><a href="{settings.FRONTEND_URL}/institution/dashboard" class="btn">Submit Updated Documents</a></center>
                    """
                    
                    send_verification_email(
                        institution.owner,
                        "Institution Verification Update - Action Required",
                        email_content
                    )
                    
                    return Response(
                        {
                            'detail': 'Institution verification rejected',
                            'entity_type': 'institution',
                            'id': institution.id
                        },
                        status=status.HTTP_200_OK
                    )
                
                elif entity_type == 'tutor':
                    # Reject tutor
                    tutor = User.objects.get(id=submission_id)
                    
                    # Mark all pending documents as rejected
                    docs = TutorVerificationDocument.objects.filter(
                        tutor=tutor,
                        status=TutorVerificationDocument.STATUS_PENDING
                    )
                    
                    docs.update(
                        status=TutorVerificationDocument.STATUS_REJECTED,
                        reviewed_by=request.user,
                        reviewed_at=timezone.now(),
                        review_notes=reason
                    )
                    
                    # Send rejection email
                    email_content = f"""
                    <p>Hello {tutor.first_name or tutor.username},</p>
                    <p>Thank you for submitting your tutor verification documents. Unfortunately, we were unable to approve your application at this time.</p>
                    <div class="error-box">
                        <p><strong>Reason for Rejection:</strong></p>
                        <p>{reason}</p>
                    </div>
                    <p>Please review the feedback above and resubmit your documents with the necessary corrections. You can submit updated documents from your tutor dashboard.</p>
                    <p>If you have any questions, please contact our support team.</p>
                    <center><a href="{settings.FRONTEND_URL}/tutor/dashboard" class="btn">Submit Updated Documents</a></center>
                    """
                    
                    send_verification_email(
                        tutor,
                        "Tutor Verification Update - Action Required",
                        email_content
                    )
                    
                    return Response(
                        {
                            'detail': 'Tutor verification rejected',
                            'entity_type': 'tutor',
                            'id': tutor.id
                        },
                        status=status.HTTP_200_OK
                    )
                
                else:
                    return Response(
                        {'detail': 'Invalid entity_type. Must be "institution" or "tutor"'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        except Institution.DoesNotExist:
            return Response(
                {'detail': 'Institution not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except User.DoesNotExist:
            return Response(
                {'detail': 'Tutor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error rejecting verification: {str(e)}")
            return Response(
                {'detail': 'Error rejecting verification'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
