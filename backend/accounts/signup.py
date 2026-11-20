"""학생 가입 규칙과 PostgreSQL 일회성 인증 소비."""
import math
import re
import secrets
import string
import uuid
from datetime import timedelta

import redis
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.debug import sensitive_variables

from provisioning.models import ActivityEvent
from .models import AuthChallenge, User

PURPOSE = "SIGNUP_SCHOOL_EMAIL"
FLOW_SESSION_KEY = "signup_flow_id"


class SignupError(Exception):
    def __init__(self, code, message, status=400, details=None):
        self.code, self.message, self.status = code, message, status
        self.details = details or {}
        super().__init__(code)


def invalid(fields):
    return SignupError("VALIDATION_ERROR", "입력값을 확인해 주세요.", details={"fields": fields})


def challenge_error():
    return SignupError("CHALLENGE_INVALID_OR_EXPIRED", "인증이 유효하지 않거나 만료되었습니다.")


def email_address(value):
    if not isinstance(value, str):
        raise invalid({"school_email": "학교 이메일 문자열이 필요합니다."})
    value = value.strip().lower()
    try:
        if len(value) > 254 or not value.isascii() or not value.endswith("@syuin.ac.kr"):
            raise ValidationError("email")
        validate_email(value)
    except ValidationError:
        raise invalid({"school_email": "@syuin.ac.kr 학교 이메일을 입력해 주세요."}) from None
    return value


def identifiers(data, session, *, issuing=False):
    flow = data.get("flow_id")
    if issuing and flow is None:
        flow = session.get(FLOW_SESSION_KEY)
        if flow is None:
            raise challenge_error()
    identifiers = {"flow_id": flow}
    if not issuing:
        identifiers["challenge_id"] = data.get("challenge_id")
    for field, value in identifiers.items():
        try:
            if not isinstance(value, str):
                raise ValueError
            identifiers[field] = uuid.UUID(value)
        except ValueError:
            raise invalid({field: "올바른 UUID 문자열이 필요합니다."}) from None
    flow = identifiers["flow_id"]
    if str(flow) != session.get(FLOW_SESSION_KEY):
        raise challenge_error()
    return flow, identifiers.get("challenge_id")


def digest(challenge, code):
    value = f"{challenge.challenge_id}:{challenge.flow_id}:{challenge.target_email}:{code}"
    return salted_hmac("accounts.signup.otp", value, algorithm="sha256").hexdigest()


def lock_flow_email(flow, email):
    # 행이 없는 최초 발급도 잠근다. 모든 경로에서 같은 잠금 순서로 교착을 피한다.
    keys = sorted(int(salted_hmac("accounts.signup.lock", k).hexdigest()[:15], 16)
                  for k in (f"flow:{flow}", f"email:{email}"))
    with connection.cursor() as cursor:
        for key in keys:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


# 이메일/IP 두 한도를 원자적으로 검사·증가시켜 병렬 요청 우회를 막는다.
RATE_SCRIPT = """
local wait = 0
for i = 1, 2 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= tonumber(ARGV[i]) then
    wait = math.max(wait, 1, redis.call('TTL', KEYS[i]))
  end
end
if wait > 0 then return wait end
for i = 1, 2 do
  if redis.call('INCR', KEYS[i]) == 1 then redis.call('EXPIRE', KEYS[i], ARGV[3]) end
end
return 0
"""


