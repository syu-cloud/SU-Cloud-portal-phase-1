import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone


PRESET_CODES = ("LITE", "STANDARD", "PLUS", "PRO", "ULTRA")
QUOTA_CODES = (*PRESET_CODES, "CUSTOM")
OPEN_APPLICATION_STATES = ("PENDING", "NEEDS_INFO")


class ProviderProject(models.Model):
    provider_project_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    openstack_project_id = models.TextField()
    region_name = models.CharField(max_length=100)
    connection_profile_key = models.CharField(max_length=100)
    allocation_enabled = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "provider_projects"
        constraints = [
            models.UniqueConstraint(
                name="uniq_provider_connection",
                fields=["connection_profile_key", "region_name", "openstack_project_id"],
            ),
        ]


class OperationSettings(models.Model):
    settings_version = models.IntegerField(primary_key=True)
    max_initial_days = models.SmallIntegerField()
    ext_max_count = models.SmallIntegerField()
    ext_max_days = models.SmallIntegerField()
    ext_open_before_days = models.SmallIntegerField()
    retention_hours = models.SmallIntegerField()
    changed_fields = models.JSONField(default=dict, db_default={})
    changed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settings_changes", null=True, blank=True)
    effective_from = models.DateTimeField(default=timezone.now, db_default=Now())
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())

    class Meta:
        db_table = "operation_settings"
        constraints = [
            models.CheckConstraint(
                name="settings_positive_limits",
                condition=Q(max_initial_days__gte=1, ext_max_count__gte=1, ext_max_days__gte=1,
                  ext_open_before_days__gte=1, retention_hours__gte=1,
                  ext_open_before_days__lt=F("max_initial_days")),
            ),
        ]


class ProjectApplication(models.Model):
    application_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="project_applications")
    request_key = models.UUIDField()
    revision = models.IntegerField(default=1, db_default=1)
    project_name = models.CharField(max_length=100)
    applicant_snapshot = models.JSONField()
    usage_purpose = models.TextField()
    quota_preset = models.CharField(max_length=10)
    requested_vcpus = models.IntegerField()
    requested_ram_mib = models.IntegerField()
    requested_storage_gib = models.IntegerField()
    requested_vm_count = models.IntegerField(default=5, db_default=5)
    requested_duration_days = models.SmallIntegerField()
    status = models.CharField(max_length=20, default="PENDING", db_default="PENDING")
    decision_actor = models.CharField(max_length=10, null=True, blank=True)
    reviewed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviewed_applications", null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)
    approved_snapshot = models.JSONField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=30, null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField()
    last_submitted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "project_applications"
        constraints = [
            models.UniqueConstraint(
                name="uniq_application_request",
                fields=["user", "request_key"],
            ),
            models.UniqueConstraint(
                name="uniq_open_application",
                fields=["user"], condition=Q(status__in=OPEN_APPLICATION_STATES),
            ),
            models.CheckConstraint(
                name="application_status_valid",
                condition=Q(status__in=(*OPEN_APPLICATION_STATES, "APPROVED", "REJECTED", "CANCELED")),
            ),
            models.CheckConstraint(
                name="application_actor_valid",
                condition=Q(decision_actor__isnull=True) | Q(decision_actor__in=("ADMIN", "SYSTEM")),
            ),
            models.CheckConstraint(
                name="application_quota_valid",
                condition=Q(quota_preset__in=QUOTA_CODES, requested_vcpus__gt=0, requested_ram_mib__gt=0,
                  requested_storage_gib__gt=0, requested_vm_count=5, requested_duration_days__gte=1, revision__gte=1),
            ),
            models.CheckConstraint(
                name="application_review_reason",
                condition=~Q(status__in=("NEEDS_INFO", "REJECTED")) | Q(reviewed_by_user__isnull=False,
                  decision_reason__isnull=False, decision_reason__regex=r"\S"),
            ),
            models.CheckConstraint(
                name="application_review_time",
                condition=~Q(status="REJECTED") | Q(decided_at__isnull=False),
            ),
            models.CheckConstraint(
                name="application_admin_reviewer",
                condition=~Q(decision_actor="ADMIN") | Q(reviewed_by_user__isnull=False),
            ),
            models.CheckConstraint(
                name="application_approved_fields",
                condition=~Q(status="APPROVED") | Q(approved_snapshot__isnull=False,
                  decided_at__isnull=False, decision_actor__isnull=False),
            ),
            models.CheckConstraint(
                name="application_cancel_fields",
                condition=~Q(status="CANCELED") | Q(canceled_at__isnull=False,
                  cancel_reason__isnull=False, cancel_reason__regex=r"\S"),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "last_submitted_at", "application_id"]),
        ]


