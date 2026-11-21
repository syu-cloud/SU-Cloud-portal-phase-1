# 학생 가입 인증메일: Gmail SMTP

발신 계정은 `sahmyookcloud@gmail.com`, 표시 이름은 `SU Cloud`다. 가입 폼에 입력한 `@syuin.ac.kr` 주소로 발송한다. 기존 Django SMTP 백엔드와 Celery 작업을 사용한다.

## 1. 앱 비밀번호 직접 설정

1. 발신 Google 계정으로 로그인해 **2단계 인증**을 설정한다.
2. [Google 앱 비밀번호](https://myaccount.google.com/apppasswords)에서 이 개발 환경용 앱 비밀번호를 만든다.
3. VS Code에서 저장소 루트 `.env`를 열고 `EMAIL_HOST_PASSWORD`의 빈 값에 직접 입력·저장한다. 표시용 공백을 제외한 16자 값을 사용한다. Gmail 일반 로그인 비밀번호를 입력하지 않는다.

현재 이 Mac의 `.env`에는 다음 메일 설정을 준비했다. 기존 PostgreSQL·Django 설정은 보존했다.

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=sahmyookcloud@gmail.com
EMAIL_HOST_PASSWORD=''
DEFAULT_FROM_EMAIL='SU Cloud <sahmyookcloud@gmail.com>'
```

앱 비밀번호를 채팅·명령줄 인자·스크린샷·Git·프런트엔드 환경변수에 넣지 않는다. `.env`는 Git에서 제외하며 현재 파일 권한은 600이다.

앱 비밀번호 항목이 없다면 [Google 공식 안내](https://support.google.com/accounts/answer/185833?hl=ko)의 계정 제한을 확인한다. 조직 정책, 고급 보호, 보안 키만 사용하는 2단계 인증 등이 영향을 줄 수 있다. 보안 기능을 끄는 방식으로 해결하지 않는다. 앱 비밀번호를 사용할 수 없는 계정에서는 OAuth 2.0 SMTP 인증 또는 별도 발송 서비스가 대안이며, 이는 필요 시 별도 결정·구현한다. Google 비밀번호를 바꾸면 앱 비밀번호가 취소될 수 있다.

## 2. 안전한 사전 진단

저장소 루트에서 실행한다.

```bash
# 설정의 존재만 검사: 값 출력·네트워크 연결·메일 발송 없음
.venv/bin/python backend/manage.py check_signup_mail

# SMTP 접속·STARTTLS·인증 검사: 메일 발송 없음
.venv/bin/python backend/manage.py check_signup_mail --connect
```

앱 비밀번호를 아직 입력하지 않았다면 `MAIL_CONFIG_ERROR`와 `EMAIL_HOST_PASSWORD`라는 항목명만 나온다. 값을 입력한 뒤 `--connect` 결과가 `SMTP_CONNECT_AUTH_OK`인지 확인한다. 이 결과는 실제 메일 발송·수신 완료를 뜻하지 않는다.

| 진단/로그 코드 | 확인할 내용 |
| --- | --- |
| MAIL_CONFIG_ERROR | `.env`의 필수 메일 설정 누락 또는 지원하지 않는 백엔드. 앱 비밀번호 입력 후 프로세스 재시작 |
| SMTP_AUTH_FAILED | 발신 계정, 2단계 인증, 앱 비밀번호, Google 계정 정책. 일반 비밀번호 사용 금지 |
| SMTP_CONNECTION_FAILED | smtp.gmail.com:587 접속, DNS·방화벽·네트워크, 타임아웃 |
| SMTP_TLS_FAILED | STARTTLS 설정·시스템 인증서·네트워크 검사. 인증서 검증을 끄지 않음 |
| SMTP_RECIPIENT_REJECTED | 실제 학교 수신 주소의 존재·정확성·학교 수신 정책 |
| MAIL_DELIVERY_FAILED | 그 외 메일 처리/서버 거절. 원시 예외 대신 안전한 코드로 확인 |

진단 명령과 작업 로그는 SMTP 비밀번호·번호·본문·수신 주소·원시 SMTP 예외를 출력하지 않는다. `diff .env`, 전체 환경변수 출력, SMTP 디버그 출력으로 진단하지 않는다.

## 3. 재시작과 실제 시험

`.env`를 바꾼 후에는 **Django와 Celery를 모두 종료하고 다시 실행**한다. Django의 코드 자동 새로고침만으로는 Celery 설정이 갱신되지 않는다. 다른 터미널에서 오래된 워커를 함께 실행하지 않는다.

```bash
# 저장소 루트, 터미널 1
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

```bash
# 저장소 루트, 터미널 2
cd backend
../.venv/bin/python -m celery -A config worker --loglevel=info --concurrency=2
```

```bash
# 저장소 루트, 터미널 3 (이 Mac의 Node 24 선택)
. ./scripts/dev-env.sh
cd frontend
npm run dev
```

PostgreSQL·Redis는 기존 개발 환경대로 먼저 실행한다. 브라우저에서 http://127.0.0.1:5173/ 을 열어 다음 순서로 확인한다.

1. 실제 수신 시험에 허용한 본인의 학교 주소를 입력한다. SMTP 모드의 **새 예시 정보**는 가짜 수신 주소를 채우지 않는다.
2. 인증번호 받기 후 `HTTP 200`을 확인한다. 이는 API가 Celery 작업 접수를 마쳤다는 뜻이다.
3. Celery의 `signup_mail_accepted ... mode=smtp` 로그를 확인한다. 응답의 challenge_id와 대조할 수 있다. 이는 SMTP 서버의 메시지 접수 성공이며 받은편지함 도착을 보장하지 않는다.
4. 본인이 학교 메일 **수신함·스팸함**에서 발신자와 인증번호를 확인한다. 이 단계가 실제 수신 확인이다.
5. 인증번호를 로컬 가입 화면에 직접 입력하고 인증 확인 `200`, 가입 `201`을 확인한다. 코드를 채팅으로 보낼 필요는 없다.

실제 발송은 사용자가 제공한 수신 주소로만 시험한다. 수신 주소나 자격증명이 준비되지 않았으면 발송·수신 성공으로 보고하지 않는다. 기존 주소가 이미 가입되어 있다면 중복 거절이 정상이며 기존 계정을 자동 삭제하지 않는다. 계정은 개발 DB에 저장된다.

`signup_mail_failed` 로그는 challenge_id·안전한 분류 코드·재시도 횟수만 기록한다. 기존대로 30초 간격 최대 3회 재시도하고 최종 실패 시 미확인 인증을 무효화한다. SMTP 발송 실패에도 이미 기록된 발송 요청 접수 시각(`last_sent_at`)은 보존한다.

학교 측 필터·계정 정책·Gmail 발송 제한 때문에 SMTP 접수 후에도 수신이 지연되거나 거절될 수 있다. 반복 발송보다 주소·스팸함·정책을 먼저 확인한다. 인증번호 기한 10분, 재발급 대기 60초, 현재 누적 요청 제한은 유지한다.

## 4. 파일 메일 모드로 돌아가기

개인 `.env`의 다음 한 줄을 바꾸고 Django와 Celery를 모두 재시작한다.

```dotenv
EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend
```

이때는 실제 메일을 보내지 않으며 `.local/mail/*.log`에서 확인한다. SMTP 설정은 남겨 두어도 파일 모드에서 사용되지 않는다. 화면의 메일 안내는 서버가 CSRF 응답에 포함하는 `email_delivery` 방식만으로 바뀐다. 화면을 새로고침하거나 CSRF 연결 갱신을 누른다. 계정·비밀번호·SMTP 서버 설정은 프런트엔드에 전달하지 않는다.

## 5. 자동 검증과 실제 검증 구분

```bash
# 저장소 루트
.venv/bin/python backend/manage.py test accounts admin_api provisioning --noinput
```

```bash
# frontend
npm test
npm run build
npm run lint
```

자동 테스트의 메일 전달은 locmem이며, SMTP 설정·접속·오류 경로는 모의 객체로 검사한다. 자동 테스트에서 실제 인증메일을 발송하지 않는다. 테스트에는 기존 인증/CSRF/경합/롤백, 발신자·수신 대상, SMTP 오류 비노출, 접수 시각 보존, 화면 확인 방식 전환이 포함된다.

실제 검증은 각각 별도로 기록한다: **설정 존재 → TCP/TLS 연결 → SMTP 인증 → API 접수 → SMTP 메시지 접수 → 수신함 확인 → 인증·가입 성공**. 아직 완료하지 못한 단계는 미검증으로 남긴다.

2026-11-21 사용자 확인: 실제 인증메일이 정상 발송되는 것을 확인했다. 수신 주소·앱 비밀번호·인증번호는 문서에 기록하지 않는다. 실수신 번호로 인증 확인과 가입까지 완료했는지는 별도 확인이 필요하다.

공식 참고: [Gmail SMTP 주소·포트](https://developers.google.com/workspace/gmail/imap/imap-smtp), [앱 비밀번호](https://support.google.com/accounts/answer/185833?hl=ko), [Django 메일 백엔드](https://docs.djangoproject.com/en/5.2/topics/email/).
