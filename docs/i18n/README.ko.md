# Hermes Pet

> **macOS 전용 MVP.** 현재 Hermes Pet 배포판은 macOS 네이티브 데스크탑 펫만
> 제공합니다. Windows/Linux 렌더러는 별도 target으로 확장 가능하지만, 이번
> release에는 동일한 desktop overlay 기능이 포함되어 있지 않습니다.

Hermes Agent용 데스크탑 펫입니다. Hermes Pet은 브라우저 안이 아니라 macOS 화면 위에서 직접 살아 움직이는 네이티브 오버레이이며, 로컬 Hermes CLI/TUI 작업 상태에 반응하고, 입력 대기/완료 알림을 유지하며, Codex Pet Share의 애니메이션 아트워크를 가져와 교체할 수 있습니다.

언어:

- [English](../../README.md)
- [한국어](README.ko.md)
- [简体中文](README.zh.md)
- [日本語](README.ja.md)

## 개요

Hermes Pet은 Hermes Agent의 화면 위 컴패니언입니다. 웹 대시보드 위젯이 아니며, 투명한 always-on-top macOS 패널로 실행됩니다. 현재 MVP는 `hermes pet` CLI와 `hermes-pet` 스킬 wrapper를 함께 사용하지만, 장기 구조는 Hermes 원판을 수정하지 않는 독립 macOS 앱 + 얇은 Hermes connector입니다.

아키텍처 문서:

- [`docs/architecture/hermes-pet-architecture.md`](../architecture/hermes-pet-architecture.md)
- [`apps/macos/HermesPet`](../../apps/macos/HermesPet)

기본 로컬 MVP는 localhost 전용입니다.

```bash
hermes pet --background --port 8768
```

## 주요 기능

- AppKit `NSPanel` 기반 네이티브 macOS 데스크탑 펫
- Hermes CLI/TUI 이벤트용 localhost event inlet
- 활성/최근 Hermes 세션 우클릭 메뉴
- 좌클릭으로 활성 CLI/TUI 세션 포커스
- CLI/TUI 실행, 세션 선택, 설정, 아트워크, 런타임 관리, 알림 정리, 종료 메뉴
- 로컬 데스크탑 펫 렌더링과 세션 상태 반응
- 입력 대기/완료/실패 상태 알림 배지
- Codex Pet Share 아트워크 검색, 다운로드, 변환, 적용
- 한국어, 영어, 일본어, 중국어 UI
- macOS LaunchAgent 로그인 자동 실행 지원
- Hermes skill wrapper와 `petctl.sh` helper 제공

## 빠른 시작

```bash
INSTALLER=/tmp/hermes-pet-install-from-git.sh
curl -fsSL https://raw.githubusercontent.com/ktkarchive/taiei-hermes-pet/main/connectors/hermes/install-from-git.sh -o "$INSTALLER"
bash "$INSTALLER"
```

수동 clone 방식:

```bash
git clone https://github.com/ktkarchive/taiei-hermes-pet.git
cd taiei-hermes-pet
bash connectors/hermes/install.sh
hermes-pet --background --port 8768
```

상태 확인:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

재시작:

```bash
hermes-pet --restart --port 8768
```

종료:

```bash
hermes-pet --stop
```

## Hermes에게 설치 요청하기

macOS에서 이미 실행 중인 Hermes CLI/TUI에 아래처럼 요청하면 됩니다.

```text
https://github.com/ktkarchive/taiei-hermes-pet 를 참고해서 Hermes Pet을 설치해줘.
repo의 connectors/hermes/install-from-git.sh installer를 사용하고, 로컬 desktop
pet을 8768 포트로 시작한 다음 status, health, 설치된 hermes-pet skill doctor를
검증해줘. 전역 hermes 명령은 수정하지 마.
```

installer는 repo를 `~/.hermes/pet/taiei-hermes-pet` 아래에 clone 또는
fast-forward update하고, 필요하면 `venv/`를 bootstrap한 뒤, 제거 가능한
skill/wrapper connector를 설치하고 pet을 시작합니다.

## Hermes 스킬 wrapper

스킬 위치:

