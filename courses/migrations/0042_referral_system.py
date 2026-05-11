from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0041_alter_diploma_academics_alter_diploma_admissions_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReferralSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points_per_success', models.PositiveIntegerField(default=1000)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Referral Settings',
                'verbose_name_plural': 'Referral Settings',
            },
        ),
        migrations.CreateModel(
            name='ReferralProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=24, unique=True)),
                ('points_balance', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='referral_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReferralRelationship',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_used', models.CharField(max_length=24)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('referred', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='referred_by_relationship', to=settings.AUTH_USER_MODEL)),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referrals_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReferralEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('signup_verified', 'Signup Verified'), ('course_purchase', 'Course Purchase'), ('material_purchase', 'Material Purchase'), ('points_redeemed', 'Points Redeemed')], max_length=32)),
                ('points', models.IntegerField(help_text='Positive for awards, negative for redemptions')),
                ('material_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referral_events', to='courses.course')),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referral_events', to='courses.payment')),
                ('referred', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referral_events_as_referred', to=settings.AUTH_USER_MODEL)),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referral_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='referralrelationship',
            index=models.Index(fields=['referrer', '-created_at'], name='courses_ref_referr_55c4a6_idx'),
        ),
        migrations.AddIndex(
            model_name='referralrelationship',
            index=models.Index(fields=['code_used'], name='courses_ref_code_us_8d5b42_idx'),
        ),
        migrations.AddIndex(
            model_name='referralevent',
            index=models.Index(fields=['referrer', '-created_at'], name='courses_ref_referr_8df17b_idx'),
        ),
        migrations.AddIndex(
            model_name='referralevent',
            index=models.Index(fields=['event_type', '-created_at'], name='courses_ref_event_t_d04064_idx'),
        ),
        migrations.AddIndex(
            model_name='referralevent',
            index=models.Index(fields=['referred', 'event_type'], name='courses_ref_referre_f9aef1_idx'),
        ),
        migrations.AddConstraint(
            model_name='referralevent',
            constraint=models.UniqueConstraint(condition=models.Q(('event_type', 'signup_verified')), fields=('referred', 'event_type'), name='unique_referral_signup_verified'),
        ),
        migrations.AddConstraint(
            model_name='referralevent',
            constraint=models.UniqueConstraint(condition=models.Q(('event_type', 'course_purchase')), fields=('referred', 'event_type', 'course'), name='unique_referral_course_purchase'),
        ),
        migrations.AddConstraint(
            model_name='referralevent',
            constraint=models.UniqueConstraint(condition=models.Q(('event_type', 'material_purchase')), fields=('referred', 'event_type', 'material_id'), name='unique_referral_material_purchase'),
        ),
    ]