class ProjectPreset(models.Model):
    pk = models.CompositePrimaryKey("settings_id", "preset_code")
    settings = models.ForeignKey(OperationSettings, on_delete=models.PROTECT, related_name="project_presets", db_column="settings_version")
    preset_code = models.CharField(max_length=10)
    display_name = models.CharField(max_length=30)
    vcpus = models.IntegerField()
    ram_mib = models.IntegerField()
    storage_gib = models.IntegerField()
    vm_count = models.IntegerField(default=5, db_default=5)
    enabled = models.BooleanField(default=False, db_default=False)
    sort_order = models.SmallIntegerField()

    class Meta:
        db_table = "project_presets"
        constraints = [
            models.CheckConstraint(
                name="preset_code_valid",
                condition=Q(preset_code__in=PRESET_CODES),
            ),
            models.CheckConstraint(
                name="preset_values_valid",
                condition=Q(vcpus__gt=0, ram_mib__gt=0, storage_gib__gt=0, vm_count=5, sort_order__gte=0),
            ),
        ]
        indexes = [
            models.Index(fields=["settings", "enabled", "sort_order"]),
        ]


class Project(models.Model):
    project_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(ProjectApplication, on_delete=models.PROTECT, related_name="project")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="projects")
    provider_project = models.ForeignKey(ProviderProject, on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=100)
    quota_preset = models.CharField(max_length=10)
    quota_vcpus = models.IntegerField()
    quota_ram_mib = models.IntegerField()
    quota_storage_gib = models.IntegerField()
    quota_vm_count = models.IntegerField(default=5, db_default=5)
    allocated_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    reclaim_after = models.DateTimeField()
    retention_hours = models.SmallIntegerField()
    ext_max_count = models.SmallIntegerField()
    ext_max_days = models.SmallIntegerField()
    ext_open_before_days = models.SmallIntegerField()
    settings = models.ForeignKey(OperationSettings, on_delete=models.PROTECT, related_name="projects", db_column="settings_version")
    revision = models.IntegerField(default=1, db_default=1)
    status = models.CharField(max_length=20, default="ACTIVE", db_default="ACTIVE")
    restriction_requested_at = models.DateTimeField(null=True, blank=True)
    usage_restricted_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    reclaim_started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_reason = models.CharField(max_length=20, null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "projects"
        constraints = [
            models.UniqueConstraint(
                name="uniq_unreturned_project",
                fields=["user"], condition=Q(returned_at__isnull=True),
            ),
            models.CheckConstraint(
                name="project_status_valid",
                condition=Q(status__in=("ACTIVE", "RESTRICTED", "RECLAIMING", "RECLAIM_FAILED", "CLOSED")),
            ),
            models.CheckConstraint(
                name="project_values_valid",
                condition=Q(quota_preset__in=QUOTA_CODES, quota_vcpus__gt=0, quota_ram_mib__gt=0,
                  quota_storage_gib__gt=0, quota_vm_count__gt=0, revision__gte=1,
                  ext_max_count__gte=1, ext_max_days__gte=1, ext_open_before_days__gte=1, retention_hours__gte=1),
            ),
            models.CheckConstraint(
                name="project_return_recorded",
                condition=~Q(status__in=("RECLAIMING", "RECLAIM_FAILED", "CLOSED")) | Q(returned_at__isnull=False),
            ),
            models.CheckConstraint(
                name="project_closure_reason",
                condition=Q(closure_reason__isnull=True) | Q(closure_reason__in=("USER_RETURN", "EXPIRED_RECLAIM")),
            ),
            models.CheckConstraint(
                name="project_closed_fields",
                condition=~Q(status="CLOSED") | Q(closed_at__isnull=False, closure_reason__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "returned_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["provider_project", "status"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["status", "reclaim_after"]),
        ]


ACTIVE_JOB_STATES = ("QUEUED", "RUNNING", "VERIFYING", "RETRY_WAIT")
ACTIVE_BACKUP_STATES = ("PENDING", "OPENING", "OPEN", "CLOSING", "CLOSE_FAILED")
VM_JOB_TYPES = (
    "VM_CREATE", "VM_START", "VM_STOP", "VM_PAUSE", "VM_RESUME", "VM_REBOOT", "VM_DELETE",
)


class ProjectChangeRequest(models.Model):
    change_request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    request_key = models.UUIDField()
    request_type = models.CharField(max_length=20)
    base_project_revision = models.IntegerField()
    base_snapshot = models.JSONField()
    requested_extension_days = models.SmallIntegerField(null=True, blank=True)
    requested_quota_vcpus = models.IntegerField(null=True, blank=True)
    requested_quota_ram_mib = models.IntegerField(null=True, blank=True)
    requested_quota_storage_gib = models.IntegerField(null=True, blank=True)
    request_reason = models.TextField()
    status = models.CharField(max_length=20, default="PENDING", db_default="PENDING")
    decision_actor = models.CharField(max_length=10, null=True, blank=True)
    reviewed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    decision_reason = models.TextField(null=True, blank=True)
    approved_snapshot = models.JSONField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "project_change_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"],
                name="uniq_change_request",
            ),
            models.UniqueConstraint(
                fields=["project", "request_type"],
                condition=Q(status__in=("PENDING", "APPROVED", "APPLYING")),
                name="uniq_active_project_change",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=("PENDING", "APPROVED", "APPLYING", "APPLIED",
                      "APPLY_FAILED", "REJECTED", "EXPIRED"))
                ),
                name="change_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(request_type="EXTENSION", requested_extension_days__isnull=False,
                      requested_extension_days__gt=0, requested_quota_vcpus__isnull=True,
                      requested_quota_ram_mib__isnull=True, requested_quota_storage_gib__isnull=True)
                    | (Q(request_type="QUOTA_INCREASE", requested_extension_days__isnull=True)
                   & Q(requested_quota_vcpus__isnull=False, requested_quota_vcpus__gt=0,
                       requested_quota_ram_mib__isnull=False, requested_quota_ram_mib__gt=0,
                       requested_quota_storage_gib__isnull=False, requested_quota_storage_gib__gt=0))
                ),
                name="change_input_valid",
            ),
            models.CheckConstraint(
                condition=Q(base_project_revision__gte=1),
                name="change_revision_valid",
            ),
            models.CheckConstraint(
                condition=Q(decision_actor__isnull=True) | Q(decision_actor__in=("ADMIN", "SYSTEM")),
                name="change_decision_actor",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="REJECTED") | Q(
                      reviewed_by_user__isnull=False, decision_reason__isnull=False, decision_reason__regex=r"\S")
                ),
                name="change_rejection_details",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="APPLIED", applied_at__isnull=False)
                    | (~Q(status="APPLIED") & Q(applied_at__isnull=True))
                ),
                name="change_applied_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "request_type", "status"]),
            models.Index(fields=["project", "request_type", "applied_at"]),
        ]


