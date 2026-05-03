#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${HERMES_PET_REPO_URL:-https://github.com/ktkarchive/taiei-hermes-pet.git}"
INSTALL_DIR="${HERMES_PET_INSTALL_DIR:-${HOME}/.hermes/pet/taiei-hermes-pet}"
BRANCH="${HERMES_PET_BRANCH:-main}"
PORT="${HERMES_PET_PORT:-8768}"
START_PET=1

usage() {
  cat <<'EOF'
Usage: install-from-git.sh [options]

Clone or update the public Hermes Pet repository, install the Hermes connector,
and start the local macOS desktop pet.

Options:
  --repo URL       Git repository URL
  --dir PATH       Install directory
  --branch NAME    Git branch to checkout
  --port PORT      Local pet port, default 8768
  --no-start       Install only; do not start the pet
  -h, --help       Show this help

Environment:
  HERMES_PET_REPO_URL, HERMES_PET_INSTALL_DIR, HERMES_PET_BRANCH,
  HERMES_PET_PORT
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      REPO_URL="${2:?--repo requires a URL}"
      shift 2
      ;;
    --dir)
      INSTALL_DIR="${2:?--dir requires a path}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?--branch requires a branch name}"
      shift 2
      ;;
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

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Hermes Pet MVP is macOS-only. Windows/Linux renderers are not included yet." >&2
  exit 1
fi

for command in git python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

if ! xcode-select -p >/dev/null 2>&1 || [ ! -x /usr/bin/swiftc ]; then
  echo "Hermes Pet requires Apple Command Line Tools for the native macOS helper." >&2
  echo "Install them with: xcode-select --install" >&2
  exit 1
fi

case "$INSTALL_DIR" in
  /*) ;;
  *)
    echo "Install directory must be absolute: ${INSTALL_DIR}" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname -- "$INSTALL_DIR")"

if [ ! -e "$INSTALL_DIR" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
elif [ -d "${INSTALL_DIR}/.git" ]; then
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  if git -C "$INSTALL_DIR" show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    git -C "$INSTALL_DIR" checkout "$BRANCH"
  else
    git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/${BRANCH}"
  fi
  git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
else
  echo "Install directory exists but is not a git repository: ${INSTALL_DIR}" >&2
  exit 1
fi

bash "${INSTALL_DIR}/connectors/hermes/install.sh"

if [ "$START_PET" -eq 1 ]; then
  "${HOME}/.local/bin/hermes-pet" --background --port "$PORT"
  if command -v curl >/dev/null 2>&1; then
    health="$(curl -fsS "http://127.0.0.1:${PORT}/health")"
    case "$health" in
      *'"name":"hermes-pet"'*|*'"name": "hermes-pet"'*) ;;
      *)
        echo "Unexpected health response on port ${PORT}: ${health}" >&2
        exit 1
        ;;
    esac
  fi
fi

cat <<EOF
Hermes Pet installed.
Repository: ${INSTALL_DIR}
Command: ${HOME}/.local/bin/hermes-pet
Skill: ${HOME}/.hermes/skills/productivity/hermes-pet
Port: ${PORT}
EOF
