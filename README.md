# SU Cloud Phase 0.5 — 보존·참고 브랜치

이 브랜치 `archive/phase-0.5`는 Phase 1 개발을 시작하기 전의 **Phase 0.5 수업 배치 서비스 코드**를 보존합니다.

## 브랜치 역할

- 기존 서비스의 구현과 변경 이력을 참고할 수 있도록 유지합니다.
- Phase 1에서 재사용할 OpenStack·Warpgate 연동, 인증·CSRF 처리, 공통 UI 및 테스트를 검토하는 기준으로 사용합니다.
- 신규 Phase 1 기능 개발은 [`dev` 브랜치](https://github.com/syu-cloud/SU-Cloud-portal-phase-1/tree/dev)에서 진행합니다. 이 보존 브랜치에서는 기존 구현을 유지하며 설명 문서를 보완할 수 있습니다.

## 보존된 코드의 범위

- Django·Django REST Framework 기반 로그인·로그아웃 및 VM API
- React·TypeScript 기반 포털 화면
- 고정 Slot 기반 VM 발급·회수와 DB polling 워커
- OpenStack SDK 및 Warpgate Admin API 연동

## Phase 1에서 재사용할 때

필요한 코드를 선택적으로 가져와 Phase 1 명세와 데이터 모델에 맞게 수정하고 검증합니다.

특히 고정 Slot, VM 이름·학생 계정·FIP 결정 규칙, VM 회수 시 Warpgate 사용자 삭제, 기존 VM API의 권한 검사 범위는 Phase 1의 사용자별 논리 프로젝트·Quota·1계정 다중 VM 구조에 맞게 재설계해야 합니다.

코드 보존은 현재 서버의 배포 상태나 Phase 1 요구사항 충족을 검증한 기록과 구분합니다.

## 보존 기준

- Phase 0.5 기준 커밋: [`9553c75`](https://github.com/syu-cloud/SU-Cloud-portal-phase-1/commit/9553c758669932c510f1d20d33ff4c55cff61216)
- README 작성일: 2026-11-18
