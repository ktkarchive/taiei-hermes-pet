#!/usr/bin/env bash
set -euo pipefail

PORT="${HERMES_PET_PORT:-8768}"
CMD="${1:-status}"
if [ "$#" -gt 0 ]; then
  shift
fi

PROJECT_ROOT="${HERMES_PET_PROJECT_ROOT:-}"
if [ -z "$PROJECT_ROOT" ] && [ -n "${HERMES_SKILL_DIR:-}" ] && [ -f "${HERMES_SKILL_DIR}/.project-root" ]; then
  PROJECT_ROOT="$(sed -n '1p' "${HERMES_SKILL_DIR}/.project-root")"
fi

run_pet() {
  if [ -n "$PROJECT_ROOT" ] && [ -x "${PROJECT_ROOT}/venv/bin/python3" ] && [ -f "${PROJECT_ROOT}/hermes_pet/cli.py" ]; then
    (cd "$PROJECT_ROOT" && "${PROJECT_ROOT}/venv/bin/python3" -m hermes_pet.cli "$@")
    return
  fi
  hermes-pet "$@"
}

usage() {
  cat <<'EOF'
Usage: petctl.sh <command> [extra hermes pet args]

Commands:
  status               Show active Hermes Pet runtime
  start                Start local localhost pet in background
  restart              Restart local pet in background
  stop                 Stop active pet
  health               Check localhost health endpoint
  sessions             List active/recent CLI/TUI sessions
  install-login        Install and load macOS LaunchAgent login item
  uninstall-login      Remove macOS LaunchAgent login item
  login-status         Show macOS LaunchAgent status
  start-login          Start installed LaunchAgent
  stop-login           Stop installed LaunchAgent
  share-list           List Codex Pet Share pets
  share-search QUERY   Search Codex Pet Share pets
  share-installed      List local saved pet artwork
  doctor               Print install/runtime diagnostics

Environment:
  HERMES_PET_PORT      Port for localhost pet commands, default 8768.
  HERMES_PET_PROJECT_ROOT
                       Pet workspace used before falling back to global hermes.
EOF
}

case "$CMD" in
  status)
    run_pet --status "$@"
    ;;
  start)
    run_pet --background --port "$PORT" "$@"
    ;;
  restart)
    run_pet --restart --port "$PORT" "$@"
    ;;
  stop)
    run_pet --stop "$@"
    ;;
  health)
    curl -fsS "http://127.0.0.1:${PORT}/health"
    ;;
  sessions)
    run_pet --sessions "$@"
    ;;
  install-login)
    run_pet --install-launch-agent --port "$PORT" --force "$@"
    ;;
  uninstall-login)
    run_pet --uninstall-launch-agent "$@"
    ;;
  login-status)
    run_pet --launch-agent-status "$@"
    ;;
  start-login)
    run_pet --start-launch-agent "$@"
    ;;
  stop-login)
    run_pet --stop-launch-agent "$@"
    ;;
  share-list)
    run_pet --share-list "$@"
    ;;
  share-search)
    run_pet --share-search "${1:-}" "${@:2}"
    ;;
  share-installed)
    run_pet --share-installed "$@"
    ;;
  doctor)
    echo "Hermes Pet doctor"
    echo "PORT=${PORT}"
    echo "HERMES_SKILL_DIR=${HERMES_SKILL_DIR:-}"
    echo "PROJECT_ROOT=${PROJECT_ROOT:-}"
    if [ -n "${PROJECT_ROOT:-}" ]; then
      if [ -f "${PROJECT_ROOT}/hermes_pet/cli.py" ]; then
        echo "project_pet_cli=ok"
      else
        echo "project_pet_cli=missing"
      fi
      if [ -x "${PROJECT_ROOT}/venv/bin/python3" ]; then
        echo "project_python=ok"
      else
        echo "project_python=missing"
      fi
    fi
    if command -v hermes-pet >/dev/null 2>&1; then
      echo "hermes_pet_command=$(command -v hermes-pet)"
    else
      echo "hermes_pet_command=missing"
    fi
    if command -v hermes >/dev/null 2>&1; then
      echo "hermes_command=$(command -v hermes)"
    else
      echo "hermes_command=missing"
    fi
    run_pet --status || true
    run_pet --launch-agent-status || true
    curl -fsS "http://127.0.0.1:${PORT}/health" || true
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    usage >&2
    exit 2
    ;;
esac