class VirtualMachine(models.Model):
    vm_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="+")
    openstack_server_id = models.TextField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=100)
    image = models.ForeignKey("VMImage", on_delete=models.PROTECT, related_name="+")
    flavor = models.ForeignKey("VMFlavor", on_delete=models.PROTECT, related_name="+")
    image_ref = models.TextField()
    flavor_ref = models.TextField()
    vcpus = models.IntegerField()
    ram_mib = models.IntegerField()
    root_disk_gib = models.IntegerField()
    status = models.CharField(max_length=15, default="CREATING", db_default="CREATING")
    provider_state = models.JSONField(default=dict, db_default={})
    connection_info = models.JSONField(default=dict, db_default={})
    observed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "vms"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_live_vm_name",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=("CREATING", "RUNNING", "STOPPED", "PAUSED",
                      "ERROR", "DELETING", "DELETED", "UNKNOWN"))
                ),
                name="vm_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="DELETED", deleted_at__isnull=False)
                    | (~Q(status="DELETED") & Q(deleted_at__isnull=True))
                ),
                name="vm_deleted_timestamp",
            ),
            models.CheckConstraint(
                condition=Q(vcpus__gt=0, ram_mib__gt=0, root_disk_gib__gt=0),
                name="vm_resources_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "name"]),
        ]


