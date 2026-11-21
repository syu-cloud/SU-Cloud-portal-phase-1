import smtplib
import ssl

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def delivery_mode():
    return {
        "django.core.mail.backends.smtp.EmailBackend": "smtp",
        "django.core.mail.backends.filebased.EmailBackend": "file",
        "django.core.mail.backends.locmem.EmailBackend": "test",
    }.get(settings.EMAIL_BACKEND, "other")


def missing_smtp_settings():
    return [name for name in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL")
            if not getattr(settings, name, "")]


def failure_code(error):
    if isinstance(error, ImproperlyConfigured):
        return "MAIL_CONFIG_ERROR"
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "SMTP_AUTH_FAILED"
    if isinstance(error, ssl.SSLError):
        return "SMTP_TLS_FAILED"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "SMTP_RECIPIENT_REJECTED"
    if isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "SMTP_CONNECTION_FAILED"
    if isinstance(error, smtplib.SMTPException):
        return "MAIL_DELIVERY_FAILED"
    if isinstance(error, OSError):
        return "SMTP_CONNECTION_FAILED"
    return "MAIL_DELIVERY_FAILED"
