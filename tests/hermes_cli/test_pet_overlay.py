import json
from types import SimpleNamespace

import pytest

import hermes_cli.pet_overlay as pet_overlay
from hermes_cli.pet_overlay import (
    LOCAL_SOURCE_ID,
    PetViewState,
    _apply_pet_event,
    _connected_pet_modes,
    _expire_pet_states,
    _handle_macos_helper_action,
    _hermes_python_executable,
    _snapshot_payload,
    generate_pet_launchd_plist,
    load_or_create_relay_token,
    normalize_event,
    read_pet_preferences,
    read_relay_token,
    relay_token_file,
    resolve_tailscale_host,
    write_runtime,
    write_pet_language,
    write_relay_token,
)


def test_remote_ttl_expiry_removes_pet_but_keeps_local():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(
            source_id=LOCAL_SOURCE_ID,
            label="Hermes Local",
            state="idle",
            message="ready",
        )
    }
    event = normalize_event({
        "source_id": "telegram-demo",
        "label": "Telegram Demo",
        "state": "running",
        "message": "ready",
        "ttl_ms": 1000,
        "notification_count": 0,
    })

    assert _apply_pet_event(pets, event, now=10.0)
    assert "telegram-demo" in pets

    assert _expire_pet_states(pets, now=11.1)
    assert LOCAL_SOURCE_ID in pets
    assert "telegram-demo" not in pets


def test_local_ttl_expiry_returns_to_idle():
    pets = {}
    event = normalize_event({
        "source_id": LOCAL_SOURCE_ID,
        "label": "Hermes Local",
        "state": "running",
        "message": "working",
        "ttl_ms": 1000,
    })

    _apply_pet_event(pets, event, now=20.0)
    assert pets[LOCAL_SOURCE_ID].state == "running"

    assert _expire_pet_states(pets, now=21.1)
    assert pets[LOCAL_SOURCE_ID].state == "idle"
    assert pets[LOCAL_SOURCE_ID].message == "ready"


def test_local_notification_survives_ttl_until_cleared():
    pets = {}
    event = normalize_event({
        "source_id": LOCAL_SOURCE_ID,
        "label": "Hermes Local",
        "state": "review",
        "message": "done",
        "ttl_ms": 1000,
        "notification_kind": "done",
        "notification_count": 1,
    })

    _apply_pet_event(pets, event, now=20.0)

    assert _expire_pet_states(pets, now=21.1)
    assert pets[LOCAL_SOURCE_ID].state == "idle"
    assert pets[LOCAL_SOURCE_ID].notification_count == 1

    assert _handle_macos_helper_action(pets, "clear_notifications", label="Hermes Local")
    assert pets[LOCAL_SOURCE_ID].notification_count == 0


def test_remove_action_removes_selected_remote_pet():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
        "remote-a": PetViewState("remote-a", "Remote A", "review", "done"),
        "remote-b": PetViewState("remote-b", "Remote B", "failed", "failed"),
    }
    event = normalize_event({"action": "remove", "source_id": "remote-a"})

    assert _apply_pet_event(pets, event, now=30.0)
    assert "remote-a" not in pets
    assert "remote-b" in pets
    assert LOCAL_SOURCE_ID in pets


def test_clear_action_keeps_local_and_removes_remotes():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "running", "working"),
        "remote-a": PetViewState("remote-a", "Remote A", "review", "done"),
    }
    event = normalize_event({"action": "clear"})

    assert _apply_pet_event(pets, event, now=40.0)
    assert list(pets) == [LOCAL_SOURCE_ID]
    assert pets[LOCAL_SOURCE_ID].state == "running"


