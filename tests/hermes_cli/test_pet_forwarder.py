import json

from hermes_cli.pet_forwarder import (
    default_pet_label,
    default_pet_source_id,
    pet_event_from_gateway_event,
    pet_event_from_gateway_frame,
    read_pet_runtime,
    relay_test_event,
    run_relay_test,
)


def test_gateway_tool_start_maps_to_codex_style_running_pet_event():
    event = pet_event_from_gateway_event(
        "tool.start",
        {"name": "terminal", "preview": "pwd"},
    )

    assert event == {
        "protocol": "hermes-pet.v1",
        "source_id": "local-hermes",
        "label": "Hermes Local",
        "state": "running",
        "message": "terminal",
        "event_type": "tool.start",
        "animation": "running",
        "pet_action": "running",
        "emotion": "focused",
        "ttl_ms": 12000,
    }


def test_gateway_approval_maps_to_waiting_pet_event():
    event = pet_event_from_gateway_event("approval.request", {"context": "approval needed"})

    assert event["source_id"] == "local-hermes"
    assert event["state"] == "waiting"
    assert event["message"] == "approval needed"
    assert event["animation"] == "waiting"
    assert event["pet_action"] == "waiting"
    assert event["ttl_ms"] == 60000
    assert event["notification_count"] == 1
    assert event["notification_kind"] == "choice"
    assert event["notification_label"] == "!"


def test_gateway_completion_error_maps_to_failed_pet_event():
    event = pet_event_from_gateway_event(
        "message.complete",
        {"status": "failed", "summary": "rate limited"},
    )

    assert event["state"] == "failed"
    assert event["message"] == "rate limited"
    assert event["animation"] == "failed"
    assert event["emotion"] == "error"
    assert event["notification_kind"] == "failed"


def test_gateway_frame_parses_json_rpc_event():
    frame = json.dumps({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "message.complete",
            "payload": {"status": "complete", "summary": "done"},
        },
    })

    event = pet_event_from_gateway_frame(frame)

    assert event["state"] == "review"
    assert event["message"] == "done"
    assert event["animation"] == "review"
    assert event["notification_kind"] == "done"
    assert event["notification_label"] == "1"


def test_gateway_payload_can_override_pet_animation_tokens():
    event = pet_event_from_gateway_event(
        "message.delta",
        {
            "text": "moving",
            "animation": "jumping",
            "direction": "left",
            "pet_action": "jump",
            "emotion": "excited",
        },
    )

    assert event["animation"] == "jumping"
    assert event["direction"] == "left"
    assert event["pet_action"] == "jump"
    assert event["emotion"] == "excited"


def test_env_runtime_supports_remote_pet_forwarding(monkeypatch):
    monkeypatch.setenv("HERMES_PET_RELAY_URL", "http://pet-host:8768/api/pet/events")
    monkeypatch.setenv("HERMES_PET_RELAY_TOKEN", "relay-token")

    runtime = read_pet_runtime()

    assert runtime["source"] == "env"
    assert runtime["url"] == "http://pet-host:8768/api/pet/events"
    assert runtime["token"] == "relay-token"


def test_remote_env_changes_default_source_and_label(monkeypatch):
    monkeypatch.setenv("HERMES_PET_RELAY_URL", "http://pet-host:8768/api/pet/events")
    monkeypatch.setenv("HERMES_PET_SOURCE_ID", "lab mac 01")
    monkeypatch.setenv("HERMES_PET_LABEL", "Hermes Lab Mac")

    event = pet_event_from_gateway_event("message.complete", {"summary": "done"})

    assert default_pet_source_id() == "lab-mac-01"
    assert default_pet_label() == "Hermes Lab Mac"
    assert event["source_id"] == "lab-mac-01"
    assert event["label"] == "Hermes Lab Mac"


def test_env_asset_id_is_forwarded(monkeypatch):
    monkeypatch.setenv("HERMES_PET_ASSET_ID", "mimi 20260503")

    event = pet_event_from_gateway_event("message.complete", {"summary": "done"})

    assert event["pet_asset_id"] == "mimi-20260503"


def test_relay_test_event_uses_remote_identity(monkeypatch):
    monkeypatch.setenv("HERMES_PET_RELAY_URL", "http://pet-host:8768/api/pet/events")
    monkeypatch.setenv("HERMES_PET_SOURCE_ID", "lab mac 01")
    monkeypatch.setenv("HERMES_PET_LABEL", "Hermes Lab Mac")

    event = relay_test_event("hello")

    assert event["source_id"] == "lab-mac-01"
    assert event["label"] == "Hermes Lab Mac"
    assert event["protocol"] == "hermes-pet.v1"
    assert event["state"] == "review"
    assert event["message"] == "hello"
    assert event["animation"] == "review"
    assert event["pet_action"] == "done"
    assert event["notification_kind"] == "done"


def test_run_relay_test_reports_missing_runtime(monkeypatch):
    monkeypatch.delenv("HERMES_PET_RELAY_URL", raising=False)
    monkeypatch.delenv("HERMES_PET_RELAY_TOKEN", raising=False)
    monkeypatch.setattr("hermes_cli.pet_forwarder.runtime_path", lambda: object())

    ok, message = run_relay_test()

    assert ok is False
    assert "No Hermes Pet relay runtime" in message
