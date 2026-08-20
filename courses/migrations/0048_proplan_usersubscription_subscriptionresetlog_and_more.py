import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cbt', '0001_initial'),
        ('courses', '0047_course_is_series_seriesitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='kind',
            field=models.CharField(
                choices=[
                    ('course', 'Course Purchase'),
                    ('diploma', 'Diploma Enrollment'),
                    ('unlock', 'Account Unlock'),
                    ('material', 'Material Purchase'),
                    ('subscription', 'Pro Subscription'),
                ],
                default='course',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='activationunlock',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Whether this unlock is currently active'),
        ),
        migrations.AddField(
            model_name='activationunlock',
            name='expires_at',
            field=models.DateTimeField(blank=True, help_text='Optional expiration date for time-limited unlock', null=True),
        ),
        migrations.AddField(
            model_name='activationunlock',
            name='revoked_at',
            field=models.DateTimeField(blank=True, help_text='When this unlock was revoked/reset by admin', null=True),
        ),
        migrations.AddField(
            model_name='activationunlock',
            name='revocation_reason',
            field=models.CharField(blank=True, help_text='Reason for revocation (e.g. bulk reset older than 9 months)', max_length=255, null=True),
        ),
        migrations.CreateModel(
            name='ProPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. Pro Monthly, Pro Exam Master', max_length=100)),
                ('slug', models.SlugField(max_length=120, unique=True)),
                ('description', models.TextField(blank=True, help_text='Brief marketing summary of this plan')),
                ('price_ngn', models.DecimalField(decimal_places=2, default=3500.0, help_text='Price in NGN', max_digits=10)),
                ('price_usd', models.DecimalField(decimal_places=2, default=5.0, help_text='Price in USD', max_digits=10)),
                ('billing_interval_days', models.PositiveIntegerField(default=30, help_text='Duration of subscription in days (e.g. 30 for monthly, 365 for annual)')),
                ('all_exams_unlocked', models.BooleanField(default=True, help_text='Grants access to ALL CBT exams without individual activation')),
                ('allow_mock_exams', models.BooleanField(default=True, help_text='Grants access to custom mock exams')),
                ('allow_materials_download', models.BooleanField(default=True, help_text='Grants unlimited download of past questions & study materials')),
                ('features_list', models.JSONField(blank=True, default=list, help_text='List of feature bullet points for checkout card')),
                ('badge', models.CharField(blank=True, help_text="Marketing tag e.g. 'Most Popular', 'Best Value'", max_length=50, null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this tier is visible and purchasable by students')),
                ('order', models.PositiveIntegerField(default=0, help_text='Display order in pricing tables')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('included_exams', models.ManyToManyField(blank=True, help_text='Specific exams included if all_exams_unlocked is False', related_name='pro_plans', to='cbt.exam')),
            ],
            options={
                'verbose_name': 'Pro Plan',
                'verbose_name_plural': 'Pro Plans',
                'ordering': ['order', 'price_ngn'],
            },
        ),
        migrations.CreateModel(
            name='SubscriptionResetLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_identifier', models.CharField(default='all', help_text="Exam slug/id reset or 'all'", max_length=255)),
                ('exam_title', models.CharField(default='All Exams', max_length=255)),
                ('months_threshold', models.PositiveIntegerField(help_text='Cutoff duration in months (e.g. 9)')),
                ('cutoff_date', models.DateTimeField(help_text='Calculated date before which unlocks were revoked')),
                ('affected_users_count', models.PositiveIntegerField(default=0, help_text='Number of student unlocks reset')),
                ('reason', models.TextField(blank=True, default='Scheduled periodic subscription reset')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('admin_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subscription_resets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled'), ('pending', 'Pending')], default='active', max_length=20)),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('end_date', models.DateTimeField(help_text='When this subscription expires')),
                ('auto_renew', models.BooleanField(default=True, help_text='Whether to auto-renew card charge on expiry')),
                ('paystack_customer_code', models.CharField(blank=True, max_length=255, null=True)),
                ('paystack_authorization_code', models.CharField(blank=True, help_text='Saved card authorization token for recurring debits', max_length=255, null=True)),
                ('paystack_subscription_code', models.CharField(blank=True, max_length=255, null=True)),
                ('card_last4', models.CharField(blank=True, help_text='Last 4 digits of saved card', max_length=8, null=True)),
                ('card_brand', models.CharField(blank=True, help_text='e.g. Visa, Mastercard, Verve', max_length=32, null=True)),
                ('notes', models.TextField(blank=True, help_text='Admin or system notes', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subscriptions', to='courses.payment')),
                ('plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subscriptions', to='courses.proplan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'status'], name='courses_use_user_id_44f123_idx'),
                    models.Index(fields=['end_date', 'status'], name='courses_use_end_dat_88b901_idx'),
                ],
            },
        ),
    ]
