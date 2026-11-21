import logging

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from .models import AuthChallenge
from .mail import delivery_mode, failure_code, missing_smtp_settings
from .signup import PURPOSE, digest

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, max_retries=3)
@sensitive_variables("code")
def send_signup_email(self, challenge_id, code):
    challenge = AuthChallenge.objects.filter(pk=challenge_id, purpose=PURPOSE).first()
    if (not challenge or challenge.revoked_at or challenge.consumed_at or challenge.verified_at
            or challenge.expires_at <= timezone.now()
            or not constant_time_compare(challenge.secret_digest, digest(challenge, code))):
        return
    try:
        mode = delivery_mode()
        if mode == "other" or (mode == "smtp" and missing_smtp_settings()):
            raise ImproperlyConfigured("가입 메일 설정 확인 필요")
        if settings.EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend":
            settings.EMAIL_FILE_PATH.mkdir(mode=0o700, parents=True, exist_ok=True)
        sent = send_mail(
            "SU Cloud 학교 이메일 인증",
            f"인증번호: {code}\n발급 후 10분 안에 입력해 주세요. 본인이 요청하지 않았다면 무시해 주세요.",
            settings.DEFAULT_FROM_EMAIL, [challenge.target_email], fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("인증메일 접수 실패")
        logger.info("signup_mail_accepted challenge_id=%s mode=%s", challenge_id, mode)
    except Exception as error:
        logger.warning("signup_mail_failed challenge_id=%s category=%s retry=%s",
                       challenge_id, failure_code(error), self.request.retries)
        if self.request.retries < self.max_retries:
            # SMTP 예외의 본문·주소를 일반 로그에 노출하지 않는다.
            raise self.retry(exc=RuntimeError("인증메일 발송 실패"), countdown=30,
                             argsrepr="(<challenge>, <redacted>)") from None
        AuthChallenge.objects.filter(pk=challenge.pk, consumed_at__isnull=True, verified_at__isnull=True).update(
            revoked_at=timezone.now(), updated_at=timezone.now())
