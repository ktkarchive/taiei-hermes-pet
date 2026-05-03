"""Telegram-to-Hermes-pet relay.

This is a small one-way adapter: Telegram updates become pet events on the
local screen overlay. It does not send Telegram messages back to users.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from hermes_cli.config import get_hermes_home
from hermes_cli.pet_forwarder import post_pet_event_now

COMMAND_STATES = {
    "/run": "running",
    "/running": "running",
    "/work": "running",
    "/working": "running",
    "/wait": "waiting",
    "/waiting": "waiting",
    "/fail": "failed",
    "/failed": "failed",
    "/error": "failed",
    "/done": "review",
    "/review": "review",
    "/idle": "idle",
}


def _clean_chat_id(value: Any) -> str:
    return str(value or "").strip()


def _message_from_update(update: dict[str, Any]) -> Optional[dict[str, Any]]:
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        value = update.get(key)
        if isinstance(value, dict):
            return value
    return None


def _display_label(message: dict[str, Any], chat: dict[str, Any]) -> str:
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    for value in (
        sender.get("username"),
        sender.get("first_name"),
        chat.get("title"),
        chat.get("username"),
    ):
        if isinstance(value, str) and value.strip():
            return f"Telegram {value.strip()[:48]}"
    chat_id = _clean_chat_id(chat.get("id"))
    return f"Telegram {chat_id[-8:]}" if chat_id else "Telegram"


def telegram_update_to_pet_event(
    update: dict[str, Any],
    *,
    allowed_chat_id: Optional[str] = None,
    allow_any_chat: bool = False,
    default_ttl_ms: int = 60_000,
) -> Optional[dict[str, Any]]:
    message = _message_from_update(update)
    if not message:
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = _clean_chat_id(chat.get("id"))
    if not allowed_chat_id and not allow_any_chat:
        return None
    if allowed_chat_id and chat_id != _clean_chat_id(allowed_chat_id):
        return None

    raw_text = message.get("text") or message.get("caption") or ""
    text = str(raw_text).strip()
    first = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
    action = "update"
    state = COMMAND_STATES.get(first, "review")
    if first == "/clear":
        action = "clear"
        state = "idle"

    if first in COMMAND_STATES or first == "/clear":
        text = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else state
    if not text:
        text = "telegram update"

    return {
        "source_id": f"telegram-{chat_id or 'unknown'}",
        "label": _display_label(message, chat),
        "state": state,
        "message": text[:180],
        "action": action,
        "event_type": "telegram.update",
        "ttl_ms": default_ttl_ms,
    }


def _telegram_api(
    bot_token: str,
    method: str,
    params: dict[str, Any],
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/{method}",
        data=encoded,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(str(payload))
    return payload


def _offset_file(path: Optional[str]) -> Path:
    if path:
        return Path(path).expanduser()
    return get_hermes_home() / "runtime" / "pet_telegram_offset.json"


def _read_offset(path: Path) -> Optional[int]:
    try:
        value = json.loads(path.read_text()).get("offset")
        return int(value)
    except Exception:
        return None


def _write_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"offset": offset}, indent=2))
    tmp.replace(path)


def poll_telegram_once(
    *,
    bot_token: str,
    chat_id: Optional[str] = None,
    allow_any_chat: bool = False,
    relay_url: Optional[str] = None,
    relay_token: Optional[str] = None,
    offset_path: Optional[str] = None,
    default_ttl_ms: int = 60_000,
    timeout: float = 15.0,
) -> int:
    path = _offset_file(offset_path)
    offset = _read_offset(path)
    params: dict[str, Any] = {
        "timeout": 0,
        "allowed_updates": json.dumps(["message", "edited_message", "channel_post", "edited_channel_post"]),
    }
    if offset is not None:
        params["offset"] = offset

    payload = _telegram_api(bot_token, "getUpdates", params, timeout=timeout)
    updates = payload.get("result") if isinstance(payload, dict) else []
    sent = 0
    committed_update_id: Optional[int] = None

    for update in updates if isinstance(updates, list) else []:
        if not isinstance(update, dict):
            continue
        update_id = update.get("update_id")
        event = telegram_update_to_pet_event(
            update,
            allowed_chat_id=chat_id,
            allow_any_chat=allow_any_chat,
            default_ttl_ms=default_ttl_ms,
        )
        if event:
            if not post_pet_event_now(event, url=relay_url, token=relay_token, timeout=min(timeout, 2.0)):
                break
            sent += 1
        if isinstance(update_id, int):
            committed_update_id = update_id

    if committed_update_id is not None:
        _write_offset(path, committed_update_id + 1)
    return sent


def run_telegram_relay(
    *,
    bot_token: str,
    chat_id: Optional[str] = None,
    allow_any_chat: bool = False,
    relay_url: Optional[str] = None,
    relay_token: Optional[str] = None,
    offset_path: Optional[str] = None,
    poll_interval: float = 2.0,
    once: bool = False,
) -> None:
    print("Hermes Pet Telegram relay running. Press Ctrl-C to stop.")
    while True:
        sent = poll_telegram_once(
            bot_token=bot_token,
            chat_id=chat_id,
            allow_any_chat=allow_any_chat,
            relay_url=relay_url,
            relay_token=relay_token,
            offset_path=offset_path,
        )
        if sent:
            print(f"Forwarded {sent} Telegram update(s) to Hermes Pet.")
        if once:
            return
        time.sleep(max(0.5, poll_interval))