class OperationJob(models.Model):
    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    celery_task_id = models.TextField(null=True, blank=True)
    project = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="+")
    vm = models.ForeignKey(
        "VirtualMachine",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    backup_access = models.ForeignKey(
        "BackupAccessRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    parent_job = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    requested_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    job_type = models.CharField(max_length=25)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=12, default="QUEUED", db_default="QUEUED")
    attempt_count = models.SmallIntegerField(default=0, db_default=0)
    max_attempts = models.SmallIntegerField(default=3, db_default=3)
    retry_interval_seconds = models.IntegerField(default=60, db_default=60)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.TextField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    request_payload = models.JSONField(default=dict, db_default={})
    result_payload = models.JSONField(default=dict, db_default={})
    last_error_code = models.CharField(max_length=100, null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())
    verification_started_at = models.DateTimeField(null=True, blank=True)
    attention_required = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = "operation_jobs"
        constraints = [
            models.UniqueConstraint(
                fields=["vm"],
                condition=Q(vm__isnull=False, status__in=ACTIVE_JOB_STATES),
                name="uniq_active_vm_job",
            ),
            models.CheckConstraint(
                condition=Q(status__in=(*ACTIVE_JOB_STATES, "SUCCEEDED", "FAILED", "CANCELLED")),
                name="job_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(job_type__in=VM_JOB_TYPES, vm__isnull=False, backup_access__isnull=True)
                    | Q(job_type__in=("PROJECT_RESTRICT", "PROJECT_RECLAIM"),
                      vm__isnull=True, backup_access__isnull=True)
                    | Q(job_type__in=("BACKUP_ACCESS_OPEN", "BACKUP_ACCESS_CLOSE"),
                      vm__isnull=True, backup_access__isnull=False)
                ),
                name="job_target_valid",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__gte=0, max_attempts__gte=1, retry_interval_seconds__gte=1),
                name="job_retry_values_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status="VERIFYING") | Q(verification_started_at__isnull=False),
                name="job_verification_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["vm", "status"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["status", "verification_started_at"]),
            models.Index(fields=["attention_required"]),
        ]


class OperationAttempt(models.Model):
    attempt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey("OperationJob", on_delete=models.PROTECT, related_name="+")
    attempt_no = models.SmallIntegerField()
    status = models.CharField(max_length=10, default="RUNNING", db_default="RUNNING")
    retryable = models.BooleanField(default=False, db_default=False)
    provider_request_id = models.TextField(null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    result_snapshot = models.JSONField(default=dict, db_default={})
    started_at = models.DateTimeField(default=timezone.now, db_default=Now())
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "operation_attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "attempt_no"],
                name="uniq_job_attempt",
            ),
            models.CheckConstraint(
                condition=Q(attempt_no__gte=1),
                name="attempt_number_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=("SUCCEEDED", "FAILED"), finished_at__isnull=False)
                    | Q(status__in=("RUNNING", "UNKNOWN"), finished_at__isnull=True)
                ),
                name="attempt_finished_timestamp",
            ),
            models.CheckConstraint(
                condition=Q(retryable=False) | Q(status="FAILED"),
                name="attempt_retryable_failed",
            ),
        ]


class QuotaReservation(models.Model):
    reservation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="+")
    vm = models.OneToOneField("VirtualMachine", on_delete=models.PROTECT, related_name="+")
    job = models.OneToOneField("OperationJob", on_delete=models.PROTECT, related_name="+")
    vcpus = models.IntegerField()
    ram_mib = models.IntegerField()
    storage_gib = models.IntegerField()
    status = models.CharField(max_length=10, default="RESERVED", db_default="RESERVED")
    committed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "quota_reservations"
        constraints = [
            models.CheckConstraint(
                condition=Q(vcpus__gt=0, ram_mib__gt=0, storage_gib__gt=0),
                name="reservation_resources_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="RESERVED", committed_at__isnull=True, released_at__isnull=True)
                    | Q(status="COMMITTED", committed_at__isnull=False, released_at__isnull=True)
                    | Q(status="RELEASED", released_at__isnull=False)
                ),
                name="reservation_status_timestamps",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"]),
        ]


class ActivityEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_type = models.CharField(max_length=10)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    application = models.ForeignKey(
        "ProjectApplication",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    change_request = models.ForeignKey(
        "ProjectChangeRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    backup_access = models.ForeignKey(
        "BackupAccessRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    vm = models.ForeignKey(
        "VirtualMachine",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    job = models.ForeignKey(
        "OperationJob",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    attempt = models.ForeignKey(
        "OperationAttempt",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    notification = models.ForeignKey(
        "Notification",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=50)
    from_status = models.CharField(max_length=30, null=True, blank=True)
    to_status = models.CharField(max_length=30, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    payload_snapshot = models.JSONField(default=dict, db_default={})
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())

    class Meta:
        db_table = "activity_events"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(actor_type="SYSTEM", actor_user__isnull=True)
                    | Q(actor_type__in=("USER", "ADMIN"), actor_user__isnull=False)
                ),
                name="event_actor_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor_type", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["application", "created_at"]),
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["target_user", "created_at"]),
            models.Index(fields=["job", "created_at"]),
            models.Index(fields=["attempt", "created_at"]),
            models.Index(fields=["change_request", "created_at"]),
            models.Index(fields=["backup_access", "created_at"]),
        ]


