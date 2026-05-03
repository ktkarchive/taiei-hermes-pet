#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PYTHON="${ROOT}/venv/bin/python3"
SWIFTC="/usr/bin/swiftc"
APP_BUILD_PATH="${HERMES_PET_APP_BUILD_PATH:-/tmp/hermes-pet-app-build}"
HELPER_OUT="${HERMES_PET_HELPER_OUT:-/tmp/hermes_pet_macos_test}"

if [ ! -x "$PYTHON" ]; then
  echo "Missing project Python: ${PYTHON}" >&2
  exit 1
fi

cd "$ROOT"

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run bash -n \
  connectors/hermes/install.sh \
  connectors/hermes/uninstall.sh \
  connectors/hermes/install-from-git.sh \
  connectors/hermes/bin/hermes-pet \
  skills/productivity/hermes-pet/scripts/petctl.sh

run python3 -B -m py_compile \
  hermes_pet/protocol.py \
  hermes_cli/pet_protocol.py \
  hermes_cli/pet_overlay.py \
  hermes_cli/pet_sessions.py \
  hermes_cli/pet_forwarder.py \
  hermes_cli/pet_telegram_relay.py \
  hermes_cli/main.py \
  hermes_cli/web_server.py

run "$PYTHON" -m pytest -q -o addopts='' \
  tests/hermes_cli/test_pet_protocol.py \
  tests/hermes_cli/test_pet_sessions.py \
  tests/hermes_cli/test_pet_overlay.py \
  tests/hermes_cli/test_pet_forwarder.py \
  tests/hermes_cli/test_pet_share.py \
  tests/hermes_cli/test_pet_telegram_relay.py

run "$PYTHON" -m pytest -q -o addopts='' \
  tests/hermes_cli/test_web_server.py \
  tests/hermes_cli/test_web_server_host_header.py \
  tests/hermes_cli/test_dashboard_browser_safe_imports.py

PUBLIC_FORBIDDEN_PATTERN='Tailscale|tailscale|tailnet|--tailscale|Telegram|telegram|Discord|discord|remote-env|Remote Pets|private-network|chat-relay|relay setup|relay tools|--relay-test|relay-test|원격|リモート|远程'
PUBLIC_SURFACE_FILES=(
  README.md
  NOTICE.md
  docs/i18n
  docs/release
  connectors/README.md
  connectors/hermes/README.md
  skills/productivity/hermes-pet
  apps/macos/HermesPet/README.md
)

if rg -n -I "$PUBLIC_FORBIDDEN_PATTERN" "${PUBLIC_SURFACE_FILES[@]}"; then
  echo "Public macOS MVP docs still expose private-network or chat-relay setup." >&2
  exit 1
fi

if "$PYTHON" -m hermes_cli.main pet --help | rg -n -I "$PUBLIC_FORBIDDEN_PATTERN"; then
  echo "Public hermes pet help still exposes private-network or chat-relay setup." >&2
  exit 1
fi

MINIMAL_SMOKE_DIR="${HERMES_PET_MINIMAL_SMOKE_DIR:-/tmp/hermes-pet-minimal-release-check}"
if [ "${HERMES_PET_SKIP_MINIMAL_SMOKE:-0}" != "1" ]; then
  run rm -rf "$MINIMAL_SMOKE_DIR"
  run python3 -m venv "${MINIMAL_SMOKE_DIR}/venv"
  run "${MINIMAL_SMOKE_DIR}/venv/bin/python3" -m pip install --disable-pip-version-check \
    "PyYAML>=6.0.2,<7" \
    "python-dotenv>=1.2.1,<2"
  run env HERMES_HOME="${MINIMAL_SMOKE_DIR}/home" \
    "${MINIMAL_SMOKE_DIR}/venv/bin/python3" -m hermes_cli.main pet --status
  run env HERMES_HOME="${MINIMAL_SMOKE_DIR}/home" \
    "${MINIMAL_SMOKE_DIR}/venv/bin/python3" -m hermes_cli.main pet --share-current
fi

if [ -x "$SWIFTC" ]; then
  run "$SWIFTC" hermes_cli/assets/hermes_pet_macos.swift -o "$HELPER_OUT"
else
  echo "Skipping AppKit helper compile; swiftc not found at ${SWIFTC}" >&2
fi

if command -v swift >/dev/null 2>&1; then
  run swift build --package-path apps/macos/HermesPet --build-path "$APP_BUILD_PATH"
else
  echo "Skipping SwiftPM app build; swift not found" >&2
fi

run git diff --check

if command -v hermes-pet >/dev/null 2>&1; then
  run hermes-pet --status
elif [ "${HERMES_PET_SKIP_INSTALLED_STATUS:-0}" = "1" ]; then
  echo "Skipping installed hermes-pet status by HERMES_PET_SKIP_INSTALLED_STATUS=1" >&2
else
  echo "Missing installed hermes-pet command. Install the connector first or set HERMES_PET_SKIP_INSTALLED_STATUS=1 for CI-only source checks." >&2
  exit 1
fi

echo
echo "Hermes Pet release check passed."