def test_done_notifications_accumulate_and_can_be_acknowledged():
    pets = {}
    first = normalize_event({
        "source_id": LOCAL_SOURCE_ID,
        "state": "review",
        "message": "done 1",
        "notification_kind": "done",
        "notification_count": 1,
    })
    second = normalize_event({
        "source_id": LOCAL_SOURCE_ID,
        "state": "review",
        "message": "done 2",
        "notification_kind": "done",
        "notification_count": 1,
    })

    assert _apply_pet_event(pets, first, now=10.0)
    assert _apply_pet_event(pets, second, now=11.0)
    assert pets[LOCAL_SOURCE_ID].notification_count == 2

    assert _apply_pet_event(
        pets,
        normalize_event({"action": "ack", "source_id": LOCAL_SOURCE_ID}),
        now=12.0,
    )
    assert pets[LOCAL_SOURCE_ID].notification_count == 0
    assert pets[LOCAL_SOURCE_ID].notification_kind is None


def test_helper_clear_remotes_action_uses_same_lifecycle():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
        "remote-a": PetViewState("remote-a", "Remote A", "review", "done"),
    }

    assert _handle_macos_helper_action(pets, "clear_remotes", label="Hermes Local")
    assert list(pets) == [LOCAL_SOURCE_ID]


def test_helper_clear_notifications_keeps_pet_state():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(
            LOCAL_SOURCE_ID,
            "Hermes Local",
            "review",
            "done",
            notification_count=3,
            notification_kind="done",
            notification_label="3",
        ),
    }

    assert _handle_macos_helper_action(pets, "clear_notifications", label="Hermes Local")
    assert pets[LOCAL_SOURCE_ID].state == "review"
    assert pets[LOCAL_SOURCE_ID].notification_count == 0
    assert pets[LOCAL_SOURCE_ID].notification_kind is None


def test_helper_launch_action_updates_local_status(monkeypatch):
    def fake_launch(*, tui: bool):
        assert tui is True
        return True, "launched Hermes TUI"

    monkeypatch.setattr(pet_overlay, "_launch_hermes_terminal", fake_launch)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(pets, "launch_tui", label="Hermes Local")
    assert pets[LOCAL_SOURCE_ID].state == "review"
    assert pets[LOCAL_SOURCE_ID].message == "launched Hermes TUI"


def test_helper_launch_ssh_action_updates_local_status(monkeypatch):
    def fake_launch_ssh(*, target: str):
        assert target == "lab-mac"
        return True, "opened SSH helper for lab-mac"

    monkeypatch.setattr(pet_overlay, "_launch_hermes_ssh_terminal", fake_launch_ssh)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "launch_ssh", "target": "lab-mac"},
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].state == "review"
    assert pets[LOCAL_SOURCE_ID].message == "opened SSH helper for lab-mac"


def test_helper_launch_telegram_action_reports_failure(monkeypatch):
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_telegram_relay",
        lambda: (False, "Telegram relay needs HERMES_TELEGRAM_BOT_TOKEN"),
    )
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "launch_telegram"},
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].state == "failed"
    assert pets[LOCAL_SOURCE_ID].animation == "failed"
    assert "Telegram relay needs" in pets[LOCAL_SOURCE_ID].message


def test_launch_cli_focuses_existing_active_session_before_new_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pet_overlay.write_pet_preferences(terminal_launcher="cmux")
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "cli",
            "session_id": "session-a",
            "label": "Hermes CLI",
            "active": True,
            "terminal_app": "cmux",
            "terminal_bundle_id": "com.cmuxterm.app",
        }],
    )
    monkeypatch.setattr(pet_overlay, "_focus_terminal_session", lambda _session: (False, "exact tab not found"))
    monkeypatch.setattr(pet_overlay, "_activate_cmux_app", lambda: (True, "activated cmux"))
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_resume_terminal",
        lambda **_: (_ for _ in ()).throw(AssertionError("active launch should not duplicate")),
    )

    ok, message = pet_overlay._launch_hermes_terminal(tui=False)

    assert ok is True
    assert message == "activated cmux for existing Hermes CLI: exact tab not found; activated cmux"


