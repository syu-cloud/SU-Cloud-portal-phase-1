import django.db.models.deletion
import django.db.models.functions.datetime
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthChallenge',
            fields=[
                ('challenge_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('purpose', models.CharField(max_length=30)),
                ('target_email', models.CharField(max_length=254)),
                ('flow_id', models.UUIDField()),
                ('secret_digest', models.TextField()),
                ('expires_at', models.DateTimeField()),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('grant_expires_at', models.DateTimeField(blank=True, null=True)),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('failed_attempts', models.IntegerField(db_default=0, default=0)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('resend_available_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'auth_challenges',
                'indexes': [models.Index(fields=['flow_id', 'purpose'], name='auth_challe_flow_id_b6a0b4_idx'), models.Index(fields=['user', 'purpose'], name='auth_challe_user_id_2318b8_idx'), models.Index(fields=['target_email', 'purpose'], name='auth_challe_target__84d3ed_idx'), models.Index(fields=['expires_at'], name='auth_challe_expires_3ca899_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('purpose__in', ('SIGNUP_SCHOOL_EMAIL', 'REVERIFY_SCHOOL_EMAIL', 'VERIFY_CONTACT_EMAIL', 'RESET_PASSWORD'))), name='purpose_valid'), models.CheckConstraint(condition=models.Q(('purpose', 'SIGNUP_SCHOOL_EMAIL'), ('user__isnull', False), _connector='OR'), name='user_required'), models.CheckConstraint(condition=models.Q(('failed_attempts__gte', 0)), name='challenge_attempts_valid'), models.CheckConstraint(condition=models.Q(('grant_expires_at__isnull', True), models.Q(('grant_expires_at__gt', models.F('verified_at')), ('verified_at__isnull', False)), _connector='OR'), name='challenge_grant_valid'), models.CheckConstraint(condition=models.Q(('consumed_at__isnull', True), models.Q(('consumed_at__gte', models.F('verified_at')), ('revoked_at__isnull', True), ('verified_at__isnull', False)), _connector='OR'), name='challenge_consumption_valid')],
            },
        ),
    ]
