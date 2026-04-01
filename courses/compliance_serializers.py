# backend/courses/compliance_serializers.py
from rest_framework import serializers
from .models import ComplianceSubmission, VerificationDocument, TutorVerificationDocument


class ComplianceDocumentSerializer(serializers.Serializer):
    """Serializer for documents within a compliance submission."""
    id = serializers.IntegerField(read_only=True)
    filename = serializers.CharField(source='document_name')
    file_type = serializers.CharField(source='document_type')
    uploaded_at = serializers.DateTimeField(source='submitted_at')
    file_url = serializers.CharField(source='document_file')


class ComplianceSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for compliance submission folders."""
    documents = serializers.SerializerMethodField()
    tutor_username = serializers.CharField(source='tutor.username', read_only=True, allow_null=True)
    tutor_email = serializers.CharField(source='tutor.email', read_only=True, allow_null=True)
    institution_name = serializers.CharField(source='institution.name', read_only=True, allow_null=True)
    institution_owner_email = serializers.CharField(source='institution.owner.email', read_only=True, allow_null=True)
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = ComplianceSubmission
        fields = [
            'id', 'submission_id', 'entity_type', 'tutor', 'tutor_username', 'tutor_email',
            'institution', 'institution_name', 'institution_owner_email',
            'contact_name', 'contact_email', 'contact_phone',
            'status', 'comments', 'submitted_at', 'reviewed_at',
            'reviewed_by_username', 'review_notes', 'documents'
        ]
        read_only_fields = [
            'id', 'submission_id', 'submitted_at', 'reviewed_at', 'reviewed_by_username', 'documents'
        ]
    
    def get_documents(self, obj):
        """Get all documents for this submission."""
        documents = obj.get_all_documents()
        serialized = []
        
        for doc in documents:
            serialized.append({
                'id': doc.id,
                'filename': doc.document_name,
                'file_type': doc.document_type,
                'uploaded_at': doc.submitted_at,
                'file_url': doc.document_file
            })
        
        return serialized