def test_helper_set_language_persists_preference(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "set_language", "language": "en"},
        label="Hermes Local",
    )

    assert read_pet_preferences()["language"] == "en"
    assert read_pet_preferences()["left_click_opens_terminal"] is False
    assert read_pet_preferences()["session_list_limit"] == 5
    assert read_pet_preferences()["terminal_launcher"] == "macos"
    assert pets[LOCAL_SOURCE_ID].state == "review"
    assert pets[LOCAL_SOURCE_ID].notification_kind == "done"

    assert _handle_macos_helper_action(
        pets,
        {"action": "set_language", "language": "ja"},
        label="Hermes Local",
    )
    assert read_pet_preferences()["language"] == "ja"

    assert _handle_macos_helper_action(
        pets,
        {"action": "set_language", "language": "zh"},
        label="Hermes Local",
    )
    assert read_pet_preferences()["language"] == "zh"


def test_helper_set_preferences_persists_click_and_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {
            "action": "set_preferences",
            "language": "ja",
            "left_click_opens_terminal": "true",
            "session_list_limit": "9",
            "terminal_launcher": "cmux",
        },
        label="Hermes Local",
    )

    assert read_pet_preferences()["language"] == "ja"
    assert read_pet_preferences()["left_click_opens_terminal"] is True
    assert read_pet_preferences()["session_list_limit"] == 9
    assert read_pet_preferences()["terminal_launcher"] == "cmux"


def test_helper_launch_agent_status_reports_runtime_state(monkeypatch):
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    monkeypatch.setattr(
        pet_overlay,
        "pet_launchd_status",
        lambda: {"installed": True, "loaded": False},
    )

    assert _handle_macos_helper_action(
        pets,
        {"action": "launch_agent_status"},
        label="Hermes Local",
    )

    assert pets[LOCAL_SOURCE_ID].state == "review"
    assert "installed=True" in pets[LOCAL_SOURCE_ID].message
    assert pets[LOCAL_SOURCE_ID].notification_kind == "done"


def test_helper_install_launch_agent_uses_current_runtime(monkeypatch):
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    calls = []

    def fake_install(**kwargs):
        calls.append(kwargs)
        return True, "installed"

    monkeypatch.setattr(pet_overlay, "install_pet_launch_agent", fake_install)

    assert _handle_macos_helper_action(
        pets,
        {"action": "install_launch_agent"},
        label="Hermes Local",
        size=96,
        runtime_host="127.0.0.1",
        runtime_port=8768,
        relay_token="token-a",
    )

    assert calls == [{
        "host": "127.0.0.1",
        "port": 8768,
        "token": "token-a",
        "label": "Hermes Local",
        "size": 96,
        "show_local": True,
        "insecure": False,
        "force": True,
    }]
    assert pets[LOCAL_SOURCE_ID].message == "installed"


def test_helper_stop_launch_agent_keeps_current_pet(monkeypatch):
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    calls = []
    monkeypatch.setattr(
        pet_overlay,
        "stop_pet_launch_agent",
        lambda **kwargs: (calls.append(kwargs) or (True, "stopped")),
    )

    assert _handle_macos_helper_action(
        pets,
        {"action": "stop_launch_agent"},
        label="Hermes Local",
    )

    assert calls == [{"stop_current": False}]
    assert pets[LOCAL_SOURCE_ID].message == "stopped"


def test_legacy_terminus_preference_falls_back_to_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)

    pet_overlay.write_pet_preferences(terminal_launcher="terminus")

    assert read_pet_preferences()["terminal_launcher"] == "macos"


def test_selected_cmux_launcher_is_used_for_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pet_overlay.write_pet_preferences(terminal_launcher="cmux")
    calls = []

    def fake_cmux(lines, *, session_id=None):
        calls.append((lines, session_id))
        return True, "opened cmux tab"

    monkeypatch.setattr(pet_overlay, "_focus_cmux_terminal_for_session", lambda _session_id: (False, "not found"))
    monkeypatch.setattr(pet_overlay, "_launch_cmux_terminal", fake_cmux)

    ok, message = pet_overlay._launch_hermes_resume_terminal(tui=False, session_id="session-a")

    assert ok is True
    assert "via cmux" in message
    assert calls[0][1] == "session-a"
    assert any("--resume session-a" in line for line in calls[0][0])
    assert any("Hermes CLI session-a" in line for line in calls[0][0])


