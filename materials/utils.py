# backend/materials/utils.py

import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def check_email_configuration():
    """
    Diagnose email configuration and return status report.
    Useful for debugging why emails aren't being sent.
    """
    
    report = {
        'email_backend': settings.EMAIL_BACKEND,
        'from_email': settings.DEFAULT_FROM_EMAIL,
        'is_configured': False,
        'backend_type': 'unknown',
        'issues': [],
        'recommendations': []
    }
    
    # Check which backend is configured
    if 'mailjet' in settings.EMAIL_BACKEND.lower():
        report['backend_type'] = 'Mailjet'
        mailjet_key = os.environ.get('MAILJET_API_KEY')
        mailjet_secret = os.environ.get('MAILJET_SECRET_KEY')
        
        if mailjet_key and mailjet_secret:
            report['is_configured'] = True
            logger.info("✅ Mailjet email is configured")
        else:
            report['issues'].append("Mailjet API key or secret is not set")
            report['recommendations'].append("Set MAILJET_API_KEY and MAILJET_SECRET_KEY environment variables")
            
    elif 'console' in settings.EMAIL_BACKEND.lower():
        report['backend_type'] = 'Console (Development)'
        report['is_configured'] = True  # This is valid for development
        report['issues'].append("Using console email backend - emails are printed to console, not actually sent")
        report['recommendations'].append("For production, configure Mailjet or another SMTP provider")
        
    elif 'smtp' in settings.EMAIL_BACKEND.lower():
        report['backend_type'] = 'SMTP'
        report['is_configured'] = True
        
    else:
        report['issues'].append(f"Unknown email backend: {settings.EMAIL_BACKEND}")
        report['recommendations'].append("Check EMAIL_BACKEND configuration in settings.py")
    
    # Check DEFAULT_FROM_EMAIL
    if not settings.DEFAULT_FROM_EMAIL:
        report['issues'].append("DEFAULT_FROM_EMAIL is not configured")
        report['recommendations'].append("Set DEFAULT_FROM_EMAIL in settings.py or DEFAULT_FROM_EMAIL env var")
    
    # Check if email template exists
    try:
        from django.template.loader import get_template
        template = get_template('materials/download_link_email.html')
        logger.info("✅ Email template found")
    except Exception as e:
        report['issues'].append(f"Email template not found: {str(e)}")
        report['recommendations'].append("Ensure 'materials/download_link_email.html' template exists in templates directory")
    
    return report


def get_email_status_text():
    """Get a human-readable email configuration status."""
    
    report = check_email_configuration()
    
    status_lines = [
        "📧 EMAIL CONFIGURATION STATUS",
        "=" * 50,
        f"Backend: {report['backend_type']}",
        f"Configured: {'✅ Yes' if report['is_configured'] else '❌ No'}",
        f"From Email: {report['from_email']}",
    ]
    
    if report['issues']:
        status_lines.append("\n⚠️  ISSUES:")
        for issue in report['issues']:
            status_lines.append(f"  - {issue}")
    
    if report['recommendations']:
        status_lines.append("\n💡 RECOMMENDATIONS:")
        for rec in report['recommendations']:
            status_lines.append(f"  - {rec}")
    
    status_lines.append("=" * 50)
    
    return "\n".join(status_lines)
