"""
Management command to diagnose CloudFront configuration issues.
Run with: python manage.py diagnose_cloudfront
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Diagnose CloudFront PEM key configuration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== CloudFront Configuration Diagnosis ===\n'))
        
        # Check environment variables
        cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN')
        cloudfront_key_pair_id = os.environ.get('CLOUDFRONT_KEY_PAIR_ID')
        cloudfront_key_content = os.environ.get('CLOUDFRONT_PRIVATE_KEY_CONTENT', '')
        cloudfront_key_path = os.environ.get('CLOUDFRONT_PRIVATE_KEY_PATH')
        
        self.stdout.write(f'CLOUDFRONT_DOMAIN: {cloudfront_domain}')
        self.stdout.write(f'CLOUDFRONT_KEY_PAIR_ID: {cloudfront_key_pair_id}')
        self.stdout.write(f'CLOUDFRONT_PRIVATE_KEY_PATH (env): {cloudfront_key_path}\n')
        
        # Check if using content or path
        if cloudfront_key_content:
            self.stdout.write(self.style.WARNING('Using CLOUDFRONT_PRIVATE_KEY_CONTENT from environment variable'))
            
            # Show first and last lines
            lines = cloudfront_key_content.split('\\n' if '\\n' in cloudfront_key_content else '\n')
            self.stdout.write(f'  Lines in content: {len(lines)}')
            self.stdout.write(f'  First 100 chars: {cloudfront_key_content[:100]}')
            self.stdout.write(f'  Last 100 chars: {cloudfront_key_content[-100:]}\n')
            
            # Check for issues
            if '\\n' in cloudfront_key_content:
                self.stdout.write(self.style.SUCCESS('✓ Contains escaped newlines (\\\\n) - will be converted'))
            elif '\n' in cloudfront_key_content:
                self.stdout.write(self.style.SUCCESS('✓ Contains actual newlines'))
            else:
                self.stdout.write(self.style.ERROR('✗ No newlines found - PEM might be on single line'))
        else:
            self.stdout.write(self.style.WARNING('Using CLOUDFRONT_PRIVATE_KEY_PATH from environment'))
        
        # Check actual file path being used
        try:
            actual_key_path = getattr(settings, 'CLOUDFRONT_PRIVATE_KEY_PATH', None)
            if actual_key_path:
                self.stdout.write(f'\nActual CLOUDFRONT_PRIVATE_KEY_PATH: {actual_key_path}')
                
                if os.path.exists(actual_key_path):
                    with open(actual_key_path, 'rb') as f:
                        file_content = f.read()
                    
                    self.stdout.write(f'File size: {len(file_content)} bytes')
                    self.stdout.write(f'First 100 bytes: {file_content[:100]}')
                    self.stdout.write(f'Starts with BEGIN: {file_content.startswith(b"-----BEGIN")}')
                    
                    # Try to validate
                    try:
                        from cryptography.hazmat.primitives import serialization
                        from cryptography.hazmat.backends import default_backend
                        private_key = serialization.load_pem_private_key(
                            file_content,
                            password=None,
                            backend=default_backend()
                        )
                        self.stdout.write(self.style.SUCCESS('✓ PEM file is valid and can be loaded'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'✗ PEM file is invalid: {str(e)}'))
                else:
                    self.stdout.write(self.style.ERROR(f'✗ File does not exist at {actual_key_path}'))
            else:
                self.stdout.write(self.style.ERROR('✗ CLOUDFRONT_PRIVATE_KEY_PATH not set in settings'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during diagnosis: {str(e)}'))
