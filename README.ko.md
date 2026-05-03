# Taiei Hermes Pet

> **macOS 전용 MVP.** 이 저장소는 Hermes Agent용 macOS 데스크탑 펫을 배포합니다.
> Windows/Linux 데스크탑 렌더러는 이번 릴리스에 포함되어 있지 않습니다.

Taiei Hermes Pet은 제거 가능한 Hermes Pet 패키지입니다. 전역 `hermes` 명령이나
사용자의 Hermes checkout을 수정하지 않고, 독립 `hermes-pet` 명령과 Hermes skill
wrapper를 설치합니다.

언어: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh.md) | [日本語](README.ja.md)

## 패키지

설치 가능한 패키지는 `hermes-pet-macos/`에 있습니다.

## 설치

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/install.sh"
```

설치 후 확인:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

자세한 사용법은 [`hermes-pet-macos/README.md`](hermes-pet-macos/README.md)와
[`hermes-pet-macos/docs/i18n/README.ko.md`](hermes-pet-macos/docs/i18n/README.ko.md)를 보세요.

## Hermes에게 설치 요청하기

```text
https://github.com/ktkarchive/taiei-hermes-pet 에서 Hermes Pet을 설치해줘.
저장소의 install.sh를 사용해서 macOS 데스크탑 펫을 8768 포트로 시작하고,
hermes-pet --status와 http://127.0.0.1:8768/health를 검증해줘.
전역 hermes 명령은 수정하지 마.
```

## 감사

Hermes Pet은 Hermes Agent 사용자를 위해 만들었습니다. 펫 아트워크 선택/가져오기
기능은 [Codex Pet Share](https://codex-pet-share.pages.dev/) 커뮤니티의 공개 공유
사이트에 감사하며 참고합니다.
