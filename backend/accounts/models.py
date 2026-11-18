import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, login_id, password=None, **fields):
        user = self.model(login_id=login_id, **fields)
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    login_id = models.CharField(max_length=32, unique=True)
    account_role = models.CharField(
        max_length=10, choices=[("USER", "사용자"), ("ADMIN", "관리자")],
        default="USER", db_default="USER",
    )
    member_type = models.CharField(max_length=10, null=True, blank=True)
    name = models.CharField(max_length=40)
    department = models.CharField(max_length=100, null=True, blank=True)
    nickname = models.CharField(max_length=30, null=True, blank=True)

    # Django 인증이 사용하는 속성명과 SSP 명세의 DB 열 이름을 연결한다.
    password = models.TextField(db_column="password_hash")
    last_login = models.DateTimeField(db_column="last_login_at", null=True, blank=True)
    password_changed_at = models.DateTimeField(default=timezone.now, db_default=Now())
    school_email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    school_email_verified_at = models.DateTimeField(null=True, blank=True)
    contact_email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    contact_email_verified_at = models.DateTimeField(null=True, blank=True)
    notification_email_type = models.CharField(
        max_length=10, choices=[("SCHOOL", "학교 이메일"), ("CONTACT", "개인 이메일")],
        default="SCHOOL", db_default="SCHOOL",
    )
    account_status = models.CharField(
        max_length=15, choices=[("ACTIVE", "활성"), ("SUSPENDED", "정지")],
        default="ACTIVE", db_default="ACTIVE",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    objects = UserManager()
    USERNAME_FIELD = "login_id"
    EMAIL_FIELD = "school_email"

    # 포털의 관리자 역할과 Django 내장 관리 사이트 권한은 독립적이다.
    is_staff = False
    is_superuser = False

    @property
    def is_active(self):
        return self.account_status == "ACTIVE"

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                name="users_role_profile_valid",
                condition=(
                    Q(account_role="ADMIN", member_type__isnull=True)
                    | (
                        Q(account_role="USER", member_type__isnull=False,
                          department__isnull=False, school_email__isnull=False,
                          school_email_verified_at__isnull=False)
                        & ~Q(member_type="") & ~Q(department="") & ~Q(school_email="")
                    )
                ),
            ),
            models.CheckConstraint(
                name="users_status_valid",
                condition=Q(account_status__in=["ACTIVE", "SUSPENDED"]),
            ),
            models.CheckConstraint(
                name="users_contact_verified_pair",
                condition=(
                    Q(contact_email__isnull=True, contact_email_verified_at__isnull=True)
                    | (Q(contact_email__isnull=False, contact_email_verified_at__isnull=False)
                       & ~Q(contact_email=""))
                ),
            ),
            models.CheckConstraint(
                name="users_notification_target_valid",
                condition=Q(notification_email_type="SCHOOL")
                | Q(notification_email_type="CONTACT", contact_email_verified_at__isnull=False),
            ),
        ]

    def __str__(self):
        return self.login_id


class AuthChallenge(models.Model):
    challenge_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    purpose = models.CharField(max_length=30)
    target_email = models.CharField(max_length=254)
    flow_id = models.UUIDField()
    secret_digest = models.TextField()
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    grant_expires_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.IntegerField(default=0, db_default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    resend_available_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "auth_challenges"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(purpose__in=("SIGNUP_SCHOOL_EMAIL", "REVERIFY_SCHOOL_EMAIL",
                      "VERIFY_CONTACT_EMAIL", "RESET_PASSWORD"))
                ),
                name="purpose_valid",
            ),
            models.CheckConstraint(
                condition=Q(purpose="SIGNUP_SCHOOL_EMAIL") | Q(user__isnull=False),
                name="user_required",
            ),
            models.CheckConstraint(
                condition=Q(failed_attempts__gte=0),
                name="challenge_attempts_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(grant_expires_at__isnull=True) | Q(
                      verified_at__isnull=False, grant_expires_at__gt=F("verified_at"))
                ),
                name="challenge_grant_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(consumed_at__isnull=True) | Q(
                      verified_at__isnull=False, consumed_at__gte=F("verified_at"), revoked_at__isnull=True)
                ),
                name="challenge_consumption_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["flow_id", "purpose"]),
            models.Index(fields=["user", "purpose"]),
            models.Index(fields=["target_email", "purpose"]),
            models.Index(fields=["expires_at"]),
        ]
