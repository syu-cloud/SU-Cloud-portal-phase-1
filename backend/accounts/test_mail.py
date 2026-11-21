import io
import smtplib
import ssl
from unittest.mock import ANY, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.gmail.com", EMAIL_PORT=587, EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
    EMAIL_HOST_USER="sender@example.com", EMAIL_HOST_PASSWORD="test-only-app-password",
    DEFAULT_FROM_EMAIL="SU Cloud <sender@example.com>", EMAIL_TIMEOUT=10,
)
class SignupMailDiagnosticTests(SimpleTestCase):
    def test_missing_password_does_not_connect(self):
        with override_settings(EMAIL_HOST_PASSWORD=""):
            with patch("accounts.management.commands.check_signup_mail.get_connection") as connection:
                with self.assertRaisesMessage(CommandError, "EMAIL_HOST_PASSWORD"):
                    call_command("check_signup_mail", "--connect", stdout=io.StringIO())
        connection.assert_not_called()

    def test_configuration_check_does_not_connect(self):
        output = io.StringIO()
        with patch("accounts.management.commands.check_signup_mail.get_connection") as connection:
            call_command("check_signup_mail", stdout=output)
        connection.assert_not_called()
        self.assertNotIn("test-only-app-password", output.getvalue())
        self.assertNotIn("sender@example.com", output.getvalue())

    def test_gmail_starttls_authentication_without_sending(self):
        output = io.StringIO()
        with patch("django.core.mail.backends.smtp.smtplib.SMTP") as smtp:
            call_command("check_signup_mail", "--connect", stdout=output)
        smtp.assert_called_once_with("smtp.gmail.com", 587, local_hostname=ANY, timeout=10)
        smtp.return_value.starttls.assert_called_once()
        smtp.return_value.login.assert_called_once_with("sender@example.com", "test-only-app-password")
        smtp.return_value.sendmail.assert_not_called()
        self.assertIn("SMTP_CONNECT_AUTH_OK", output.getvalue())
        self.assertIn("수신함 도착은 별도 검증", output.getvalue())
        self.assertNotIn("test-only-app-password", output.getvalue())

    def test_failure_categories_redact_original_exception(self):
        private = "test-only-app-password recipient@example.com 123456"
        cases = (
            (smtplib.SMTPAuthenticationError(535, private.encode()), "SMTP_AUTH_FAILED"),
            (ssl.SSLError(private), "SMTP_TLS_FAILED"),
            (OSError(private), "SMTP_CONNECTION_FAILED"),
        )
        for failure, code in cases:
            with self.subTest(code=code):
                output = io.StringIO()
                with patch("accounts.management.commands.check_signup_mail.get_connection") as connection:
                    connection.return_value.open.side_effect = failure
                    with self.assertRaises(CommandError) as caught:
                        call_command("check_signup_mail", "--connect", stdout=output)
                self.assertIn(code, str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertNotIn(private, str(caught.exception) + output.getvalue())
                connection.return_value.close.assert_called_once()

    def test_file_mode_diagnostic_does_not_connect(self):
        output = io.StringIO()
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.filebased.EmailBackend"):
            with patch("accounts.management.commands.check_signup_mail.get_connection") as connection:
                call_command("check_signup_mail", "--connect", stdout=output)
        connection.assert_not_called()
        self.assertIn(".local/mail", output.getvalue())
