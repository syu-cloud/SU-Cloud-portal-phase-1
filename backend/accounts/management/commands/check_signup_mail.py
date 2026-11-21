from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError
from django.views.decorators.debug import sensitive_variables

from accounts.mail import delivery_mode, failure_code, missing_smtp_settings


class Command(BaseCommand):
    help = "비밀값을 표시하거나 메일을 보내지 않고 가입 SMTP 설정·접속·인증을 확인합니다."

    def add_arguments(self, parser):
        parser.add_argument("--connect", action="store_true", help="SMTP 연결·TLS·인증까지 검사합니다. 메일은 보내지 않습니다.")

    @sensitive_variables()
    def handle(self, *args, **options):
        mode = delivery_mode()
        self.stdout.write(f"메일 확인 방식: {mode}")
        if mode != "smtp":
            self.stdout.write("SMTP가 선택되지 않았습니다. 파일 모드는 .local/mail에서 확인합니다.")
            return
        missing = missing_smtp_settings()
        if missing:
            raise CommandError("MAIL_CONFIG_ERROR: .env에서 설정할 항목: " + ", ".join(missing))
        self.stdout.write("SMTP 필수 설정 존재 확인 완료 (값은 표시하지 않음).")
        if not options["connect"]:
            self.stdout.write("실제 접속·인증은 --connect로 확인하세요.")
            return
        try:
            connection = get_connection(fail_silently=False)
            try:
                connection.open()
            finally:
                connection.close()
        except Exception as error:
            code = failure_code(error)
            guide = {
                "SMTP_AUTH_FAILED": "Google 2단계 인증·앱 비밀번호·계정 정책을 확인하세요.",
                "SMTP_TLS_FAILED": "TLS 설정·시스템 인증서를 확인하세요. 인증서 검증을 끄지 마세요.",
                "SMTP_CONNECTION_FAILED": "SMTP 주소·포트·네트워크 연결을 확인하세요.",
            }.get(code, "메일 설정을 확인하세요.")
            raise CommandError(f"{code}: {guide}") from None
        self.stdout.write(self.style.SUCCESS("SMTP_CONNECT_AUTH_OK: 연결·TLS·인증 완료. 메일은 보내지 않았습니다."))
        self.stdout.write("실제 SMTP 발송 성공과 수신함 도착은 별도 검증이 필요합니다.")