def test_selected_cmux_launcher_focuses_existing_session_tab(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pet_overlay.write_pet_preferences(terminal_launcher="cmux")
    monkeypatch.setattr(
        pet_overlay,
        "_focus_cmux_terminal_for_session",
        lambda session_id: (True, f"focused {session_id}"),
    )
    monkeypatch.setattr(
        pet_overlay,
        "_launch_cmux_terminal",
        lambda _lines: (_ for _ in ()).throw(AssertionError("new cmux tab should not be opened")),
    )

    ok, message = pet_overlay._launch_hermes_resume_terminal(tui=True, session_id="session-a")

    assert ok is True
    assert message == "focused session-a in existing cmux tab"


def test_cmux_launcher_remembers_terminal_id(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_overlay.sys, "platform", "darwin")
    monkeypatch.setattr(pet_overlay, "_app_available", lambda name: name == "cmux")
    monkeypatch.setattr(pet_overlay, "_run_osascript", lambda _script: (True, "opened cmux tab terminal-123"))

    ok, message = pet_overlay._launch_cmux_terminal(["#!/bin/zsh", "echo hi"], session_id="session-a")

    assert ok is True
    assert message == "opened cmux tab terminal-123"
    assert pet_overlay._cmux_terminal_id_for_session("session-a") == "terminal-123"


def test_cmux_focus_uses_remembered_terminal_id(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_overlay.sys, "platform", "darwin")
    monkeypatch.setattr(pet_overlay, "_app_available", lambda name: name == "cmux")
    pet_overlay._remember_cmux_session_terminal("session-a", "terminal-123")
    scripts = []

    def fake_osascript(script):
        scripts.append(script)
        return True, "focused cmux terminal"

    monkeypatch.setattr(pet_overlay, "_run_osascript", fake_osascript)

    ok, message = pet_overlay._focus_cmux_terminal_for_session("session-a")

    assert ok is True
    assert message == "focused cmux terminal"
    assert "terminal-123" in scripts[0]


def test_cmux_focus_falls_back_to_cwd_and_tab_matching(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_overlay.sys, "platform", "darwin")
    monkeypatch.setattr(pet_overlay, "_app_available", lambda name: name == "cmux")
    scripts = []

    def fake_osascript(script):
        scripts.append(script)
        return True, "focused cmux terminal"

    monkeypatch.setattr(pet_overlay, "_run_osascript", fake_osascript)

    ok, message = pet_overlay._focus_cmux_terminal_for_session_fields(
        "session-a",
        cwd="/Users/example/.hermes/hermes-agent",
        label="disk cleanup",
    )

    assert ok is True
    assert message == "focused cmux terminal"
    assert "working directory of term" in scripts[0]
    assert "/Users/example/.hermes/hermes-agent" in scripts[0]
    assert "tabName contains" in scripts[0]


def test_focus_terminal_session_detects_cmux_from_socket_metadata(monkeypatch):
    calls = []

    def fake_focus(session_id, *, cwd="", label=""):
        calls.append((session_id, cwd, label))
        return True, "focused cmux terminal"

    monkeypatch.setattr(pet_overlay, "_focus_cmux_terminal_for_session_fields", fake_focus)

    ok, message = pet_overlay._focus_terminal_session({
        "session_id": "session-a",
        "label": "Hermes TUI",
        "cwd": "/Users/example/.hermes/hermes-agent",
        "terminal_app": "Ghostty",
        "terminal_bundle_id": "com.mitchellh.ghostty",
        "cmux_socket_path": "/Users/example/Library/Application Support/cmux/cmux.sock",
    })

    assert ok is True
    assert message == "focused cmux terminal"
    assert calls == [("session-a", "/Users/example/.hermes/hermes-agent", "Hermes TUI")]


def test_termius_preference_falls_back_to_macos_launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pet_overlay.write_pet_preferences(terminal_launcher="termius")
    calls = []

    def fake_macos(script_path):
        calls.append(script_path)
        return True, "opened macOS Terminal"

    monkeypatch.setattr(pet_overlay, "_launch_macos_terminal_script", fake_macos)

    ok, message = pet_overlay._launch_hermes_resume_terminal(tui=True, session_id="session-a")

    assert ok is True
    assert "via macOS Terminal" in message
    assert calls[0].name == "pet_launch_tui.command"
    assert "--resume session-a" in calls[0].read_text()


def test_terminal_launcher_options_exclude_termius(monkeypatch):
    monkeypatch.setattr(pet_overlay.sys, "platform", "darwin")

    option_ids = [option["id"] for option in pet_overlay._terminal_launcher_options()]

    assert option_ids == ["macos", "cmux"]


def test_helper_open_session_action_resumes_selected_session(monkeypatch):
    calls = []

    def fake_resume(*, tui: bool, session_id: str):
        calls.append((tui, session_id))
        return True, f"resuming {session_id}"

    monkeypatch.setattr(pet_overlay, "_launch_hermes_resume_terminal", fake_resume)
    monkeypatch.setattr(pet_overlay, "_pet_menu_sessions", lambda: [])
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "open_session_tui", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert calls == [(True, "20260502_120000_abc123")]
    assert pets[LOCAL_SOURCE_ID].state == "review"


def test_helper_open_session_focuses_active_session_before_launch(monkeypatch):
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "cli",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes CLI",
            "active": True,
            "terminal_app": "cmux",
            "terminal_bundle_id": "com.cmuxterm.app",
        }],
    )
    monkeypatch.setattr(
        pet_overlay,
        "_focus_terminal_session",
        lambda session: (True, f"focused {session['session_id']}"),
    )
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_resume_terminal",
        lambda **_: (_ for _ in ()).throw(AssertionError("resume fallback should not run")),
    )
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "open_session_cli", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].message == "focused 20260502_120000_abc123"


