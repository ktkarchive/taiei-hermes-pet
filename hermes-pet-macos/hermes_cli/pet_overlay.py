"""Desktop Hermes pet overlay.

This is intentionally independent from the web dashboard: it creates a small
transparent, always-on-top screen overlay and exposes a tiny local HTTP event
inlet. On macOS the overlay uses a native AppKit helper; Tk remains the fallback
path. Dashboard/TUI events can discover the inlet through the runtime file
written under the active Hermes home.
"""

from __future__ import annotations

import hmac
import hashlib
import html
import json
import locale
import os
import queue
import re
import shutil
import shlex
import signal
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

try:
    import tkinter as tk
    from tkinter import Menu
except Exception:  # Tk is only needed for the non-macOS development fallback.
    tk = None  # type: ignore[assignment]
    Menu = None  # type: ignore[assignment]

from hermes_pet.constants import get_hermes_home
from hermes_pet.protocol import (
    CMUX_SESSION_MAP_FILENAME,
    LOCAL_SOURCE_ID,
    PET_PREFERENCES_FILENAME,
    PET_RELAY_HEADER_NAME,
    PET_RELAY_TOKEN_ENV,
    PROTOCOL_VERSION,
    RELAY_TOKEN_FILENAME,
    RUNTIME_FILENAME,
    SUPPORTED_PET_LANGUAGES,
    PetEvent,
    PetViewState,
    clean_notification_count as _clean_notification_count,
    clean_optional_token as _clean_optional_token,
    clean_source_id as _clean_source_id,
    clean_text as _clean_text,
    default_notification_kind as _default_notification_kind,
    default_notification_label as _default_notification_label,
    is_loopback_host as _is_loopback_host,
    normalize_event,
    runtime_url as _runtime_url,
)
from hermes_cli.pet_share import active_pet_asset_dir

try:
    from PIL import Image, ImageDraw, ImageFilter
except Exception:  # Pillow is optional; the live Tk pet uses canvas primitives.
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]

DEFAULT_LEFT_CLICK_OPENS_TERMINAL = False
DEFAULT_SESSION_LIST_LIMIT = 5
DEFAULT_TERMINAL_LAUNCHER = "macos"
TERMINAL_LAUNCHERS = {
    "macos": "macOS Terminal",
    "cmux": "cmux",
}
SUPPORTED_TERMINAL_LAUNCHERS = frozenset({"macos", "cmux"})
MAX_BODY_BYTES = 64 * 1024
ASSET_DIR = Path(__file__).with_name("assets")
DEFAULT_PET_PORT = 8768
SPRITE_FILES = {
    "idle": "hermes_pet_idle.png",
    "blink": "hermes_pet_blink.png",
    "working": "hermes_pet_working.png",
    "review": "hermes_pet_review.png",
}
MACOS_HELPER_SOURCE = ASSET_DIR / "hermes_pet_macos.swift"
MACOS_HELPER_BINARY = "hermes_pet_macos"
PET_LAUNCHD_BASE_LABEL = "ai.hermes.pet"


def _active_asset_dir() -> Path:
    return active_pet_asset_dir(ASSET_DIR)


def runtime_file() -> Path:
    return get_hermes_home() / "runtime" / RUNTIME_FILENAME


def relay_token_file() -> Path:
    return get_hermes_home() / "runtime" / RELAY_TOKEN_FILENAME


def pet_preferences_file() -> Path:
    return get_hermes_home() / "runtime" / PET_PREFERENCES_FILENAME


def cmux_session_map_file() -> Path:
    return get_hermes_home() / "runtime" / CMUX_SESSION_MAP_FILENAME


def _system_pet_language() -> str:
    explicit = str(os.getenv("HERMES_PET_LANGUAGE") or "").strip().lower()
    if explicit in SUPPORTED_PET_LANGUAGES:
        return explicit
    locale_values = [
        os.getenv("LC_ALL"),
        os.getenv("LC_MESSAGES"),
        os.getenv("LANG"),
        locale.getlocale()[0],
    ]
    for value in locale_values:
        if str(value or "").lower().startswith("ko"):
            return "ko"
        if str(value or "").lower().startswith("en"):
            return "en"
        if str(value or "").lower().startswith("ja"):
            return "ja"
        if str(value or "").lower().startswith("zh"):
            return "zh"
    return "ko"


def read_pet_preferences() -> dict[str, Any]:
    language = _system_pet_language()
    try:
        data = json.loads(pet_preferences_file().read_text())
    except Exception:
        return {
            "language": language,
            "left_click_opens_terminal": DEFAULT_LEFT_CLICK_OPENS_TERMINAL,
            "session_list_limit": DEFAULT_SESSION_LIST_LIMIT,
            "terminal_launcher": DEFAULT_TERMINAL_LAUNCHER,
        }
    if not isinstance(data, dict):
        data = {}
    saved_language = str(data.get("language") or "").strip().lower()
    if saved_language in SUPPORTED_PET_LANGUAGES:
        language = saved_language
    try:
        session_list_limit = int(data.get("session_list_limit") or DEFAULT_SESSION_LIST_LIMIT)
    except Exception:
        session_list_limit = DEFAULT_SESSION_LIST_LIMIT
    return {
        "language": language,
        "left_click_opens_terminal": bool(data.get("left_click_opens_terminal", DEFAULT_LEFT_CLICK_OPENS_TERMINAL)),
        "session_list_limit": max(1, min(session_list_limit, 50)),
        "terminal_launcher": _clean_terminal_launcher(data.get("terminal_launcher")),
    }


def _boolish(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def write_pet_preferences(
    *,
    language: Optional[str] = None,
    left_click_opens_terminal: Optional[bool] = None,
    session_list_limit: Optional[int] = None,
    terminal_launcher: Optional[str] = None,
) -> dict[str, Any]:
    prefs = read_pet_preferences()
    if language is not None:
        clean_language = str(language or "").strip().lower()
        if clean_language not in SUPPORTED_PET_LANGUAGES:
            raise ValueError("language must be ko, en, ja, or zh")
        prefs["language"] = clean_language
    if left_click_opens_terminal is not None:
        prefs["left_click_opens_terminal"] = bool(left_click_opens_terminal)
    if session_list_limit is not None:
        prefs["session_list_limit"] = max(1, min(int(session_list_limit), 50))
    if terminal_launcher is not None:
        prefs["terminal_launcher"] = _clean_terminal_launcher(terminal_launcher)

    path = pet_preferences_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**prefs, "updated_at": time.time()}, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return prefs


def write_pet_language(language: str) -> str:
    return str(write_pet_preferences(language=language)["language"])


def _clean_terminal_launcher(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"terminus", "termius"}:
        return DEFAULT_TERMINAL_LAUNCHER
    return raw if raw in SUPPORTED_TERMINAL_LAUNCHERS else DEFAULT_TERMINAL_LAUNCHER


def _app_available(name: str) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ["open", "-Ra", name],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _terminal_launcher_options() -> list[dict[str, Any]]:
    return [
        {"id": "macos", "label": TERMINAL_LAUNCHERS["macos"], "available": sys.platform == "darwin"},
        {
            "id": "cmux",
            "label": TERMINAL_LAUNCHERS["cmux"],
            "available": _app_available("cmux") or Path("/Applications/cmux.app").exists(),
        },
    ]


def write_relay_token(token: str) -> Path:
    path = relay_token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(token.strip() + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)
    return path


def read_relay_token() -> Optional[str]:
    try:
        token = relay_token_file().read_text().strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return token or None


def load_or_create_relay_token(*, rotate: bool = False) -> str:
    if not rotate:
        existing = read_relay_token()
        if existing:
            return existing
    token = secrets.token_urlsafe(32)
    write_relay_token(token)
    return token


def resolve_relay_token(
    explicit_token: Optional[str],
    *,
    use_token_file: bool = False,
    rotate: bool = False,
) -> Optional[str]:
    if rotate:
        return load_or_create_relay_token(rotate=True)
    if explicit_token:
        if use_token_file:
            write_relay_token(explicit_token)
        return explicit_token
    if use_token_file:
        return load_or_create_relay_token()
    return None


def _ensure_tk_library_paths() -> None:
    if os.getenv("TCL_LIBRARY") and os.getenv("TK_LIBRARY"):
        return

    candidates: list[Path] = []
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        candidates.append(parent / "lib")
    candidates.extend([
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib",
        Path.home() / ".local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib",
    ])

    for lib_dir in candidates:
        tcl_dir = lib_dir / "tcl9.0"
        tk_dir = lib_dir / "tk9.0"
        if (tcl_dir / "init.tcl").exists() and (tk_dir / "tk.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
            os.environ.setdefault("TK_LIBRARY", str(tk_dir))
            return


def write_runtime(endpoint_url: str, token: str) -> None:
    path = runtime_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": endpoint_url,
                "token": token,
                "token_header": PET_RELAY_HEADER_NAME,
                "process_kind": "hermes_pet_overlay",
                "updated_at": time.time(),
            },
            indent=2,
        )
    )
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)


def remove_runtime() -> None:
    path = runtime_file()
    try:
        data = json.loads(path.read_text())
    except Exception:
        return
    if data.get("pid") == os.getpid():
        path.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_command(pid: int) -> Optional[str]:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    command = result.stdout.strip()
    return command or None


def _pid_matches_pet_runtime(pid: int) -> tuple[bool, str]:
    if not _pid_alive(pid):
        return False, "runtime pid is not alive"
    command = _pid_command(pid)
    if not command:
        return False, "runtime pid command could not be verified"
    if (
        "hermes_pet.cli" in command
    ) or (
        "hermes_cli.main" in command
        and re.search(r"(^|\s)pet(\s|$)", command)
    ) or re.search(r"(^|/|\\)hermes-pet(\s|$)", command) or (
        re.search(r"(^|/|\\)hermes(\s|$)", command)
        and re.search(r"(^|\s)pet(\s|$)", command)
    ):
        return True, command
    return False, "runtime pid does not look like Hermes Pet"


def pet_overlay_status() -> dict[str, Any]:
    path = runtime_file()
    status: dict[str, Any] = {
        "running": False,
        "runtime_path": str(path),
    }
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        status["reason"] = "runtime file not found"
        return status
    except Exception as exc:
        status["reason"] = f"runtime file is unreadable: {exc}"
        return status

    if isinstance(data, dict):
        status.update(data)
    pid = data.get("pid") if isinstance(data, dict) else None
    if isinstance(pid, int):
        matches, detail = _pid_matches_pet_runtime(pid)
        status["running"] = matches
        if not status["running"]:
            status["reason"] = detail
        else:
            status["process_command"] = detail
    else:
        status["reason"] = "runtime file has no pid"
    return status