def rate_limit(action, email, ip):
    client = redis.Redis.from_url(settings.SIGNUP_RATE_REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    keys = [f"{settings.SIGNUP_RATE_PREFIX}:{action}:{kind}:"
            + salted_hmac("accounts.signup.rate", value, algorithm="sha256").hexdigest()
            for kind, value in (("email", email), ("ip", ip))]
    limits = settings.SIGNUP_ISSUE_LIMITS if action == "issue" else settings.SIGNUP_VERIFY_LIMITS
    wait = client.eval(RATE_SCRIPT, 2, *keys, *limits, settings.SIGNUP_RATE_WINDOW_SECONDS)
    if wait:
        raise SignupError("TOO_MANY_REQUESTS", "잠시 후 다시 시도해 주세요.", 429,
                          {"retry_after_seconds": wait})


def duplicate(email, login_id=None):
    query = Q(school_email__iexact=email)
    if login_id is not None:
        query |= Q(login_id=login_id)
    return User.objects.filter(query).exists()


def duplicate_error():
    return SignupError("DUPLICATE_ACCOUNT", "이미 등록된 학번 또는 학교 이메일입니다.", 409)


@sensitive_variables("code")
def issue(flow, email, ip):
    from .tasks import send_signup_email

    rate_limit("issue", email, ip)
    with transaction.atomic():
        lock_flow_email(flow, email)
        now = timezone.now()
        if duplicate(email):
            raise duplicate_error()
        previous = AuthChallenge.objects.filter(purpose=PURPOSE).filter(Q(flow_id=flow) | Q(target_email=email))
        cooling = previous.filter(last_sent_at__isnull=False, resend_available_at__gt=now).order_by(
            "-resend_available_at").first()
        if cooling:
            raise SignupError("COOLDOWN_ACTIVE", "인증번호 재발송 대기 중입니다.", 429,
                              {"retry_after_seconds": math.ceil((cooling.resend_available_at - now).total_seconds())})
        previous.filter(flow_id=flow, consumed_at__isnull=True, revoked_at__isnull=True).update(
            revoked_at=now, updated_at=now)
        challenge = AuthChallenge(
            flow_id=flow, purpose=PURPOSE, target_email=email, expires_at=now + timedelta(minutes=10),
            last_sent_at=now, resend_available_at=now + timedelta(seconds=60),
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge.secret_digest = digest(challenge, code)
        challenge.save()

        def enqueue():
            try:
                send_signup_email.apply_async(
                    args=[str(challenge.pk), code], argsrepr="(<challenge>, <redacted>)",
                    expires=challenge.expires_at, retry=False,
                )
            except Exception:
                AuthChallenge.objects.filter(pk=challenge.pk, consumed_at__isnull=True).update(
                    revoked_at=timezone.now(), last_sent_at=None, updated_at=timezone.now())
                raise SignupError("INTERNAL_ERROR", "메일 발송 접수에 실패했습니다. 다시 시도해 주세요.", 500) from None

        transaction.on_commit(enqueue)
    return challenge


def locked_challenge(flow, challenge_id, email):
    lock_flow_email(flow, email)
    challenge = AuthChallenge.objects.select_for_update().filter(
        pk=challenge_id, flow_id=flow, purpose=PURPOSE, target_email=email, user__isnull=True,
    ).first()
    if (challenge is None or challenge.revoked_at or challenge.consumed_at
            or challenge.failed_attempts >= settings.SIGNUP_MAX_FAILED_ATTEMPTS):
        raise challenge_error()
    return challenge


@sensitive_variables("code")
def verify(flow, challenge_id, email, code, ip):
    rate_limit("verify", email, ip)
    failure = False
    with transaction.atomic():
        challenge = locked_challenge(flow, challenge_id, email)
        now = timezone.now()
        if challenge.expires_at <= now:
            raise challenge_error()
        if not constant_time_compare(challenge.secret_digest, digest(challenge, code)):
            challenge.failed_attempts += 1
            if challenge.failed_attempts >= settings.SIGNUP_MAX_FAILED_ATTEMPTS:
                challenge.revoked_at = now
            challenge.save(update_fields=["failed_attempts", "revoked_at", "updated_at"])
            failure = True
        elif challenge.verified_at is None:
            challenge.verified_at = now
            challenge.grant_expires_at = now + timedelta(seconds=settings.SIGNUP_GRANT_SECONDS)
            challenge.save(update_fields=["verified_at", "grant_expires_at", "updated_at"])
        elif challenge.grant_expires_at is None or challenge.grant_expires_at <= now:
            raise challenge_error()
    # 실패 횟수 갱신까지 롤백하지 않도록 트랜잭션 밖에서 오류를 반환한다.
    if failure:
        raise challenge_error()
    return challenge


@sensitive_variables("data", "password")
def validate_profile(data):
    errors = {}
    for field, limit in (("name", 40), ("department", 100), ("login_id", 32)):
        value = data.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.strip() or "\x00" in value:
            errors[field] = f"1~{limit}자의 문자열이 필요합니다."
    password = data.get("password")
    if not isinstance(password, str) or not 8 <= len(password) <= 64 or "\x00" in password:
        errors["password"] = "8~64자의 비밀번호가 필요합니다."
    elif sum((bool(re.search(r"[A-Za-z]", password)), bool(re.search(r"[0-9]", password)),
              any(c in string.punctuation for c in password))) < 2:
        errors["password"] = "영문·숫자·특수기호 중 두 종류 이상을 조합해 주세요."
    if not isinstance(data.get("password_confirm"), str) or password != data.get("password_confirm"):
        errors["password_confirm"] = "비밀번호 확인이 일치해야 합니다."
    if errors:
        raise invalid(errors)


@sensitive_variables("data")
def signup(flow, challenge_id, email, data):
    validate_profile(data)
    try:
        with transaction.atomic():
            challenge = locked_challenge(flow, challenge_id, email)
            now = timezone.now()
            if not challenge.verified_at or not challenge.grant_expires_at or challenge.grant_expires_at <= now:
                raise challenge_error()
            if duplicate(email, data["login_id"]):
                raise duplicate_error()
            user = User.objects.create_user(
                login_id=data["login_id"], password=data["password"], name=data["name"],
                department=data["department"], account_role="USER", member_type="STUDENT",
                school_email=email, school_email_verified_at=challenge.verified_at, notification_email_type="SCHOOL",
            )
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at", "updated_at"])
            ActivityEvent.objects.create(
                actor_type="USER", actor_user=user, target_user=user, event_type="USER_SIGNED_UP",
                payload_snapshot={"schema_version": 1, "user_id": str(user.pk),
                                  "login_id": user.login_id, "account_role": "USER", "member_type": "STUDENT"},
            )
    except (IntegrityError, ValidationError):
        # 다른 이메일로 같은 학번이 동시에 가입한 경우 DB 유일 제약이 최종 방어선이다.
        if duplicate(email, data["login_id"]):
            raise duplicate_error() from None
        raise
    return user
