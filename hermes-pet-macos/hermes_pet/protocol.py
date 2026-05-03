"""Shared Hermes Pet wire protocol and payload normalization.

This module is deliberately free of Hermes CLI/runtime side effects so the
desktop companion app, Hermes connector, and relay adapters can share one event
contract without importing the overlay renderer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

PROTOCOL_VERSION = "hermes-pet.v1"

PET_RELAY_HEADER_NAME = "X-Hermes-Pet-Relay-Token"
PET_RELAY_TOKEN_ENV = "HERMES_PET_RELAY_TOKEN"
PET_RELAY_URL_ENV = "HERMES_PET_RELAY_URL"
PET_SOURCE_ID_ENV = "HERMES_PET_SOURCE_ID"
PET_LABEL_ENV = "HERMES_PET_LABEL"
PET_ASSET_ID_ENV = "HERMES_PET_ASSET_ID"

PET_STATES = frozenset({"idle", "running", "waiting", "failed", "review"})
PET_ACTIONS = frozenset({"update", "remove", "clear", "ack"})
SUPPORTED_PET_LANGUAGES = frozenset({"ko", "en", "ja", "zh"})

LOCAL_SOURCE_ID = "local-hermes"
RUNTIME_FILENAME = "pet_overlay.json"
RELAY_TOKEN_FILENAME = "pet_relay_token"
PET_PREFERENCES_FILENAME = "pet_preferences.json"
CMUX_SESSION_MAP_FILENAME = "pet_cmux_sessions.json"

__all__ = [
    "CMUX_SESSION_MAP_FILENAME",
    "LOCAL_SOURCE_ID",
    "PET_ACTIONS",
    "PET_ASSET_ID_ENV",
    "PET_LABEL_ENV",
    "PET_PREFERENCES_FILENAME",
    "PET_RELAY_HEADER_NAME",
    "PET_RELAY_TOKEN_ENV",
    "PET_RELAY_URL_ENV",
    "PET_SOURCE_ID_ENV",
    "PET_STATES",
    "PROTOCOL_VERSION",
    "RELAY_TOKEN_FILENAME",
    "RUNTIME_FILENAME",
    "SUPPORTED_PET_LANGUAGES",
    "PetEvent",
    "PetViewState",
    "clean_notification_count",
    "clean_optional_token",
    "clean_source_id",
    "clean_text",
    "default_notification_kind",
    "default_notification_label",
    "is_loopback_host",
    "normalize_event",
    "runtime_url",
]


@dataclass
class PetEvent:
    source_id: str
    label: str
    state: str
    message: str
    action: str = "update"
    ttl_ms: Optional[int] = None
    animation: Optional[str] = None
    direction: Optional[str] = None
    pet_action: Optional[str] = None
    emotion: Optional[str] = None
    asset_id: Optional[str] = None
    notification_count: int = 0
    notification_kind: Optional[str] = None
    notification_label: Optional[str] = None
    updated_at: float = field(default_factory=time.time)


@dataclass
class PetViewState:
    source_id: str
    label: str
    state: str
    message: str
    expires_at: Optional[float] = None
    animation: Optional[str] = None
    direction: Optional[str] = None
    pet_action: Optional[str] = None
    emotion: Optional[str] = None
    asset_id: Optional[str] = None
    notification_count: int = 0
    notification_kind: Optional[str] = None
    notification_label: Optional[str] = None
    updated_at: float = field(default_factory=time.time)


def clean_text(value: Any, fallback: str, max_len: int) -> str:
    text = str(value or fallback).strip()
    if not text:
        text = fallback
    return text[:max_len]


def clean_source_id(value: Any, *, fallback: str = "remote") -> str:
    raw = clean_text(value, fallback, 64)
    clean = "".join(
        ch if (ch.isascii() and ch.isalnum()) or ch in "._-" else "-"
        for ch in raw
    )
    return clean.strip("._-")[:64] or fallback


def clean_optional_token(value: Any, max_len: int = 32) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    clean = "".join(
        ch if (ch.isascii() and ch.isalnum()) or ch in "._-" else "-"
        for ch in raw
    )
    clean = clean.strip("._-")[:max_len]
    return clean or None


def clean_notification_count(value: Any, state: str, kind: Optional[str]) -> int:
    if value is not None:
        try:
            return max(0, min(int(value), 99))
        except (TypeError, ValueError):
            return 0
    if kind:
        return 1
    if state in {"waiting", "failed", "review"}:
        return 1
    return 0


def default_notification_kind(state: str, raw_kind: Any) -> Optional[str]:
    kind = clean_optional_token(raw_kind, 24)
    if kind:
        return kind
    if state == "waiting":
        return "choice"
    if state == "failed":
        return "failed"
    if state == "review":
        return "done"
    return None


def default_notification_label(
    state: str,
    kind: Optional[str],
    raw_label: Any,
) -> Optional[str]:
    if raw_label is not None:
        label = str(raw_label).strip()
        return label[:4] if label else None
    if kind in {"choice", "attention", "failed"} or state in {"waiting", "failed"}:
        return "!"
    if kind in {"done", "review"} or state == "review":
        return "1"
    return None


def normalize_event(payload: dict[str, Any], *, require_protocol: bool = False) -> PetEvent:
    protocol = payload.get("protocol")
    if require_protocol and protocol != PROTOCOL_VERSION:
        raise ValueError(f"protocol must be {PROTOCOL_VERSION}")
    if protocol is not None and protocol != PROTOCOL_VERSION:
        raise ValueError(f"protocol must be {PROTOCOL_VERSION}")

    action = clean_text(payload.get("action"), "update", 16).lower()
    if action not in PET_ACTIONS:
        raise ValueError(f"action must be one of {', '.join(sorted(PET_ACTIONS))}")

    state = clean_text(payload.get("state"), "idle", 32).lower()
    if state not in PET_STATES:
        raise ValueError(f"state must be one of {', '.join(sorted(PET_STATES))}")

    ttl_raw = payload.get("ttl_ms")
    ttl_ms: Optional[int]
    if ttl_raw is None:
        ttl_ms = None
    else:
        ttl_ms = max(1_000, min(int(ttl_raw), 600_000))

    source_id = clean_source_id(payload.get("source_id"))
    notification_kind = default_notification_kind(
        state,
        payload.get("notification_kind")
        or payload.get("notificationKind")
        or payload.get("badge_kind")
        or payload.get("badgeKind"),
    )
    notification_count = clean_notification_count(
        payload.get("notification_count")
        or payload.get("notificationCount")
        or payload.get("badge_count")
        or payload.get("badgeCount"),
        state,
        notification_kind,
    )
    notification_label = default_notification_label(
        state,
        notification_kind,
        payload.get("notification_label")
        or payload.get("notificationLabel")
        or payload.get("badge_label")
        or payload.get("badgeLabel"),
    )
    return PetEvent(
        source_id=source_id,
        label=clean_text(payload.get("label"), source_id, 64),
        state=state,
        message=clean_text(
            payload.get("message") or payload.get("event_type"),
            action if action != "update" else state,
            180,
        ),
        action=action,
        ttl_ms=ttl_ms,
        animation=clean_optional_token(payload.get("animation")),
        direction=clean_optional_token(payload.get("direction"), 16),
        pet_action=clean_optional_token(
            payload.get("pet_action") or payload.get("petAction") or payload.get("pose")
        ),
        emotion=clean_optional_token(payload.get("emotion"), 24),
        asset_id=clean_optional_token(
            payload.get("pet_asset_id")
            or payload.get("petAssetId")
            or payload.get("artwork_asset_id")
            or payload.get("artworkAssetId")
            or payload.get("asset_id")
            or payload.get("assetId"),
            96,
        ),
        notification_count=notification_count,
        notification_kind=notification_kind,
        notification_label=notification_label,
    )


def is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def runtime_url(host: str, port: int) -> str:
    visible_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in visible_host and not visible_host.startswith("["):
        visible_host = f"[{visible_host}]"
    return f"http://{visible_host}:{port}/api/pet/events"
