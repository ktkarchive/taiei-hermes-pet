# Universal Pet App Roadmap

## Goal

Build a standalone macOS desktop pet app that can run without Hermes, then bind
each pet to Hermes, OpenClaw, Codex CLI, Kimi CLI, Claude Code, opencode, or a
custom command through removable connectors.

The Hermes-specific connector remains the reference integration and should ship
first.

## Feasibility

| Feature | Feasibility | Notes |
|---|---:|---|
| Up to 4 pets on screen | Easy | Multiple transparent `NSPanel` instances are straightforward. Persist one `PetSlot` per pet. |
| Per-pet position | Easy | Store `x`, `y`, and `size` per slot. |
| Per-pet artwork | Easy | The existing Codex Pet Share asset bundles can map per slot. |
| Per-pet Hermes CLI/TUI session binding | Feasible | Existing Hermes session registry already has `session_id`, mode, cwd, terminal metadata, and active state. |
| Two pets bound to two different local Hermes sessions | Feasible | Requires `PetSlot.binding.sessionID` and per-source event routing. |
| Online Hermes through SSH | Feasible but brittle | Prefer relay env/bootstrap over terminal scraping. Requires reconnect/heartbeat and safe token handling. |
| Online Hermes through Telegram | Feasible but should stay later | Requires bot token plus chat id allow-list. Long polling is simple; UX setup and credential storage need care. |
| OpenClaw local/online | Feasible after connector research | Similar class of agent, but should use its own connector rather than Hermes-specific assumptions. |
| Codex/Kimi/Claude/opencode CLI | Feasible as generic local CLI connectors | Launching is easy; reliable state detection depends on structured output, logs, hooks, or conservative heuristics. |
| Focus any existing third-party terminal tab | Hard | macOS automation is app-specific. Terminal/cmux can be supported; arbitrary tabs cannot be guaranteed. |
| Perfect parsing of all CLI states | Hard | ANSI/spinner/human text parsing breaks on updates. Prefer structured event emitters or narrow heuristics. |

## Not Impossible, But Should Be Deferred

- Public Telegram setup UI with credential storage.
- SSH auto-bootstrap that installs remote helpers automatically.
- Discord/Slack connectors.
- Inter-pet interactions.
- App Store sandboxing decisions.
- Fully native replacements for every Python helper.

## App Model

The universal app should separate renderer state from connector state:

- `PetSlot`: user-visible pet instance, capped at 4.
- `PetPlacement`: independent position and size.
- `PetArtworkRef`: current artwork bundle.
- `PetAgentBinding`: connector kind, transport, mode, and optional session id.
- `PetWireEvent`: runtime event sent by connectors.

This lets one app host:

- Pet 1: local Hermes TUI session A.
- Pet 2: local Hermes CLI session B.
- Pet 3: remote Hermes through Tailscale/SSH relay.
- Pet 4: local Codex CLI or Kimi CLI through a generic command connector.

## Phase 1: Hermes Distribution Finish

Deliverable: update-safe Hermes-specific package.

- Keep global `hermes` untouched.
- Install only `~/.local/bin/hermes-pet` and
  `~/.hermes/skills/productivity/hermes-pet`.
- Use localhost by default.
- Keep SSH/Telegram internal in MVP menus.
- Run `connectors/hermes/release-check.sh` before release.
- Keep `work_status.md` and `.harness/runs` current.

## Phase 2: Universal Local App

Deliverable: standalone app with local multi-pet support.

- Move the mature AppKit renderer from `hermes_cli/assets/hermes_pet_macos.swift`
  into `apps/macos/HermesPet`.
- Persist up to 4 `PetSlot` records.
- Add menu-bar controls:
  - add/remove pet;
  - bind connector;
  - choose session;
  - choose artwork;
  - reset position;
  - quit.
- Bind Pet 1-4 independently to local Hermes CLI/TUI sessions.
- Add generic local command connector with conservative state mapping.

## Phase 3: Network And Non-Hermes Connectors

Deliverable: connector packs behind the same `PetAgentBinding` model.

- Hermes SSH relay:
  - explicit Tailscale/local network setup;
  - token file or QR/setup copy flow;
  - heartbeat and reconnect.
- Hermes Telegram relay:
  - bot token reference;
  - chat id allow-list;
  - no “any chat” default.
- OpenClaw local/online:
  - separate connector discovery;
  - no Hermes session registry assumptions.
- Codex/Kimi/Claude/opencode:
  - prefer structured logs/events if available;
  - otherwise use command lifecycle and conservative parsing.

## Release Boundary

The Hermes connector can be released first. The universal app should not claim
full multi-agent support until:

- two local Hermes sessions can be independently bound to two pets;
- each pet can keep a separate artwork bundle and position;
- relays are token-protected and localhost-only by default;
- install/uninstall leaves no LaunchAgent or runtime residue;
- the app builds through SwiftPM and the helper migration no longer depends on
running from the Hermes source checkout.
