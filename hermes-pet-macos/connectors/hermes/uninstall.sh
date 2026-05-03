#!/usr/bin/env bash
set -euo pipefail

BIN_PATH="${HERMES_PET_BIN_PATH:-${HOME}/.local/bin/hermes-pet}"
SKILL_TARGET="${HERMES_PET_SKILL_DIR:-${HOME}/.hermes/skills/productivity/hermes-pet}"
RUNTIME_DIR="${HERMES_PET_RUNTIME_DIR:-${HOME}/.hermes/runtime}"
DEFAULT_BIN_PATH="${HOME}/.local/bin/hermes-pet"
DEFAULT_SKILL_TARGET="${HOME}/.hermes/skills/productivity/hermes-pet"
DEFAULT_RUNTIME_DIR="${HOME}/.hermes/runtime"
ALLOW_CUSTOM_INSTALL="${HERMES_PET_ALLOW_CUSTOM_INSTALL:-0}"
STOP_RUNNING=1
PURGE_RUNTIME=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: uninstall.sh [options]

Remove the Hermes-specific Hermes Pet connector. This does not remove or modify
the global `hermes` command.

Options:
  --keep-running        Do not stop the currently running pet
  --purge-runtime       Remove Hermes Pet runtime/cache files
  --dry-run             Print actions without changing files
  -h, --help            Show this help

Environment:
  HERMES_PET_BIN_PATH, HERMES_PET_SKILL_DIR, HERMES_PET_RUNTIME_DIR
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --keep-running)
      STOP_RUNNING=0
      shift
      ;;
    --purge-runtime)
      PURGE_RUNTIME=1
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

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    return
  fi
  "$@"
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
      echo "Refusing dangerous uninstall path: ${path}" >&2
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

validate_uninstall_paths() {
  BIN_PATH="$(absolute_path "$BIN_PATH")"
  SKILL_TARGET="$(absolute_path "$SKILL_TARGET")"
  RUNTIME_DIR="$(absolute_path "$RUNTIME_DIR")"
  reject_dangerous_path "$BIN_PATH"
  reject_dangerous_path "$SKILL_TARGET"
  reject_dangerous_path "$RUNTIME_DIR"

  if [ "$(basename -- "$BIN_PATH")" != "hermes-pet" ]; then
    echo "Command path must end with hermes-pet: ${BIN_PATH}" >&2
    exit 1
  fi
  if [ "$(basename -- "$SKILL_TARGET")" != "hermes-pet" ]; then
    echo "Skill target must end with hermes-pet: ${SKILL_TARGET}" >&2
    exit 1
  fi

  if [ "$ALLOW_CUSTOM_INSTALL" != "1" ]; then
    if [ "$BIN_PATH" != "$DEFAULT_BIN_PATH" ]; then
      echo "Custom command path requires HERMES_PET_ALLOW_CUSTOM_INSTALL=1: ${BIN_PATH}" >&2
      exit 1
    fi
    if [ "$SKILL_TARGET" != "$DEFAULT_SKILL_TARGET" ]; then
      echo "Custom skill dir requires HERMES_PET_ALLOW_CUSTOM_INSTALL=1: ${SKILL_TARGET}" >&2
      exit 1
    fi
    if [ "$RUNTIME_DIR" != "$DEFAULT_RUNTIME_DIR" ]; then
      echo "Custom runtime dir requires HERMES_PET_ALLOW_CUSTOM_INSTALL=1: ${RUNTIME_DIR}" >&2
      exit 1
    fi
  fi
}

remove_launch_agents() {
  local launch_agents="${HOME}/Library/LaunchAgents"
  if [ -x "$BIN_PATH" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '+ %q --uninstall-launch-agent\n' "$BIN_PATH"
    else
      "$BIN_PATH" --uninstall-launch-agent >/dev/null 2>&1 || true
    fi
  fi

  if [ -d "$launch_agents" ]; then
    for plist in "$launch_agents"/ai.hermes.pet*.plist; do
      [ -e "$plist" ] || continue
      local label
      label="$(basename -- "$plist" .plist)"
      if [ "$DRY_RUN" -eq 1 ]; then
        printf '+ launchctl bootout %q\n' "gui/$(id -u)/${label}"
        printf '+ rm -f %q\n' "$plist"
      else
        launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
        rm -f "$plist"
      fi
    done
  fi
}

safe_remove_connector() {
  validate_uninstall_paths
  [ -e "$SKILL_TARGET" ] && run rm -rf "$SKILL_TARGET"
  [ -e "$BIN_PATH" ] && run rm -f "$BIN_PATH"
  return 0
}

safe_remove_runtime_entry() {
  local path="$1"
  case "$path" in
    "$RUNTIME_DIR"/*) ;;
    *)
      echo "Refusing runtime purge outside runtime dir: ${path}" >&2
      exit 1
      ;;
  esac
  [ -e "$path" ] && run rm -rf "$path"
  return 0
}

validate_uninstall_paths

if [ "$STOP_RUNNING" -eq 1 ] && [ -x "$BIN_PATH" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ %q --stop\n' "$BIN_PATH"
  else
    "$BIN_PATH" --stop >/dev/null 2>&1 || true
  fi
fi

remove_launch_agents
safe_remove_connector

if [ "$PURGE_RUNTIME" -eq 1 ]; then
  safe_remove_runtime_entry "${RUNTIME_DIR}/hermes_pet_macos"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_assets"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_launch_cli.command"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_launch_tui.command"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_overlay.json"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_overlay.log"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_overlay.error.log"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_preferences.json"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_relay_token"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_cmux_sessions.json"
  safe_remove_runtime_entry "${RUNTIME_DIR}/pet_share_sheet_converter"
fi

cat <<EOF
Hermes Pet connector removed.
Skill removed: ${SKILL_TARGET}
Command removed: ${BIN_PATH}
Runtime purged: ${PURGE_RUNTIME}
EOF
