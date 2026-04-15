# backend/materials/tasks.py

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.timezone import now
import os
from datetime import datetime


@shared_task
def send_download_email(user_email, user_name, material_name, download_url, expires_at):
    """
    Send beautifully styled email with download link and expiration time.
    Uses Celery to send asynchronously.
    """
    
    try:
        # Parse expiry time
        from dateutil import parser
        expires_dt = parser.parse(expires_at)
        
        # Prepare context for template
        context = {
            'user_name': user_name or user_email.split('@')[0],
            'material_name': material_name,
            'download_url': download_url,
            'expires_at': expires_dt,
            'current_date': now(),
            'platform_url': os.environ.get('FRONTEND_URL', 'https://lighthubacademy.org'),
            'support_email': os.environ.get('SUPPORT_EMAIL', 'support@lighthubacademy.org'),
        }
        
        # Render HTML template
        html_content = render_to_string('materials/download_link_email.html', context)
        
        # Plain text fallback
        text_content = f"""
Your Material is Ready!

Hi {user_name},

Your material '{material_name}' is ready to download.

Download Link: {download_url}
Link Expires: {expires_dt.strftime('%B %d, %Y at %H:%M')} (24 hours from now)

Visit Platform: {context['platform_url']}
Support: {context['support_email']}

This is an automated email. Please do not reply.
        """
        
        # Create email
        subject = f"📥 Your Material is Ready: {material_name}"
        from_email = os.environ.get('EMAIL_FROM', 'noreply@lighthubacademy.org')
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[user_email]
        )
        
        # Attach HTML version
        email.attach_alternative(html_content, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        print(f"✓ Download email sent to {user_email} for '{material_name}'")
        return {'status': 'sent', 'email': user_email}
    
    except Exception as e:
        print(f"✗ Error sending email to {user_email}: {str(e)}")
        # Retry on error
        raise
