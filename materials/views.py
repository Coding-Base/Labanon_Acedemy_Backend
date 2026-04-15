# backend/materials/views.py

import uuid
import os
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Sum, Count, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Material, MaterialPurchase, MaterialDownload
from .serializers import (
    MaterialListSerializer, MaterialDetailSerializer, MaterialCreateSerializer,
    MaterialPurchaseSerializer, MaterialDownloadSerializer, MaterialStatsSerializer
)
from .permissions import IsAdminForMaterials, CanAccessMaterial
from .tasks import send_download_email


class MaterialViewSet(viewsets.ModelViewSet):
    """
    API ViewSet for managing materials.
    - GET: List/retrieve published materials
    - POST/PUT/PATCH/DELETE: Admin only
    """
    
    queryset = Material.objects.filter(is_published=True)
    permission_classes = [IsAdminForMaterials]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    filter_backends = [SearchFilter, DjangoFilterBackend, OrderingFilter]
    
    # Search across multiple fields
    search_fields = ['name', 'topic_category', 'description', 'area', 'creator_name']
    
    # Filter by area and price range
    filterset_fields = ['area', 'price']
    
    # Order options
    ordering_fields = ['created_at', 'price', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use different serializers based on action."""
        if self.action in ['create', 'update', 'partial_update']:
            return MaterialCreateSerializer
        elif self.action == 'retrieve':
            return MaterialDetailSerializer
        return MaterialListSerializer
    
    def get_queryset(self):
        """Override to show all materials to admin, only published to others."""
        user = self.request.user
        
        if user and user.is_authenticated and user.is_staff:
            # Admin sees all materials
            return Material.objects.all()
        
        # Everyone else sees only published
        return Material.objects.filter(is_published=True)
    
    def perform_create(self, serializer):
        """Save material with current user as creator."""
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def upload_file(self, request):
        """
        Upload material file to S3.
        Max file size: 10MB
        Returns: file_url, file_name, file_size
        """
        if not request.FILES.get('file'):
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if file.size > max_size:
            return Response(
                {'error': f'File size exceeds 10MB limit. Current: {file.size / 1024 / 1024:.2f}MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Import storage backend
            from django.core.files.storage import default_storage
            
            # Generate unique filename
            file_ext = os.path.splitext(file.name)[1]
            unique_name = f"materials/{uuid.uuid4()}{file_ext}"
            
            # Save to S3
            file_path = default_storage.save(unique_name, file)
            file_url = default_storage.url(file_path)

            # Ensure returned URL is absolute (DRF URLField expects a full URL)
            # default_storage.url() may return a relative path like '/media/..'
            if file_url and file_url.startswith('/'):
                try:
                    file_url = request.build_absolute_uri(file_url)
                except Exception:
                    # Fallback: leave as-is if build_absolute_uri is unavailable
                    pass
            
            return Response({
                'file_url': file_url,
                'file_name': file.name,
                'file_size': file.size,
                'message': 'File uploaded successfully'
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {'error': f'Upload failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def validate_gdrive(self, request):
        """
        Validate Google Drive link.
        Returns: file_name, file_size (estimated)
        """
        gdrive_link = request.data.get('gdrive_link')
        
        if not gdrive_link:
            return Response(
                {'error': 'No Google Drive link provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Basic validation - check if it's a valid GDrive URL
        if 'drive.google.com' not in gdrive_link:
            return Response(
                {'error': 'Invalid Google Drive URL'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract filename from URL if possible
        try:
            # Remove query params
            url_parts = gdrive_link.split('?')[0]
            # Try to extract filename
            if '/d/' in url_parts:
                file_id = url_parts.split('/d/')[1]
                file_name = f"material_{file_id[:8]}.pdf"
            else:
                file_name = "material_from_gdrive.pdf"
            
            return Response({
                'file_name': file_name,
                'file_size': 'Unknown (from Google Drive)',
                'message': 'Link validated successfully'
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {'error': f'Validation failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def download(self, request, pk=None):
        """
        Generate expiring download link and send via email.
        Updates download count and records download activity.
        """
        material = self.get_object()
        user = request.user
        
        # Check if user has access
        if material.price > 0:  # Paid material
            if not MaterialPurchase.objects.filter(user=user, material=material).exists():
                return Response(
                    {'error': 'You need to purchase this material first'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get or create purchase record (for free materials)
        if material.is_free:
            purchase, _ = MaterialPurchase.objects.get_or_create(
                user=user,
                material=material
            )
        else:
            purchase = MaterialPurchase.objects.get(user=user, material=material)
        
        # Generate download token and expiry
        download_token = str(uuid.uuid4())
        expires_at = now() + timedelta(hours=24)
        
        # Create download record
        download_record = MaterialDownload.objects.create(
            user=user,
            material=material,
            download_token=download_token,
            link_expires_at=expires_at,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Generate signed URL
        download_url = self.generate_signed_url(material, expires_at)
        
        # Update counters
        purchase.download_count += 1
        purchase.last_downloaded_at = now()
        purchase.save(update_fields=['download_count', 'last_downloaded_at'])
        
        # Send email asynchronously; if the broker is down, fall back to synchronous send
        try:
            send_download_email.delay(
                user_email=user.email,
                user_name=user.first_name or user.email.split('@')[0],
                material_name=material.name,
                download_url=download_url,
                expires_at=expires_at.isoformat()
            )
        except Exception as e:
            # Broker not available (e.g., RabbitMQ/Redis). Log and send synchronously.
            print(f"Celery broker unavailable, sending email synchronously: {str(e)}")
            try:
                send_download_email(
                    user_email=user.email,
                    user_name=user.first_name or user.email.split('@')[0],
                    material_name=material.name,
                    download_url=download_url,
                    expires_at=expires_at.isoformat()
                )
            except Exception as e2:
                print(f"Failed to send download email synchronously: {str(e2)}")
        
        return Response({
            'download_url': download_url,
            'expires_at': expires_at,
            'token': download_token,
            'message': 'Download link generated and sent to your email. Link expires in 24 hours.'
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_downloads(self, request):
        """Get user's download history and statistics."""
        purchases = MaterialPurchase.objects.filter(
            user=request.user
        ).select_related('material')
        
        materials = [p.material for p in purchases]
        serializer = MaterialListSerializer(
            materials,
            many=True,
            context={'request': request}
        )
        
        total_downloads = sum(p.download_count for p in purchases)
        
        return Response({
            'total_downloads': total_downloads,
            'total_materials': len(purchases),
            'materials': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def stats(self, request):
        """Get material statistics for admin dashboard."""
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        
        total_materials = Material.objects.count()
        total_downloads = MaterialPurchase.objects.aggregate(
            total=Sum('download_count')
        )['total'] or 0
        total_revenue = Material.objects.aggregate(
            total=Sum('total_revenue')
        )['total'] or 0
        
        # This month's growth
        this_month_start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_purchases = MaterialPurchase.objects.filter(
            accessed_at__gte=this_month_start
        ).count()
        
        last_month_start = (now().replace(day=1) - relativedelta(months=1)).replace(day=1)
        last_month_end = now().replace(day=1)
        last_month_purchases = MaterialPurchase.objects.filter(
            accessed_at__gte=last_month_start,
            accessed_at__lt=last_month_end
        ).count()
        
        # Calculate growth percentage
        growth = 0
        if last_month_purchases > 0:
            growth = int(((this_month_purchases - last_month_purchases) / last_month_purchases) * 100)
        
        return Response({
            'total_materials': total_materials,
            'total_downloads': total_downloads,
            'total_revenue': float(total_revenue),
            'this_month_growth': growth
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def activities(self, request):
        """Get recent download and payment activities."""
        from django.utils.timesince import timesince
        
        activities = []
        
        # Recent downloads
        recent_downloads = MaterialDownload.objects.select_related(
            'user', 'material'
        ).order_by('-created_at')[:10]
        
        for download in recent_downloads:
            activities.append({
                'type': 'download',
                'user_email': download.user.email,
                'material_name': download.material.name,
                'time_ago': timesince(download.created_at) + ' ago',
                'created_at': download.created_at
            })
        
        # Recent purchases (paid materials only)
        from courses.models import Payment
        
        recent_payments = Payment.objects.filter(
            kind='material',
            status='success'
        ).select_related('user').order_by('-verified_at')[:10]
        
        for payment in recent_payments:
            # Try to get material from relationship
            if hasattr(payment, 'material_purchase'):
                material_name = payment.material_purchase.material.name
                activities.append({
                    'type': 'purchase',
                    'user_email': payment.user.email,
                    'material_name': material_name,
                    'amount': float(payment.amount),
                    'time_ago': timesince(payment.verified_at) + ' ago',
                    'created_at': payment.verified_at
                })
        
        # Sort by created_at descending
        activities.sort(key=lambda x: x['created_at'], reverse=True)
        
        return Response(activities[:20], status=status.HTTP_200_OK)
    
    @staticmethod
    def generate_signed_url(material, expires_at):
        """
        Generate CloudFront signed URL for S3-hosted file.
        For Google Drive links, returns the link as-is.
        """
        if material.file_source == 'gdrive':
            return material.gdrive_link
        # For S3 uploads, try CloudFront signed URL first, then S3 presigned URL via boto3, then fallback
        # 1) CloudFront
        try:
            from django_cloudfront_signed_urls import CloudFrontSigner

            signer = CloudFrontSigner(
                key_id=os.environ.get('CLOUDFRONT_KEY_ID'),
                private_key=open(os.environ.get('CLOUDFRONT_PRIVATE_KEY_PATH')).read()
            )

            url = signer.generate_presigned_url(
                url=material.file_url,
                expire_time=int(expires_at.timestamp())
            )
            return url
        except Exception as e:
            print(f"Error generating signed URL (CloudFront): {str(e)}")

        # 2) Try boto3 S3 presigned URL (if file_url points to S3)
        try:
            import boto3
            from urllib.parse import urlparse

            parsed = urlparse(material.file_url)
            bucket = None
            key = None

            # s3://bucket/key
            if parsed.scheme == 's3':
                bucket = parsed.netloc
                key = parsed.path.lstrip('/')
            else:
                host = parsed.netloc or ''
                path = parsed.path.lstrip('/')
                # virtual-hosted-style: bucket.s3.amazonaws.com/key
                if host.endswith('s3.amazonaws.com'):
                    parts = host.split('.')
                    bucket = parts[0]
                    key = path
                # path-style: s3.amazonaws.com/bucket/key
                elif host == 's3.amazonaws.com' or 's3.' in host:
                    path_parts = path.split('/', 1)
                    if len(path_parts) == 2:
                        bucket, key = path_parts[0], path_parts[1]

            if bucket and key:
                s3 = boto3.client(
                    's3',
                    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=os.environ.get('AWS_REGION')
                )

                expires_in = max(60, int((expires_at - now()).total_seconds()))
                presigned = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=expires_in
                )
                return presigned
        except Exception as e2:
            print(f"Error generating S3 presigned URL: {str(e2)}")

        # 3) Fallback to direct URL
        return material.file_url
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
