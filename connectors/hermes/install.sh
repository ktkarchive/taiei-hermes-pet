#!/usr/bin/env bash
set -euo pipefail

CONNECTOR_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT_DEFAULT="$(CDPATH= cd -- "${CONNECTOR_DIR}/../.." && pwd)"
PROJECT_ROOT="${HERMES_PET_PROJECT_ROOT:-$PROJECT_ROOT_DEFAULT}"
BIN_DIR="${HERMES_PET_BIN_DIR:-${HOME}/.local/bin}"
SKILL_TARGET="${HERMES_PET_SKILL_DIR:-${HOME}/.hermes/skills/productivity/hermes-pet}"
DEFAULT_BIN_DIR="${HOME}/.local/bin"
DEFAULT_SKILL_TARGET="${HOME}/.hermes/skills/productivity/hermes-pet"
ALLOW_CUSTOM_INSTALL="${HERMES_PET_ALLOW_CUSTOM_INSTALL:-0}"
BOOTSTRAP_VENV="${HERMES_PET_BOOTSTRAP_VENV:-1}"
DRY_RUN=0
PET_RUNTIME_DEPS=(
  "PyYAML>=6.0.2,<7"
  "python-dotenv>=1.2.1,<2"
)

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install the Hermes-specific Hermes Pet connector without changing the global
`hermes` command.

Options:
  --project-root PATH   Pet workspace to pin in the installed skill
  --bin-dir PATH        Directory for the standalone hermes-pet command
  --skill-dir PATH      Installed Hermes skill directory
  --no-bootstrap        Do not create/install the project venv if missing
  --dry-run             Print actions without changing files
  -h, --help            Show this help

Environment:
  HERMES_PET_PROJECT_ROOT, HERMES_PET_BIN_DIR, HERMES_PET_SKILL_DIR,
  HERMES_PET_BOOTSTRAP_VENV, HERMES_PET_ALLOW_CUSTOM_INSTALL
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="${2:?--project-root requires a path}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?--bin-dir requires a path}"
      shift 2
      ;;
    --skill-dir)
      SKILL_TARGET="${2:?--skill-dir requires a path}"
      shift 2
      ;;
    --no-bootstrap)
      BOOTSTRAP_VENV=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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

if [ ! -f "${PROJECT_ROOT}/hermes_pet/cli.py" ]; then
  echo "Invalid Hermes Pet project root: ${PROJECT_ROOT}" >&2
  echo "Expected hermes_pet/cli.py." >&2
  exit 1
fi

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    return
  fi
  "$@"
}

ensure_project_python() {
  if [ -x "${PROJECT_ROOT}/venv/bin/python3" ]; then
    return
  fi
  if [ "$BOOTSTRAP_VENV" != "1" ]; then
    echo "Missing project Python: ${PROJECT_ROOT}/venv/bin/python3" >&2
    echo "Run python3 -m venv venv && venv/bin/python3 -m pip install PyYAML python-dotenv, or omit --no-bootstrap." >&2
    exit 1
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ python3 -m venv %q\n' "${PROJECT_ROOT}/venv"
    printf '+ %q -m pip install --disable-pip-version-check' "${PROJECT_ROOT}/venv/bin/python3"
    printf ' %q' "${PET_RUNTIME_DEPS[@]}"
    printf '\n'
    return
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to bootstrap ${PROJECT_ROOT}/venv" >&2
    exit 1
  fi
  python3 -m venv "${PROJECT_ROOT}/venv"
  "${PROJECT_ROOT}/venv/bin/python3" -m pip install --disable-pip-version-check "${PET_RUNTIME_DEPS[@]}"
}

absolute_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) echo "Path must be absolute: $1" >&2; exit 1 ;;
  esac
}

reject_dangerous_path() {
  local path="$1"
  case "$path" in
    ""|"/"|"$HOME"|"$HOME/"|"/Users"|"/Users/"|"/tmp"|"/tmp/")
      echo "Refusing dangerous install path: ${path}" >&2
      exit 1
      ;;
  esac
  case "$path" in
    *"/.."*|*"../"*|*"/."|*"/./"*)
      echo "Refusing path with parent/current traversal: ${path}" >&2
      exit 1
      ;;
  esac
}

validate_install_paths() {
  PROJECT_ROOT="$(absolute_path "$PROJECT_ROOT")"
  BIN_DIR="$(absolute_path "$BIN_DIR")"
  SKILL_TARGET="$(absolute_path "$SKILL_TARGET")"
  reject_dangerous_path "$PROJECT_ROOT"
  reject_dangerous_path "$BIN_DIR"
  reject_dangerous_path "$SKILL_TARGET"

  if [ "$(basename -- "$SKILL_TARGET")" != "hermes-pet" ]; then
    echo "Skill target must end with hermes-pet: ${SKILL_TARGET}" >&2
    exit 1
  fi

  if [ "$ALLOW_CUSTOM_INSTALL" != "1" ]; then
    if [ "$BIN_DIR" != "$DEFAULT_BIN_DIR" ]; then
      echo "Custom bin dir requires HERMES_PET_ALLOW_CUSTOM_INSTALL=1: ${BIN_DIR}" >&2
      exit 1
    fi
    if [ "$SKILL_TARGET" != "$DEFAULT_SKILL_TARGET" ]; then
      echo "Custom skill dir requires HERMES_PET_ALLOW_CUSTOM_INSTALL=1: ${SKILL_TARGET}" >&2
      exit 1
    fi
  fi
}

safe_remove_skill_target() {
  validate_install_paths
  if [ -e "$SKILL_TARGET" ]; then
    run rm -rf "$SKILL_TARGET"
  fi
}

validate_install_paths
ensure_project_python
SKILL_PARENT="$(dirname -- "$SKILL_TARGET")"
run mkdir -p "$BIN_DIR" "$SKILL_PARENT"
safe_remove_skill_target
run cp -R "${PROJECT_ROOT}/skills/productivity/hermes-pet" "$SKILL_TARGET"
run chmod +x "${SKILL_TARGET}/scripts/petctl.sh"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '+ write %q\n' "${SKILL_TARGET}/.project-root"
else
  printf '%s\n' "$PROJECT_ROOT" > "${SKILL_TARGET}/.project-root"
fi
run install -m 0755 "${CONNECTOR_DIR}/bin/hermes-pet" "${BIN_DIR}/hermes-pet"

cat <<EOF
Hermes Pet connector installed.
Skill: ${SKILL_TARGET}
Command: ${BIN_DIR}/hermes-pet
Project root: ${PROJECT_ROOT}
EOF