def test_helper_open_session_does_not_focus_active_other_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "tui",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes TUI",
            "active": True,
            "terminal_app": "cmux",
            "terminal_bundle_id": "com.cmuxterm.app",
        }],
    )
    monkeypatch.setattr(
        pet_overlay,
        "_focus_terminal_session",
        lambda _session: (_ for _ in ()).throw(AssertionError("wrong mode should not focus")),
    )

    def fake_resume(*, tui: bool, session_id: str):
        calls.append((tui, session_id))
        return True, f"resuming {session_id}"

    monkeypatch.setattr(pet_overlay, "_launch_hermes_resume_terminal", fake_resume)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "open_session_cli", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert calls == [(False, "20260502_120000_abc123")]


def test_helper_open_session_activates_cmux_instead_of_duplicate_when_focus_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    pet_overlay.write_pet_preferences(terminal_launcher="cmux")
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "cli",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes CLI",
            "active": True,
        }],
    )
    monkeypatch.setattr(pet_overlay, "_focus_terminal_session", lambda _session: (False, "exact tab not found"))
    monkeypatch.setattr(pet_overlay, "_activate_cmux_app", lambda: (True, "activated cmux"))
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_resume_terminal",
        lambda **_: (_ for _ in ()).throw(AssertionError("active cmux session should not duplicate")),
    )
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "open_session_cli", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].message == "exact tab not found; activated cmux"


def test_helper_focus_session_prefers_existing_terminal(monkeypatch):
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "cli",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes CLI",
            "active": True,
            "terminal_app": "Terminal",
            "tty": "/dev/ttys123",
        }],
    )
    monkeypatch.setattr(
        pet_overlay,
        "_focus_terminal_session",
        lambda session: (True, f"focused {session['session_id']}"),
    )
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_resume_terminal",
        lambda **_: (_ for _ in ()).throw(AssertionError("resume fallback should not run")),
    )
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "focus_session", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].message == "focused 20260502_120000_abc123"


def test_helper_focus_session_falls_back_to_resume(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "tui",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes TUI",
        }],
    )
    monkeypatch.setattr(
        pet_overlay,
        "_focus_terminal_session",
        lambda _session: (False, "tab not found"),
    )

    def fake_resume(*, tui: bool, session_id: str):
        calls.append((tui, session_id))
        return True, f"resuming {session_id}"

    monkeypatch.setattr(pet_overlay, "_launch_hermes_resume_terminal", fake_resume)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {"action": "focus_session", "session_id": "20260502_120000_abc123"},
        label="Hermes Local",
    )
    assert calls == [(True, "20260502_120000_abc123")]
    assert "resuming" in pets[LOCAL_SOURCE_ID].message


