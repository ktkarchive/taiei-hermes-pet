"""Best-effort bridge from local Hermes runtime events to the screen pet."""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from hermes_cli.config import get_hermes_home
from hermes_pet.protocol import (
    LOCAL_SOURCE_ID,
    PET_ASSET_ID_ENV,
    PET_LABEL_ENV,
    PET_RELAY_HEADER_NAME,
    PET_RELAY_TOKEN_ENV,
    PET_RELAY_URL_ENV,
    PET_SOURCE_ID_ENV,
    PROTOCOL_VERSION,
    RUNTIME_FILENAME,
    clean_optional_token,
    clean_source_id,
)

PET_OVERLAY_RUNTIME_FILENAME = RUNTIME_FILENAME
FORWARD_INTERVAL_SECONDS = 0.35

RUNNING_TYPES = frozenset({
    "message.start",
    "message.delta",
    "thinking.delta",
    "reasoning.delta",
    "tool.start",
    "tool.progress",
    "tool.generating",
    "subagent.start",
    "subagent.progress",
    "subagent.tool.start",
    "subagent.tool.progress",
})
WAITING_TYPES = frozenset({
    "approval.request",
    "clarify.request",
    "secret.request",
    "sudo.request",
    "subagent.spawn_requested",
})
FAILED_TYPES = frozenset({
    "error",
    "message.error",
    "tool.error",
    "subagent.error",
})
REVIEW_TYPES = frozenset({
    "message.complete",
    "turn.complete",
    "review.start",
    "review.ready",
})

_queue: queue.Queue[tuple[str, str, dict[str, Any]] | None] = queue.Queue(maxsize=128)
_worker_started = False
_worker_lock = threading.Lock()
_throttle_lock = threading.Lock()
_last_state: str | None = None
_last_forward_at = 0.0


def _clean_source_id(value: str) -> str:
    return clean_source_id(value, fallback="remote-hermes")


def default_pet_source_id() -> str:
    raw = str(os.getenv(PET_SOURCE_ID_ENV) or "").strip()
    if raw:
        return _clean_source_id(raw)
    if os.getenv(PET_RELAY_URL_ENV):
        return _clean_source_id(f"remote-hermes-{socket.gethostname()}")
    return LOCAL_SOURCE_ID


def default_pet_label() -> str:
    raw = str(os.getenv(PET_LABEL_ENV) or "").strip()
    if raw:
        return raw[:64]
    if os.getenv(PET_RELAY_URL_ENV):
        host = socket.gethostname().split(".")[0] or "remote"
        return f"Hermes {host}"[:64]
    return "Hermes Local"


def default_pet_asset_id() -> Optional[str]:
    return clean_optional_token(os.getenv(PET_ASSET_ID_ENV), 96)


def runtime_path() -> Path:
    return get_hermes_home() / "runtime" / PET_OVERLAY_RUNTIME_FILENAME


def _read_env_runtime() -> Optional[dict[str, Any]]:
    url = str(os.getenv(PET_RELAY_URL_ENV) or "").strip()
    token = str(os.getenv(PET_RELAY_TOKEN_ENV) or "").strip()
    if not url or not token:
        return None
    return {
        "url": url,
        "token": token,
        "token_header": PET_RELAY_HEADER_NAME,
        "source": "env",
    }


def _read_runtime() -> Optional[dict[str, Any]]:
    env_runtime = _read_env_runtime()
    if env_runtime:
        return env_runtime

    try:
        data = json.loads(runtime_path().read_text())
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    pid = data.get("pid")
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
        except OSError:
            return None

    url = data.get("url")
    token = data.get("token")
    if not isinstance(url, str) or not isinstance(token, str) or not url or not token:
        return None
    return data


def read_pet_runtime() -> Optional[dict[str, Any]]:
    """Return the active pet runtime descriptor, if a live overlay exists."""
    return _read_runtime()


