import json
import logging
import math
import re
import uuid
from functools import wraps

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.csrf import csrf_failure as django_csrf_failure
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET

from . import signup as service
from .mail import delivery_mode

logger = logging.getLogger(__name__)


def error_response(error):
    response = JsonResponse({"error": {"code": error.code, "message": error.message, "details": error.details}},
                            status=error.status)
    if error.status == 429:
        response["Retry-After"] = str(error.details["retry_after_seconds"])
    return response


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/v1/auth/"):
        response = error_response(service.SignupError("CSRF_FAILED", "CSRF 토큰을 확인해 주세요.", 403))
        response["Cache-Control"] = "no-store"
        return response
    return django_csrf_failure(request, reason=reason)


def signup_post(fields, optional=()):
    def decorate(view):
        @never_cache
        @sensitive_post_parameters()
        @wraps(view)
        @sensitive_variables("data")
        def wrapped(request):
            if request.method != "POST":
                response = error_response(service.SignupError("VALIDATION_ERROR", "POST 요청이 필요합니다.", 405))
                response["Allow"] = "POST"
                return response
            try:
                if request.content_type != "application/json":
                    raise service.invalid({"body": "application/json 요청이 필요합니다."})
                try:
                    data = json.loads(request.body)
                except RequestDataTooBig:
                    raise service.invalid({"body": "요청 본문이 너무 큽니다."}) from None
                except (ValueError, UnicodeError):
                    raise service.invalid({"body": "올바른 JSON 객체가 필요합니다."}) from None
                if not isinstance(data, dict):
                    raise service.invalid({"body": "JSON 객체가 필요합니다."})
                invalid_fields = (set(data) - set(fields) - set(optional)) | (set(fields) - set(data))
                if invalid_fields:
                    raise service.invalid({k: "누락되었거나 허용되지 않는 필드입니다." for k in sorted(invalid_fields)})
                if not request.META.get("HTTP_X_CSRFTOKEN"):
                    raise service.SignupError("CSRF_FAILED", "CSRF 헤더가 필요합니다.", 403)
                return view(request, data)
            except service.SignupError as error:
                return error_response(error)
            except Exception as error:
                # JSON의 비밀번호·번호와 내부 예외를 디버그 응답/로그로 노출하지 않는다.
                logger.error("학생 가입 API 처리 실패 (%s)", type(error).__name__)
                return error_response(service.SignupError("INTERNAL_ERROR", "요청 처리 중 오류가 발생했습니다.", 500))
        return wrapped
    return decorate


def timestamp(value):
    return timezone.localtime(value).isoformat()


@never_cache
@require_GET
@ensure_csrf_cookie
def csrf(request):
    if service.FLOW_SESSION_KEY not in request.session:
        request.session[service.FLOW_SESSION_KEY] = str(uuid.uuid4())
    return JsonResponse({"csrf_token": get_token(request), "email_delivery": delivery_mode()})


@signup_post({"school_email"}, optional={"flow_id"})
def email_challenge(request, data):
    email = service.email_address(data["school_email"])
    flow, _ = service.identifiers(data, request.session, issuing=True)
    challenge = service.issue(flow, email, request.META.get("REMOTE_ADDR", ""))
    now = timezone.now()
    return JsonResponse({
        "flow_id": str(challenge.flow_id), "challenge_id": str(challenge.pk), "target_email": email,
        "expires_at": timestamp(challenge.expires_at),
        "expires_in_seconds": max(0, math.ceil((challenge.expires_at - now).total_seconds())),
        "resend_available_at": timestamp(challenge.resend_available_at),
        "resend_cooldown_seconds": max(0, math.ceil((challenge.resend_available_at - now).total_seconds())),
    })


@signup_post({"flow_id", "challenge_id", "school_email", "verification_code"})
def verify_challenge(request, data):
    email = service.email_address(data["school_email"])
    flow, challenge_id = service.identifiers(data, request.session)
    code = data["verification_code"]
    if not isinstance(code, str) or re.fullmatch(r"[0-9]{6}", code) is None:
        raise service.challenge_error()
    challenge = service.verify(flow, challenge_id, email, code, request.META.get("REMOTE_ADDR", ""))
    return JsonResponse({
        "flow_id": str(flow), "challenge_id": str(challenge_id), "school_email": email, "verified": True,
        "verified_at": timestamp(challenge.verified_at), "grant_expires_at": timestamp(challenge.grant_expires_at),
        "message": "인증되었습니다.",
    })


@signup_post({"flow_id", "challenge_id", "school_email", "name", "department", "login_id",
              "password", "password_confirm"})
def signup(request, data):
    email = service.email_address(data["school_email"])
    flow, challenge_id = service.identifiers(data, request.session)
    user = service.signup(flow, challenge_id, email, data)
    return JsonResponse({"user": {
        "user_id": str(user.pk), "login_id": user.login_id, "account_role": user.account_role,
        "member_type": user.member_type, "name": user.name, "department": user.department,
        "school_email": user.school_email, "school_email_verified_at": timestamp(user.school_email_verified_at),
        "notification_email_type": user.notification_email_type, "created_at": timestamp(user.created_at),
    }}, status=201)