def test_helper_focus_session_does_not_resume_when_fallback_disabled(monkeypatch):
    monkeypatch.setattr(
        pet_overlay,
        "_pet_menu_sessions",
        lambda: [{
            "mode": "cli",
            "session_id": "20260502_120000_abc123",
            "label": "Hermes CLI",
            "active": True,
        }],
    )
    monkeypatch.setattr(
        pet_overlay,
        "_focus_terminal_session",
        lambda _session: (False, "tab not found"),
    )
    monkeypatch.setattr(
        pet_overlay,
        "_launch_hermes_resume_terminal",
        lambda **_: (_ for _ in ()).throw(AssertionError("resume fallback should not run")),
    )
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }

    assert _handle_macos_helper_action(
        pets,
        {
            "action": "focus_session",
            "session_id": "20260502_120000_abc123",
            "allow_resume": "false",
        },
        label="Hermes Local",
    )
    assert pets[LOCAL_SOURCE_ID].state == "failed"
    assert "fallback is off" in pets[LOCAL_SOURCE_ID].message


def test_helper_search_pet_share_returns_picker_payload(monkeypatch):
    from hermes_cli.pet_share import PetSharePage, PetSharePet
    import hermes_cli.pet_share as pet_share

    def fake_list_share_pets(*, query, page_size, sort, content):
        assert query == "mi"
        assert page_size == 8
        assert sort == "new"
        assert content == "safe"
        return PetSharePage(
            pets=(
                PetSharePet(
                    id="mimi",
                    display_name="Mimi",
                    description="Tiny",
                    owner_name="plutoless",
                    tags=("cute",),
                    like_count=1,
                    view_count=2,
                    spritesheet_url="",
                    download_url="",
                ),
            ),
            page=1,
            page_size=8,
            total=1,
            total_pages=1,
        )

    monkeypatch.setattr(pet_share, "list_share_pets", fake_list_share_pets)
    share = []

    assert _handle_macos_helper_action(
        {},
        {"action": "search_pet_share", "query": "mi"},
        label="Hermes Local",
        share_response_box=share,
    )
    assert share[0]["status"] == "results"
    assert share[0]["pets"][0]["id"] == "mimi"
    assert "thumbnail_path" in share[0]["pets"][0]
    assert share[0]["pets"][0]["share_url"].endswith("/mimi")


def test_helper_apply_pet_share_sets_review_status(monkeypatch):
    import hermes_cli.pet_share as pet_share

    def fake_apply_share_pet(identifier, *, size):
        assert identifier == "mimi"
        assert size == 84
        return SimpleNamespace(
            pet=SimpleNamespace(id="mimi", display_name="Mimi"),
            asset_dir=None,
            manifest_path=None,
            backup_dir=None,
        )

    monkeypatch.setattr(pet_share, "apply_share_pet", fake_apply_share_pet)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    share = []

    assert _handle_macos_helper_action(
        pets,
        {"action": "apply_share_pet", "pet_id": "mimi"},
        label="Hermes Local",
        size=84,
        share_response_box=share,
    )
    assert share[0]["status"] == "applied"
    assert pets[LOCAL_SOURCE_ID].animation == "review"


def test_helper_apply_installed_pet_sets_review_status(monkeypatch):
    import hermes_cli.pet_share as pet_share

    def fake_activate_installed_pet_asset(asset_id):
        assert asset_id == "mimi-20260503"
        return SimpleNamespace(pet_id="mimi", display_name="Mimi")

    monkeypatch.setattr(pet_share, "activate_installed_pet_asset", fake_activate_installed_pet_asset)
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    share = []

    assert _handle_macos_helper_action(
        pets,
        {"action": "apply_installed_pet", "asset_id": "mimi-20260503"},
        label="Hermes Local",
        share_response_box=share,
    )
    assert share[0]["status"] == "applied"
    assert pets[LOCAL_SOURCE_ID].animation == "review"


