"""Active Hermes session registry for the desktop pet.

This registry is intentionally separate from the durable SessionDB. SessionDB
answers "what sessions exist"; this file answers "what Hermes sessions are
alive right now and can be offered in the pet menu".
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_cli.config import get_hermes_home

REGISTRY_FILENAME = "pet_sessions.json"
LOCK_FILENAME = "pet_sessions.lock"
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_STALE_AFTER_SECONDS = 20.0
DEFAULT_RECENT_LIMIT = 5
MAX_STORED_RECENT_SESSIONS = 50

_TERM_PROGRAM_APPS = {
    "apple_terminal": ("Terminal", "com.apple.Terminal"),
    "iterm.app": ("iTerm2", "com.googlecode.iterm2"),
    "iterm2": ("iTerm2", "com.googlecode.iterm2"),
    "wezterm": ("WezTerm", "com.github.wez.wezterm"),
    "warpterminal": ("Warp", "dev.warp.Warp-Stable"),
    "warp": ("Warp", "dev.warp.Warp-Stable"),
    "vscode": ("Visual Studio Code", "com.microsoft.VSCode"),
    "kitty": ("kitty", "net.kovidgoyal.kitty"),
    "ghostty": ("Ghostty", "com.mitchellh.ghostty"),
    "cmux": ("cmux", "com.cmuxterm.app"),
}


def _terminal_context() -> dict[str, Any]:
    term_program = str(os.getenv("TERM_PROGRAM") or "").strip()
    app_name = ""
    bundle_id = ""
    if os.getenv("CMUX_PORT") or os.getenv("CMUX_SOCKET_PATH"):
        app_name, bundle_id = ("cmux", "com.cmuxterm.app")
    elif term_program:
        app_name, bundle_id = _TERM_PROGRAM_APPS.get(term_program.lower(), ("", ""))

    tty = str(os.getenv("TTY") or "").strip()
    if not tty:
        try:
            if sys.stdin.isatty():
                tty = os.ttyname(sys.stdin.fileno())
        except Exception:
            tty = ""

    return {
        "tty": tty,
        "term_program": term_program,
        "term_session_id": str(os.getenv("TERM_SESSION_ID") or "").strip(),
        "iterm_session_id": str(os.getenv("ITERM_SESSION_ID") or "").strip(),
        "wezterm_pane": str(os.getenv("WEZTERM_PANE") or "").strip(),
        "kitty_window_id": str(os.getenv("KITTY_WINDOW_ID") or "").strip(),
        "cmux_port": str(os.getenv("CMUX_PORT") or "").strip(),
        "cmux_port_end": str(os.getenv("CMUX_PORT_END") or "").strip(),
        "cmux_socket_path": str(os.getenv("CMUX_SOCKET_PATH") or "").strip(),
        "tmux": str(os.getenv("TMUX") or "").strip(),
        "vscode_pid": str(os.getenv("VSCODE_PID") or "").strip(),
        "terminal_app": app_name,
        "terminal_bundle_id": bundle_id,
    }


def _registry_path() -> Path:
    return get_hermes_home() / "runtime" / REGISTRY_FILENAME


def _lock_path() -> Path:
    return get_hermes_home() / "runtime" / LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_registry_unlocked(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {"sessions": {}}
    except Exception:
        return {"sessions": {}}
    if not isinstance(data, dict):
        return {"sessions": {}}
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        data["sessions"] = {}
    recent = data.get("recent_sessions")
    if not isinstance(recent, dict):
        data["recent_sessions"] = {}
    return data


def _write_registry_unlocked(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def _with_registry_lock(mutator: Callable[[dict[str, Any]], Any]) -> Any:
    import fcntl

    path = _registry_path()
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        data = _read_registry_unlocked(path)
        result = mutator(data)
        _write_registry_unlocked(path, data)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return result


def _prune_sessions(data: dict[str, Any], now: float, stale_after: float) -> None:
    sessions = data.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        data["sessions"] = {}
        return

    changed = False
    for key, entry in list(sessions.items()):
        if not isinstance(entry, dict):
            sessions.pop(key, None)
            changed = True
            continue
        pid = entry.get("pid")
        updated_at = float(entry.get("updated_at") or 0)
        stale = now - updated_at > stale_after
        dead = isinstance(pid, int) and not _pid_alive(pid)
        if stale or dead:
            sessions.pop(key, None)
            changed = True
    if changed:
        _sync_recent_active_flags(data)


def _recent_sessions(data: dict[str, Any]) -> dict[str, Any]:
    recent = data.setdefault("recent_sessions", {})
    if not isinstance(recent, dict):
        recent = {}
        data["recent_sessions"] = recent
    return recent


def _active_sessions(data: dict[str, Any]) -> dict[str, Any]:
    sessions = data.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        data["sessions"] = sessions
    return sessions


def _session_display_key(entry: dict[str, Any]) -> str:
    label = str(entry.get("label") or "").strip().casefold()
    if label:
        return f"label:{' '.join(label.split())}"
    session_id = str(entry.get("session_id") or "").strip().casefold()
    if session_id:
        return f"id:{session_id}"
    return f"entry:{entry.get('id') or ''}"


def _entry_uses_cmux(entry: dict[str, Any]) -> bool:
    terminal = entry.get("terminal")
    if not isinstance(terminal, dict):
        terminal = {}
    app_name = str(terminal.get("terminal_app") or "").strip().lower()
    bundle_id = str(terminal.get("terminal_bundle_id") or "").strip()
    return (
        app_name == "cmux"
        or bundle_id == "com.cmuxterm.app"
        or bool(str(terminal.get("cmux_socket_path") or "").strip())
        or bool(str(terminal.get("cmux_port") or "").strip())
    )


def _sync_recent_active_flags(data: dict[str, Any]) -> None:
    sessions = _active_sessions(data)
    recent = _recent_sessions(data)
    active_by_session: dict[str, dict[str, Any]] = {}
    for entry in sessions.values():
        if not isinstance(entry, dict):
            continue
        session_id = str(entry.get("session_id") or "").strip()
        if not session_id:
            continue
        current = active_by_session.get(session_id)
        if current is None:
            active_by_session[session_id] = entry
            continue
        entry_cmux = _entry_uses_cmux(entry)
        current_cmux = _entry_uses_cmux(current)
        if (entry_cmux and not current_cmux) or (
            entry_cmux == current_cmux
            and float(entry.get("updated_at") or 0) >= float(current.get("updated_at") or 0)
        ):
            active_by_session[session_id] = entry

    for session_id, entry in list(recent.items()):
        if not isinstance(entry, dict):
            recent.pop(session_id, None)
            continue
        active = active_by_session.get(str(session_id))
        if active is not None:
            merged = dict(active)
            merged["active"] = True
            recent[str(session_id)] = merged
        else:
            entry["active"] = False


def _trim_recent_sessions(data: dict[str, Any], *, max_items: int = MAX_STORED_RECENT_SESSIONS) -> None:
    recent = _recent_sessions(data)
    ordered = sorted(
        recent.items(),
        key=lambda item: float(item[1].get("updated_at") or 0) if isinstance(item[1], dict) else 0.0,
        reverse=True,
    )
    for key, _entry in ordered[max_items:]:
        recent.pop(key, None)


def list_active_pet_sessions(
    *,
    stale_after: float = DEFAULT_STALE_AFTER_SECONDS,
) -> list[dict[str, Any]]:
    now = time.time()

    def mutate(data: dict[str, Any]) -> list[dict[str, Any]]:
        _prune_sessions(data, now, stale_after)
        sessions = data.get("sessions") or {}
        if not isinstance(sessions, dict):
            return []
        return sorted(
            [dict(entry, active=True) for entry in sessions.values() if isinstance(entry, dict)],
            key=lambda item: (str(item.get("mode") or ""), str(item.get("session_id") or "")),
        )

    return _with_registry_lock(mutate)


def list_pet_menu_sessions(
    *,
    limit: int = DEFAULT_RECENT_LIMIT,
    stale_after: float = DEFAULT_STALE_AFTER_SECONDS,
) -> list[dict[str, Any]]:
    """Return active and recent sessions for the pet menu.

    Active sessions are marked with ``active=True``. Recently active sessions
    remain available for resume, but duplicate display names collapse to a
    single newest/active row so one session opened twice does not clutter the
    pet menu.
    """
    now = time.time()
    clean_limit = max(1, min(int(limit or DEFAULT_RECENT_LIMIT), 50))

    def mutate(data: dict[str, Any]) -> list[dict[str, Any]]:
        _prune_sessions(data, now, stale_after)
        _sync_recent_active_flags(data)
        recent = _recent_sessions(data)
        deduped: dict[str, dict[str, Any]] = {}
        for entry in recent.values():
            if not isinstance(entry, dict):
                continue
            key = _session_display_key(entry)
            current = deduped.get(key)
            if current is None:
                deduped[key] = dict(entry)
                continue
            entry_active = bool(entry.get("active"))
            current_active = bool(current.get("active"))
            entry_updated = float(entry.get("updated_at") or 0)
            current_updated = float(current.get("updated_at") or 0)
            entry_cmux = _entry_uses_cmux(entry)
            current_cmux = _entry_uses_cmux(current)
            if (
                entry_active
                and current_active
                and entry_cmux
                and not current_cmux
            ) or (entry_active and not current_active) or (
                entry_active == current_active and entry_updated >= current_updated
            ):
                deduped[key] = dict(entry)

        ordered = sorted(
            deduped.values(),
            key=lambda item: (
                0 if bool(item.get("active")) else 1,
                -float(item.get("updated_at") or 0),
                str(item.get("label") or ""),
            ),
        )
        return ordered[:clean_limit]

    return _with_registry_lock(mutate)


def _session_key(pid: int, mode: str, session_id: str) -> str:
    return f"{pid}:{mode}:{session_id}"


def _write_session_entry(
    *,
    mode: str,
    session_id: str,
    label: str | Callable[[], str],
    cwd: str,
    command: str,
    started_at: float,
    previous_key: Optional[str],
    terminal: Optional[dict[str, Any]] = None,
) -> str:
    now = time.time()
    pid = os.getpid()
    key = _session_key(pid, mode, session_id)

    def mutate(data: dict[str, Any]) -> None:
        _prune_sessions(data, now, DEFAULT_STALE_AFTER_SECONDS)
        sessions = _active_sessions(data)
        if previous_key and previous_key != key:
            sessions.pop(previous_key, None)
        entry = {
            "id": key,
            "mode": mode,
            "session_id": session_id,
            "label": label,
            "cwd": cwd,
            "command": command,
            "pid": pid,
            "ppid": os.getppid(),
            "terminal": terminal or _terminal_context(),
            "active": True,
            "started_at": started_at,
            "updated_at": now,
        }
        sessions[key] = entry
        recent = _recent_sessions(data)
        recent[session_id] = dict(entry)
        _sync_recent_active_flags(data)
        _trim_recent_sessions(data)

    _with_registry_lock(mutate)
    return key


def remove_pet_session(key: str) -> None:
    if not key:
        return

    def mutate(data: dict[str, Any]) -> None:
        sessions = _active_sessions(data)
        entry = sessions.pop(key, None)
        if isinstance(entry, dict):
            session_id = str(entry.get("session_id") or "").strip()
            if session_id:
                still_active = any(
                    isinstance(value, dict)
                    and str(value.get("session_id") or "").strip() == session_id
                    for value in sessions.values()
                )
                if not still_active:
                    recent = _recent_sessions(data)
                    recent_entry = recent.get(session_id)
                    if isinstance(recent_entry, dict):
                        recent_entry["active"] = False
                        recent_entry["updated_at"] = time.time()
        _sync_recent_active_flags(data)

    _with_registry_lock(mutate)


@dataclass
class PetSessionHeartbeat:
    mode: str
    get_session_id: Callable[[], str]
    label: str | Callable[[], str]
    cwd: str
    command: str
    terminal: Optional[dict[str, Any]] = None
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS
    started_at: float = field(default_factory=time.time)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _current_key: Optional[str] = field(default=None, init=False)

    def _label(self) -> str:
        try:
            raw = self.label() if callable(self.label) else self.label
        except Exception:
            raw = ""
        text = str(raw or "").strip()
        if not text:
            text = f"Hermes {self.mode.upper()}"
        return text[:96]

    def start(self) -> "PetSessionHeartbeat":
        if self._thread is not None:
            return self
        self._beat()
        self._thread = threading.Thread(
            target=self._run,
            name=f"hermes-pet-session-{self.mode}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._current_key:
            remove_pet_session(self._current_key)
            self._current_key = None

    def _beat(self) -> None:
        session_id = (self.get_session_id() or "").strip()
        if session_id:
            self._current_key = _write_session_entry(
                mode=self.mode,
                session_id=session_id,
                label=self._label(),
                cwd=self.cwd,
                command=self.command,
                started_at=self.started_at,
                previous_key=self._current_key,
                terminal=self.terminal,
            )

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            self._beat()


def start_pet_session_heartbeat(
    *,
    mode: str,
    get_session_id: Callable[[], str],
    label: str | Callable[[], str],
    cwd: Optional[str] = None,
    command: Optional[str] = None,
    terminal: Optional[dict[str, Any]] = None,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> PetSessionHeartbeat:
    handle = PetSessionHeartbeat(
        mode=mode,
        get_session_id=get_session_id,
        label=label,
        cwd=cwd or os.getcwd(),
        command=command or "",
        terminal=terminal,
        heartbeat_seconds=heartbeat_seconds,
    )
    return handle.start()
