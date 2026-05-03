# Hermes Pet macOS App Scaffold

This directory is the update-safe desktop app track. It is intentionally outside
the Hermes CLI package so the pet can ship as a DMG/app bundle without requiring
patches to upstream Hermes.

## Target Shape

- `HermesPetApp`: floating desktop pet plus menu bar controller.
- `PetWireEvent`: shared event schema aligned with `hermes_pet.protocol`.
- `PetSlot`: one independent pet instance. The universal app caps active slots
  at 4 for MVP ergonomics and rendering simplicity.
- `PetAgentBinding`: per-pet connector binding, separate from artwork and
  placement.
- Connector layer:
  - Hermes connector: optional skill/wrapper that posts events to the app.
  - OpenClaw connector: same protocol, different process discovery.
  - Generic CLI connector: watches a configured command/session and emits the
    same pet events.

## Distribution Split

- Hermes-specific distribution: skill/wrapper package for Hermes users.
- Universal distribution: signed/notarized DMG with connector selection.

The universal app should never require modifying Hermes source files. Hermes
integration should be installed as a skill, shell wrapper, or env-based relay
that can be removed cleanly when Hermes updates.

## Current Status

This is a compileable macOS scaffold. The existing MVP renderer still lives in
`hermes_cli/pet_overlay.py`; the next migration step is to move its mature
AppKit helper behavior into this app target and leave Hermes with only a thin
connector.

## Runtime Behavior To Preserve

- If Hermes is not running, the app still shows the floating pet and a
  disconnected status item.
- Each pet has independent position, artwork, notification state, and connector
  binding.
- Connector failures should retry with bounded backoff and never block the UI.
- If a relay/session disappears mid-run, the app should keep the pet alive,
  clear stale source state after TTL expiry, and keep notifications until the
  user acknowledges them.

## Universal MVP Roadmap

1. **Hermes distribution finish:** keep the removable Hermes connector as the
   reference integration and run `connectors/hermes/release-check.sh` before
   publishing.
2. **Local multi-pet app:** move the mature AppKit renderer into this target,
   persist up to 4 `PetSlot` entries, and let each slot bind to one local
   Hermes CLI/TUI session or a generic CLI command.
3. **Connector expansion:** add more local agent connectors behind the same
   `PetAgentBinding` model while keeping credentials outside app logs and
   exported docs.

## Packaging Notes

For a signed DMG, decide sandboxing explicitly. A sandboxed build that connects
to a localhost relay needs the network client entitlement; a build that owns the
local relay listener needs the network server entitlement. The current scaffold
is a development target and does not yet define release entitlements.