def test_snapshot_payload_includes_sessions():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(LOCAL_SOURCE_ID, "Hermes Local", "idle", "ready"),
    }
    payload = _snapshot_payload(
        pets,
        sessions=[{"mode": "cli", "session_id": "abc", "label": "Hermes CLI", "active": True}],
    )

    assert '"sessions":[{"mode":"cli","session_id":"abc","label":"Hermes CLI","active":true}]' in payload
    assert '"connected_modes":["cli"]' in payload
    assert '"preferences":' in payload
    assert '"terminal_launcher":"' in payload
    assert '"terminal_options":' in payload


def test_connected_modes_include_telegram_status(monkeypatch):
    monkeypatch.setattr(pet_overlay, "_telegram_relay_status", lambda: {"running": True})

    assert _connected_pet_modes([{"mode": "cli", "active": True}, {"mode": "tui", "active": False}]) == ["cli", "telegram"]


def test_snapshot_payload_includes_animation_hints_and_share_response():
    pets = {
        LOCAL_SOURCE_ID: PetViewState(
            LOCAL_SOURCE_ID,
            "Hermes Local",
            "running",
            "working",
            animation="running-left",
            direction="left",
            pet_action="running",
            emotion="focused",
            notification_count=1,
            notification_kind="done",
            notification_label="1",
        ),
    }
    payload = _snapshot_payload(
        pets,
        share={"request_id": "abc", "status": "results", "message": "1 result", "query": "mi", "pets": []},
        asset_version="assets:1",
        artwork={"current": {"id": "mimi", "display_name": "Mimi"}, "installed": []},
    )

    assert '"animation":"running-left"' in payload
    assert '"direction":"left"' in payload
    assert '"pet_action":"running"' in payload
    assert '"emotion":"focused"' in payload
    assert '"asset_version":"assets:1"' in payload
    assert '"request_id":"abc"' in payload
    assert '"artwork":{"current":{"id":"mimi","display_name":"Mimi"},"installed":[]}' in payload
    assert '"notification_count":1' in payload
    assert '"notification_kind":"done"' in payload
    assert '"ui_language":"' in payload


def test_snapshot_payload_includes_source_specific_asset(monkeypatch, tmp_path):
    asset_dir = tmp_path / "mimi"
    asset_dir.mkdir()
    (asset_dir / "manifest.json").write_text("{}")

    monkeypatch.setattr(
        pet_overlay,
        "_source_pet_skin_asset",
        lambda source_id, asset_id=None: SimpleNamespace(asset_id="mimi-20260503", path=asset_dir),
    )
    pets = {
        "remote-lab": PetViewState("remote-lab", "Remote Lab", "running", "working"),
    }

    payload = _snapshot_payload(pets)

    assert '"asset_id":"mimi-20260503"' in payload
    assert f'"asset_dir":"{asset_dir}"' in payload


def test_normalize_event_accepts_animation_hints():
    event = normalize_event({
        "source_id": "remote",
        "state": "running",
        "message": "moving",
        "animation": "running-left",
        "direction": "left",
        "pet_action": "running",
        "emotion": "focused",
        "pet_asset_id": "mimi-20260503",
        "notification_kind": "choice",
        "notification_label": "!",
    })

    assert event.animation == "running-left"
    assert event.direction == "left"
    assert event.pet_action == "running"
    assert event.emotion == "focused"
    assert event.asset_id == "mimi-20260503"
    assert event.notification_count == 1
    assert event.notification_kind == "choice"
    assert event.notification_label == "!"


def test_write_pet_language_rejects_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)

    assert write_pet_language("ko") == "ko"
    assert read_pet_preferences()["language"] == "ko"
    assert write_pet_language("en") == "en"
    assert write_pet_language("ja") == "ja"
    assert write_pet_language("zh") == "zh"

    with pytest.raises(ValueError, match="language must be ko, en, ja, or zh"):
        write_pet_language("fr")


def test_launcher_prefers_repo_venv_python():
    assert _hermes_python_executable().name == "python3"
    assert "venv/bin/python3" in str(_hermes_python_executable())


