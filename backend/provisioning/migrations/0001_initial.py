import django.db.models.deletion
import django.db.models.functions.datetime
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OperationSettings',
            fields=[
                ('settings_version', models.IntegerField(primary_key=True, serialize=False)),
                ('max_initial_days', models.SmallIntegerField()),
                ('ext_max_count', models.SmallIntegerField()),
                ('ext_max_days', models.SmallIntegerField()),
                ('ext_open_before_days', models.SmallIntegerField()),
                ('retention_hours', models.SmallIntegerField()),
                ('changed_fields', models.JSONField(db_default={}, default=dict)),
                ('effective_from', models.DateTimeField(db_default=django.db.models.functions.datetime.Now(), default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('changed_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='settings_changes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'operation_settings',
            },
        ),
        migrations.CreateModel(
            name='ProjectApplication',
            fields=[
                ('application_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_key', models.UUIDField()),
                ('revision', models.IntegerField(db_default=1, default=1)),
                ('project_name', models.CharField(max_length=100)),
                ('applicant_snapshot', models.JSONField()),
                ('usage_purpose', models.TextField()),
                ('quota_preset', models.CharField(max_length=10)),
                ('requested_vcpus', models.IntegerField()),
                ('requested_ram_mib', models.IntegerField()),
                ('requested_storage_gib', models.IntegerField()),
                ('requested_vm_count', models.IntegerField(db_default=5, default=5)),
                ('requested_duration_days', models.SmallIntegerField()),
                ('status', models.CharField(db_default='PENDING', default='PENDING', max_length=20)),
                ('decision_actor', models.CharField(blank=True, max_length=10, null=True)),
                ('decision_reason', models.TextField(blank=True, null=True)),
                ('approved_snapshot', models.JSONField(blank=True, null=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_reason', models.CharField(blank=True, max_length=30, null=True)),
                ('canceled_at', models.DateTimeField(blank=True, null=True)),
                ('submitted_at', models.DateTimeField()),
                ('last_submitted_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('reviewed_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_applications', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='project_applications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'project_applications',
            },
        ),
        migrations.CreateModel(
            name='ProjectPreset',
            fields=[
                ('pk', models.CompositePrimaryKey('settings_id', 'preset_code', blank=True, editable=False, primary_key=True, serialize=False)),
                ('preset_code', models.CharField(max_length=10)),
                ('display_name', models.CharField(max_length=30)),
                ('vcpus', models.IntegerField()),
                ('ram_mib', models.IntegerField()),
                ('storage_gib', models.IntegerField()),
                ('vm_count', models.IntegerField(db_default=5, default=5)),
                ('enabled', models.BooleanField(db_default=False, default=False)),
                ('sort_order', models.SmallIntegerField()),
                ('settings', models.ForeignKey(db_column='settings_version', on_delete=django.db.models.deletion.PROTECT, related_name='project_presets', to='provisioning.operationsettings')),
            ],
            options={
                'db_table': 'project_presets',
            },
        ),
        migrations.CreateModel(
            name='ProviderProject',
            fields=[
                ('provider_project_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('openstack_project_id', models.TextField()),
                ('region_name', models.CharField(max_length=100)),
                ('connection_profile_key', models.CharField(max_length=100)),
                ('allocation_enabled', models.BooleanField(db_default=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
            ],
            options={
                'db_table': 'provider_projects',
                'constraints': [models.UniqueConstraint(fields=('connection_profile_key', 'region_name', 'openstack_project_id'), name='uniq_provider_connection')],
            },
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('project_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('quota_preset', models.CharField(max_length=10)),
                ('quota_vcpus', models.IntegerField()),
                ('quota_ram_mib', models.IntegerField()),
                ('quota_storage_gib', models.IntegerField()),
                ('quota_vm_count', models.IntegerField(db_default=5, default=5)),
                ('allocated_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField()),
                ('reclaim_after', models.DateTimeField()),
                ('retention_hours', models.SmallIntegerField()),
                ('ext_max_count', models.SmallIntegerField()),
                ('ext_max_days', models.SmallIntegerField()),
                ('ext_open_before_days', models.SmallIntegerField()),
                ('revision', models.IntegerField(db_default=1, default=1)),
                ('status', models.CharField(db_default='ACTIVE', default='ACTIVE', max_length=20)),
                ('restriction_requested_at', models.DateTimeField(blank=True, null=True)),
                ('usage_restricted_at', models.DateTimeField(blank=True, null=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('reclaim_started_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('closure_reason', models.CharField(blank=True, max_length=20, null=True)),
                ('last_error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.datetime.Now())),
                ('updated_at', models.DateTimeField(auto_now=True, db_default=django.db.models.functions.datetime.Now())),
                ('settings', models.ForeignKey(db_column='settings_version', on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='provisioning.operationsettings')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to=settings.AUTH_USER_MODEL)),
                ('application', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='project', to='provisioning.projectapplication')),
                ('provider_project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='provisioning.providerproject')),
            ],
            options={
                'db_table': 'projects',
            },
        ),
        migrations.AddConstraint(
            model_name='operationsettings',
            constraint=models.CheckConstraint(condition=models.Q(('ext_max_count__gte', 1), ('ext_max_days__gte', 1), ('ext_open_before_days__gte', 1), ('ext_open_before_days__lt', models.F('max_initial_days')), ('max_initial_days__gte', 1), ('retention_hours__gte', 1)), name='settings_positive_limits'),
        ),
        migrations.AddIndex(
            model_name='projectapplication',
            index=models.Index(fields=['user', 'status'], name='project_app_user_id_49508c_idx'),
        ),
        migrations.AddIndex(
            model_name='projectapplication',
            index=models.Index(fields=['status', 'last_submitted_at', 'application_id'], name='project_app_status_95f69e_idx'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.UniqueConstraint(fields=('user', 'request_key'), name='uniq_application_request'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ('PENDING', 'NEEDS_INFO'))), fields=('user',), name='uniq_open_application'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('PENDING', 'NEEDS_INFO', 'APPROVED', 'REJECTED', 'CANCELED'))), name='application_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(('decision_actor__isnull', True), ('decision_actor__in', ('ADMIN', 'SYSTEM')), _connector='OR'), name='application_actor_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(('quota_preset__in', ('LITE', 'STANDARD', 'PLUS', 'PRO', 'ULTRA', 'CUSTOM')), ('requested_duration_days__gte', 1), ('requested_ram_mib__gt', 0), ('requested_storage_gib__gt', 0), ('requested_vcpus__gt', 0), ('requested_vm_count', 5), ('revision__gte', 1)), name='application_quota_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status__in', ('NEEDS_INFO', 'REJECTED')), _negated=True), models.Q(('decision_reason__isnull', False), ('decision_reason__regex', '\\S'), ('reviewed_by_user__isnull', False)), _connector='OR'), name='application_review_reason'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'REJECTED'), _negated=True), ('decided_at__isnull', False), _connector='OR'), name='application_review_time'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('decision_actor', 'ADMIN'), _negated=True), ('reviewed_by_user__isnull', False), _connector='OR'), name='application_admin_reviewer'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'APPROVED'), _negated=True), models.Q(('approved_snapshot__isnull', False), ('decided_at__isnull', False), ('decision_actor__isnull', False)), _connector='OR'), name='application_approved_fields'),
        ),
        migrations.AddConstraint(
            model_name='projectapplication',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'CANCELED'), _negated=True), models.Q(('cancel_reason__isnull', False), ('cancel_reason__regex', '\\S'), ('canceled_at__isnull', False)), _connector='OR'), name='application_cancel_fields'),
        ),
        migrations.AddIndex(
            model_name='projectpreset',
            index=models.Index(fields=['settings', 'enabled', 'sort_order'], name='project_pre_setting_52e462_idx'),
        ),
        migrations.AddConstraint(
            model_name='projectpreset',
            constraint=models.CheckConstraint(condition=models.Q(('preset_code__in', ('LITE', 'STANDARD', 'PLUS', 'PRO', 'ULTRA'))), name='preset_code_valid'),
        ),
        migrations.AddConstraint(
            model_name='projectpreset',
            constraint=models.CheckConstraint(condition=models.Q(('ram_mib__gt', 0), ('sort_order__gte', 0), ('storage_gib__gt', 0), ('vcpus__gt', 0), ('vm_count', 5)), name='preset_values_valid'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['user', 'returned_at'], name='projects_user_id_cfc30e_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['user', 'status'], name='projects_user_id_05c680_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['provider_project', 'status'], name='projects_provide_5e653e_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['status', 'expires_at'], name='projects_status_45f847_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['status', 'reclaim_after'], name='projects_status_89d68b_idx'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.UniqueConstraint(condition=models.Q(('returned_at__isnull', True)), fields=('user',), name='uniq_unreturned_project'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ('ACTIVE', 'RESTRICTED', 'RECLAIMING', 'RECLAIM_FAILED', 'CLOSED'))), name='project_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(condition=models.Q(('ext_max_count__gte', 1), ('ext_max_days__gte', 1), ('ext_open_before_days__gte', 1), ('quota_preset__in', ('LITE', 'STANDARD', 'PLUS', 'PRO', 'ULTRA', 'CUSTOM')), ('quota_ram_mib__gt', 0), ('quota_storage_gib__gt', 0), ('quota_vcpus__gt', 0), ('quota_vm_count__gt', 0), ('retention_hours__gte', 1), ('revision__gte', 1)), name='project_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status__in', ('RECLAIMING', 'RECLAIM_FAILED', 'CLOSED')), _negated=True), ('returned_at__isnull', False), _connector='OR'), name='project_return_recorded'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(condition=models.Q(('closure_reason__isnull', True), ('closure_reason__in', ('USER_RETURN', 'EXPIRED_RECLAIM')), _connector='OR'), name='project_closure_reason'),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'CLOSED'), _negated=True), models.Q(('closed_at__isnull', False), ('closure_reason__isnull', False)), _connector='OR'), name='project_closed_fields'),
        ),
    ]