```text
skills/productivity/hermes-pet/SKILL.md
```

Hermes용 MVP connector는 전역 `hermes` 명령을 바꾸지 않고 설치/업데이트합니다.

```bash
bash connectors/hermes/install.sh
```

이 명령은 `~/.local/bin/hermes-pet`과
`~/.hermes/skills/productivity/hermes-pet`을 설치하고, `.project-root`로 현재
workspace를 고정합니다.
fresh clone에서 `venv/bin/python3`가 없으면 installer가 `python3 -m venv venv`
및 `venv/bin/python3 -m pip install .`로 자동 bootstrap합니다. 직접 준비하고
싶으면 `--no-bootstrap`을 사용하고, local development에서는
`HERMES_PET_EDITABLE_INSTALL=1`을 사용할 수 있습니다.
기본 설치/삭제는 위 표준 경로만 사용하며, 커스텀 경로는
`HERMES_PET_ALLOW_CUSTOM_INSTALL=1`이 있어야 합니다. 그래도 `$HOME`, `/`,
`/tmp`, `hermes-pet`으로 끝나지 않는 경로는 거부합니다.

Hermes가 bundled skills를 `~/.hermes/skills`로 sync하면, 사용자는 자연어로 다음처럼 요청할 수 있습니다.

- "Hermes Pet 켜줘."
- "데스크탑 펫 재시작해."
- "로그인할 때 자동 실행되게 설치해."
- "픽셀 느낌 펫 아트워크 검색해."
- "현재 펫 세션 보여줘."

스킬 helper:

```bash
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" status
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" start
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" restart
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" stop
```

repo 안에서 직접 실행할 수도 있습니다.

```bash
bash skills/productivity/hermes-pet/scripts/petctl.sh status
```

### 설치, 업데이트, 삭제

Hermes 전용 배포판 설치/업데이트:

```bash
bash connectors/hermes/install.sh
```

이 명령은 의도적으로 좁게 동작합니다.

- `~/.local/bin/hermes-pet` 설치
- `~/.hermes/skills/productivity/hermes-pet` 설치
- `.project-root`로 현재 workspace 고정
- 전역 `hermes` 명령은 변경하지 않음

설치 후 검증:

```bash
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

connector만 삭제:

```bash
bash connectors/hermes/uninstall.sh
```

connector와 pet runtime/cache까지 삭제:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

uninstall은 실행 중인 pet을 기본으로 중지하고, 존재하는
`ai.hermes.pet*.plist` LaunchAgent를 unload/remove한 뒤, standalone
`hermes-pet` wrapper, 설치된 skill, 알려진 Hermes Pet runtime 파일만 지웁니다.
Hermes Agent 자체는 삭제하지 않습니다.

## CLI 명령

런타임:

```bash
hermes pet --status
hermes pet --background --port 8768
hermes pet --restart --port 8768
hermes pet --stop
```

세션:

```bash
hermes pet --sessions
```

로그인 자동 실행:

```bash
hermes pet --install-launch-agent --port 8768 --force
hermes pet --launch-agent-status
hermes pet --start-launch-agent
hermes pet --stop-launch-agent
hermes pet --uninstall-launch-agent
```

LaunchAgent plist:

```text
~/Library/LaunchAgents/ai.hermes.pet.plist
```

## 아트워크

Codex Pet Share에서 펫 아트워크를 가져옵니다.

```bash
hermes pet --share-list
hermes pet --share-search "pixel"
hermes pet --share-apply "<pet-id-or-url>" --size 84
hermes pet --share-current
hermes pet --share-installed
hermes pet --share-use-installed "<asset-id>"
hermes pet --share-clear
```

Codex Pet Share 사이트:

```text
https://codex-pet-share.pages.dev/
```

우클릭 메뉴의 `펫 아트워크`에서도 검색, 적용, 사이트 열기, 최근 펫 선택이 가능합니다.
CLI에서는 pet id 또는 Codex Pet Share URL을 그대로 `--share-apply`에 넣을 수 있습니다.

```bash
hermes pet --share-apply "https://codex-pet-share.pages.dev/#/pets/<pet-id>" --size 84
```

가져온 아트워크는 이 Mac의 Hermes runtime 아래에 로컬로 저장됩니다. Codex Pet
Share의 다른 제작자가 만든 펫을 스크린샷, 데모, 배포 문서에 사용할 때는 가능한
한 pet 이름과 제작자 정보를 함께 남겨 주세요.

## 우클릭 메뉴

현재 네이티브 메뉴는 다음을 제공합니다.

- Hermes 작동 방식: CLI/TUI 실행 또는 포커스
- 활성 세션: 최근/활성 CLI/TUI 세션 열기
- 펫 아트워크: Codex Pet Share 검색/적용/최근 펫
- 설정: 언어, 터미널, 좌클릭 동작, 세션 목록 개수
- 펫 실행 관리: 재시작, 로그인 항목 상태/설치/시작/중지
- 알림 지우기
- Hermes Pet 종료

## 알림과 애니메이션

알림:

- `!`: 선택/승인/입력 대기 또는 실패
- `1`: 완료 또는 리뷰 상태

알림은 사용자가 클릭하거나 직접 지울 때까지 유지됩니다.

애니메이션:

- idle: 기본 대기/깜빡임
- drag left/right: running-left / running-right
- hover: jumping
- 작업 중: running
- 입력 대기: waiting
- 완료/리뷰: review 후 idle
- 실패: failed 후 idle

## 안전 원칙

- 기본은 `127.0.0.1`
- 공개 macOS MVP installer는 private-network relay tool을 요구하지 않습니다.
- runtime 상태 파일은 프로세스/세션 metadata를 담을 때 사용자 전용 권한으로 저장합니다.
- LaunchAgent 설치/삭제는 사용자 승인 후 진행

## 개발 검증

```bash
venv/bin/python3 -m py_compile hermes_cli/main.py hermes_cli/pet_overlay.py tests/hermes_cli/test_pet_overlay.py
/usr/bin/swiftc hermes_cli/assets/hermes_pet_macos.swift -o /tmp/hermes_pet_macos_test
venv/bin/python3 -m pytest -q tests/hermes_cli/test_pet_overlay.py tests/hermes_cli/test_pet_sessions.py
git diff --check
```

배포 전 전체 Hermes Pet release gate:

```bash
bash connectors/hermes/release-check.sh
```

이 검증은 shell syntax, Python import, pet regression, web/dashboard test,
AppKit helper compile, SwiftPM app scaffold build, `git diff --check`, 설치된
`hermes-pet --status`를 확인합니다.

## 배포 방향

배포는 두 트랙을 병행합니다.

1. Hermes 전용 패키지: 기존 사용자를 위한 skill/wrapper와 `hermes pet ...` 호환 명령
2. 범용 macOS 앱: 향후 signed `.dmg`, 상태표시줄, connector 선택, 독립 로그인 항목, Hermes/OpenClaw/Codex/Claude Code/Kimi 계열 connector 지원

기본 배포 경로는 Hermes upstream source를 수정하지 않는 방식이어야 합니다. 현재 repo 내부 Hermes hook은 MVP 검증과 로컬 개발용으로 유지하고, 사용자 배포는 독립 앱 + 제거 가능한 Hermes connector로 수렴시킵니다.

## 참고

- Hermes Agent upstream: https://github.com/NousResearch/hermes-agent
- Codex Pet Share: https://codex-pet-share.pages.dev/
- Notice 및 attribution: [NOTICE.md](../../NOTICE.md)

## 감사

Hermes Pet은 Nous Research의 Hermes Agent 위에서 동작하되, upstream Hermes를
수정하지 않는 제거 가능한 connector 방향을 유지합니다. 애니메이션 펫 가져오기
기능은 Codex Pet Share의 공개 pixel companion catalog와 커뮤니티 아트워크
덕분에 가능했습니다. 사이트 운영자와 pet artwork를 공유한 제작자들에게
감사합니다. 데스크탑 펫의 상태/애니메이션 UX는 Codex Desktop pet 경험을
참고했습니다.

## 라이선스

MIT. [LICENSE](../../LICENSE)를 참고하세요.