def test_persistent_relay_token_file_is_reused_and_private(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)

    token = load_or_create_relay_token()
    assert token
    assert read_relay_token() == token
    assert load_or_create_relay_token() == token
    assert relay_token_file().stat().st_mode & 0o777 == 0o600


def test_runtime_file_is_written_private(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)

    write_runtime("http://127.0.0.1:8768/api/pet/events", "sample-token")

    runtime_path = tmp_path / "runtime" / "pet_overlay.json"
    assert runtime_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(runtime_path.read_text())["process_kind"] == "hermes_pet_overlay"


def test_runtime_status_rejects_unrelated_reused_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    runtime_path = tmp_path / "runtime" / "pet_overlay.json"
    runtime_path.parent.mkdir(parents=True)
    runtime_path.write_text(json.dumps({"pid": 12345, "url": "http://127.0.0.1:8768/api/pet/events"}))
    monkeypatch.setattr(pet_overlay, "_pid_alive", lambda pid: pid == 12345)
    monkeypatch.setattr(pet_overlay, "_pid_command", lambda pid: "sleep 100")

    status = pet_overlay.pet_overlay_status()

    assert status["running"] is False
    assert status["reason"] == "runtime pid does not look like Hermes Pet"


def test_persistent_relay_token_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_overlay, "get_hermes_home", lambda: tmp_path)
    write_relay_token("old-token")

    token = load_or_create_relay_token(rotate=True)

    assert token != "old-token"
    assert read_relay_token() == token


def test_launchd_plist_runs_pet_foreground_at_login(monkeypatch):
    monkeypatch.setattr(pet_overlay, "_installed_hermes_pet_wrapper", lambda: None)
    plist = generate_pet_launchd_plist(
        host="127.0.0.1",
        port=8768,
        token="sample-token",
        label="Hermes Local",
        size=84,
        show_local=True,
        insecure=False,
        initial_x=None,
        initial_y=None,
    )

    assert "<key>RunAtLoad</key>" in plist
    assert "<string>hermes_cli.main</string>" in plist
    assert "<string>pet</string>" in plist
    assert "<string>--background</string>" not in plist
    assert "<string>--token</string>" not in plist
    assert "<key>HERMES_PET_RELAY_TOKEN</key>" in plist
    assert "<string>127.0.0.1</string>" in plist
    assert "<string>8768</string>" in plist


def test_launchd_plist_prefers_installed_wrapper(tmp_path, monkeypatch):
    wrapper = tmp_path / "hermes-pet"
    wrapper.write_text("#!/usr/bin/env bash\n")
    wrapper.chmod(0o755)
    monkeypatch.setattr(pet_overlay, "_installed_hermes_pet_wrapper", lambda: wrapper)

    plist = generate_pet_launchd_plist(
        host="127.0.0.1",
        port=8768,
        token="sample-token",
        label="Hermes Local",
        size=84,
        show_local=True,
        insecure=False,
        initial_x=None,
        initial_y=None,
    )

    assert f"<string>{wrapper}</string>" in plist
    assert "<string>hermes_cli.main</string>" not in plist


def test_tailscale_host_uses_env_override(monkeypatch):
    monkeypatch.setenv("HERMES_PET_TAILSCALE_IP", "100.64.0.42")

    assert resolve_tailscale_host() == "100.64.0.42"


def test_tailscale_host_rejects_non_tailscale_env_override(monkeypatch):
    monkeypatch.setenv("HERMES_PET_TAILSCALE_IP", "0.0.0.0")

    with pytest.raises(RuntimeError, match="not in the Tailscale IPv4 range"):
        resolve_tailscale_host()


def test_tailscale_host_reads_tailscale_cli(monkeypatch):
    monkeypatch.delenv("HERMES_PET_TAILSCALE_IP", raising=False)

    class _Result:
        returncode = 0
        stdout = "100.101.102.103\n"
        stderr = ""

    monkeypatch.setattr(pet_overlay.subprocess, "run", lambda *a, **kw: _Result())

    assert resolve_tailscale_host() == "100.101.102.103"
