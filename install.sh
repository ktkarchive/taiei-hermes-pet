#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PET_ROOT="${ROOT}/hermes-pet-macos"
PORT="${HERMES_PET_PORT:-8768}"
START_PET=1
BIN_DIR="${HERMES_PET_BIN_DIR:-${HOME}/.local/bin}"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install the Hermes Pet macOS package from this repository.

Options:
  --port PORT      Local pet port, default 8768
  --no-start       Install only; do not start the pet
  -h, --help       Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port)
      PORT="${2:?--port requires a port}"
      shift 2
      ;;
    --no-start)
      START_PET=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -f "${PET_ROOT}/connectors/hermes/install.sh" ]; then
  echo "Missing Hermes Pet macOS package: ${PET_ROOT}" >&2
  exit 1
fi

bash "${PET_ROOT}/connectors/hermes/install.sh" --project-root "${PET_ROOT}"

if [ "$START_PET" -eq 1 ]; then
  "${BIN_DIR}/hermes-pet" --background --port "$PORT"
  if command -v curl >/dev/null 2>&1; then
    health=""
    deadline=$((SECONDS + 25))
    while [ "$SECONDS" -lt "$deadline" ]; do
      if health="$(curl -fsS "http://127.0.0.1:${PORT}/health" 2>/dev/null)"; then
        break
      fi
      sleep 0.5
    done
    case "$health" in
      *'"name":"hermes-pet"'*|*'"name": "hermes-pet"'*) ;;
      *)
        echo "Hermes Pet did not become healthy on port ${PORT}: ${health}" >&2
        exit 1
        ;;
    esac
  fi
fi

cat <<EOF
Hermes Pet installed.
Package: ${PET_ROOT}
Command: ${BIN_DIR}/hermes-pet
Port: ${PORT}
EOF
