import django.db.models.deletion
import django.db.models.functions.datetime
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('provisioning', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BackupAccessRequest',
            fields=[
                ('backup_access_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_key', models.UUIDField()),
                ('status', models.CharField(db_default='PENDING', default='PENDING', max_length=15)),
                ('decision_actor', models.CharField(blank=True, max_length=10, null=True)),
                ('decision_reason', models.TextField(blank=True, null=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('opened_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('reviewed_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'backup_access_requests',
            },
        ),
        migrations.CreateModel(
            name='CapacityPool',
            fields=[
                ('pool_id', models.SmallIntegerField(primary_key=True, serialize=False)),
                ('total_vcpus', models.IntegerField()),
                ('total_ram_mib', models.IntegerField()),
                ('total_storage_gib', models.IntegerField()),
                ('reservation_enabled', models.BooleanField(db_default=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('provider_project', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.providerproject')),
            ],
            options={
                'db_table': 'capacity_pools',
            },
        ),
        migrations.CreateModel(
            name='OperationJob',
            fields=[
                ('job_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('celery_task_id', models.TextField(blank=True, null=True)),
                ('job_type', models.CharField(max_length=25)),
                ('idempotency_key', models.CharField(max_length=200, unique=True)),
                ('status', models.CharField(db_default='QUEUED', default='QUEUED', max_length=12)),
                ('attempt_count', models.SmallIntegerField(db_default=0, default=0)),
                ('max_attempts', models.SmallIntegerField(db_default=3, default=3)),
                ('retry_interval_seconds', models.IntegerField(db_default=60, default=60)),
                ('next_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('lease_owner', models.TextField(blank=True, null=True)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('request_payload', models.JSONField(db_default={}, default=dict)),
                ('result_payload', models.JSONField(db_default={}, default=dict)),
                ('last_error_code', models.CharField(blank=True, max_length=100, null=True)),
                ('last_error_message', models.TextField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('verification_started_at', models.DateTimeField(blank=True, null=True)),
                ('attention_required', models.BooleanField(db_default=False, default=False)),
                ('backup_access', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.backupaccessrequest')),
                ('parent_job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.operationjob')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('requested_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'operation_jobs',
            },
        ),
        migrations.CreateModel(
            name='OperationAttempt',
            fields=[
                ('attempt_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('attempt_no', models.SmallIntegerField()),
                ('status', models.CharField(db_default='RUNNING', default='RUNNING', max_length=10)),
                ('retryable', models.BooleanField(db_default=False, default=False)),
                ('provider_request_id', models.TextField(blank=True, null=True)),
                ('error_code', models.CharField(blank=True, max_length=100, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('result_snapshot', models.JSONField(db_default={}, default=dict)),
                ('started_at', models.DateTimeField(db_default=django.db.models.functions.datetime.Now(), default=django.utils.timezone.now)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.operationjob')),
            ],
            options={
                'db_table': 'operation_attempts',
            },
        ),
        migrations.CreateModel(
            name='ProjectChangeRequest',
            fields=[
                ('change_request_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_key', models.UUIDField()),
                ('request_type', models.CharField(max_length=20)),
                ('base_project_revision', models.IntegerField()),
                ('base_snapshot', models.JSONField()),
                ('requested_extension_days', models.SmallIntegerField(blank=True, null=True)),
                ('requested_quota_vcpus', models.IntegerField(blank=True, null=True)),
                ('requested_quota_ram_mib', models.IntegerField(blank=True, null=True)),
                ('requested_quota_storage_gib', models.IntegerField(blank=True, null=True)),
                ('request_reason', models.TextField()),
                ('status', models.CharField(db_default='PENDING', default='PENDING', max_length=20)),
                ('decision_actor', models.CharField(blank=True, max_length=10, null=True)),
                ('decision_reason', models.TextField(blank=True, null=True)),
                ('approved_snapshot', models.JSONField(blank=True, null=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('reviewed_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'project_change_requests',
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('notification_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('notification_type', models.CharField(max_length=35)),
                ('event_key', models.CharField(max_length=200, unique=True)),
                ('basis_deadline_at', models.DateTimeField(blank=True, null=True)),
                ('scheduled_at', models.DateTimeField()),
                ('status', models.CharField(db_default='PENDING', default='PENDING', max_length=12)),
                ('recipient_email', models.CharField(blank=True, max_length=254, null=True)),
                ('recipient_type', models.CharField(blank=True, max_length=10, null=True)),
                ('attempt_count', models.SmallIntegerField(db_default=0, default=0)),
                ('max_attempts', models.SmallIntegerField(db_default=3, default=3)),
                ('retry_interval_seconds', models.IntegerField(db_default=60, default=60)),
                ('next_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('lease_owner', models.TextField(blank=True, null=True)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('payload_snapshot', models.JSONField(db_default={}, default=dict)),
                ('provider_message_id', models.TextField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('last_error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.projectapplication')),
                ('backup_access', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.backupaccessrequest')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('change_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.projectchangerequest')),
            ],
            options={
                'db_table': 'notifications',
            },
        ),
        migrations.CreateModel(
            name='VirtualMachine',
            fields=[
                ('vm_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('openstack_server_id', models.TextField(blank=True, null=True, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('image_ref', models.TextField()),
                ('flavor_ref', models.TextField()),
                ('vcpus', models.IntegerField()),
                ('ram_mib', models.IntegerField()),
                ('root_disk_gib', models.IntegerField()),
                ('status', models.CharField(db_default='CREATING', default='CREATING', max_length=15)),
                ('provider_state', models.JSONField(db_default={}, default=dict)),
                ('connection_info', models.JSONField(db_default={}, default=dict)),
                ('observed_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('last_error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
            ],
            options={
                'db_table': 'vms',
            },
        ),
        migrations.CreateModel(
            name='QuotaReservation',
            fields=[
                ('reservation_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('vcpus', models.IntegerField()),
                ('ram_mib', models.IntegerField()),
                ('storage_gib', models.IntegerField()),
                ('status', models.CharField(db_default='RESERVED', default='RESERVED', max_length=10)),
                ('committed_at', models.DateTimeField(blank=True, null=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('job', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.operationjob')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('vm', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.virtualmachine')),
            ],
            options={
                'db_table': 'quota_reservations',
            },
        ),
        migrations.AddField(
            model_name='operationjob',
            name='vm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.virtualmachine'),
        ),
        migrations.CreateModel(
            name='ActivityEvent',
            fields=[
                ('event_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('actor_type', models.CharField(max_length=10)),
                ('event_type', models.CharField(max_length=50)),
                ('from_status', models.CharField(blank=True, max_length=30, null=True)),
                ('to_status', models.CharField(blank=True, max_length=30, null=True)),
                ('reason', models.TextField(blank=True, null=True)),
                ('payload_snapshot', models.JSONField(db_default={}, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('actor_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.projectapplication')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.project')),
                ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('backup_access', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.backupaccessrequest')),
                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.notification')),
                ('attempt', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.operationattempt')),
                ('job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.operationjob')),
                ('change_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.projectchangerequest')),
                ('vm', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.virtualmachine')),
            ],
            options={
                'db_table': 'activity_events',
            },
        ),
        migrations.CreateModel(
            name='VMFlavor',
            fields=[
                ('flavor_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('flavor_ref', models.TextField()),
                ('name', models.CharField(max_length=100)),
                ('vcpus', models.IntegerField()),
                ('ram_mib', models.IntegerField()),
                ('root_disk_gib', models.IntegerField()),
                ('enabled', models.BooleanField(db_default=False, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('provider_project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.providerproject')),
            ],
            options={
                'db_table': 'vm_flavors',
            },
        ),
        migrations.AddField(
            model_name='virtualmachine',
            name='flavor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.vmflavor'),
        ),
        migrations.CreateModel(
            name='VMImage',
            fields=[
                ('image_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image_ref', models.TextField()),
                ('display_name', models.CharField(max_length=100)),
                ('default_ssh_user', models.CharField(max_length=64)),
                ('enabled', models.BooleanField(db_default=False, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('provider_project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.providerproject')),
            ],
            options={
                'db_table': 'vm_images',
            },
        ),
        migrations.AddField(
            model_name='virtualmachine',
            name='image',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='provisioning.vmimage'),
        ),
        migrations.AddIndex(
            model_name='backupaccessrequest',
            index=models.Index(fields=['project', 'status'], name='backup_acce_project_bfd02a_idx'),
        ),
        migrations.AddIndex(
            model_name='backupaccessrequest',
            index=models.Index(fields=['status', 'expires_at'], name='backup_acce_status_fabdcf_idx'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.UniqueConstraint(fields=('user', 'request_key'), name='uniq_backup_request'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('opened_at__isnull', False)), fields=('project',), name='uniq_opened_project_backup'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ('PENDING', 'OPENING', 'OPEN', 'CLOSING', 'CLOSE_FAILED'))), fields=('project',), name='uniq_active_project_backup'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('PENDING', 'OPENING', 'OPEN', 'CLOSING', 'CLOSE_FAILED', 'REJECTED', 'EXPIRED', 'OPEN_FAILED', 'CLOSED'))), name='backup_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'REJECTED'), _negated=True), models.Q(('decision_reason__isnull', False), ('decision_reason__regex', '\\S'), ('reviewed_by_user__isnull', False)), _connector='OR'), name='backup_rejection_details'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'OPEN'), _negated=True), ('opened_at__isnull', False), _connector='OR'), name='backup_open_timestamp'),
        ),
        migrations.AddConstraint(
            model_name='backupaccessrequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'CLOSED'), _negated=True), ('closed_at__isnull', False), _connector='OR'), name='backup_closed_timestamp'),
        ),
        migrations.AddConstraint(
            model_name='capacitypool',
            constraint=models.CheckConstraint(condition=models.Q(('total_ram_mib__gt', 0), ('total_storage_gib__gt', 0), ('total_vcpus__gt', 0)), name='capacity_limits_positive'),
        ),
        migrations.AddConstraint(
            model_name='operationattempt',
            constraint=models.UniqueConstraint(fields=('job', 'attempt_no'), name='uniq_job_attempt'),
        ),
        migrations.AddConstraint(
            model_name='operationattempt',
            constraint=models.CheckConstraint(condition=models.Q(('attempt_no__gte', 1)), name='attempt_number_positive'),
        ),
        migrations.AddConstraint(
            model_name='operationattempt',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('finished_at__isnull', False), ('status__in', ('SUCCEEDED', 'FAILED'))), models.Q(('finished_at__isnull', True), ('status__in', ('RUNNING', 'UNKNOWN'))), _connector='OR'), name='attempt_finished_timestamp'),
        ),
        migrations.AddConstraint(
            model_name='operationattempt',
            constraint=models.CheckConstraint(condition=models.Q(('retryable', False), ('status', 'FAILED'), _connector='OR'), name='attempt_retryable_failed'),
        ),
        migrations.AddIndex(
            model_name='projectchangerequest',
            index=models.Index(fields=['project', 'request_type', 'status'], name='project_cha_project_bc84a8_idx'),
        ),
        migrations.AddIndex(
            model_name='projectchangerequest',
            index=models.Index(fields=['project', 'request_type', 'applied_at'], name='project_cha_project_6409d8_idx'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.UniqueConstraint(fields=('user', 'request_key'), name='uniq_change_request'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ('PENDING', 'APPROVED', 'APPLYING'))), fields=('project', 'request_type'), name='uniq_active_project_change'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('PENDING', 'APPROVED', 'APPLYING', 'APPLIED', 'APPLY_FAILED', 'REJECTED', 'EXPIRED'))), name='change_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('request_type', 'EXTENSION'), ('requested_extension_days__gt', 0), ('requested_extension_days__isnull', False), ('requested_quota_ram_mib__isnull', True), ('requested_quota_storage_gib__isnull', True), ('requested_quota_vcpus__isnull', True)), models.Q(('request_type', 'QUOTA_INCREASE'), ('requested_extension_days__isnull', True), ('requested_quota_ram_mib__gt', 0), ('requested_quota_ram_mib__isnull', False), ('requested_quota_storage_gib__gt', 0), ('requested_quota_storage_gib__isnull', False), ('requested_quota_vcpus__gt', 0), ('requested_quota_vcpus__isnull', False)), _connector='OR'), name='change_input_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(('base_project_revision__gte', 1)), name='change_revision_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(('decision_actor__isnull', True), ('decision_actor__in', ('ADMIN', 'SYSTEM')), _connector='OR'), name='change_decision_actor'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'REJECTED'), _negated=True), models.Q(('decision_reason__isnull', False), ('decision_reason__regex', '\\S'), ('reviewed_by_user__isnull', False)), _connector='OR'), name='change_rejection_details'),
        ),
        migrations.AddConstraint(
            model_name='projectchangerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('applied_at__isnull', False), ('status', 'APPLIED')), models.Q(models.Q(('status', 'APPLIED'), _negated=True), ('applied_at__isnull', True)), _connector='OR'), name='change_applied_timestamp'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['status', 'scheduled_at'], name='notificatio_status_2ea0f1_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['status', 'next_attempt_at'], name='notificatio_status_55722f_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'created_at'], name='notificatio_user_id_7336fd_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['project', 'notification_type'], name='notificatio_project_7f6e7a_idx'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('PENDING', 'SENDING', 'RETRY_WAIT', 'SENT', 'FAILED', 'UNKNOWN', 'CANCELLED'))), name='notification_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('recipient_email__isnull', True), ('recipient_type__isnull', True)), models.Q(('recipient_email__isnull', False), ('recipient_type__in', ('SCHOOL', 'CONTACT')), ('recipient_type__isnull', False)), _connector='OR'), name='notification_recipient_pair'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.CheckConstraint(condition=models.Q(('attempt_count__gte', 0), ('max_attempts__gte', 1), ('retry_interval_seconds__gte', 1)), name='notification_retry_values'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'SENT'), _negated=True), models.Q(('recipient_email__isnull', False), ('sent_at__isnull', False)), _connector='OR'), name='notification_sent_timestamp'),
        ),
        migrations.AddIndex(
            model_name='quotareservation',
            index=models.Index(fields=['project', 'status'], name='quota_reser_project_710d99_idx'),
        ),
        migrations.AddConstraint(
            model_name='quotareservation',
            constraint=models.CheckConstraint(condition=models.Q(('ram_mib__gt', 0), ('storage_gib__gt', 0), ('vcpus__gt', 0)), name='reservation_resources_positive'),
        ),
        migrations.AddConstraint(
            model_name='quotareservation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('committed_at__isnull', True), ('released_at__isnull', True), ('status', 'RESERVED')), models.Q(('committed_at__isnull', False), ('released_at__isnull', True), ('status', 'COMMITTED')), models.Q(('released_at__isnull', False), ('status', 'RELEASED')), _connector='OR'), name='reservation_status_timestamps'),
        ),
        migrations.AddIndex(
            model_name='operationjob',
            index=models.Index(fields=['project', 'status'], name='operation_j_project_4d8e98_idx'),
        ),
        migrations.AddIndex(
            model_name='operationjob',
            index=models.Index(fields=['vm', 'status'], name='operation_j_vm_id_bea848_idx'),
        ),
        migrations.AddIndex(
            model_name='operationjob',
            index=models.Index(fields=['status', 'next_attempt_at'], name='operation_j_status_21910d_idx'),
        ),
        migrations.AddIndex(
            model_name='operationjob',
            index=models.Index(fields=['status', 'verification_started_at'], name='operation_j_status_e48866_idx'),
        ),
        migrations.AddIndex(
            model_name='operationjob',
            index=models.Index(fields=['attention_required'], name='operation_j_attenti_b0b412_idx'),
        ),
        migrations.AddConstraint(
            model_name='operationjob',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ('QUEUED', 'RUNNING', 'VERIFYING', 'RETRY_WAIT')), ('vm__isnull', False)), fields=('vm',), name='uniq_active_vm_job'),
        ),
        migrations.AddConstraint(
            model_name='operationjob',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('QUEUED', 'RUNNING', 'VERIFYING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED'))), name='job_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='operationjob',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('backup_access__isnull', True), ('job_type__in', ('VM_CREATE', 'VM_START', 'VM_STOP', 'VM_PAUSE', 'VM_RESUME', 'VM_REBOOT', 'VM_DELETE')), ('vm__isnull', False)), models.Q(('backup_access__isnull', True), ('job_type__in', ('PROJECT_RESTRICT', 'PROJECT_RECLAIM')), ('vm__isnull', True)), models.Q(('backup_access__isnull', False), ('job_type__in', ('BACKUP_ACCESS_OPEN', 'BACKUP_ACCESS_CLOSE')), ('vm__isnull', True)), _connector='OR'), name='job_target_valid'),
        ),
        migrations.AddConstraint(
            model_name='operationjob',
            constraint=models.CheckConstraint(condition=models.Q(('attempt_count__gte', 0), ('max_attempts__gte', 1), ('retry_interval_seconds__gte', 1)), name='job_retry_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='operationjob',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'VERIFYING'), _negated=True), ('verification_started_at__isnull', False), _connector='OR'), name='job_verification_timestamp'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['created_at'], name='activity_ev_created_cc5c13_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['actor_type', 'created_at'], name='activity_ev_actor_t_122fcd_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['event_type', 'created_at'], name='activity_ev_event_t_a0a379_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['application', 'created_at'], name='activity_ev_applica_9008b8_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['project', 'created_at'], name='activity_ev_project_b468fe_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['target_user', 'created_at'], name='activity_ev_target__71118d_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['job', 'created_at'], name='activity_ev_job_id_42c481_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['attempt', 'created_at'], name='activity_ev_attempt_782cbc_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['change_request', 'created_at'], name='activity_ev_change__261655_idx'),
        ),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['backup_access', 'created_at'], name='activity_ev_backup__6a95e3_idx'),
        ),
        migrations.AddConstraint(
            model_name='activityevent',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('actor_type', 'SYSTEM'), ('actor_user__isnull', True)), models.Q(('actor_type__in', ('USER', 'ADMIN')), ('actor_user__isnull', False)), _connector='OR'), name='event_actor_valid'),
        ),
        migrations.AddIndex(
            model_name='vmflavor',
            index=models.Index(fields=['provider_project', 'enabled'], name='vm_flavors_provide_e4a39b_idx'),
        ),
        migrations.AddConstraint(
            model_name='vmflavor',
            constraint=models.UniqueConstraint(fields=('provider_project', 'flavor_ref'), name='uniq_provider_flavor_ref'),
        ),
        migrations.AddConstraint(
            model_name='vmflavor',
            constraint=models.UniqueConstraint(fields=('provider_project', 'name'), name='uniq_provider_flavor_name'),
        ),
        migrations.AddConstraint(
            model_name='vmflavor',
            constraint=models.CheckConstraint(condition=models.Q(('ram_mib__gt', 0), ('root_disk_gib__gt', 0), ('vcpus__gt', 0)), name='flavor_resources_positive'),
        ),
        migrations.AddIndex(
            model_name='vmimage',
            index=models.Index(fields=['provider_project', 'enabled'], name='vm_images_provide_fd71ca_idx'),
        ),
        migrations.AddConstraint(
            model_name='vmimage',
            constraint=models.UniqueConstraint(fields=('provider_project', 'image_ref'), name='uniq_provider_image_ref'),
        ),
        migrations.AddIndex(
            model_name='virtualmachine',
            index=models.Index(fields=['project', 'status'], name='vms_project_99d679_idx'),
        ),
        migrations.AddIndex(
            model_name='virtualmachine',
            index=models.Index(fields=['project', 'name'], name='vms_project_6930c9_idx'),
        ),
        migrations.AddConstraint(
            model_name='virtualmachine',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('project', 'name'), name='uniq_live_vm_name'),
        ),
        migrations.AddConstraint(
            model_name='virtualmachine',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('CREATING', 'RUNNING', 'STOPPED', 'PAUSED', 'ERROR', 'DELETING', 'DELETED', 'UNKNOWN'))), name='vm_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='virtualmachine',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('deleted_at__isnull', False), ('status', 'DELETED')), models.Q(models.Q(('status', 'DELETED'), _negated=True), ('deleted_at__isnull', True)), _connector='OR'), name='vm_deleted_timestamp'),
        ),
        migrations.AddConstraint(
            model_name='virtualmachine',
            constraint=models.CheckConstraint(condition=models.Q(('ram_mib__gt', 0), ('root_disk_gib__gt', 0), ('vcpus__gt', 0)), name='vm_resources_positive'),
        ),
    ]
