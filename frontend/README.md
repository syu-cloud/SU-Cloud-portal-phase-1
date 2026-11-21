# SU Cloud 학생 회원가입 연동 테스트

기존 React/TypeScript/Vite에 받은 회원가입 목업의 구조·스타일을 반영했다. UAPI-01~03과 CSRF 경로를 호출하며 화면의 가입 성공·오류·인증 시각은 서버 응답이다. Gmail SMTP 설정과 앱 비밀번호 입력·재시작·안전한 진단은 [GMAIL_SMTP.md](../GMAIL_SMTP.md)를 따른다.

## 실행

저장소 루트 `.env`와 PostgreSQL·Redis, Python 3.12 가상환경, Node.js 24가 준비되어 있어야 한다. 저장소 루트에서 각 명령을 **별도 터미널**에 실행한다.

```bash
# 1. DB·Redis: 이 Mac에서는 Docker 연결을 먼저 선택한다.
. ./scripts/dev-env.sh
docker compose up -d --wait
```

```bash
# 2. Django
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

```bash
# 3. Celery: 인증메일 파일 생성
cd backend
../.venv/bin/python -m celery -A config worker --loglevel=info --concurrency=2
```

```bash
# 4. 프런트엔드 (저장소 루트 기준)
. ./scripts/dev-env.sh
cd frontend
# 최초 설치가 필요할 때만 npm ci
npm run dev
```

다른 PC에서는 팀의 Node 24·Docker Compose 환경을 사용한다. `scripts/dev-env.sh`는 이 Mac의 로컬 보조 파일이다. 이후 브라우저에서 **http://127.0.0.1:5173/** 을 연다. HTML 파일을 직접 여는 방식은 사용하지 않는다. 서버와 워커는 실행한 터미널에서 Ctrl+C로 종료한다.

Vite의 `/api` 프록시가 Django `127.0.0.1:8000`으로 전달한다. 원래 Host·Origin과 쿠키를 유지하며 Django CSRF 검사를 적용한다. CORS 허용이나 CSRF 면제는 추가하지 않았다. 브라우저에서는 5173 주소를 계속 사용한다.

## 정상 가입 시험

1. 화면 아래 **새 예시 정보**를 누른다. 서로 다른 테스트 학번과 개발용 예시 비밀번호가 채워진다. **SMTP 모드에서는 본인의 실제 @syuin.ac.kr 주소를 직접 입력**한다. 파일 모드에서만 예시 주소가 채워진다. 학번 선행 0도 확인할 수 있다.
2. **인증번호 받기**를 누르고 응답 `HTTP 200`을 확인한다.
3. **SMTP 모드**에서는 학교 메일 수신함·스팸함에서 번호를 확인한다. **파일 모드**에서는 VS Code의 저장소 루트 `.local/mail/` 최신 `.log` 파일에서 해당 수신 주소와 번호를 확인한다. 화면은 서버가 제공한 `email_delivery` 방식만으로 안내를 전환한다. SMTP 계정·비밀번호는 프런트엔드로 전달하지 않는다.
4. 번호를 입력하고 **인증 확인**을 누른다. 응답 `200`과 가입 가능 시간을 확인한다.
5. **가입하기**를 누른다. 실제 `201` 응답과 USER/STUDENT/SCHOOL 계정 생성 결과를 확인한다. 비밀번호 입력은 성공 후 지워진다.

생성한 테스트 계정은 개발 DB에 남는다. **입력 초기화**는 화면 입력만 지우며 계정·서버 대기 시간·누적 요청 제한은 유지한다. 같은 주소/학번을 새 계정에 재사용하면 중복 오류가 발생한다. 요청 제한 기본값은 이메일별 발급 5회·확인 20회, IP별 발급 30회·확인 100회/15분이다.

## 오류와 인증 흐름 시험

개발 서버에서는 아래 **개발용 API 점검 도구**를 펼칠 수 있다. API를 선택하고 **현재 입력에서 요청 만들기**를 누른 뒤 JSON을 편집한다. 가입 비밀번호·확인 값은 위 가입 폼에서 가져오며 JSON 편집기에 복제하지 않는다. 요청 본문·비밀번호·번호를 콘솔이나 응답 이력에 기록하지 않는다. 도구는 실제 API를 호출하며 클라이언트의 버튼 제한을 적용하지 않는다.

| 시험 | 방법 | 예상 결과 |
| --- | --- | --- |
| 잘못된 학교 주소 | 가입 폼에 다른 도메인을 입력하고 발급 | 400 VALIDATION_ERROR |
| 입력 길이·비밀번호 불일치 | 이름 41자 등 경계값 또는 확인 값을 바꾸고 가입 요청 | 400 VALIDATION_ERROR |
| 미인증 가입 | 번호 발급 후 확인하기 전에 가입 API 요청 본문을 만들고 전송 | 400 CHALLENGE_INVALID_OR_EXPIRED |
| 잘못된 번호 | 다른 6자리 번호를 확인 요청 | 400 CHALLENGE_INVALID_OR_EXPIRED. 로컬 설정상 5회 실패하면 무효화 |
| 재발급 대기 | 발급 직후 점검 도구에서 같은 발급 요청 전송 | 429 COOLDOWN_ACTIVE |
| 이전 번호·가입 권한 무효화 | 이전 확인/가입 요청 JSON을 복사해 두고 60초 뒤 재발급, 복사해 둔 요청 전송 | 이전 challenge_id는 400 CHALLENGE_INVALID_OR_EXPIRED |
| 주소·흐름 결합 | 확인/가입 요청의 주소나 형식이 정상인 UUID를 다른 값으로 수정 | 400 CHALLENGE_INVALID_OR_EXPIRED |
| UUID 형식 | flow_id 또는 challenge_id를 `not-a-uuid`로 수정 | 400 VALIDATION_ERROR |
| 다른 브라우저의 인증 사용 | 시크릿 창/다른 브라우저에서 발급한 flow/challenge를 현재 창 요청에 사용 | 400 CHALLENGE_INVALID_OR_EXPIRED. 일반 탭끼리는 세션 쿠키를 공유함 |
| CSRF | **CSRF 헤더 없이 요청하기** 체크 후 전송 | 403 CSRF_FAILED |
| ADMIN 생성 시도 | 가입 JSON에 `"account_role": "ADMIN"` 추가 | 400 VALIDATION_ERROR |
| 동일 인증 동시 소비 | 인증 완료 후 가입 요청을 만들고 **동일 요청 2개 동시 보내기** | 보통 201/400. 계정과 가입 이력은 한 번만 저장 |
| 소비한 인증 재사용 | 가입 후 비밀번호 두 칸을 다시 채우고 같은 flow/challenge로 가입 요청 | 400 CHALLENGE_INVALID_OR_EXPIRED |
| 중복 계정 | 이미 가입한 이메일로 발급 요청. 또는 새 이메일 인증 후 가입 JSON의 학번을 기존 값으로 수정 | 409 DUPLICATE_ACCOUNT |
| 기한 만료 | 번호 확인은 10분, 확인된 가입 권한은 로컬 설정 30분 후 요청 | 400 CHALLENGE_INVALID_OR_EXPIRED |

점검 도구의 JSON은 자동으로 갱신되지 않으므로 폼·인증 상태가 바뀌면 **현재 입력에서 요청 만들기**를 다시 누른다. 이전 요청을 유지해 재사용 거절을 시험할 수도 있다. CSRF 연결에 실패하면 Django를 실행한 뒤 **CSRF 연결 갱신**을 누른다. 도구는 `npm run dev`에서 제공하며 배포 빌드에서는 표시하지 않는다.

## 받은 목업의 범위

원본 `Phase1_mockup`의 5개 HTML은 보존한다. `public/mockups/`에는 스크립트와 외부 폰트 로딩을 제거하고 `inert`를 적용한 읽기 전용 사본을 두었다. 화면의 **디자인** 버튼으로 미리 본다. iframe도 스크립트·폼 실행을 허용하지 않는다.

로그인·마이페이지·포털·콘솔은 디자인 미리보기다. 해당 백엔드, 개인정보 동의 기록, Access Service·Warpgate 연동은 추가하지 않았다. 개인정보 동의 기록은 사용자 결정에 따라 Warpgate 연동 이후 진행한다.

## 자동 검사

```bash
# frontend 디렉터리
npm test
npm run build
npm run lint
```

프런트엔드 테스트 10개는 Node 24 내장 테스트 도구로 요청 URL·메서드·쿠키·CSRF·오류 응답, SMTP/파일 안내 전환과 목업 사본의 읽기 전용 처리를 확인한다. 새 테스트 의존성은 없다.

저장소 루트에서 가입·SMTP 테스트 55개도 실행할 수 있다. 가입 경합에는 실제 PostgreSQL/Redis를 사용하고, 메일은 locmem 또는 모의 SMTP 연결로 검사해 실제로 발송하지 않는다.

```bash
.venv/bin/python backend/manage.py test accounts admin_api provisioning --noinput
```

DB 이력 INSERT 실패/전체 롤백, 다른 인증 목적, 처리 순서를 고정한 경합 검증은 자동 테스트에서 수행한다. 화면에 서버 시간을 조작하거나 이력 실패를 강제로 발생시키는 백엔드 경로는 만들지 않았다.

검증: 목업 연동 당시 Vite 5173을 거친 CSRF·학교 이메일 인증·Celery 파일 메일·동시 가입(201/400)·중복(409)·재발급 대기(429)·CSRF 누락(403)·잘못된 입력(400)을 HTTP로 확인했다. SMTP 변경 후에는 백엔드 55개·프런트엔드 10개 테스트, 빌드·린트와 Gmail TCP/STARTTLS 연결을 확인했다. 2026-11-21 사용자가 실제 인증메일 정상 발송을 확인했다. 실수신 번호로 인증·가입 완료 여부, 브라우저 자동 조작과 모바일 시각 검증은 별도 확인이 필요하다.