class Notification(models.Model):
    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    application = models.ForeignKey(
        "ProjectApplication",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    change_request = models.ForeignKey(
        "ProjectChangeRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    backup_access = models.ForeignKey(
        "BackupAccessRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(max_length=35)
    event_key = models.CharField(max_length=200, unique=True)
    basis_deadline_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=12, default="PENDING", db_default="PENDING")
    recipient_email = models.CharField(max_length=254, null=True, blank=True)
    recipient_type = models.CharField(max_length=10, null=True, blank=True)
    attempt_count = models.SmallIntegerField(default=0, db_default=0)
    max_attempts = models.SmallIntegerField(default=3, db_default=3)
    retry_interval_seconds = models.IntegerField(default=60, db_default=60)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.TextField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    payload_snapshot = models.JSONField(default=dict, db_default={})
    provider_message_id = models.TextField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "notifications"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status__in=("PENDING", "SENDING", "RETRY_WAIT", "SENT",
                      "FAILED", "UNKNOWN", "CANCELLED"))
                ),
                name="notification_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(recipient_email__isnull=True, recipient_type__isnull=True)
                    | Q(recipient_email__isnull=False, recipient_type__isnull=False,
                      recipient_type__in=("SCHOOL", "CONTACT"))
                ),
                name="notification_recipient_pair",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__gte=0, max_attempts__gte=1, retry_interval_seconds__gte=1),
                name="notification_retry_values",
            ),
            models.CheckConstraint(
                condition=~Q(status="SENT") | Q(sent_at__isnull=False, recipient_email__isnull=False),
                name="notification_sent_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["project", "notification_type"]),
        ]


class BackupAccessRequest(models.Model):
    backup_access_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    request_key = models.UUIDField()
    status = models.CharField(max_length=15, default="PENDING", db_default="PENDING")
    decision_actor = models.CharField(max_length=10, null=True, blank=True)
    reviewed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    decision_reason = models.TextField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "backup_access_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"],
                name="uniq_backup_request",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(opened_at__isnull=False),
                name="uniq_opened_project_backup",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(status__in=ACTIVE_BACKUP_STATES),
                name="uniq_active_project_backup",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=(*ACTIVE_BACKUP_STATES, "REJECTED", "EXPIRED",
                      "OPEN_FAILED", "CLOSED"))
                ),
                name="backup_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="REJECTED") | Q(
                      reviewed_by_user__isnull=False, decision_reason__isnull=False, decision_reason__regex=r"\S")
                ),
                name="backup_rejection_details",
            ),
            models.CheckConstraint(
                condition=~Q(status="OPEN") | Q(opened_at__isnull=False),
                name="backup_open_timestamp",
            ),
            models.CheckConstraint(
                condition=~Q(status="CLOSED") | Q(closed_at__isnull=False),
                name="backup_closed_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]


class CapacityPool(models.Model):
    pool_id = models.SmallIntegerField(primary_key=True)
    provider_project = models.OneToOneField(
        "ProviderProject",
        on_delete=models.PROTECT,
        related_name="+",
    )
    total_vcpus = models.IntegerField()
    total_ram_mib = models.IntegerField()
    total_storage_gib = models.IntegerField()
    reservation_enabled = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "capacity_pools"
        constraints = [
            models.CheckConstraint(
                condition=Q(total_vcpus__gt=0, total_ram_mib__gt=0, total_storage_gib__gt=0),
                name="capacity_limits_positive",
            ),
        ]


class VMFlavor(models.Model):
    flavor_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_project = models.ForeignKey("ProviderProject", on_delete=models.PROTECT, related_name="+")
    flavor_ref = models.TextField()
    name = models.CharField(max_length=100)
    vcpus = models.IntegerField()
    ram_mib = models.IntegerField()
    root_disk_gib = models.IntegerField()
    enabled = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "vm_flavors"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_project", "flavor_ref"],
                name="uniq_provider_flavor_ref",
            ),
            models.UniqueConstraint(
                fields=["provider_project", "name"],
                name="uniq_provider_flavor_name",
            ),
            models.CheckConstraint(
                condition=Q(vcpus__gt=0, ram_mib__gt=0, root_disk_gib__gt=0),
                name="flavor_resources_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["provider_project", "enabled"]),
        ]


class VMImage(models.Model):
    image_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_project = models.ForeignKey("ProviderProject", on_delete=models.PROTECT, related_name="+")
    image_ref = models.TextField()
    display_name = models.CharField(max_length=100)
    default_ssh_user = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "vm_images"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_project", "image_ref"],
                name="uniq_provider_image_ref",
            ),
        ]
        indexes = [
            models.Index(fields=["provider_project", "enabled"]),
        ]