def post_pet_event_now(
    event: dict[str, Any],
    *,
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 1.0,
) -> bool:
    """Synchronously POST one pet event.

    Local CLI/TUI forwarding uses the throttled background queue below. Relay
    adapters use this direct path so external events are not dropped by local
    activity throttling.
    """
    runtime = None if url and token else _read_runtime()
    target_url = url or (str(runtime.get("url")) if runtime else "")
    target_token = token or (str(runtime.get("token")) if runtime else "")
    if not target_url or not target_token:
        return False

    try:
        data = json.dumps(_with_protocol(event), separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            target_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                PET_RELAY_HEADER_NAME: target_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(128)
        return True
    except Exception:
        return False


def relay_test_event(message: str = "relay test") -> dict[str, Any]:
    event = {
        "protocol": PROTOCOL_VERSION,
        "source_id": default_pet_source_id(),
        "label": default_pet_label(),
        "state": "review",
        "message": message[:180],
        "event_type": "relay.test",
        "animation": "review",
        "pet_action": "done",
        "emotion": "ready",
        "notification_count": 1,
        "notification_kind": "done",
        "notification_label": "1",
        "ttl_ms": 5_000,
    }
    asset_id = default_pet_asset_id()
    if asset_id:
        event["pet_asset_id"] = asset_id
    return event


def run_relay_test(message: str = "relay test", *, timeout: float = 2.0) -> tuple[bool, str]:
    runtime = _read_runtime()
    if not runtime:
        return False, "No Hermes Pet relay runtime found. Set HERMES_PET_RELAY_URL and HERMES_PET_RELAY_TOKEN, or start `hermes pet` locally."
    event = relay_test_event(message)
    ok = post_pet_event_now(
        event,
        url=str(runtime["url"]),
        token=str(runtime["token"]),
        timeout=timeout,
    )
    if ok:
        return True, f"Relay test sent to {runtime['url']} as {event['source_id']}"
    return False, f"Relay test failed to reach {runtime['url']}"


def _with_protocol(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("protocol") == PROTOCOL_VERSION:
        return event
    return {"protocol": PROTOCOL_VERSION, **event}


def _payload_label(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ("name", "tool", "context", "summary", "preview", "message", "error", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:180]
    return None


def _payload_token(payload: Any, *keys: str) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        clean = clean_optional_token(value, 32)
        if clean:
            return clean
    return None


def pet_event_from_gateway_event(
    event_type: str,
    payload: Any = None,
    *,
    source_id: Optional[str] = None,
    label: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    hint = _payload_label(payload)
    resolved_source_id = source_id or default_pet_source_id()
    resolved_label = label or default_pet_label()
    resolved_asset_id = default_pet_asset_id()
    animation = _payload_token(payload, "animation", "pose")
    direction = _payload_token(payload, "direction")
    pet_action = _payload_token(payload, "pet_action", "petAction", "action", "pose")
    emotion = _payload_token(payload, "emotion", "mood")
    notification_kind: Optional[str] = None
    notification_label: Optional[str] = None
    notification_count = 0

    if event_type == "tool.complete":
        has_error = isinstance(payload, dict) and bool(payload.get("error"))
        state = "failed" if has_error else "review"
        message = hint or ("tool failed" if has_error else "tool complete")
        ttl_ms = 8_000 if has_error else 5_000
        animation = animation or ("failed" if has_error else "review")
        emotion = emotion or ("error" if has_error else "done")
        notification_kind = "failed" if has_error else "done"
        notification_label = "!" if has_error else "1"
        notification_count = 1
    elif event_type in RUNNING_TYPES:
        state = "running"
        message = hint or "working"
        ttl_ms = 12_000
        if animation is None:
            animation = "running"
        pet_action = pet_action or "running"
        emotion = emotion or "focused"
    elif event_type in WAITING_TYPES:
        state = "waiting"
        message = hint or "waiting for input"
        ttl_ms = 60_000
        animation = animation or "waiting"
        pet_action = pet_action or "waiting"
        emotion = emotion or "waiting"
        notification_kind = "choice"
        notification_label = "!"
        notification_count = 1
    elif event_type in FAILED_TYPES:
        state = "failed"
        message = hint or "attention needed"
        ttl_ms = 12_000
        animation = animation or "failed"
        emotion = emotion or "error"
        notification_kind = "failed"
        notification_label = "!"
        notification_count = 1
    elif event_type in REVIEW_TYPES:
        status = payload.get("status") if isinstance(payload, dict) else None
        if status in ("error", "failed"):
            state = "failed"
            message = hint or "run failed"
            ttl_ms = 12_000
            animation = animation or "failed"
            emotion = emotion or "error"
            notification_kind = "failed"
            notification_label = "!"
            notification_count = 1
        else:
            state = "review"
            message = hint or "ready to review"
            ttl_ms = 5_000
            animation = animation or "review"
            emotion = emotion or "done"
            notification_kind = "done"
            notification_label = "1"
            notification_count = 1
    else:
        return None

    event = {
        "protocol": PROTOCOL_VERSION,
        "source_id": resolved_source_id,
        "label": resolved_label,
        "state": state,
        "message": message,
        "event_type": event_type,
        "ttl_ms": ttl_ms,
    }
    if animation:
        event["animation"] = animation
    if direction:
        event["direction"] = direction
    if pet_action:
        event["pet_action"] = pet_action
    if emotion:
        event["emotion"] = emotion
    if notification_count:
        event["notification_count"] = notification_count
    if notification_kind:
        event["notification_kind"] = notification_kind
    if notification_label:
        event["notification_label"] = notification_label
    if resolved_asset_id:
        event["pet_asset_id"] = resolved_asset_id
    return event


def pet_event_from_gateway_frame(frame_text: str) -> Optional[dict[str, Any]]:
    try:
        frame = json.loads(frame_text)
    except Exception:
        return None

    if not isinstance(frame, dict) or frame.get("method") != "event":
        return None

    params = frame.get("params")
    if not isinstance(params, dict):
        return None

    event_type = params.get("type")
    if not isinstance(event_type, str):
        return None

    return pet_event_from_gateway_event(event_type, params.get("payload"))


def forward_gateway_frame(frame_text: str) -> None:
    event = pet_event_from_gateway_frame(frame_text)
    if event:
        forward_pet_event(event)


def forward_gateway_event(event_type: str, payload: Any = None) -> None:
    event = pet_event_from_gateway_event(event_type, payload)
    if event:
        forward_pet_event(event)


def forward_pet_event(event: dict[str, Any]) -> None:
    global _last_forward_at, _last_state

    runtime = _read_runtime()
    if not runtime:
        return

    now = time.time()
    event = _with_protocol(event)
    state = str(event.get("state", "idle"))
    with _throttle_lock:
        if state == _last_state and now - _last_forward_at < FORWARD_INTERVAL_SECONDS:
            return
        _last_state = state
        _last_forward_at = now

    _ensure_worker()
    try:
        _queue.put_nowait((str(runtime["url"]), str(runtime["token"]), event))
    except queue.Full:
        pass


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_drain, name="hermes-pet-forwarder", daemon=True)
        thread.start()
        _worker_started = True


def _drain() -> None:
    while True:
        item = _queue.get()
        if item is None:
            return
        url, token, event = item
        try:
            data = json.dumps(event, separators=(",", ":")).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    PET_RELAY_HEADER_NAME: token,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=0.3) as resp:
                resp.read(128)
        except Exception:
            pass
