import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import redis
from django.conf import settings
from django.core import mail
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from provisioning.models import ActivityEvent
from . import signup as service
from .models import AuthChallenge, User
from .tasks import send_signup_email

ROOT = "/api/v1/auth/"
ISSUE = ROOT + "signup/email-challenge"
VERIFY = ISSUE + "/verify"
SIGNUP = ROOT + "signup"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SIGNUP_RATE_REDIS_URL="redis://127.0.0.1:6379/15",
    SIGNUP_MAX_FAILED_ATTEMPTS=5, SIGNUP_GRANT_SECONDS=1800,
    SIGNUP_RATE_WINDOW_SECONDS=900, SIGNUP_ISSUE_LIMITS=(5, 30), SIGNUP_VERIFY_LIMITS=(20, 100),
)
class SignupTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql", "경합 검증에는 실제 PostgreSQL이 필요합니다.")
        self.prefix = "test:signup:" + uuid.uuid4().hex
        self.policy = override_settings(SIGNUP_RATE_PREFIX=self.prefix)
        self.policy.enable()
        self.addCleanup(self.policy.disable)
        self.redis = redis.Redis.from_url(settings.SIGNUP_RATE_REDIS_URL)
        self.redis.ping()
        self.addCleanup(self.clean_limits)
        mail.get_connection()
        mail.outbox.clear()
        self.client = self.browser()

    def clean_limits(self):
        keys = list(self.redis.scan_iter(self.prefix + ":*"))
        if keys:
            self.redis.delete(*keys)

    def browser(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(ROOT + "csrf").status_code, 200)
        return client

    def post(self, path, data, client=None, **extra):
        client = client or self.client
        return client.post(path, json.dumps(data), content_type="application/json",
                           HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value, **extra)

    def assert_error(self, response, code, status=400):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["error"]["code"], code)

    def issue(self, email="Cloud.Student+tag@SYUIN.AC.KR", client=None, flow=None):
        response = self.post(ISSUE, {"flow_id": flow, "school_email": email}, client)
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        result["school_email"] = result["target_email"]
        result["verification_code"] = re.search(r"인증번호: ([0-9]{6})", mail.outbox[-1].body)[1]
        return result

    def verify(self, issued, client=None):
        return self.post(VERIFY, {k: issued[k] for k in
                                 ("flow_id", "challenge_id", "school_email", "verification_code")}, client)

    def verified(self, email="student@syuin.ac.kr", client=None):
        issued = self.issue(email, client)
        self.assertEqual(self.verify(issued, client).status_code, 200)
        return issued

    def profile(self, issued, **changes):
        data = {k: issued[k] for k in ("flow_id", "challenge_id", "school_email")}
        data.update(name="홍길동", department="컴퓨터공학부", login_id="00123456",
                    password="Cloud123!", password_confirm="Cloud123!")
        data.update(changes)
        return data

    def existing_user(self, login="old", email="old@syuin.ac.kr"):
        return User.objects.create_user(login, "Existing1!", name="기존", department="학과",
                                        member_type="STUDENT", school_email=email,
                                        school_email_verified_at=timezone.now())

    def test_complete_signup_and_response_contract(self):
        issued = self.issue("  Cloud.Student+tag@SYUIN.AC.KR  ")
        self.assertEqual(issued["target_email"], "cloud.student+tag@syuin.ac.kr")
        self.assertEqual(issued["expires_in_seconds"], 600)
        self.assertEqual(issued["resend_cooldown_seconds"], 60)
        challenge = AuthChallenge.objects.get()
        self.assertEqual(challenge.expires_at - challenge.last_sent_at, timedelta(minutes=10))
        self.assertNotEqual(challenge.secret_digest, issued["verification_code"])
        self.assertIsNone(challenge.user_id)
        response = self.verify(issued)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["verified"])
        self.assertEqual(response.json()["message"], "인증되었습니다.")
        challenge.refresh_from_db()
        self.assertEqual(challenge.grant_expires_at - challenge.verified_at, timedelta(minutes=30))
        response = self.post(SIGNUP, self.profile(issued))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(set(response.json()["user"]), {
            "user_id", "login_id", "account_role", "member_type", "name", "department", "school_email",
            "school_email_verified_at", "notification_email_type", "created_at"})
        user = User.objects.get()
        self.assertEqual((user.login_id, user.account_role, user.member_type, user.notification_email_type),
                         ("00123456", "USER", "STUDENT", "SCHOOL"))
        self.assertTrue(user.check_password("Cloud123!"))
        self.assertNotEqual(user.password, "Cloud123!")
        self.assertEqual(user.school_email_verified_at, challenge.verified_at)
        self.assertTrue(response.json()["user"]["created_at"].endswith("+09:00"))
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)
        event = ActivityEvent.objects.get()
        self.assertEqual((event.event_type, event.actor_user_id, event.target_user_id),
                         ("USER_SIGNED_UP", user.pk, user.pk))
        self.assertEqual(event.payload_snapshot["schema_version"], 1)
        self.assertNotIn("_auth_user_id", self.client.session)
        for secret in ("Cloud123!", issued["verification_code"], "secret_digest", "password"):
            self.assertNotIn(secret, response.content.decode())
            self.assertNotIn(secret, json.dumps(event.payload_snapshot))
        self.assertIn("no-store", response["Cache-Control"])

    def test_invalid_school_emails(self):
        for value in (None, 123, "x@gmail.com", "x@sub.syuin.ac.kr", "x@syuin.ac.kr.evil",
                      "@syuin.ac.kr", "한글@syuin.ac.kr", "a b@syuin.ac.kr", "x" * 243 + "@syuin.ac.kr"):
            with self.subTest(value=value):
                self.assert_error(self.post(ISSUE, {"school_email": value}), "VALIDATION_ERROR")
        self.assertFalse(AuthChallenge.objects.exists())

    def test_email_case_duplicate_and_aliases_preserved(self):
        self.existing_user(email="Cloud.Student+TAG@syuin.ac.kr")
        self.assert_error(self.post(ISSUE, {"school_email": " cloud.student+tag@SYUIN.AC.KR "}),
                          "DUPLICATE_ACCOUNT", 409)
        self.assertEqual(service.email_address(" A.B+tag@syuin.ac.kr "), "a.b+tag@syuin.ac.kr")

    def test_cooldown_resend_and_previous_grant_revoked(self):
        first = self.verified()
        self.assert_error(self.post(ISSUE, {"flow_id": first["flow_id"], "school_email": first["school_email"]}),
                          "COOLDOWN_ACTIVE", 429)
        self.assert_error(self.post(ISSUE, {"school_email": first["school_email"]}, self.browser()),
                          "COOLDOWN_ACTIVE", 429)
        self.assert_error(self.post(ISSUE, {"flow_id": first["flow_id"], "school_email": "new@syuin.ac.kr"}),
                          "COOLDOWN_ACTIVE", 429)
        old = AuthChallenge.objects.get()
        with patch("accounts.signup.timezone.now", return_value=old.resend_available_at):
            second = self.issue(first["school_email"], flow=first["flow_id"])
        self.assertNotEqual(first["challenge_id"], second["challenge_id"])
        old.refresh_from_db()
        self.assertIsNotNone(old.revoked_at)
        self.assert_error(self.verify(first), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assert_error(self.post(SIGNUP, self.profile(first)), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assertEqual(self.verify(second).status_code, 200)

    def test_changed_email_invalidates_previous_challenge(self):
        first = self.issue()
        old = AuthChallenge.objects.get()
        with patch("accounts.signup.timezone.now", return_value=old.resend_available_at):
            self.issue("other@syuin.ac.kr", flow=first["flow_id"])
        self.assert_error(self.verify(first), "CHALLENGE_INVALID_OR_EXPIRED")

    def test_wrong_codes_increment_and_revoke_at_five(self):
        issued = self.issue()
        issued["verification_code"] = "000000" if issued["verification_code"] != "000000" else "111111"
        for attempt in range(1, 6):
            self.assert_error(self.verify(issued), "CHALLENGE_INVALID_OR_EXPIRED")
            challenge = AuthChallenge.objects.get()
            self.assertEqual(challenge.failed_attempts, attempt)
            self.assertEqual(challenge.revoked_at is not None, attempt == 5)
        self.assert_error(self.verify(issued), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assertEqual(AuthChallenge.objects.get().failed_attempts, 5)

    def test_expiry_at_exact_deadline(self):
        issued = self.issue()
        challenge = AuthChallenge.objects.get()
        with patch("accounts.signup.timezone.now", return_value=challenge.expires_at):
            self.assert_error(self.verify(issued), "CHALLENGE_INVALID_OR_EXPIRED")

    def test_code_format_is_six_ascii_digits(self):
        issued = self.issue()
        for code in (123456, "12345", "1234567", "１２３４５６", None):
            with self.subTest(code=code):
                self.assert_error(self.verify(dict(issued, verification_code=code)), "CHALLENGE_INVALID_OR_EXPIRED")

    def test_verify_does_not_extend_grant(self):
        issued = self.verified()
        old = AuthChallenge.objects.get()
        with patch("accounts.signup.timezone.now", return_value=old.verified_at + timedelta(minutes=1)):
            self.assertEqual(self.verify(issued).status_code, 200)
        new = AuthChallenge.objects.get()
        self.assertEqual((old.verified_at, old.grant_expires_at), (new.verified_at, new.grant_expires_at))

    def test_other_browser_flow_email_and_challenge_rejected(self):
        issued = self.verified()
        stranger = self.browser()
        self.assert_error(self.verify(issued, stranger), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assert_error(self.post(SIGNUP, self.profile(issued), stranger), "CHALLENGE_INVALID_OR_EXPIRED")
        for field, value in (("flow_id", str(uuid.uuid4())), ("challenge_id", str(uuid.uuid4())),
                             ("school_email", "other@syuin.ac.kr")):
            with self.subTest(field=field):
                changed = dict(issued, **{field: value})
                self.assert_error(self.verify(changed), "CHALLENGE_INVALID_OR_EXPIRED")
                self.assert_error(self.post(SIGNUP, self.profile(changed)), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assert_error(self.post(ISSUE, {"flow_id": issued["flow_id"], "school_email": "new@syuin.ac.kr"}, stranger),
                          "CHALLENGE_INVALID_OR_EXPIRED")

    def test_malformed_uuids_are_validation_errors(self):
        issued = self.verified()
        for field in ("flow_id", "challenge_id"):
            for value in (None, True, 123, [], {}, "", "not-a-uuid"):
                with self.subTest(field=field, value=value):
                    changed = dict(issued, **{field: value})
                    responses = [self.verify(changed), self.post(SIGNUP, self.profile(changed))]
                    if field == "flow_id" and value is not None:
                        responses.append(self.post(ISSUE, {"flow_id": value, "school_email": issued["school_email"]}))
                    for response in responses:
                        self.assert_error(response, "VALIDATION_ERROR")
                        self.assertIn(field, response.json()["error"]["details"]["fields"])
        self.assertFalse(User.objects.exists())
        self.assertIsNone(AuthChallenge.objects.get().consumed_at)

    def test_other_purpose_or_user_challenge_rejected(self):
        issued = self.verified()
        user = self.existing_user()
        AuthChallenge.objects.update(purpose="RESET_PASSWORD", user=user)
        self.assert_error(self.verify(issued), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        AuthChallenge.objects.update(purpose=service.PURPOSE)
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")

    def test_unverified_revoked_and_consumed_rejected(self):
        issued = self.issue()
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assertEqual(self.verify(issued).status_code, 200)
        AuthChallenge.objects.update(revoked_at=timezone.now())
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        AuthChallenge.objects.update(revoked_at=None)
        self.assertEqual(self.post(SIGNUP, self.profile(issued)).status_code, 201)
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assert_error(self.verify(issued), "CHALLENGE_INVALID_OR_EXPIRED")

    def test_grant_deadline_and_separate_code_expiry(self):
        issued = self.verified()
        challenge = AuthChallenge.objects.get()
        with patch("accounts.signup.timezone.now", return_value=challenge.grant_expires_at):
            self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        with patch("accounts.signup.timezone.now", return_value=challenge.expires_at + timedelta(minutes=1)):
            self.assertEqual(self.post(SIGNUP, self.profile(issued)).status_code, 201)

    def test_duplicate_login_or_email_does_not_consume(self):
        issued = self.verified()
        for kwargs in ({"login": "00123456"}, {"email": "STUDENT@syuin.ac.kr"}):
            user = self.existing_user(**kwargs)
            self.assert_error(self.post(SIGNUP, self.profile(issued)), "DUPLICATE_ACCOUNT", 409)
            self.assertIsNone(AuthChallenge.objects.get().consumed_at)
            self.assertFalse(ActivityEvent.objects.exists())
            user.delete()

    def test_invalid_profile_boundaries_and_role_injection(self):
        issued = self.verified()
        changes = [{field: value} for field, value in (
            ("name", ""), ("name", "가" * 41), ("name", " "), ("department", "가" * 101),
            ("department", ""), ("login_id", "0" * 33), ("login_id", 123), ("login_id", ""),
            ("password", "a1!" + "x" * 4), ("password", "a1!" + "x" * 62),
            ("password", "abcdefgh"), ("password", "12345678"), ("password", "!!!!!!!!"),
            ("password", None), ("password_confirm", "different"), ("account_role", "ADMIN"),
            ("role", "ADMIN"), ("member_type", "ADMIN"), ("name", "a\x00b"))]
        for change in changes:
            with self.subTest(change=change):
                self.assert_error(self.post(SIGNUP, self.profile(issued, **change)), "VALIDATION_ERROR")
        self.assertFalse(User.objects.exists())
        self.assertIsNone(AuthChallenge.objects.get().consumed_at)

    def test_valid_profile_boundary_values(self):
        base = dict(name="가" * 40, department="과" * 100, login_id="0" * 32)
        for password in ("a1" * 4, "a1" * 32, "letters!", "1234567!", "a1한글비밀번호"):
            service.validate_profile(dict(base, password=password, password_confirm=password))
        issued = self.verified()
        self.assertEqual(self.post(SIGNUP, self.profile(issued, **base, password="a1" * 32,
                                                      password_confirm="a1" * 32)).status_code, 201)

    def test_leading_zero_code_and_minimum_profile_lengths(self):
        with patch("accounts.signup.secrets.randbelow", return_value=42):
            issued = self.issue()
        self.assertEqual(issued["verification_code"], "000042")
        self.assertEqual(self.verify(issued).status_code, 200)
        response = self.post(SIGNUP, self.profile(issued, name="홍", department="과", login_id="0"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["login_id"], "0")

    def test_event_failure_rolls_back_account_and_consumption(self):
        issued = self.verified()
        for failure in (RuntimeError("private failure"), IntegrityError("private constraint")):
            with patch("accounts.signup.ActivityEvent.objects.create", side_effect=failure):
                response = self.post(SIGNUP, self.profile(issued))
            self.assert_error(response, "INTERNAL_ERROR", 500)
            self.assertNotIn("private", response.content.decode())
            self.assertFalse(User.objects.exists())
            self.assertFalse(ActivityEvent.objects.exists())
            self.assertIsNone(AuthChallenge.objects.get().consumed_at)

    def test_actual_event_constraint_failure_rolls_back_and_can_retry(self):
        issued = self.verified()
        create_event = ActivityEvent.objects.create
        violated_constraints = []

        def invalid_event(**fields):
            fields["actor_type"] = "INVALID"
            try:
                return create_event(**fields)
            except IntegrityError as error:
                violated_constraints.append(error.__cause__.diag.constraint_name)
                raise

        with patch("accounts.signup.ActivityEvent.objects.create", side_effect=invalid_event):
            with self.assertLogs("accounts.views", level="ERROR"):
                response = self.post(SIGNUP, self.profile(issued))
        self.assert_error(response, "INTERNAL_ERROR", 500)
        self.assertEqual(violated_constraints, ["event_actor_valid"])
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityEvent.objects.exists())
        self.assertIsNone(AuthChallenge.objects.get().consumed_at)
        self.assertEqual(self.post(SIGNUP, self.profile(issued)).status_code, 201)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.count(), 1)

    def test_enqueue_failure_revokes_and_allows_immediate_retry(self):
        with patch("accounts.tasks.send_signup_email.apply_async", side_effect=RuntimeError("private queue error")):
            response = self.post(ISSUE, {"school_email": "student@syuin.ac.kr"})
        self.assert_error(response, "INTERNAL_ERROR", 500)
        challenge = AuthChallenge.objects.get()
        self.assertIsNotNone(challenge.revoked_at)
        self.assertIsNone(challenge.last_sent_at)
        self.issue("student@syuin.ac.kr")

    def test_stale_mail_task_does_not_send(self):
        issued = self.issue()
        mail.outbox.clear()
        AuthChallenge.objects.update(revoked_at=timezone.now())
        send_signup_email.run(issued["challenge_id"], issued["verification_code"])
        self.assertEqual(len(mail.outbox), 0)

    def test_queue_arguments_are_redacted_and_publish_follows_commit(self):
        def publish_after_commit(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(AuthChallenge.objects.filter(pk=kwargs["args"][0]).exists())

        with patch("accounts.tasks.send_signup_email.apply_async", side_effect=publish_after_commit) as publish:
            response = self.post(ISSUE, {"school_email": "student@syuin.ac.kr"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(publish.call_args.kwargs["argsrepr"], "(<challenge>, <redacted>)")
        self.assertNotIn(publish.call_args.kwargs["args"][1], response.content.decode())
        self.assertFalse(connection.in_atomic_block)

    def test_response_countdown_accounts_for_queue_publish_time(self):
        clock = [timezone.now()]

        def publish(**kwargs):
            clock[0] += timedelta(seconds=2)

        with patch("accounts.signup.timezone.now", side_effect=lambda: clock[0]):
            with patch("accounts.tasks.send_signup_email.apply_async", side_effect=publish):
                response = self.post(ISSUE, {"school_email": "student@syuin.ac.kr"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["expires_in_seconds"], 598)
        self.assertEqual(response.json()["resend_cooldown_seconds"], 58)

    def test_csrf_is_required_for_all_signup_posts(self):
        for path in (ISSUE, VERIFY, SIGNUP):
            for client in (Client(enforce_csrf_checks=True), self.client):
                self.assert_error(client.post(path, "{}", content_type="application/json"), "CSRF_FAILED", 403)
            response = self.client.post(path, "{}", content_type="application/json", HTTP_X_CSRFTOKEN="x" * 32)
            self.assert_error(response, "CSRF_FAILED", 403)
            self.assert_error(self.post(path, {}, HTTP_ORIGIN="https://evil.example"), "CSRF_FAILED", 403)
        self.assertFalse(AuthChallenge.objects.exists())

    def test_csrf_bootstrap_preserves_flow_and_admin_failure(self):
        flow = self.client.session[service.FLOW_SESSION_KEY]
        response = self.client.get(ROOT + "csrf")
        self.assertIn("csrf_token", response.json())
        self.assertEqual(self.client.session[service.FLOW_SESSION_KEY], flow)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(self.client.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.cookies["sessionid"]["samesite"], "Lax")
        response = self.client.post("/admin/login/", {})
        self.assertEqual(response.status_code, 403)
        self.assertIn("text/html", response["Content-Type"])

    def test_json_shape_and_unknown_fields(self):
        for body in ("[]", "null", "{", '{"school_email":"x@syuin.ac.kr","role":"ADMIN"}'):
            response = self.client.post(ISSUE, body, content_type="application/json",
                                        HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assert_error(response, "VALIDATION_ERROR")
        self.assert_error(self.post(ISSUE, {}), "VALIDATION_ERROR")

    def test_oversized_json_is_validation_error_for_all_signup_posts(self):
        issued = self.verified()
        for path in (ISSUE, VERIFY, SIGNUP):
            with self.subTest(path=path):
                response = self.post(path, {"school_email": "x" * (settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1)})
                self.assert_error(response, "VALIDATION_ERROR")
                self.assertIn("body", response.json()["error"]["details"]["fields"])
        self.assertEqual(AuthChallenge.objects.count(), 1)
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityEvent.objects.exists())
        self.assertIsNone(AuthChallenge.objects.get(pk=issued["challenge_id"]).consumed_at)

    def test_email_issue_limit_survives_new_browser_and_cooldown(self):
        issued = self.issue()
        for _ in range(4):
            self.assert_error(self.post(ISSUE, {"school_email": issued["school_email"]}, self.browser()),
                              "COOLDOWN_ACTIVE", 429)
        response = self.post(ISSUE, {"school_email": issued["school_email"]})
        self.assert_error(response, "TOO_MANY_REQUESTS", 429)
        self.assertGreater(response.json()["error"]["details"]["retry_after_seconds"], 0)
        self.assertIn("Retry-After", response)

    def test_ip_issue_limit_and_verify_limits(self):
        with override_settings(SIGNUP_ISSUE_LIMITS=(5, 2), SIGNUP_VERIFY_LIMITS=(2, 10)):
            issued = self.issue()
            self.assert_error(self.post(ISSUE, {"school_email": "other@syuin.ac.kr"}), "COOLDOWN_ACTIVE", 429)
            self.assert_error(self.post(ISSUE, {"school_email": "third@syuin.ac.kr"}), "TOO_MANY_REQUESTS", 429)
            self.assertEqual(self.verify(issued).status_code, 200)
            self.assertEqual(self.verify(issued).status_code, 200)
            self.assert_error(self.verify(issued), "TOO_MANY_REQUESTS", 429)
        with override_settings(SIGNUP_VERIFY_LIMITS=(20, 2)):
            self.assert_error(self.verify(dict(issued, school_email="other@syuin.ac.kr")), "TOO_MANY_REQUESTS", 429)

    def test_rate_storage_has_no_raw_email_or_ip(self):
        issued = self.issue()
        keys = list(self.redis.scan_iter(self.prefix + ":*"))
        self.assertEqual(len(keys), 2)
        for key in keys:
            self.assertNotIn(issued["school_email"].encode(), key)
            self.assertNotIn(b"127.0.0.1", key)
            self.assertGreater(self.redis.ttl(key), 0)

    def test_redis_failure_does_not_issue_or_verify(self):
        with patch("accounts.signup.redis.Redis.from_url", side_effect=redis.ConnectionError("private")):
            self.assert_error(self.post(ISSUE, {"school_email": "student@syuin.ac.kr"}), "INTERNAL_ERROR", 500)
        self.assertFalse(AuthChallenge.objects.exists())

    def test_error_logs_and_response_hide_request_secrets(self):
        issued = self.verified()
        with patch("accounts.signup.ActivityEvent.objects.create", side_effect=RuntimeError("Cloud123!")):
            with self.assertLogs("accounts.views", level="ERROR") as logs:
                response = self.post(SIGNUP, self.profile(issued))
        self.assert_error(response, "INTERNAL_ERROR", 500)
        for secret in ("Cloud123!", issued["verification_code"], issued["school_email"]):
            self.assertNotIn(secret, " ".join(logs.output))
            self.assertNotIn(secret, response.content.decode())

    def test_subsecond_rate_window_still_rejects_excess_requests(self):
        service.rate_limit("issue", "student@syuin.ac.kr", "127.0.0.1")
        keys = list(self.redis.scan_iter(self.prefix + ":*"))
        for key in keys:
            self.redis.set(key, 100, px=800)
        with self.assertRaises(service.SignupError) as error:
            service.rate_limit("issue", "student@syuin.ac.kr", "127.0.0.1")
        self.assertEqual(error.exception.code, "TOO_MANY_REQUESTS")
        self.assertEqual(error.exception.details["retry_after_seconds"], 1)

    def test_mail_retry_hides_smtp_exception_and_arguments(self):
        issued = self.issue()
        with patch("accounts.tasks.send_mail", side_effect=RuntimeError("private SMTP body")):
            with patch.object(send_signup_email, "retry", side_effect=RuntimeError("safe retry")) as retry:
                with self.assertRaisesRegex(RuntimeError, "safe retry"):
                    send_signup_email.run(issued["challenge_id"], issued["verification_code"])
        self.assertEqual(str(retry.call_args.kwargs["exc"]), "인증메일 발송 실패")
        self.assertEqual(retry.call_args.kwargs["argsrepr"], "(<challenge>, <redacted>)")

    def test_terminal_mail_failure_revokes_unverified_challenge(self):
        issued = self.issue()
        accepted_at = AuthChallenge.objects.get().last_sent_at
        self.assertIsNotNone(accepted_at)
        send_signup_email.push_request(retries=3)
        try:
            with patch("accounts.tasks.send_mail", side_effect=RuntimeError("private SMTP body")):
                send_signup_email.run(issued["challenge_id"], issued["verification_code"])
        finally:
            send_signup_email.pop_request()
        challenge = AuthChallenge.objects.get()
        self.assertIsNotNone(challenge.revoked_at)
        self.assertEqual(challenge.last_sent_at, accepted_at)

    def parallel(self, jobs):
        barrier = threading.Barrier(len(jobs))

        def run(job):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=30) for future in futures]

    def cloned_browser(self, original):
        client = Client(enforce_csrf_checks=True)
        client.cookies = original.cookies.copy()
        return client

    def in_lock_order(self, first_job, second_job):
        first_locked, second_arrived, release_first = (threading.Event() for _ in range(3))
        thread_state = threading.local()
        backend_pids = {}
        lock_flow_email = service.lock_flow_email

        def controlled_lock(flow, email):
            if thread_state.position == "second":
                second_arrived.set()
            lock_flow_email(flow, email)
            if thread_state.position == "first":
                first_locked.set()
                if not release_first.wait(timeout=10):
                    raise RuntimeError("테스트 잠금 해제 대기 시간 초과")

        def run(job, position):
            close_old_connections()
            try:
                thread_state.position = position
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pids[position] = cursor.fetchone()[0]
                return job()
            finally:
                connections.close_all()

        with patch("accounts.signup.lock_flow_email", side_effect=controlled_lock):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(run, first_job, "first")
                try:
                    self.assertTrue(first_locked.wait(timeout=5), "첫 요청이 잠금을 얻지 못했습니다.")
                    second = pool.submit(run, second_job, "second")
                    self.assertTrue(second_arrived.wait(timeout=5), "둘째 요청이 도착하지 않았습니다.")
                    # 스레드 시작 시각 대신 실제 PostgreSQL 잠금 대기를 확인한다.
                    deadline, blocked = time.monotonic() + 5, False
                    while time.monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))",
                                           [backend_pids["first"], backend_pids["second"]])
                            blocked = cursor.fetchone()[0]
                        if blocked:
                            break
                        time.sleep(0.01)
                    self.assertTrue(blocked, "둘째 요청이 첫 요청의 DB 잠금을 기다리지 않았습니다.")
                    self.assertFalse(second.done())
                finally:
                    release_first.set()
                return first.result(timeout=10), second.result(timeout=10)

    def test_signup_before_reissue_consumes_once(self):
        issued = self.verified()
        AuthChallenge.objects.update(resend_available_at=timezone.now() - timedelta(seconds=1))
        first, second = self.cloned_browser(self.client), self.cloned_browser(self.client)
        with patch("accounts.tasks.send_signup_email.apply_async"):
            signed_up, reissued = self.in_lock_order(
                lambda: self.post(SIGNUP, self.profile(issued), first),
                lambda: self.post(ISSUE, {"flow_id": issued["flow_id"], "school_email": issued["school_email"]}, second),
            )
        self.assertEqual(signed_up.status_code, 201)
        self.assert_error(reissued, "DUPLICATE_ACCOUNT", 409)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.count(), 1)
        self.assertEqual(AuthChallenge.objects.count(), 1)
        self.assertIsNotNone(AuthChallenge.objects.get().consumed_at)
        self.assertIsNone(AuthChallenge.objects.get().revoked_at)

    def test_reissue_before_signup_revokes_previous_grant(self):
        issued = self.verified()
        AuthChallenge.objects.update(resend_available_at=timezone.now() - timedelta(seconds=1))
        first, second = self.cloned_browser(self.client), self.cloned_browser(self.client)
        with patch("accounts.tasks.send_signup_email.apply_async"):
            reissued, signed_up = self.in_lock_order(
                lambda: self.post(ISSUE, {"flow_id": issued["flow_id"], "school_email": issued["school_email"]}, first),
                lambda: self.post(SIGNUP, self.profile(issued), second),
            )
        self.assertEqual(reissued.status_code, 200)
        self.assert_error(signed_up, "CHALLENGE_INVALID_OR_EXPIRED")
        old = AuthChallenge.objects.get(pk=issued["challenge_id"])
        self.assertIsNotNone(old.verified_at)
        self.assertIsNotNone(old.revoked_at)
        self.assertIsNone(old.consumed_at)
        self.assertEqual(AuthChallenge.objects.filter(revoked_at__isnull=True).count(), 1)
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityEvent.objects.exists())

    def test_verify_before_reissue_revokes_verified_grant(self):
        issued = self.issue()
        AuthChallenge.objects.update(resend_available_at=timezone.now() - timedelta(seconds=1))
        first, second = self.cloned_browser(self.client), self.cloned_browser(self.client)
        with patch("accounts.tasks.send_signup_email.apply_async"):
            verified, reissued = self.in_lock_order(
                lambda: self.verify(issued, first),
                lambda: self.post(ISSUE, {"flow_id": issued["flow_id"], "school_email": issued["school_email"]}, second),
            )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(reissued.status_code, 200)
        old = AuthChallenge.objects.get(pk=issued["challenge_id"])
        self.assertIsNotNone(old.verified_at)
        self.assertIsNotNone(old.revoked_at)
        self.assert_error(self.post(SIGNUP, self.profile(issued)), "CHALLENGE_INVALID_OR_EXPIRED")
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityEvent.objects.exists())

    def test_reissue_before_verify_rejects_previous_code(self):
        issued = self.issue()
        AuthChallenge.objects.update(resend_available_at=timezone.now() - timedelta(seconds=1))
        first, second = self.cloned_browser(self.client), self.cloned_browser(self.client)
        with patch("accounts.tasks.send_signup_email.apply_async"):
            reissued, verified = self.in_lock_order(
                lambda: self.post(ISSUE, {"flow_id": issued["flow_id"], "school_email": issued["school_email"]}, first),
                lambda: self.verify(issued, second),
            )
        self.assertEqual(reissued.status_code, 200)
        self.assert_error(verified, "CHALLENGE_INVALID_OR_EXPIRED")
        old = AuthChallenge.objects.get(pk=issued["challenge_id"])
        self.assertIsNone(old.verified_at)
        self.assertIsNone(old.consumed_at)
        self.assertIsNotNone(old.revoked_at)
        self.assertEqual(AuthChallenge.objects.filter(revoked_at__isnull=True).count(), 1)
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityEvent.objects.exists())

    def test_parallel_same_grant_is_consumed_once(self):
        issued = self.verified()
        clients = [self.cloned_browser(self.client) for _ in range(2)]
        responses = self.parallel([lambda c=c: self.post(SIGNUP, self.profile(issued), c) for c in clients])
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.count(), 1)
        self.assertEqual(AuthChallenge.objects.filter(consumed_at__isnull=False).count(), 1)

    def test_parallel_duplicate_login_different_emails(self):
        second_client = self.browser()
        first, second = self.verified(), self.verified("another@syuin.ac.kr", second_client)
        responses = self.parallel([
            lambda: self.post(SIGNUP, self.profile(first), self.cloned_browser(self.client)),
            lambda: self.post(SIGNUP, self.profile(second), self.cloned_browser(second_client)),
        ])
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.count(), 1)
        self.assertEqual(AuthChallenge.objects.filter(consumed_at__isnull=False).count(), 1)

    def test_parallel_same_email_different_flows(self):
        second_client = self.browser()
        first = self.verified()
        AuthChallenge.objects.update(last_sent_at=timezone.now() - timedelta(seconds=60),
                                     resend_available_at=timezone.now())
        second = self.verified(first["school_email"], second_client)
        responses = self.parallel([
            lambda: self.post(SIGNUP, self.profile(first), self.cloned_browser(self.client)),
            lambda: self.post(SIGNUP, self.profile(second, login_id="other"), self.cloned_browser(second_client)),
        ])
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.count(), 1)

    def test_parallel_issue_in_same_flow(self):
        clients = [self.cloned_browser(self.client) for _ in range(2)]
        with patch("accounts.tasks.send_signup_email.apply_async"):
            responses = self.parallel([lambda c=c: self.post(ISSUE, {"school_email": "student@syuin.ac.kr"}, c)
                                       for c in clients])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 429])
        self.assertEqual(AuthChallenge.objects.count(), 1)

    def test_parallel_rate_limit_is_atomic(self):
        def attempt():
            try:
                service.rate_limit("issue", "student@syuin.ac.kr", "127.0.0.1")
                return 200
            except service.SignupError as error:
                return error.status
        with override_settings(SIGNUP_ISSUE_LIMITS=(2, 30)):
            statuses = self.parallel([attempt] * 6)
        self.assertEqual(sorted(statuses), [200, 200, 429, 429, 429, 429])
