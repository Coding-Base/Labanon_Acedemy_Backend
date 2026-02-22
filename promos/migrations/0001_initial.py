from django.db import migrations, models
import django.db.models.deletion
import promos.models
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PromoCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(default=promos.models.generate_code, max_length=32, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Amount or percentage value', max_digits=10)),
                ('is_percentage', models.BooleanField(default=False)),
                ('max_uses', models.PositiveIntegerField(blank=True, null=True)),
                ('uses', models.PositiveIntegerField(default=0)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('applicable_to', models.CharField(default='all', max_length=32, help_text='Optional: restriction tag')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
