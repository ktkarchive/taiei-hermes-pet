import json

import hermes_cli.pet_telegram_relay as pet_telegram_relay
from hermes_cli.pet_telegram_relay import poll_telegram_once, telegram_update_to_pet_event


def test_telegram_update_maps_text_to_review_pet_event():
    event = telegram_update_to_pet_event(
        {
            "update_id": 10,
            "message": {
                "text": "remote Hermes finished",
                "chat": {"id": 12345, "title": "Lab"},
                "from": {"username": "remote_box"},
            },
        },
        allow_any_chat=True,
    )

    assert event is not None
    assert event["source_id"] == "telegram-12345"
    assert event["label"] == "Telegram remote_box"
    assert event["state"] == "review"
    assert event["message"] == "remote Hermes finished"


def test_telegram_command_selects_state_and_strips_command():
    event = telegram_update_to_pet_event(
        {
            "update_id": 11,
            "message": {
                "text": "/running build in progress",
                "chat": {"id": -900},
                "from": {"first_name": "Hermes Mini"},
            },
        },
        allow_any_chat=True,
    )

    assert event is not None
    assert event["source_id"] == "telegram--900"
    assert event["label"] == "Telegram Hermes Mini"
    assert event["state"] == "running"
    assert event["message"] == "build in progress"


def test_telegram_clear_command_maps_to_clear_action():
    event = telegram_update_to_pet_event(
        {
            "update_id": 12,
            "message": {
                "text": "/clear",
                "chat": {"id": 12345},
            },
        },
        allow_any_chat=True,
    )

    assert event is not None
    assert event["action"] == "clear"
    assert event["state"] == "idle"


def test_telegram_chat_allow_list_filters_other_chats():
    event = telegram_update_to_pet_event(
        {
            "update_id": 13,
            "message": {
                "text": "ignore me",
                "chat": {"id": 777},
            },
        },
        allowed_chat_id="12345",
    )

    assert event is None


def test_telegram_requires_allow_list_or_explicit_any_chat():
    event = telegram_update_to_pet_event({
        "update_id": 14,
        "message": {
            "text": "ignore without allow list",
            "chat": {"id": 12345},
        },
    })

    assert event is None


def test_telegram_offset_does_not_advance_when_delivery_fails(tmp_path, monkeypatch):
    offset_file = tmp_path / "offset.json"

    monkeypatch.setattr(
        pet_telegram_relay,
        "_telegram_api",
        lambda *a, **kw: {
            "ok": True,
            "result": [{
                "update_id": 41,
                "message": {
                    "text": "will retry",
                    "chat": {"id": 12345},
                },
            }],
        },
    )
    monkeypatch.setattr(pet_telegram_relay, "post_pet_event_now", lambda *a, **kw: False)

    sent = poll_telegram_once(
        bot_token="token",
        chat_id="12345",
        offset_path=str(offset_file),
    )

    assert sent == 0
    assert not offset_file.exists()


def test_telegram_offset_advances_after_success_and_filtered_updates(tmp_path, monkeypatch):
    offset_file = tmp_path / "offset.json"

    monkeypatch.setattr(
        pet_telegram_relay,
        "_telegram_api",
        lambda *a, **kw: {
            "ok": True,
            "result": [
                {
                    "update_id": 50,
                    "message": {
                        "text": "filtered",
                        "chat": {"id": 999},
                    },
                },
                {
                    "update_id": 51,
                    "message": {
                        "text": "delivered",
                        "chat": {"id": 12345},
                    },
                },
            ],
        },
    )
    monkeypatch.setattr(pet_telegram_relay, "post_pet_event_now", lambda *a, **kw: True)

    sent = poll_telegram_once(
        bot_token="token",
        chat_id="12345",
        offset_path=str(offset_file),
    )

    assert sent == 1
    assert json.loads(offset_file.read_text())["offset"] == 52
