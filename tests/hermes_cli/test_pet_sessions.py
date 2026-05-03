import hermes_cli.pet_sessions as pet_sessions


def test_heartbeat_updates_and_removes_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="cli",
        get_session_id=lambda: "session-a",
        label="Hermes CLI",
        cwd="/tmp/project",
        command="hermes",
        heartbeat_seconds=60,
    )
    try:
        sessions = pet_sessions.list_active_pet_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "session-a"
        assert sessions[0]["mode"] == "cli"
    finally:
        handle.stop()

    assert pet_sessions.list_active_pet_sessions() == []
    recent = pet_sessions.list_pet_menu_sessions()
    assert len(recent) == 1
    assert recent[0]["session_id"] == "session-a"
    assert recent[0]["active"] is False


def test_heartbeat_records_terminal_context(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.setenv("TTY", "/dev/ttys123")

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="cli",
        get_session_id=lambda: "session-a",
        label="Hermes CLI",
        heartbeat_seconds=60,
    )
    try:
        session = pet_sessions.list_active_pet_sessions()[0]
        assert session["ppid"]
        assert session["terminal"]["tty"] == "/dev/ttys123"
        assert session["terminal"]["terminal_app"] == "Terminal"
        assert session["terminal"]["terminal_bundle_id"] == "com.apple.Terminal"
    finally:
        handle.stop()


def test_heartbeat_detects_cmux_terminal_context(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("CMUX_PORT", "30100")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux.sock")

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="cli",
        get_session_id=lambda: "session-a",
        label="Hermes CLI",
        heartbeat_seconds=60,
    )
    try:
        terminal = pet_sessions.list_active_pet_sessions()[0]["terminal"]
        assert terminal["terminal_app"] == "cmux"
        assert terminal["terminal_bundle_id"] == "com.cmuxterm.app"
        assert terminal["cmux_port"] == "30100"
        assert terminal["cmux_socket_path"] == "/tmp/cmux.sock"
    finally:
        handle.stop()


def test_heartbeat_prioritizes_cmux_over_inner_ghostty_context(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setenv("CMUX_PORT", "30100")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux.sock")

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="tui",
        get_session_id=lambda: "session-a",
        label="Hermes TUI",
        heartbeat_seconds=60,
    )
    try:
        terminal = pet_sessions.list_active_pet_sessions()[0]["terminal"]
        assert terminal["term_program"] == "ghostty"
        assert terminal["terminal_app"] == "cmux"
        assert terminal["terminal_bundle_id"] == "com.cmuxterm.app"
    finally:
        handle.stop()


def test_heartbeat_rekeys_when_session_id_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    current = {"value": "session-a"}

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="tui",
        get_session_id=lambda: current["value"],
        label="Hermes TUI",
        heartbeat_seconds=60,
    )
    try:
        first = pet_sessions.list_active_pet_sessions()
        assert first[0]["session_id"] == "session-a"

        current["value"] = "session-b"
        handle._beat()

        sessions = pet_sessions.list_active_pet_sessions()
        assert [s["session_id"] for s in sessions] == ["session-b"]
        menu_sessions = pet_sessions.list_pet_menu_sessions()
        assert [s["session_id"] for s in menu_sessions] == ["session-b"]
        assert menu_sessions[0]["active"] is True
    finally:
        handle.stop()


def test_heartbeat_refreshes_dynamic_label(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    label = {"value": "First Title"}

    handle = pet_sessions.start_pet_session_heartbeat(
        mode="cli",
        get_session_id=lambda: "session-a",
        label=lambda: label["value"],
        heartbeat_seconds=60,
    )
    try:
        assert pet_sessions.list_active_pet_sessions()[0]["label"] == "First Title"
        label["value"] = "Renamed Title"
        handle._beat()
        assert pet_sessions.list_active_pet_sessions()[0]["label"] == "Renamed Title"
    finally:
        handle.stop()


def test_list_prunes_stale_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    pet_sessions._write_session_entry(
        mode="cli",
        session_id="stale",
        label="Hermes CLI",
        cwd="/tmp/project",
        command="hermes",
        started_at=1.0,
        previous_key=None,
    )

    assert pet_sessions.list_active_pet_sessions(stale_after=0) == []


def test_menu_sessions_dedupe_same_label_and_prefer_active(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_sessions, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(pet_sessions.os, "getpid", lambda: 100)
    pet_sessions._write_session_entry(
        mode="cli",
        session_id="session-a",
        label="Same Title",
        cwd="/tmp/project",
        command="hermes",
        started_at=1.0,
        previous_key=None,
    )
    monkeypatch.setattr(pet_sessions.os, "getpid", lambda: 200)
    pet_sessions._write_session_entry(
        mode="tui",
        session_id="session-b",
        label="Same Title",
        cwd="/tmp/project",
        command="hermes --tui",
        started_at=2.0,
        previous_key=None,
    )

    sessions = pet_sessions.list_pet_menu_sessions(limit=5)

    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session-b"
    assert sessions[0]["active"] is True


def test_menu_sessions_prefer_cmux_entry_for_same_active_session(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_sessions, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(pet_sessions.os, "getpid", lambda: 100)
    pet_sessions._write_session_entry(
        mode="tui",
        session_id="session-a",
        label="Same Title",
        cwd="/tmp/project",
        command="hermes --tui",
        started_at=1.0,
        previous_key=None,
        terminal={
            "terminal_app": "cmux",
            "terminal_bundle_id": "com.cmuxterm.app",
            "cmux_socket_path": "/tmp/cmux.sock",
        },
    )
    monkeypatch.setattr(pet_sessions.os, "getpid", lambda: 200)
    pet_sessions._write_session_entry(
        mode="tui",
        session_id="session-a",
        label="Same Title",
        cwd="/tmp/project",
        command="hermes --tui",
        started_at=2.0,
        previous_key=None,
        terminal={
            "terminal_app": "Ghostty",
            "terminal_bundle_id": "com.mitchellh.ghostty",
        },
    )

    sessions = pet_sessions.list_pet_menu_sessions(limit=5)

    assert len(sessions) == 1
    assert sessions[0]["pid"] == 100
    assert sessions[0]["terminal"]["terminal_app"] == "cmux"


def test_menu_sessions_limit_keeps_active_first(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_sessions, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_sessions, "_pid_alive", lambda _pid: True)
    for index in range(3):
        monkeypatch.setattr(pet_sessions.os, "getpid", lambda index=index: 300 + index)
        key = pet_sessions._write_session_entry(
            mode="cli",
            session_id=f"session-{index}",
            label=f"Title {index}",
            cwd="/tmp/project",
            command="hermes",
            started_at=float(index),
            previous_key=None,
        )
        if index < 2:
            pet_sessions.remove_pet_session(key)

    sessions = pet_sessions.list_pet_menu_sessions(limit=2)

    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "session-2"
    assert sessions[0]["active"] is True