def stop_pet_overlay(timeout: float = 3.0) -> tuple[bool, str]:
    status = pet_overlay_status()
    pid = status.get("pid")
    path = runtime_file()

    if not isinstance(pid, int):
        return False, str(status.get("reason") or "Hermes Pet is not running")

    if not status.get("running"):
        path.unlink(missing_ok=True)
        return False, str(status.get("reason") or "Hermes Pet is not running")

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        path.unlink(missing_ok=True)
        return False, f"failed to stop pid {pid}: {exc}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            return True, f"stopped Hermes Pet pid {pid}"
        time.sleep(0.05)

    return False, f"sent SIGTERM to pid {pid}, but it is still running"


def _pet_process_args(
    *,
    host: str,
    port: int,
    label: str,
    size: int,
    show_local: bool,
    insecure: bool,
    initial_x: Optional[int],
    initial_y: Optional[int],
) -> list[str]:
    args = [
        str(_hermes_python_executable()),
        "-m",
        "hermes_pet.cli",
        "--host",
        str(host),
        "--port",
        str(port),
        "--label",
        str(label),
        "--size",
        str(size),
    ]
    if not show_local:
        args.append("--no-local")
    if insecure:
        args.append("--insecure")
    if initial_x is not None:
        args.extend(["--x", str(initial_x)])
    if initial_y is not None:
        args.extend(["--y", str(initial_y)])
    return args


def _pet_process_env(token: Optional[str] = None) -> dict[str, str]:
    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    venv = project_root / "venv"
    if venv.exists():
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = f"{venv / 'bin'}:{env.get('PATH', '')}"
    env["HERMES_HOME"] = str(get_hermes_home())
    if token:
        env[PET_RELAY_TOKEN_ENV] = token
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def start_pet_overlay_background(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PET_PORT,
    token: Optional[str] = None,
    label: str = "Hermes Local",
    size: int = 84,
    show_local: bool = True,
    insecure: bool = False,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
    replace: bool = True,
) -> tuple[bool, str]:
    if not _is_loopback_host(host) and not insecure:
        return False, "refusing to bind outside localhost without --insecure"

    status = pet_overlay_status()
    if status.get("running"):
        if not replace:
            return False, f"Hermes Pet already running: pid={status.get('pid')}"
        stopped, stop_message = stop_pet_overlay()
        if not stopped:
            return False, f"could not replace running Hermes Pet: {stop_message}"

    log_dir = get_hermes_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pet_overlay.log"
    args = _pet_process_args(
        host=host,
        port=port,
        label=label,
        size=size,
        show_local=show_local,
        insecure=insecure,
        initial_x=initial_x,
        initial_y=initial_y,
    )

    try:
        with log_path.open("ab", buffering=0) as log_file:
            process = subprocess.Popen(
                args,
                cwd=str(Path(__file__).resolve().parents[1]),
                env=_pet_process_env(token),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        return False, f"failed to start Hermes Pet in background: {exc}"

    deadline = time.time() + 2.0
    while time.time() < deadline:
        status = pet_overlay_status()
        if status.get("running"):
            return True, f"Hermes Pet started: pid={status.get('pid')} url={status.get('url')}"
        if process.poll() is not None:
            return False, f"Hermes Pet exited early; see {log_path}"
        time.sleep(0.1)

    return True, f"Hermes Pet starting in background: pid={process.pid}; see {log_path}"


def _schedule_pet_restart(
    *,
    host: str,
    port: int,
    token: str,
    label: str,
    size: int,
    show_local: bool,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
) -> tuple[bool, str]:
    project_root = Path(__file__).resolve().parents[1]
    args = [
        sys.executable,
        "-m",
        "hermes_pet.cli",
        "--background",
        "--host",
        host,
        "--port",
        str(port),
        "--label",
        label,
        "--size",
        str(size),
    ]
    if not show_local:
        args.append("--no-local")
    if initial_x is not None:
        args.extend(["--x", str(initial_x)])
    if initial_y is not None:
        args.extend(["--y", str(initial_y)])
    if not _is_loopback_host(host):
        args.append("--insecure")

    payload = json.dumps({
        "args": args,
        "cwd": str(project_root),
    })
    code = (
        "import json, os, subprocess, sys, time; "
        f"payload = json.loads({payload!r}); "
        "time.sleep(0.6); "
        "subprocess.Popen("
        "payload['args'], cwd=payload['cwd'], env=os.environ.copy(), "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, "
        "start_new_session=True, close_fds=True"
        ")"
    )
    try:
        subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=str(project_root),
            env=_pet_process_env(token),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        return False, f"failed to schedule Hermes Pet restart: {exc}"
    return True, "Hermes Pet restart scheduled"


def _launchd_user_home() -> Path:
    import pwd

    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _pet_profile_suffix() -> str:
    home = get_hermes_home().resolve()
    try:
        from hermes_pet.constants import get_default_hermes_root

        default = get_default_hermes_root().resolve()
        if home == default:
            return ""
        profiles_root = (default / "profiles").resolve()
        rel = home.relative_to(profiles_root)
        if len(rel.parts) == 1 and re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", rel.parts[0]):
            return rel.parts[0]
    except Exception:
        pass
    return hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:8]


def pet_launchd_label() -> str:
    suffix = _pet_profile_suffix()
    return f"{PET_LAUNCHD_BASE_LABEL}-{suffix}" if suffix else PET_LAUNCHD_BASE_LABEL


