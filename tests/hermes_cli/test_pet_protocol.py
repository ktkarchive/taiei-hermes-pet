import pytest

import hermes_cli.pet_protocol as compatibility_protocol
import hermes_pet.protocol as canonical_protocol
from hermes_cli.pet_forwarder import _with_protocol
from hermes_pet.protocol import (
    PET_RELAY_HEADER_NAME,
    PROTOCOL_VERSION,
    clean_optional_token,
    clean_source_id,
    normalize_event,
    runtime_url,
)


def test_pet_protocol_exposes_stable_wire_constants():
    assert PROTOCOL_VERSION == "hermes-pet.v1"
    assert PET_RELAY_HEADER_NAME == "X-Hermes-Pet-Relay-Token"
    assert runtime_url("0.0.0.0", 8768) == "http://127.0.0.1:8768/api/pet/events"
    assert runtime_url("::1", 8768) == "http://[::1]:8768/api/pet/events"
    assert "time" not in canonical_protocol.__all__
    assert compatibility_protocol.PROTOCOL_VERSION == canonical_protocol.PROTOCOL_VERSION


def test_pet_protocol_normalizes_shared_event_payloads():
    event = normalize_event({
        "source_id": "Remote Lab 01",
        "state": "review",
        "message": "done",
        "notification_kind": "done",
        "pet_asset_id": "Mimi 20260503",
    })

    assert event.source_id == "Remote-Lab-01"
    assert event.notification_count == 1
    assert event.notification_label == "1"
    assert event.asset_id == "mimi-20260503"


def test_pet_protocol_rejects_unknown_state():
    with pytest.raises(ValueError, match="state must be one of"):
        normalize_event({"state": "unknown"})


def test_pet_protocol_rejects_wrong_protocol_when_present():
    with pytest.raises(ValueError, match="protocol must be hermes-pet.v1"):
        normalize_event({"protocol": "wrong", "state": "review"})


def test_pet_protocol_can_require_inbound_protocol():
    with pytest.raises(ValueError, match="protocol must be hermes-pet.v1"):
        normalize_event({"state": "review"}, require_protocol=True)

    event = normalize_event(
        {"protocol": PROTOCOL_VERSION, "state": "review"},
        require_protocol=True,
    )
    assert event.state == "review"


def test_pet_protocol_source_id_fallback_can_be_connector_specific():
    assert clean_source_id(" !!! ", fallback="remote-hermes") == "remote-hermes"


def test_pet_protocol_clean_token_edges():
    assert clean_optional_token(None) is None
    assert clean_optional_token("   ") is None
    assert clean_optional_token(" Hello World ") == "hello-world"
    assert clean_optional_token("가나다") is None
    assert clean_optional_token("x" * 200, 32) == "x" * 32


def test_pet_forwarder_adds_protocol_to_raw_outbound_events():
    raw = {"source_id": "local-hermes", "state": "running"}

    event = _with_protocol(raw)

    assert event["protocol"] == PROTOCOL_VERSION
    assert raw.get("protocol") is None
