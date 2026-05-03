# Hermes Pet Code Review

Date: 2026-05-03

## Review Position

The current MVP proves the desktop pet experience, session menu, artwork import,
and localhost relay. It is not yet update-safe enough to treat as a pure Hermes
plugin because several MVP paths live inside the Hermes package tree and some
runtime events are wired directly from Hermes CLI/TUI modules.

The distribution architecture should move toward a companion app plus thin
connectors. Hermes source patches should become optional development shims, not
the primary install mechanism.

## Findings

### P1: Pet overlay is a god module

`hermes_cli/pet_overlay.py` combines protocol normalization, HTTP relay, token
storage, preferences, session actions, LaunchAgent management, AppKit/Tk
rendering, and native menu command handling. This makes future extraction into a
DMG app harder and increases regression risk when changing unrelated behavior.

Action taken in this pass: shared wire protocol and normalization were moved to
`hermes_pet/protocol.py`, with `hermes_cli/pet_protocol.py` kept as a
compatibility re-export.

### P1: Protocol constants were duplicated

Relay header names, token env vars, and runtime filename were repeated across
overlay, forwarder, and web server paths. A mismatch would break connectors in
ways that are hard to diagnose.

Action taken in this pass: `pet_overlay.py`, `pet_forwarder.py`, and
`web_server.py` now import the shared constants from `pet_protocol.py`.

### P1: Current Hermes integration is not update-safe

The MVP has working hooks inside Hermes CLI/TUI/dashboard paths. That is fine for
local validation, but it is not the structure to ship to users who expect Hermes
updates to apply cleanly.

Recommended boundary: ship the pet as a separate desktop app; ship Hermes support
as a skill/wrapper that starts Hermes with relay environment variables and posts
events through the stable HTTP protocol.

### P2: Native renderer should graduate into its own app target

The AppKit helper has mature behavior, but it is still built and launched by the
Hermes CLI package. The universal product needs its own app target, status-bar
menu, connector manager, update channel, and signing/notarization pipeline.

Action taken in this pass: added `apps/macos/HermesPet` as a compileable app
scaffold.

### P2: Raw dict event contracts need a schema marker

Most pet events are raw dictionaries. That is acceptable for a small relay, but
without a version marker the connector contract becomes ambiguous as OpenClaw,
Codex, Claude Code, Kimi, SSH, or Telegram integrations are added.

Action taken in this pass: outbound connector events and overlay snapshots now
include `protocol: hermes-pet.v1`.

## Kimi Review Mapping

Kimi's repo-wide review called out god modules, broad exception handling, import
side effects, fragmented configuration, and raw dict protocols. For the pet
work, the directly relevant items are:

- Split the pet god module before adding more connector types.
- Pull protocol/schema definitions out of renderer code.
- Keep update-sensitive Hermes hooks thin and replaceable.
- Avoid hiding connector failures once the relay becomes user-facing.

The larger Hermes `run_agent.py` / `cli.py` refactor is out of scope for this
pet productization pass.
