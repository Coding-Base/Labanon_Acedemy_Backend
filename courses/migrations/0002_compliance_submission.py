# Generated migration for ComplianceSubmission model and related changes

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0001_initial'),  # Adjust based on latest migration
    ]

    operations = [
        # Create ComplianceSubmission model
        migrations.CreateModel(
            name='ComplianceSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submission_id', models.CharField(help_text='Unique batch ID for this submission', max_length=100, unique=True)),
                ('entity_type', models.CharField(choices=[('tutor', 'Tutor'), ('institution', 'Institution')], max_length=20)),
                ('contact_name', models.CharField(max_length=255)),
                ('contact_email', models.EmailField(max_length=254)),
                ('contact_phone', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending Review'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('comments', models.TextField(blank=True, help_text='Submission comments from the user')),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_notes', models.TextField(blank=True, help_text='Admin notes on the submission')),
                ('institution', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='compliance_submissions', to='courses.institution')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_compliance_submissions', to=settings.AUTH_USER_MODEL)),
                ('tutor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='compliance_submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Compliance Submission',
                'verbose_name_plural': 'Compliance Submissions',
                'ordering': ['-submitted_at'],
            },
        ),
        # Add submission field to VerificationDocument
        migrations.AddField(
            model_name='verificationdocument',
            name='submission',
            field=models.ForeignKey(blank=True, help_text='Compliance submission folder this document belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='courses.compliancesubmission'),
        ),
        # Add submission field to TutorVerificationDocument
        migrations.AddField(
            model_name='tutorverificationdocument',
            name='submission',
            field=models.ForeignKey(blank=True, help_text='Compliance submission folder this document belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='courses.compliancesubmission'),
        ),
    ]