def pet_launchd_plist_path() -> Path:
    return _launchd_user_home() / "Library" / "LaunchAgents" / f"{pet_launchd_label()}.plist"


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl(args: list[str], *, timeout: float = 30.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    output = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, output


def _installed_hermes_pet_wrapper() -> Optional[Path]:
    raw = os.getenv("HERMES_PET_BIN_PATH") or str(Path.home() / ".local/bin/hermes-pet")
    path = Path(raw).expanduser()
    try:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    except OSError:
        return None
    return None


def _pet_wrapper_args(
    *,
    host: str,
    port: int,
    label: str,
    size: int,
    show_local: bool,
    insecure: bool,
    initial_x: Optional[int],
    initial_y: Optional[int],
) -> Optional[list[str]]:
    wrapper = _installed_hermes_pet_wrapper()
    if not wrapper:
        return None
    args = [
        str(wrapper),
        "--host",
        str(host),
        "--port",
        str(port),
        "--label",
        str(label),
        "--size",
        str(size),
    ]
    if not show_local:
        args.append("--no-local")
    if insecure:
        args.append("--insecure")
    if initial_x is not None:
        args.extend(["--x", str(initial_x)])
    if initial_y is not None:
        args.extend(["--y", str(initial_y)])
    return args


def _plist_string(value: Any) -> str:
    return f"<string>{html.escape(str(value), quote=True)}</string>"


def generate_pet_launchd_plist(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PET_PORT,
    token: Optional[str] = None,
    label: str = "Hermes Local",
    size: int = 84,
    show_local: bool = True,
    insecure: bool = False,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
) -> str:
    log_dir = get_hermes_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[1]
    venv = project_root / "venv"
    path_entries = []
    if venv.exists():
        path_entries.append(str(venv / "bin"))
    path_entries.extend([p for p in os.environ.get("PATH", "").split(":") if p])
    env_path = ":".join(dict.fromkeys(path_entries))
    args = _pet_wrapper_args(
        host=host,
        port=port,
        label=label,
        size=size,
        show_local=show_local,
        insecure=insecure,
        initial_x=initial_x,
        initial_y=initial_y,
    ) or _pet_process_args(
        host=host,
        port=port,
        label=label,
        size=size,
        show_local=show_local,
        insecure=insecure,
        initial_x=initial_x,
        initial_y=initial_y,
    )
    args_xml = "\n        ".join(_plist_string(arg) for arg in args)
    venv_xml = f"\n        <key>VIRTUAL_ENV</key>\n        {_plist_string(venv)}" if venv.exists() else ""
    relay_token_xml = (
        f"\n        <key>{PET_RELAY_TOKEN_ENV}</key>\n        {_plist_string(token)}"
        if token
        else ""
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    {_plist_string(pet_launchd_label())}

    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>

    <key>WorkingDirectory</key>
    {_plist_string(Path.home() if args[0].endswith("/hermes-pet") else project_root)}

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        {_plist_string(env_path)}
        <key>HERMES_HOME</key>
        {_plist_string(get_hermes_home().resolve())}{venv_xml}{relay_token_xml}
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>

    <key>StandardOutPath</key>
    {_plist_string(log_dir / "pet_overlay.log")}

    <key>StandardErrorPath</key>
    {_plist_string(log_dir / "pet_overlay.error.log")}
</dict>
</plist>
"""


def pet_launchd_status() -> dict[str, Any]:
    plist_path = pet_launchd_plist_path()
    label = pet_launchd_label()
    status: dict[str, Any] = {
        "label": label,
        "plist_path": str(plist_path),
        "installed": plist_path.exists(),
        "loaded": False,
    }
    if sys.platform != "darwin":
        status["reason"] = "launchd is only available on macOS"
        return status
    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status["loaded"] = result.returncode == 0
        status["launchctl"] = result.stdout.strip() or result.stderr.strip()
    except Exception as exc:
        status["reason"] = str(exc)
    return status


def install_pet_launch_agent(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PET_PORT,
    token: Optional[str] = None,
    label: str = "Hermes Local",
    size: int = 84,
    show_local: bool = True,
    insecure: bool = False,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
    force: bool = False,
) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "launchd is only available on macOS"
    plist_path = pet_launchd_plist_path()
    plist = generate_pet_launchd_plist(
        host=host,
        port=port,
        token=token,
        label=label,
        size=size,
        show_local=show_local,
        insecure=insecure,
        initial_x=initial_x,
        initial_y=initial_y,
    )
    status_before = pet_launchd_status()
    if (
        plist_path.exists()
        and not force
        and plist_path.read_text() == plist
        and status_before.get("loaded")
    ):
        return True, f"Hermes Pet launch agent already installed: {plist_path}"

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = plist_path.with_suffix(".tmp")
    tmp.write_text(plist)
    tmp.chmod(0o600)
    tmp.replace(plist_path)
    plist_path.chmod(0o600)
    launchd_target = f"{_launchd_domain()}/{pet_launchd_label()}"
    status = pet_launchd_status()
    if force or status.get("loaded"):
        _launchctl(["bootout", launchd_target])
    bootstrapped, bootstrap_output = _launchctl(["bootstrap", _launchd_domain(), str(plist_path)])
    if not bootstrapped:
        return False, f"failed to load Hermes Pet launch agent: {bootstrap_output or 'launchctl bootstrap failed'}"
    started, start_output = _launchctl(["kickstart", launchd_target])
    if not started:
        return False, f"failed to start Hermes Pet launch agent: {start_output or 'launchctl kickstart failed'}"
    return True, f"Hermes Pet launch agent installed: {plist_path}"


def uninstall_pet_launch_agent() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "launchd is only available on macOS"
    plist_path = pet_launchd_plist_path()
    _launchctl(["bootout", f"{_launchd_domain()}/{pet_launchd_label()}"])
    if plist_path.exists():
        plist_path.unlink()
        return True, f"Hermes Pet launch agent removed: {plist_path}"
    return True, "Hermes Pet launch agent was not installed"


def start_pet_launch_agent() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "launchd is only available on macOS"
    plist_path = pet_launchd_plist_path()
    if not plist_path.exists():
        return False, "Hermes Pet launch agent is not installed"
    target = f"{_launchd_domain()}/{pet_launchd_label()}"
    started, output = _launchctl(["kickstart", target])
    if not started:
        bootstrapped, bootstrap_output = _launchctl(["bootstrap", _launchd_domain(), str(plist_path)])
        if not bootstrapped:
            return False, f"failed to load Hermes Pet launch agent: {bootstrap_output or output or 'launchctl bootstrap failed'}"
        started, output = _launchctl(["kickstart", target])
    if not started:
        return False, f"failed to start Hermes Pet launch agent: {output or 'launchctl kickstart failed'}"
    return True, "Hermes Pet launch agent started"


def stop_pet_launch_agent(*, stop_current: bool = True) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "launchd is only available on macOS"
    stopped, output = _launchctl(["bootout", f"{_launchd_domain()}/{pet_launchd_label()}"])
    if stop_current:
        stop_pet_overlay()
    if not stopped:
        status = pet_launchd_status()
        if status.get("installed") and status.get("loaded"):
            return False, f"failed to stop Hermes Pet launch agent: {output or 'launchctl bootout failed'}"
    return True, "Hermes Pet launch agent stopped"


class PetEventServer(ThreadingHTTPServer):
    event_queue: "queue.Queue[PetEvent]"
    relay_token: str


class PetEventHandler(BaseHTTPRequestHandler):
    server: PetEventServer

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.server.relay_token
        actual = self.headers.get(PET_RELAY_HEADER_NAME, "")
        return bool(actual) and hmac.compare_digest(actual.encode(), expected.encode())

    def do_GET(self) -> None:
        if self.path.rstrip("/") not in {"/health", "/api/pet/health"}:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        self._send_json(200, {"ok": True, "name": "hermes-pet"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") not in {"/api/pet/events", "/event"}:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        try:
            length = min(int(self.headers.get("Content-Length", "0")), MAX_BODY_BYTES)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
            event = normalize_event(payload, require_protocol=True)
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return

        self.server.event_queue.put(event)
        self._send_json(
            200,
            {
                "ok": True,
                "action": event.action,
                "source_id": event.source_id,
                "state": event.state,
            },
        )


def _draw_pixel_pet(state: str, phase: float) -> Image.Image:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required to render pet frames to image files")

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    blink = int((phase * 10) % 36) in {0, 1}
    wing_tick = 1 if int(phase * (7.5 if state == "running" else 2.2)) % 2 else 0
    step_tick = 1 if state == "running" and int(phase * 7.5) % 2 else 0
    shake = 1 if state == "failed" and int(phase * 12) % 2 else 0

    ox = shake
    outline = (7, 9, 9, 255)
    black = (14, 15, 17, 255)
    hair_hi = (255, 255, 255, 255)
    white = (246, 246, 239, 255)
    gray = (184, 188, 184, 255)
    gold = (250, 204, 21, 255)
    teal = (35, 210, 185, 255)
    red = (239, 68, 68, 255)
    amber = (245, 158, 11, 255)

    def rect(box: tuple[int, int, int, int], fill: tuple[int, int, int, int], **kw: Any) -> None:
        x0, y0, x1, y1 = box
        d.rectangle((x0 + ox, y0, x1 + ox, y1), fill=fill, **kw)

    def poly(points: list[tuple[int, int]], fill: tuple[int, int, int, int], **kw: Any) -> None:
        d.polygon([(x + ox, y) for x, y in points], fill=fill, **kw)

    def line(points: list[tuple[int, int]], fill: tuple[int, int, int, int], width: int = 1) -> None:
        d.line([(x + ox, y) for x, y in points], fill=fill, width=width)

    # Grounding shadow, kept static so the character no longer bounces vertically.
    d.rectangle((19, 60, 45, 61), fill=(0, 0, 0, 70))
    d.rectangle((24, 62, 40, 62), fill=(0, 0, 0, 45))

    if state == "review":
        d.rectangle((9, 8, 55, 57), outline=(35, 210, 185, 100), width=1)
    elif state == "waiting":
        d.rectangle((51, 9, 55, 13), fill=amber)
        d.rectangle((53, 15, 55, 17), fill=amber)
    elif state == "failed":
        d.rectangle((51, 10, 55, 14), fill=red)
        d.rectangle((52, 15, 54, 17), fill=red)

    # Body and robe.
    poly([(22, 40), (15, 59), (49, 59), (42, 40)], fill=outline)
    poly([(24, 41), (18, 58), (46, 58), (40, 41)], fill=black)
    poly([(27, 41), (32, 48), (37, 41)], fill=teal)
    rect((29, 48, 35, 53), fill=(235, 236, 231, 255))
    rect((31, 49, 33, 52), fill=black)

    # Arms and feet. Running gets a one-pixel arm/foot alternation, not a bounce.
    line([(22, 43), (15, 51 + step_tick), (20, 52 + step_tick)], fill=outline, width=3)
    line([(42, 43), (49, 51 - step_tick), (44, 52 - step_tick)], fill=outline, width=3)
    rect((23, 57, 28, 60), fill=gold)
    rect((36, 57, 41, 60), fill=gold)

    # Hair silhouette derived from the official black/white mascot head shape.
    rect((18, 22, 46, 43), fill=outline)
    poly([(15, 27), (19, 58), (28, 57), (24, 39), (20, 25)], fill=outline)
    poly([(49, 27), (45, 58), (36, 57), (40, 39), (44, 25)], fill=outline)
    poly([(21, 17), (42, 17), (49, 27), (45, 37), (18, 37), (15, 27)], fill=outline)

    # Face plate.
    poly([(24, 25), (30, 20), (41, 23), (43, 39), (38, 48), (27, 45), (22, 35)], fill=white)
    rect((24, 24, 28, 33), fill=outline)
    poly([(23, 20), (31, 18), (39, 21), (43, 25), (25, 26)], fill=outline)
    rect((28, 19, 33, 23), fill=hair_hi)
    rect((38, 24, 40, 27), fill=hair_hi)

    # Winged petasos hat.
    poly([(24, 16), (32, 9), (40, 16), (38, 19), (26, 19)], fill=outline)
    poly([(27, 15), (32, 10), (37, 15), (36, 17), (28, 17)], fill=gold)
    rect((22, 17, 42, 19), fill=outline)
    rect((24, 16, 40, 17), fill=white)
    poly([(23, 17), (11, 14 - wing_tick), (14, 21 - wing_tick), (24, 21)], fill=outline)
    poly([(41, 17), (53, 14 - wing_tick), (50, 21 - wing_tick), (40, 21)], fill=outline)
    poly([(22, 17), (13, 15 - wing_tick), (16, 19 - wing_tick), (24, 19)], fill=white)
    poly([(42, 17), (51, 15 - wing_tick), (48, 19 - wing_tick), (40, 19)], fill=white)
    line([(14, 17 - wing_tick), (22, 18)], fill=gray)
    line([(50, 17 - wing_tick), (42, 18)], fill=gray)

    # Face details: blink is the main idle animation.
    if state == "failed":
        line([(27, 33), (30, 36)], fill=red)
        line([(30, 33), (27, 36)], fill=red)
        line([(36, 33), (39, 36)], fill=red)
        line([(39, 33), (36, 36)], fill=red)
        line([(30, 42), (37, 42)], fill=outline)
    elif blink:
        line([(27, 34), (31, 34)], fill=outline)
        line([(36, 34), (40, 34)], fill=outline)
        rect((32, 42, 36, 42), fill=outline)
    else:
        rect((28, 32, 31, 36), fill=outline)
        rect((37, 32, 40, 36), fill=outline)
        rect((30, 32, 31, 33), fill=white)
        rect((39, 32, 40, 33), fill=white)
        if state == "running":
            line([(32, 41), (36, 41)], fill=outline)
        elif state == "waiting":
            rect((32, 42, 36, 42), fill=outline)
        else:
            line([(32, 41), (35, 42), (38, 41)], fill=outline)

    # Tiny state light replaces exaggerated motion.
    mood = {
        "running": (34, 197, 94, 255),
        "waiting": amber,
        "failed": red,
        "review": teal,
        "idle": gray,
    }.get(state, gray)
    rect((31, 54, 33, 56), fill=mood)
    return img


def render_pet_frame(state: str, size: int, phase: float) -> Image.Image:
    if Image is None or ImageFilter is None:
        raise RuntimeError("Pillow is required to render pet frames to image files")

    sprite = _draw_pixel_pet(state, phase)
    if state == "review":
        glow = Image.new("RGBA", sprite.size, (35, 210, 185, 0))
        alpha = sprite.getchannel("A").filter(ImageFilter.GaussianBlur(3))
        glow.putalpha(alpha)
        underlay = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
        underlay.alpha_composite(glow)
        underlay.alpha_composite(sprite)
        sprite = underlay

    return sprite.resize((size, size), Image.Resampling.NEAREST)


def _ordered_pet_states(pets: dict[str, PetViewState]) -> list[PetViewState]:
    return sorted(
        pets.values(),
        key=lambda pet: (0 if pet.source_id == LOCAL_SOURCE_ID else 1, pet.source_id),
    )


def _pet_menu_sessions() -> list[dict[str, Any]]:
    try:
        from hermes_cli.pet_sessions import list_pet_menu_sessions
    except Exception:
        return []

    sessions: list[dict[str, Any]] = []
    limit = int(read_pet_preferences().get("session_list_limit") or DEFAULT_SESSION_LIST_LIMIT)
    for item in list_pet_menu_sessions(limit=limit):
        session_id = str(item.get("session_id") or "").strip()
        if not session_id:
            continue
        terminal = item.get("terminal") if isinstance(item.get("terminal"), dict) else {}
        sessions.append({
            "mode": str(item.get("mode") or ""),
            "session_id": session_id,
            "label": str(item.get("label") or ""),
            "cwd": str(item.get("cwd") or ""),
            "pid": item.get("pid") if isinstance(item.get("pid"), int) else 0,
            "ppid": item.get("ppid") if isinstance(item.get("ppid"), int) else 0,
            "active": bool(item.get("active")),
            "tty": str(terminal.get("tty") or ""),
            "term_program": str(terminal.get("term_program") or ""),
            "terminal_app": str(terminal.get("terminal_app") or ""),
            "terminal_bundle_id": str(terminal.get("terminal_bundle_id") or ""),
            "iterm_session_id": str(terminal.get("iterm_session_id") or ""),
            "cmux_port": str(terminal.get("cmux_port") or ""),
            "cmux_port_end": str(terminal.get("cmux_port_end") or ""),
            "cmux_socket_path": str(terminal.get("cmux_socket_path") or ""),
            "tmux": str(terminal.get("tmux") or ""),
        })
    return sessions[:12]


def _connected_pet_modes(sessions: Optional[list[dict[str, Any]]] = None) -> list[str]:
    active = set()
    for session in sessions if sessions is not None else _pet_menu_sessions():
        if not bool(session.get("active")):
            continue
        mode = str(session.get("mode") or "").strip().lower()
        if mode:
            active.add(mode)
    return sorted(active)


def _pet_preferences_payload() -> dict[str, Any]:
    prefs = read_pet_preferences()
    return {
        "language": prefs.get("language") or _system_pet_language(),
        "left_click_opens_terminal": bool(prefs.get("left_click_opens_terminal")),
        "session_list_limit": int(prefs.get("session_list_limit") or DEFAULT_SESSION_LIST_LIMIT),
        "terminal_launcher": _clean_terminal_launcher(prefs.get("terminal_launcher")),
        "terminal_options": _terminal_launcher_options(),
    }


def _snapshot_payload(
    pets: dict[str, PetViewState],
    *,
    sessions: Optional[list[dict[str, Any]]] = None,
    share: Optional[dict[str, Any]] = None,
    asset_version: Optional[str] = None,
    artwork: Optional[dict[str, Any]] = None,
) -> str:
    def pet_asset_fields(pet: PetViewState) -> dict[str, str | None]:
        asset = _source_pet_skin_asset(pet.source_id, asset_id=pet.asset_id)
        if asset is None:
            return {"asset_id": pet.asset_id, "asset_dir": None, "asset_version": None}
        return {
            "asset_id": asset.asset_id,
            "asset_dir": str(asset.path),
            "asset_version": _asset_version_for_dir(asset.path),
        }

    def pet_notification_fields(pet: PetViewState) -> dict[str, Any]:
        kind = pet.notification_kind or _default_notification_kind(pet.state, None)
        count = pet.notification_count or _clean_notification_count(None, pet.state, kind)
        label_text = pet.notification_label or _default_notification_label(pet.state, kind, None)
        return {
            "notification_count": count,
            "notification_kind": kind,
            "notification_label": label_text,
        }

    return json.dumps(
        {
            "protocol": PROTOCOL_VERSION,
            "pets": [
                {
                    "source_id": pet.source_id,
                    "label": pet.label,
                    "state": pet.state,
                    "message": pet.message,
                    "animation": pet.animation,
                    "direction": pet.direction,
                    "pet_action": pet.pet_action,
                    "emotion": pet.emotion,
                    **pet_notification_fields(pet),
                    **pet_asset_fields(pet),
                }
                for pet in _ordered_pet_states(pets)
            ],
            "sessions": sessions if sessions is not None else [],
            "connected_modes": _connected_pet_modes(sessions),
            "preferences": _pet_preferences_payload(),
            "share": share,
            "asset_version": asset_version,
            "asset_dir": str(_active_asset_dir()),
            "artwork": artwork,
            "ui_language": _pet_language(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _apply_pet_event(
    pets: dict[str, PetViewState],
    event: PetEvent,
    *,
    now: Optional[float] = None,
) -> bool:
    now = time.time() if now is None else now

    if event.action == "clear":
        local_pet = pets.get(LOCAL_SOURCE_ID)
        pets.clear()
        if local_pet is not None:
            pets[LOCAL_SOURCE_ID] = local_pet
        return True

    if event.action == "ack":
        return _clear_pet_notifications(pets, source_id=event.source_id)

    if event.action == "remove":
        if event.source_id == LOCAL_SOURCE_ID:
            local_pet = pets.get(LOCAL_SOURCE_ID)
            if local_pet is None:
                return False
            local_pet.state = "idle"
            local_pet.message = "ready"
            local_pet.expires_at = None
            local_pet.animation = None
            local_pet.direction = None
            local_pet.pet_action = None
            local_pet.emotion = None
            local_pet.asset_id = None
            local_pet.notification_count = 0
            local_pet.notification_kind = None
            local_pet.notification_label = None
            local_pet.updated_at = now
            return True
        return pets.pop(event.source_id, None) is not None

    existing = pets.get(event.source_id)
    expires_at = now + event.ttl_ms / 1000 if event.ttl_ms else None
    notification_count = _merged_notification_count(existing, event)
    pets[event.source_id] = PetViewState(
        source_id=event.source_id,
        label=event.label,
        state=event.state,
        message=event.message,
        expires_at=expires_at,
        animation=event.animation,
        direction=event.direction,
        pet_action=event.pet_action,
        emotion=event.emotion,
        asset_id=event.asset_id,
        notification_count=notification_count,
        notification_kind=event.notification_kind,
        notification_label=event.notification_label,
        updated_at=now,
    )
    return True


def _merged_notification_count(existing: Optional[PetViewState], event: PetEvent) -> int:
    if event.notification_count <= 0:
        return 0
    kind = event.notification_kind or _default_notification_kind(event.state, None)
    if (
        existing is not None
        and kind in {"done", "failed"}
        and existing.notification_kind == kind
        and existing.notification_count > 0
    ):
        return min(existing.notification_count + event.notification_count, 99)
    return event.notification_count


def _clear_pet_notifications(
    pets: dict[str, PetViewState],
    *,
    source_id: Optional[str] = None,
) -> bool:
    changed = False
    targets = [pets[source_id]] if source_id and source_id in pets else list(pets.values())
    for pet in targets:
        if pet.notification_count or pet.notification_kind or pet.notification_label:
            pet.notification_count = 0
            pet.notification_kind = None
            pet.notification_label = None
            pet.updated_at = time.time()
            changed = True
    return changed


def _expire_pet_states(pets: dict[str, PetViewState], *, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    changed = False

    for source_id, pet in list(pets.items()):
        if not pet.expires_at or pet.expires_at > now:
            continue

        if source_id == LOCAL_SOURCE_ID:
            pet.state = "idle"
            pet.message = "ready"
            pet.expires_at = None
            pet.animation = None
            pet.direction = None
            pet.pet_action = None
            pet.emotion = None
            pet.asset_id = None
            pet.updated_at = now
        elif pet.notification_count > 0:
            if (
                pet.state != "idle"
                or pet.message != "ready"
                or pet.animation is not None
                or pet.direction is not None
                or pet.pet_action is not None
                or pet.emotion is not None
            ):
                pet.state = "idle"
                pet.message = "ready"
                pet.animation = None
                pet.direction = None
                pet.pet_action = None
                pet.emotion = None
                pet.updated_at = now
                changed = True
            continue
        else:
            pets.pop(source_id, None)
        changed = True

    return changed


def _compile_macos_helper() -> Optional[Path]:
    swiftc = Path("/usr/bin/swiftc")
    if not swiftc.exists() or not MACOS_HELPER_SOURCE.exists():
        return None

    runtime_dir = get_hermes_home() / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    binary = runtime_dir / MACOS_HELPER_BINARY

    try:
        needs_compile = not binary.exists() or (
            MACOS_HELPER_SOURCE.stat().st_mtime > binary.stat().st_mtime
        )
    except OSError:
        needs_compile = True

    if needs_compile:
        subprocess.run(
            [str(swiftc), str(MACOS_HELPER_SOURCE), "-o", str(binary)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    return binary


def _active_asset_version() -> str:
    asset_dir = _active_asset_dir()
    return _asset_version_for_dir(asset_dir)


def _asset_version_for_dir(asset_dir: Path) -> str:
    manifest = asset_dir / "manifest.json"
    try:
        stat = manifest.stat() if manifest.exists() else asset_dir.stat()
        stamp = stat.st_mtime_ns
    except OSError:
        stamp = 0
    return f"{asset_dir}:{stamp}"


def _source_pet_skin_asset(source_id: str, *, asset_id: Optional[str] = None) -> Any:
    try:
        from hermes_cli.pet_share import source_pet_skin_asset

        return source_pet_skin_asset(source_id, asset_id=asset_id)
    except Exception:
        return None


def _share_response(
    status: str,
    *,
    message: str = "",
    query: str = "",
    pets: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    return {
        "request_id": secrets.token_hex(8),
        "status": status,
        "message": message[:240],
        "query": query[:80],
        "pets": pets or [],
    }


def _pet_artwork_menu_payload() -> dict[str, Any]:
    try:
        from hermes_cli.pet_share import artwork_menu_payload

        return artwork_menu_payload()
    except Exception:
        return {"current": None, "installed": []}


def _pet_language() -> str:
    return str(read_pet_preferences().get("language") or _system_pet_language())


def _hermes_python_executable() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / "venv" / "bin" / "python3"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable).resolve()


def _launch_hermes_terminal(*, tui: bool) -> tuple[bool, str]:
    mode = "tui" if tui else "cli"
    for session in _pet_menu_sessions():
        if str(session.get("mode") or "").lower() != mode or not bool(session.get("active")):
            continue
        ok, message = _focus_terminal_session(session)
        if ok:
            return True, f"focused existing Hermes {mode.upper()}: {message}"
        if _clean_terminal_launcher(read_pet_preferences().get("terminal_launcher")) == "cmux":
            activated, activate_message = _activate_cmux_app()
            if activated:
                return True, f"activated cmux for existing Hermes {mode.upper()}: {message}; {activate_message}"
        break
    return _launch_hermes_resume_terminal(tui=tui, session_id=None)


def _hermes_launch_script_lines(*, tui: bool, session_id: Optional[str]) -> tuple[str, list[str]]:
    kind = "tui" if tui else "cli"
    project_root = Path(__file__).resolve().parents[1]
    args = ['"$HERMES_CMD"']
    if tui:
        args.append("--tui")
    if session_id:
        args.extend(["--resume", shlex.quote(session_id)])

    exports = []
    hermes_home = os.getenv("HERMES_HOME")
    if hermes_home:
        exports.append(f"export HERMES_HOME={shlex.quote(hermes_home)}")

    title = f"Hermes {kind.upper()}"
    if session_id:
        title = f"{title} {session_id}"

    return kind, [
        "#!/bin/zsh",
        "set -e",
        "unset PYTHONPATH",
        "unset PYTHONHOME",
        "unset VIRTUAL_ENV",
        *exports,
        'export PATH="$HOME/.local/bin:$HOME/.hermes/hermes-agent/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"',
        'HERMES_CMD="${HERMES_PET_HERMES_CMD:-}"',
        'if [ -z "$HERMES_CMD" ]; then HERMES_CMD="$(command -v hermes || true)"; fi',
        'if [ -z "$HERMES_CMD" ]; then',
        '  echo "Hermes command not found. Install Hermes Agent first, or set HERMES_PET_HERMES_CMD to the hermes executable path." >&2',
        "  exit 127",
        "fi",
        'cd "${HERMES_PET_HERMES_CWD:-$HOME}"',
        f"printf '\\033]0;%s\\007' {shlex.quote(title)}",
        f"exec {' '.join(args)}",
        "",
    ]


def _launch_macos_terminal_script(script_path: Path) -> tuple[bool, str]:
    try:
        subprocess.Popen(
            ["open", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return False, f"failed to launch macOS Terminal: {exc}"
    return True, "opened macOS Terminal"


def _read_cmux_session_map() -> dict[str, Any]:
    try:
        data = json.loads(cmux_session_map_file().read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_cmux_session_map(data: dict[str, Any]) -> None:
    path = cmux_session_map_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _remember_cmux_session_terminal(session_id: Optional[str], terminal_id: str) -> None:
    clean_session_id = str(session_id or "").strip()
    clean_terminal_id = str(terminal_id or "").strip()
    if not clean_session_id or not clean_terminal_id:
        return
    data = _read_cmux_session_map()
    data[clean_session_id] = {
        "terminal_id": clean_terminal_id,
        "updated_at": time.time(),
    }
    ordered = sorted(
        data.items(),
        key=lambda item: float(item[1].get("updated_at") or 0) if isinstance(item[1], dict) else 0.0,
        reverse=True,
    )
    _write_cmux_session_map(dict(ordered[:100]))


def _cmux_terminal_id_for_session(session_id: str) -> str:
    entry = _read_cmux_session_map().get(str(session_id or "").strip())
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("terminal_id") or "").strip()


def _forget_cmux_session_terminal(session_id: str) -> None:
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        return
    data = _read_cmux_session_map()
    if clean_session_id in data:
        data.pop(clean_session_id, None)
        _write_cmux_session_map(data)


def _applescript_text_lines(lines: list[str]) -> str:
    parts = [_applescript_string(line) for line in lines if line]
    if not parts:
        return '""'
    return (" & return & ").join(parts) + " & return"


def _launch_cmux_terminal(lines: list[str], *, session_id: Optional[str] = None) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "cmux launch is only implemented for macOS"
    if not (_app_available("cmux") or Path("/Applications/cmux.app").exists()):
        return False, "cmux is not installed"

    command_text = _applescript_text_lines(lines[1:])
    script = f"""
tell application id "com.cmuxterm.app"
    activate
    if (count of windows) is 0 then
        set targetWindow to new window
    else
        set targetWindow to front window
    end if
    set targetTab to new tab in targetWindow
    delay 0.2
    set targetTerminal to focused terminal of targetTab
    input text {command_text} to targetTerminal
    return "opened cmux tab " & (id of targetTerminal)
end tell
"""
    ok, message = _run_osascript(script)
    if ok and session_id and message.startswith("opened cmux tab "):
        _remember_cmux_session_terminal(session_id, message.removeprefix("opened cmux tab ").strip())
    return (ok and "opened" in message), (message or "opened cmux tab")


def _focus_cmux_terminal_for_session(session_id: str) -> tuple[bool, str]:
    session = _find_pet_menu_session(session_id)
    return _focus_cmux_terminal_for_session_fields(
        session_id,
        cwd=str(session.get("cwd") or "") if session else "",
        label=str(session.get("label") or "") if session else "",
    )


def _focus_cmux_terminal_for_session_fields(
    session_id: str,
    *,
    cwd: str = "",
    label: str = "",
) -> tuple[bool, str]:
    target = str(session_id or "").strip()
    if not target:
        return False, "session id required"
    if sys.platform != "darwin":
        return False, "cmux focus is only implemented for macOS"
    if not (_app_available("cmux") or Path("/Applications/cmux.app").exists()):
        return False, "cmux is not installed"

    terminal_id = _cmux_terminal_id_for_session(target)
    if terminal_id:
        ok, message = _focus_cmux_terminal_by_id(terminal_id)
        if ok:
            return True, message
        _forget_cmux_session_terminal(target)

    cwd_target = str(cwd or "").strip()
    cwd_basename = Path(cwd_target).name if cwd_target else ""
    label_target = str(label or "").strip()
    script = f"""
tell application id "com.cmuxterm.app"
    set fallbackCount to 0
    set fallbackWindow to missing value
    set fallbackTab to missing value
    set fallbackTerminal to missing value
    repeat with w in windows
        repeat with t in tabs of w
            set tabName to ""
            try
                set tabName to name of t
            end try
            repeat with term in terminals of t
                set termName to ""
                set termWd to ""
                try
                    set termName to name of term
                end try
                try
                    set termWd to working directory of term
                end try
                if (termName contains {_applescript_string(target)}) or (tabName contains {_applescript_string(target)}) then
                    activate
                    activate window w
                    select tab t
                    delay 0.05
                    focus term
                    return "focused cmux terminal"
                end if
                if ({_applescript_string(cwd_target)} is not "" and termWd is {_applescript_string(cwd_target)}) or ({_applescript_string(cwd_basename)} is not "" and (tabName contains {_applescript_string(cwd_basename)})) or ({_applescript_string(label_target)} is not "" and (tabName contains {_applescript_string(label_target)})) then
                    set fallbackCount to fallbackCount + 1
                    if fallbackCount is 1 then
                        set fallbackWindow to w
                        set fallbackTab to t
                        set fallbackTerminal to term
                    end if
                end if
            end repeat
        end repeat
    end repeat
    if fallbackCount is 1 then
        activate
        activate window fallbackWindow
        select tab fallbackTab
        delay 0.05
        focus fallbackTerminal
        return "focused cmux terminal"
    end if
    if fallbackCount is greater than 1 then
        return "cmux terminal fallback not unique"
    end if
end tell
return "cmux terminal not found"
"""
    ok, message = _run_osascript(script)
    return ok and "focused" in message, message


def _focus_cmux_terminal_by_id(terminal_id: str) -> tuple[bool, str]:
    target = str(terminal_id or "").strip()
    if not target:
        return False, "cmux terminal id required"
    script = f"""
tell application id "com.cmuxterm.app"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with term in terminals of t
                if (id of term) is {_applescript_string(target)} then
                    activate
                    activate window w
                    select tab t
                    delay 0.05
                    focus term
                    return "focused cmux terminal"
                end if
            end repeat
        end repeat
    end repeat
end tell
return "cmux terminal id not found"
"""
    ok, message = _run_osascript(script)
    return ok and "focused" in message, message


def _activate_cmux_app() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "cmux activation is only implemented for macOS"
    if not (_app_available("cmux") or Path("/Applications/cmux.app").exists()):
        return False, "cmux is not installed"
    ok, message = _run_osascript('tell application id "com.cmuxterm.app" to activate')
    return ok, message or "activated cmux"


def _launch_or_focus_cmux_terminal(lines: list[str], *, session_id: Optional[str]) -> tuple[bool, str]:
    if session_id:
        ok, message = _focus_cmux_terminal_for_session(session_id)
        if ok:
            return True, message
    return _launch_cmux_terminal(lines, session_id=session_id)


def _launch_hermes_resume_terminal(*, tui: bool, session_id: Optional[str]) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "terminal launch is only implemented for macOS"

    runtime_dir = get_hermes_home() / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    kind, lines = _hermes_launch_script_lines(tui=tui, session_id=session_id)
    script_path = runtime_dir / f"pet_launch_{kind}.command"
    script = "\n".join(lines)
    script_path.write_text(script)
    script_path.chmod(0o700)

    launcher = _clean_terminal_launcher(read_pet_preferences().get("terminal_launcher"))
    if launcher == "cmux":
        ok, launch_message = _launch_or_focus_cmux_terminal(lines, session_id=session_id)
    else:
        ok, launch_message = _launch_macos_terminal_script(script_path)

    if not ok:
        return False, f"failed to launch Hermes {kind} in {TERMINAL_LAUNCHERS[launcher]}: {launch_message}"
    if session_id and launcher == "cmux" and "focused" in launch_message.lower():
        return True, f"focused {session_id} in existing cmux tab"
    if session_id:
        return True, f"resuming {session_id} in Hermes {'TUI' if tui else 'CLI'} via {TERMINAL_LAUNCHERS[launcher]}"
    return True, f"launched Hermes {'TUI' if tui else 'CLI'} via {TERMINAL_LAUNCHERS[launcher]}"


def _find_pet_menu_session(session_id: str) -> Optional[dict[str, Any]]:
    target = str(session_id or "").strip()
    if not target:
        return None
    for session in _pet_menu_sessions():
        if str(session.get("session_id") or "") == target:
            return session
    return None


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osascript(script: str, *, timeout: float = 5) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "session focus is only implemented for macOS"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except OSError as exc:
        return False, f"osascript unavailable: {exc}"
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output


def _focus_terminal_by_tty(app_name: str, tty: str) -> tuple[bool, str]:
    if not tty:
        return False, "session has no tty metadata"
    if app_name == "Terminal":
        script = f"""
tell application "Terminal"
    repeat with w in windows
        repeat with t in tabs of w
            if tty of t is {_applescript_string(tty)} then
                set selected tab of w to t
                set index of w to 1
                activate
                return "focused Terminal tab"
            end if
        end repeat
    end repeat
end tell
return "Terminal tab not found"
"""
        ok, message = _run_osascript(script)
        return ok and "focused" in message, message
    if app_name == "iTerm2":
        script = f"""
tell application "iTerm2"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                if tty of s is {_applescript_string(tty)} then
                    select t
                    select s
                    activate
                    return "focused iTerm2 session"
                end if
            end repeat
        end repeat
    end repeat
end tell
return "iTerm2 session not found"
"""
        ok, message = _run_osascript(script)
        return ok and "focused" in message, message
    return False, f"{app_name or 'terminal'} does not support exact tty focus"


def _activate_terminal_app(session: dict[str, Any]) -> tuple[bool, str]:
    bundle_id = str(session.get("terminal_bundle_id") or "").strip()
    app_name = str(session.get("terminal_app") or "").strip()
    if bundle_id:
        return _run_osascript(f'tell application id {_applescript_string(bundle_id)} to activate')
    if app_name:
        return _run_osascript(f'tell application {_applescript_string(app_name)} to activate')
    return False, "session has no terminal app metadata"


def _session_uses_cmux(session: dict[str, Any]) -> bool:
    app_name = str(session.get("terminal_app") or "").strip().lower()
    bundle_id = str(session.get("terminal_bundle_id") or "").strip()
    return (
        app_name == "cmux"
        or bundle_id == "com.cmuxterm.app"
        or bool(str(session.get("cmux_socket_path") or "").strip())
        or bool(str(session.get("cmux_port") or "").strip())
    )


def _focus_terminal_session(session: dict[str, Any]) -> tuple[bool, str]:
    app_name = str(session.get("terminal_app") or "").strip()
    bundle_id = str(session.get("terminal_bundle_id") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    tty = str(session.get("tty") or "").strip()

    if _session_uses_cmux(session):
        ok, message = _focus_cmux_terminal_for_session_fields(
            session_id,
            cwd=str(session.get("cwd") or ""),
            label=str(session.get("label") or ""),
        )
        if ok:
            return True, message

    if app_name in {"Terminal", "iTerm2"} and tty:
        ok, message = _focus_terminal_by_tty(app_name, tty)
        if ok:
            return True, message

    ok, message = _activate_terminal_app(session)
    if ok:
        return True, f"activated {app_name or 'terminal app'}"
    return False, message


def _focus_or_resume_hermes_session(session_id: str, *, allow_resume: bool) -> tuple[bool, str]:
    session = _find_pet_menu_session(session_id)
    if session is not None:
        if not bool(session.get("active")):
            if not allow_resume:
                return False, "session is not active; terminal launch fallback is off"
            mode = str(session.get("mode") or "cli").lower()
            return _launch_hermes_resume_terminal(tui=mode == "tui", session_id=session_id)
        ok, message = _focus_terminal_session(session)
        if ok:
            return True, message
        if _clean_terminal_launcher(read_pet_preferences().get("terminal_launcher")) == "cmux":
            activated, activate_message = _activate_cmux_app()
            if activated:
                return True, f"{message}; {activate_message}"
        if not allow_resume:
            return False, f"{message}; terminal launch fallback is off"
        mode = str(session.get("mode") or "cli").lower()
        resume_ok, resume_message = _launch_hermes_resume_terminal(
            tui=mode == "tui",
            session_id=session_id,
        )
        if resume_ok:
            return True, f"{message}; {resume_message}"
        return False, f"{message}; {resume_message}"

    if not allow_resume:
        return False, "session not found; terminal launch fallback is off"
    return _launch_hermes_resume_terminal(tui=False, session_id=session_id)


def _focus_active_session_before_launch(
    session_id: Optional[str],
    *,
    mode: Optional[str] = None,
) -> tuple[bool, str]:
    if not session_id:
        return False, "session id required"
    requested_mode = str(mode or "").lower()
    session = None
    for candidate in _pet_menu_sessions():
        if str(candidate.get("session_id") or "") != session_id:
            continue
        if requested_mode and str(candidate.get("mode") or "").lower() != requested_mode:
            continue
        session = candidate
        break
    if not session or not bool(session.get("active")):
        return False, "active session not found"
    ok, message = _focus_terminal_session(session)
    if ok:
        return True, message
    if _clean_terminal_launcher(read_pet_preferences().get("terminal_launcher")) == "cmux":
        activated, activate_message = _activate_cmux_app()
        if activated:
            return True, f"{message}; {activate_message}"
    return False, message


def _read_macos_helper_actions(
    process: subprocess.Popen[str],
    action_queue: "queue.Queue[dict[str, Any]]",
) -> None:
    if process.stdout is None:
        return

    for line in process.stdout:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        if isinstance(action, str) and action:
            action_queue.put(payload)


def _handle_macos_helper_action(
    pets: dict[str, PetViewState],
    payload: dict[str, Any] | str,
    *,
    label: str,
    size: int = 84,
    share_response_box: Optional[list[dict[str, Any]]] = None,
    runtime_host: str = "127.0.0.1",
    runtime_port: int = 8768,
    relay_token: Optional[str] = None,
) -> bool:
    def set_share_response(response: dict[str, Any]) -> None:
        if share_response_box is not None:
            share_response_box.clear()
            share_response_box.append(response)

    if isinstance(payload, str):
        action = payload
        session_id = None
        query = ""
        pet_id = ""
        asset_id = ""
        language = ""
        allow_resume = True
        left_click_opens_terminal = None
        session_list_limit = None
        terminal_launcher = None
        sort = "new"
        content = "safe"
    else:
        action = str(payload.get("action") or "")
        session_id_raw = payload.get("session_id")
        session_id = str(session_id_raw).strip() if session_id_raw else None
        query = str(payload.get("query") or "").strip()
        pet_id = str(payload.get("pet_id") or payload.get("petId") or "").strip()
        asset_id = str(payload.get("asset_id") or payload.get("assetId") or "").strip()
        language = str(payload.get("language") or "").strip().lower()
        allow_resume_raw = payload.get("allow_resume") if "allow_resume" in payload else payload.get("allowResume")
        allow_resume = _boolish(allow_resume_raw, default=True)
        left_click_opens_terminal = (
            _boolish(payload.get("left_click_opens_terminal"), default=False)
            if "left_click_opens_terminal" in payload
            else None
        )
        try:
            session_list_limit = (
                int(payload.get("session_list_limit"))
                if payload.get("session_list_limit") not in (None, "")
                else None
            )
        except Exception:
            session_list_limit = None
        terminal_launcher = (
            _clean_terminal_launcher(payload.get("terminal_launcher"))
            if payload.get("terminal_launcher") not in (None, "")
            else None
        )
        sort = str(payload.get("sort") or "new").strip()
        content = str(payload.get("content") or "safe").strip()

    if action == "clear_extra_pets":
        return _apply_pet_event(
            pets,
            PetEvent(
                source_id="remote",
                label="remote",
                state="idle",
                message="clear",
                action="clear",
            ),
        )

    if action == "clear_notifications":
        return _clear_pet_notifications(pets)

    if action == "launch_agent_status":
        status = pet_launchd_status()
        message = (
            "launch item: "
            f"installed={bool(status.get('installed'))}, "
            f"loaded={bool(status.get('loaded'))}"
        )
        return _apply_pet_event(
            pets,
            PetEvent(
                source_id=LOCAL_SOURCE_ID,
                label=label,
                state="review",
                message=message,
                animation="review",
                pet_action="done",
                emotion="done",
                ttl_ms=5_000,
                notification_count=1,
                notification_kind="done",
                notification_label="1",
            ),
        )

    if action in {"install_launch_agent", "start_launch_agent", "stop_launch_agent"}:
        try:
            if action == "install_launch_agent":
                ok, message = install_pet_launch_agent(
                    host=runtime_host,
                    port=runtime_port,
                    token=relay_token,
                    label=label,
                    size=size,
                    show_local=True,
                    insecure=not _is_loopback_host(runtime_host),
                    force=True,
                )
            elif action == "start_launch_agent":
                ok, message = start_pet_launch_agent()
            else:
                ok, message = stop_pet_launch_agent(stop_current=False)
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review" if ok else "failed",
                    message=message,
                    animation="review" if ok else "failed",
                    pet_action="done" if ok else "failed",
                    emotion="done" if ok else "error",
                    ttl_ms=5_000 if ok else 12_000,
                    notification_count=1,
                    notification_kind="done" if ok else "failed",
                    notification_label="1" if ok else "!",
                ),
            )
        except Exception as exc:
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="failed",
                    message=f"launch item failed: {exc}",
                    animation="failed",
                    emotion="error",
                    ttl_ms=12_000,
                    notification_count=1,
                    notification_kind="failed",
                    notification_label="!",
                ),
            )

    if action == "set_language":
        try:
            saved_language = write_pet_language(language)
            label_text = {
                "ko": "한국어",
                "en": "English",
                "ja": "日本語",
                "zh": "简体中文",
            }.get(saved_language, saved_language)
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review",
                    message=f"language: {label_text}",
                    animation="review",
                    pet_action="done",
                    emotion="done",
                    ttl_ms=3_000,
                    notification_count=1,
                    notification_kind="done",
                    notification_label="1",
                ),
            )
        except Exception as exc:
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="failed",
                    message=f"language failed: {exc}",
                    animation="failed",
                    emotion="error",
                    ttl_ms=8_000,
                    notification_count=1,
                    notification_kind="failed",
                    notification_label="!",
                ),
            )

    if action == "set_preferences":
        try:
            saved = write_pet_preferences(
                language=language or None,
                left_click_opens_terminal=left_click_opens_terminal,
                session_list_limit=session_list_limit,
                terminal_launcher=terminal_launcher,
            )
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review",
                    message=(
                        "settings updated: "
                        f"language={saved.get('language')}, "
                        f"left_click_opens_terminal={bool(saved.get('left_click_opens_terminal'))}, "
                        f"session_list_limit={saved.get('session_list_limit')}, "
                        f"terminal_launcher={saved.get('terminal_launcher')}"
                    ),
                    animation="review",
                    pet_action="done",
                    emotion="done",
                    ttl_ms=3_000,
                ),
            )
        except Exception as exc:
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="failed",
                    message=f"settings failed: {exc}",
                    animation="failed",
                    emotion="error",
                    ttl_ms=8_000,
                    notification_count=1,
                    notification_kind="failed",
                    notification_label="!",
                ),
            )

    if action == "search_pet_share":
        try:
            from hermes_cli.pet_share import cache_share_pet_thumbnail, list_share_pets

            page = list_share_pets(
                query=query,
                page_size=8,
                sort=sort if sort in {"new", "popular", "views"} else "new",
                content=content if content in {"safe", "all"} else "safe",
            )
            results = []
            for pet in page.pets:
                thumbnail_path = ""
                try:
                    thumbnail = cache_share_pet_thumbnail(pet, size=64)
                    thumbnail_path = str(thumbnail) if thumbnail else ""
                except Exception:
                    thumbnail_path = ""
                results.append({
                    "id": pet.id,
                    "display_name": pet.display_name,
                    "owner_name": pet.owner_name,
                    "description": pet.description,
                    "like_count": pet.like_count,
                    "view_count": pet.view_count,
                    "tags": list(pet.tags),
                    "thumbnail_path": thumbnail_path,
                    "share_url": f"https://codex-pet-share.pages.dev/#/pets/{pet.id}",
                })
            message = f"{page.total} result{'s' if page.total != 1 else ''}"
            set_share_response(_share_response("results", message=message, query=query, pets=results))
        except Exception as exc:
            set_share_response(_share_response("error", message=f"Search failed: {exc}", query=query))
        return True

    if action == "apply_installed_pet" and asset_id:
        try:
            from hermes_cli.pet_share import activate_installed_pet_asset

            asset = activate_installed_pet_asset(asset_id)
            set_share_response(
                _share_response(
                    "applied",
                    message=f"Applied {asset.display_name} ({asset.pet_id})",
                )
            )
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review",
                    message=f"applied {asset.display_name}",
                    animation="review",
                    ttl_ms=5_000,
                ),
            )
        except Exception as exc:
            set_share_response(_share_response("error", message=f"Apply failed: {exc}"))
        return True

    if action == "apply_share_pet" and pet_id:
        try:
            from hermes_cli.pet_share import apply_share_pet

            result = apply_share_pet(pet_id, size=size)
            set_share_response(
                _share_response(
                    "applied",
                    message=f"Applied {result.pet.display_name} ({result.pet.id})",
                )
            )
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review",
                    message=f"applied {result.pet.display_name}",
                    animation="review",
                    ttl_ms=5_000,
                ),
            )
        except Exception as exc:
            set_share_response(_share_response("error", message=f"Apply failed: {exc}"))
        return True

    if action == "clear_pet_artwork":
        try:
            from hermes_cli.pet_share import clear_active_pet_assets

            backup = clear_active_pet_assets()
            message = "Using bundled Hermes artwork"
            if backup:
                message = f"Using bundled Hermes artwork; previous art moved to {backup.name}"
            set_share_response(_share_response("cleared", message=message))
            return _apply_pet_event(
                pets,
                PetEvent(
                    source_id=LOCAL_SOURCE_ID,
                    label=label,
                    state="review",
                    message="bundled artwork",
                    animation="review",
                    ttl_ms=5_000,
                ),
            )
        except Exception as exc:
            set_share_response(_share_response("error", message=f"Clear failed: {exc}"))
        return True

    if action in {"launch_cli", "launch_tui"}:
        ok, message = _launch_hermes_terminal(tui=action == "launch_tui")
    elif action in {"open_session_cli", "open_session_tui"} and session_id:
        ok, message = _focus_active_session_before_launch(
            session_id,
            mode="tui" if action == "open_session_tui" else "cli",
        )
        if not ok:
            ok, message = _launch_hermes_resume_terminal(
                tui=action == "open_session_tui",
                session_id=session_id,
            )
    elif action == "focus_session" and session_id:
        ok, message = _focus_or_resume_hermes_session(session_id, allow_resume=allow_resume)
    else:
        return False

    if action in {
        "launch_cli",
        "launch_tui",
        "open_session_cli",
        "open_session_tui",
        "focus_session",
    }:
        return _apply_pet_event(
            pets,
            PetEvent(
                source_id=LOCAL_SOURCE_ID,
                label=label,
                state="review" if ok else "failed",
                message=message,
                animation="review" if ok else "failed",
                ttl_ms=5_000 if ok else 12_000,
            ),
        )
    return False


def _run_macos_native_overlay(
    event_queue: "queue.Queue[PetEvent]",
    *,
    runtime_host: str,
    runtime_port: int,
    relay_token: str,
    label: str,
    size: int,
    show_local: bool,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
) -> bool:
    binary = _compile_macos_helper()
    if binary is None:
        return False

    pets: dict[str, PetViewState] = {}
    if show_local:
        pets[LOCAL_SOURCE_ID] = PetViewState(
            source_id=LOCAL_SOURCE_ID,
            label=label,
            state="idle",
            message="ready",
        )

    command = [
        str(binary),
        "--asset-dir",
        str(_active_asset_dir()),
        "--size",
        str(max(56, min(size, 160))),
    ]
    if initial_x is not None:
        command.extend(["--x", str(initial_x)])
    if initial_y is not None:
        command.extend(["--y", str(initial_y)])

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    helper_actions: "queue.Queue[dict[str, Any]]" = queue.Queue()
    share_response_box: list[dict[str, Any]] = []
    threading.Thread(
        target=_read_macos_helper_actions,
        args=(process, helper_actions),
        daemon=True,
        name="hermes-pet-helper-actions",
    ).start()

    def send_snapshot() -> bool:
        if process.stdin is None or process.poll() is not None:
            return False
        try:
            process.stdin.write(
                _snapshot_payload(
                    pets,
                    sessions=_pet_menu_sessions(),
                    share=share_response_box[-1] if share_response_box else None,
                    asset_version=_active_asset_version(),
                    artwork=_pet_artwork_menu_payload(),
                )
                + "\n"
            )
            process.stdin.flush()
            return True
        except BrokenPipeError:
            return False

    send_snapshot()
    last_session_snapshot = 0.0

    try:
        while process.poll() is None:
            changed = False
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break

                changed = _apply_pet_event(pets, event) or changed

            while True:
                try:
                    action = helper_actions.get_nowait()
                except queue.Empty:
                    break

                if isinstance(action, dict) and action.get("action") == "restart_pet":
                    ok, message = _schedule_pet_restart(
                        host=runtime_host,
                        port=runtime_port,
                        token=relay_token,
                        label=label,
                        size=size,
                        show_local=show_local,
                        initial_x=initial_x,
                        initial_y=initial_y,
                    )
                    if not ok:
                        changed = _apply_pet_event(
                            pets,
                            PetEvent(
                                source_id=LOCAL_SOURCE_ID,
                                label=label,
                                state="failed",
                                message=message,
                                animation="failed",
                                emotion="error",
                                ttl_ms=12_000,
                                notification_count=1,
                                notification_kind="failed",
                                notification_label="!",
                            ),
                        ) or changed
                        continue
                    if process.poll() is None:
                        process.terminate()
                    return True

                changed = _handle_macos_helper_action(
                    pets,
                    action,
                    label=label,
                    size=size,
                    share_response_box=share_response_box,
                    runtime_host=runtime_host,
                    runtime_port=runtime_port,
                    relay_token=relay_token,
                ) or changed

            changed = _expire_pet_states(pets) or changed
            now = time.time()
            if now - last_session_snapshot >= 2.0:
                changed = True
                last_session_snapshot = now

            if changed:
                send_snapshot()
            time.sleep(0.05)
    except KeyboardInterrupt:
        raise
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
    return True


class HermesPetOverlay:
    def __init__(
        self,
        event_queue: "queue.Queue[PetEvent]",
        *,
        label: str,
        size: int,
        show_local: bool,
        initial_x: Optional[int] = None,
        initial_y: Optional[int] = None,
    ) -> None:
        if tk is None or Menu is None:
            raise RuntimeError("Tk fallback requires Python tkinter support")
        self.event_queue = event_queue
        self.size = max(56, min(size, 160))
        self.initial_x = initial_x
        self.initial_y = initial_y
        self.root = tk.Tk()
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.asset_dir = _active_asset_dir()
        self.sprite_images = self._load_sprite_images()
        self.pets: dict[str, PetViewState] = {}
        self.drag_start: tuple[int, int] | None = None
        self.window_size = (1, 1)
        if show_local:
            self.pets[LOCAL_SOURCE_ID] = PetViewState(
                source_id=LOCAL_SOURCE_ID,
                label=label,
                state="idle",
                message="ready",
            )

    def _load_sprite_images(self) -> dict[str, tk.PhotoImage]:
        sprites: dict[str, tk.PhotoImage] = {}
        for key, filename in SPRITE_FILES.items():
            path = self.asset_dir / filename
            sized_path = path.with_name(f"{path.stem}_{self.size}{path.suffix}")
            if sized_path.exists():
                sprites[key] = tk.PhotoImage(file=str(sized_path))
                continue
            if not path.exists():
                continue
            image = tk.PhotoImage(file=str(path))
            if self.size != 512:
                factor = max(1, round(512 / self.size))
                image = image.subsample(factor, factor)
            sprites[key] = image
        return sprites

    def run(self) -> None:
        self._setup_window()
        self._tick()
        self.root.mainloop()

    def _setup_window(self) -> None:
        self.root.withdraw()
        self.root.title("Hermes Pet")
        try:
            self.root.configure(bg="systemTransparent")
            self.canvas.configure(bg="systemTransparent")
            self.root.attributes("-transparent", True)
        except tk.TclError:
            self.root.attributes("-alpha", 0.96)
            self.root.configure(bg="#041c1c")
            self.canvas.configure(bg="#041c1c")

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.canvas.pack(fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.canvas.bind("<ButtonPress-1>", self._begin_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<Button-2>", self._show_menu)
        self.canvas.bind("<Button-3>", self._show_menu)
        self._resize_window()
        self.root.deiconify()

    def _ordered_pets(self) -> list[PetViewState]:
        return _ordered_pet_states(self.pets)

    def _resize_window(self) -> None:
        count = max(1, len(self.pets))
        slot_w = self.size + 36
        width = max(slot_w, slot_w * count)
        height = self.size + 68
        if (width, height) == self.window_size:
            return

        self.window_size = (width, height)
        self.canvas.configure(width=width, height=height)
        if self.initial_x is None or self.initial_y is None:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = max(12, screen_w - width - 76)
            y = max(12, screen_h - height - 92)
        else:
            x = self.initial_x
            y = self.initial_y
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _begin_drag(self, event: tk.Event) -> None:
        self.drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event: tk.Event) -> None:
        if not self.drag_start:
            return
        dx, dy = self.drag_start
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _show_menu(self, event: tk.Event) -> None:
        menu = Menu(self.root, tearoff=False)
        menu.add_command(label="Keep on top", state="disabled")
        menu.add_separator()
        menu.add_command(label="Quit Hermes Pet", command=self.root.destroy)
        menu.tk_popup(event.x_root, event.y_root)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            _apply_pet_event(self.pets, event)

    def _expire_pets(self) -> None:
        _expire_pet_states(self.pets)

    def _tick(self) -> None:
        self._drain_events()
        self._expire_pets()
        self._resize_window()
        self._draw()
        self.root.after(50, self._tick)

    def _draw(self) -> None:
        self.canvas.delete("all")
        phase = time.time()
        slot_w = self.size + 36
        top = 8
        for index, pet in enumerate(self._ordered_pets()):
            cx = index * slot_w + slot_w // 2
            self._draw_pet_canvas(cx, top, pet.state, phase)

            bubble_y = self.size + 22
            label = pet.label[:24]
            message = pet.message[:30]
            text = f"{label}\n{message}"
            self.canvas.create_rectangle(
                cx - slot_w // 2 + 6,
                bubble_y - 3,
                cx + slot_w // 2 - 6,
                bubble_y + 35,
                fill="#041c1c",
                outline="#ffe6cb",
                width=1,
            )
            self.canvas.create_text(
                cx,
                bubble_y + 15,
                text=text,
                fill="#ffe6cb",
                font=("Menlo", 10),
                justify="center",
                width=slot_w - 20,
            )

    def _draw_pet_canvas(self, cx: int, top: int, state: str, phase: float) -> None:
        sprite = self._sprite_for_state(state, phase)
        if sprite is not None:
            self.canvas.create_image(cx, top, image=sprite, anchor="n")
            return

        scale = self.size / 64
        blink = int((phase * 10) % 36) in {0, 1}
        wing_tick = 1 if int(phase * (7.5 if state == "running" else 2.2)) % 2 else 0
        step_tick = 1 if state == "running" and int(phase * 7.5) % 2 else 0
        shake = 1 if state == "failed" and int(phase * 12) % 2 else 0

        ox = shake
        outline = "#070909"
        black = "#0e0f11"
        white = "#f6f6ef"
        gray = "#b8bcb8"
        gold = "#facc15"
        teal = "#23d2b9"
        red = "#ef4444"
        amber = "#f59e0b"

        def xy(x: float, y: float) -> tuple[float, float]:
            return (cx + (x + ox - 32) * scale, top + y * scale)

        def rect(box: tuple[int, int, int, int], fill: str, outline_color: str = "") -> None:
            x0, y0, x1, y1 = box
            self.canvas.create_rectangle(
                *xy(x0, y0),
                *xy(x1 + 1, y1 + 1),
                fill=fill,
                outline=outline_color or fill,
                width=0,
            )

        def poly(points: list[tuple[int, int]], fill: str, outline_color: str = "") -> None:
            flat: list[float] = []
            for x, y in points:
                xp, yp = xy(x, y)
                flat.extend([xp, yp])
            self.canvas.create_polygon(
                *flat,
                fill=fill,
                outline=outline_color or fill,
                width=max(1, int(scale)) if outline_color else 0,
            )

        def line(points: list[tuple[int, int]], fill: str, width: int = 1) -> None:
            flat: list[float] = []
            for x, y in points:
                xp, yp = xy(x, y)
                flat.extend([xp, yp])
            self.canvas.create_line(*flat, fill=fill, width=max(1, int(width * scale)))

        rect((19, 60, 45, 61), "#000000")
        rect((24, 62, 40, 62), "#000000")

        if state == "review":
            self.canvas.create_rectangle(
                *xy(8, 7),
                *xy(56, 58),
                outline=teal,
                width=max(1, int(scale)),
            )
        elif state == "waiting":
            rect((51, 9, 55, 13), amber)
            rect((53, 15, 55, 17), amber)
        elif state == "failed":
            rect((51, 10, 55, 14), red)
            rect((52, 15, 54, 17), red)

        poly([(22, 40), (15, 59), (49, 59), (42, 40)], outline)
        poly([(24, 41), (18, 58), (46, 58), (40, 41)], black)
        poly([(27, 41), (32, 48), (37, 41)], teal)
        rect((29, 48, 35, 53), "#ebede7")
        rect((31, 49, 33, 52), black)

        line([(22, 43), (15, 51 + step_tick), (20, 52 + step_tick)], outline, 3)
        line([(42, 43), (49, 51 - step_tick), (44, 52 - step_tick)], outline, 3)
        rect((23, 57, 28, 60), gold)
        rect((36, 57, 41, 60), gold)

        rect((18, 22, 46, 43), outline)
        poly([(15, 27), (19, 58), (28, 57), (24, 39), (20, 25)], outline)
        poly([(49, 27), (45, 58), (36, 57), (40, 39), (44, 25)], outline)
        poly([(21, 17), (42, 17), (49, 27), (45, 37), (18, 37), (15, 27)], outline)
        poly([(24, 25), (30, 20), (41, 23), (43, 39), (38, 48), (27, 45), (22, 35)], white)
        rect((24, 24, 28, 33), outline)
        poly([(23, 20), (31, 18), (39, 21), (43, 25), (25, 26)], outline)
        rect((28, 19, 33, 23), white)
        rect((38, 24, 40, 27), white)

        poly([(24, 16), (32, 9), (40, 16), (38, 19), (26, 19)], outline)
        poly([(27, 15), (32, 10), (37, 15), (36, 17), (28, 17)], gold)
        rect((22, 17, 42, 19), outline)
        rect((24, 16, 40, 17), white)
        poly([(23, 17), (11, 14 - wing_tick), (14, 21 - wing_tick), (24, 21)], outline)
        poly([(41, 17), (53, 14 - wing_tick), (50, 21 - wing_tick), (40, 21)], outline)
        poly([(22, 17), (13, 15 - wing_tick), (16, 19 - wing_tick), (24, 19)], white)
        poly([(42, 17), (51, 15 - wing_tick), (48, 19 - wing_tick), (40, 19)], white)
        line([(14, 17 - wing_tick), (22, 18)], gray, 1)
        line([(50, 17 - wing_tick), (42, 18)], gray, 1)

        if state == "failed":
            line([(27, 33), (30, 36)], red, 1)
            line([(30, 33), (27, 36)], red, 1)
            line([(36, 33), (39, 36)], red, 1)
            line([(39, 33), (36, 36)], red, 1)
            line([(30, 42), (37, 42)], outline, 1)
        elif blink:
            line([(27, 34), (31, 34)], outline, 1)
            line([(36, 34), (40, 34)], outline, 1)
            rect((32, 42, 36, 42), outline)
        else:
            rect((28, 32, 31, 36), outline)
            rect((37, 32, 40, 36), outline)
            rect((30, 32, 31, 33), white)
            rect((39, 32, 40, 33), white)
            if state == "running":
                line([(32, 41), (36, 41)], outline, 1)
            elif state == "waiting":
                rect((32, 42, 36, 42), outline)
            else:
                line([(32, 41), (35, 42), (38, 41)], outline, 1)

        mood = {
            "running": "#22c55e",
            "waiting": amber,
            "failed": red,
            "review": teal,
            "idle": gray,
        }.get(state, gray)
        rect((31, 54, 33, 56), mood)

    def _sprite_for_state(self, state: str, phase: float) -> Optional[tk.PhotoImage]:
        if not self.sprite_images:
            return None
        if state == "running":
            return self.sprite_images.get("working") or self.sprite_images.get("idle")
        if state in {"waiting", "review"}:
            return self.sprite_images.get("review") or self.sprite_images.get("idle")
        if int((phase * 10) % 36) in {0, 1}:
            return self.sprite_images.get("blink") or self.sprite_images.get("idle")
        return self.sprite_images.get("idle")


def _make_server(host: str, port: int, token: str, event_queue: "queue.Queue[PetEvent]") -> PetEventServer:
    server = PetEventServer((host, port), PetEventHandler)
    server.event_queue = event_queue
    server.relay_token = token
    return server


def run_pet_overlay(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PET_PORT,
    token: Optional[str] = None,
    label: str = "Hermes Local",
    size: int = 84,
    show_local: bool = True,
    insecure: bool = False,
    initial_x: Optional[int] = None,
    initial_y: Optional[int] = None,
) -> None:
    if not _is_loopback_host(host) and not insecure:
        raise SystemExit(
            "Refusing to bind Hermes Pet outside localhost without --insecure. "
            "Use a strong relay token and trusted network controls."
        )

    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _raise_keyboard_interrupt(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    _ensure_tk_library_paths()
    relay_token = token or os.getenv(PET_RELAY_TOKEN_ENV) or secrets.token_urlsafe(24)
    event_queue: "queue.Queue[PetEvent]" = queue.Queue()
    server = _make_server(host, port, relay_token, event_queue)
    actual_port = int(server.server_address[1])
    endpoint_url = _runtime_url(host, actual_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    write_runtime(endpoint_url, relay_token)

    print(f"Hermes Pet overlay → {endpoint_url}")
    print(f"Relay header       → {PET_RELAY_HEADER_NAME}")
    print("Drag the pet to move it. Press Esc or right-click to quit.")
    sys.stdout.flush()

    try:
        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        if sys.platform == "darwin" and _run_macos_native_overlay(
            event_queue,
            runtime_host=host,
            runtime_port=actual_port,
            relay_token=relay_token,
            label=label,
            size=size,
            show_local=show_local,
            initial_x=initial_x,
            initial_y=initial_y,
        ):
            return

        overlay = HermesPetOverlay(
            event_queue,
            label=label,
            size=size,
            show_local=show_local,
            initial_x=initial_x,
            initial_y=initial_y,
        )
        overlay.run()
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        remove_runtime()
        server.shutdown()
        server.server_close()
