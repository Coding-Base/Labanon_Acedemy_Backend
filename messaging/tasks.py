import logging

from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

def send_broadcast_email_task(audience, subject, message):
    """
    Sends an email to all users of a specific audience (or all users) as a background task.
    audience can be: 'all', 'student', 'tutor', 'institution'
    """
    logger.info(f"Starting email broadcast to {audience}: {subject}")
    
    # 1. Gather users
    if audience == 'all':
        users = User.objects.filter(email__isnull=False).exclude(email='')
    else:
        users = User.objects.filter(role=audience, email__isnull=False).exclude(email='')
        
    emails = list(users.values_list('email', flat=True))
    if not emails:
        logger.info(f"No emails found for audience '{audience}'. Broadcast cancelled.")
        return 0

    # 2. Build HTML template
    # The message is expected to be HTML from the Quill editor.
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px 0;
            }}
            .container {{
                width: 100%;
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
                border: 1px solid #f3f4f6;
            }}
            .header {{
                background-color: #ca8a04; /* Brand Yellow/Orange */
                color: #ffffff;
                padding: 25px 20px;
                text-align: center;
            }}
            .header h2 {{
                margin: 0;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            .header p {{
                margin: 8px 0 0;
                font-size: 14px;
                opacity: 0.9;
            }}
            .content {{
                padding: 30px;
                color: #374151;
                line-height: 1.6;
            }}
            .message-box {{
                font-size: 15px;
                word-wrap: break-word;
                overflow-wrap: break-word;
                word-break: break-word;
            }}
            .footer {{
                background-color: #f9fafb;
                color: #9ca3af;
                text-align: center;
                padding: 20px;
                font-size: 13px;
                border-top: 1px solid #f3f4f6;
            }}
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 100% !important;
                    border-radius: 0 !important;
                }}
                .content {{
                    padding: 20px !important;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>LightHub Academy</h2>
                <p>Important Update</p>
            </div>
            <div class="content">
                <div class="message-box">
                    {message}
                </div>
            </div>
            <div class="footer">
                &copy; LightHub Academy<br>
                This is an automated system notification. Please do not reply directly to this email.
            </div>
        </div>
    </body>
    </html>
    """
    
    # 3. Send emails
    success_count = 0
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lighthubacademy.com')
    
    for email in emails:
        try:
            send_mail(
                subject=subject,
                message="Please view this email in an HTML-compatible client.",
                from_email=from_email,
                recipient_list=[email],
                html_message=html,
                fail_silently=True
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast email to {{email}}: {{e}}")
            
    logger.info(f"Finished email broadcast. Sent {{success_count}}/{{len(emails)}} successfully.")
    return success_count
