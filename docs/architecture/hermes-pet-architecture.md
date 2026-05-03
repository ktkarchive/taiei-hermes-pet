# Hermes Pet Architecture

## Product Tracks

Hermes Pet should support two parallel tracks:

1. Hermes-specific package:
   - installed as a Hermes skill/wrapper;
   - starts, stops, and configures the desktop pet;
   - launches Hermes CLI/TUI with relay env vars;
   - does not patch upstream Hermes source files for normal installation.

2. Universal desktop app:
   - distributed as a macOS app/DMG;
   - lives independently of Hermes;
   - supports connector selection for Hermes, OpenClaw, Codex, Claude Code,
     Kimi CLI, SSH, Telegram, and other agents over the same event protocol.

The universal app is the long-term owner of rendering, menu bar state, artwork,
multi-pet layout, login item management, and update delivery.

## Update-Safe Rule

The default install path must not modify Hermes upstream files. Patching Hermes
source is forbidden for production distribution. Anything that touches Hermes
internals is treated as a development shim for local MVP validation and must not
be required by the user-facing installer.

Allowed stable integration paths:

- shell wrapper around `hermes` / `hermes --tui`;
- Hermes skill that starts the pet and prints/sets relay env vars;
- process/session discovery from outside Hermes;
- local HTTP relay on `127.0.0.1`;
- opt-in Tailscale/SSH relay with explicit token handling.

Forbidden for production install paths:

- patching `cli.py`, `hermes_cli/main.py`, or TUI gateway source;
- editing Hermes global prompts/config in place;
- requiring a forked Hermes checkout.

## Shared Protocol

Python contract: `hermes_pet.protocol`

Key fields:

- `protocol`: `hermes-pet.v1`
- `source_id`: stable connector/session identity
- `label`: display name
- `state`: `idle`, `running`, `waiting`, `failed`, `review`
- `message`: short status text
- `animation`: Codex Pet Share animation row hint
- `pet_action`: action semantic
- `emotion`: optional mood hint
- `notification_count`, `notification_kind`, `notification_label`
- `pet_asset_id`: optional source-specific artwork
- `ttl_ms`: expiry for transient state

Relay defaults:

- URL: runtime file or `HERMES_PET_RELAY_URL`
- Token: runtime file or `HERMES_PET_RELAY_TOKEN`
- Header: `X-Hermes-Pet-Relay-Token`

### Versioning

Receivers must accept `hermes-pet.v1` payloads. Unknown or missing protocol
versions should be treated as v1 only when the payload validates against the v1
field set; otherwise they should be rejected or ignored without crashing. A v2
protocol should add a new constant and an explicit compatibility note before any
connector starts sending it.

## Runtime Ownership

Current MVP:

- Python overlay owns runtime file, token file, preferences, and LaunchAgent
  commands.
- Swift AppKit helper owns the visible floating desktop pet.

Target app:

- macOS app owns the runtime file, token, preferences, status item, login item,
  connector manager, and renderer.
- Hermes connector only discovers the runtime and posts events.

## Connector Model

Each connector should implement:

- discovery: is the target app/CLI/session present?
- launch: open target mode if user selects it;
- focus: bring existing session forward when possible;
- event mapping: convert source-specific events to `hermes-pet.v1`;
- identity: stable `source_id`, label, mode, and optional terminal metadata;
- cleanup: remove stale source state without deleting other pets.

Hermes connector MVP status:

- Implemented: CLI mode launch/focus through macOS Terminal or cmux.
- Implemented: TUI mode launch/focus through macOS Terminal or cmux.
- Implemented: localhost relay and token-protected event posting.
- Planned/internal: SSH/Telegram, hidden from MVP menu and retained as future
  connector code.

## Packaging Direction

Short term:

- keep Hermes-specific skill for easy local install;
- keep Python overlay command for fast iteration;
- add universal macOS app scaffold and migrate renderer behavior gradually.

Medium term:

- move mature AppKit renderer from helper into `apps/macos/HermesPet`;
- expose connector preferences in the app status menu;
- package the Hermes connector as a removable skill/wrapper;
- produce signed DMG once the app target owns runtime and login item behavior.

Long term:

- make connector packs independent: Hermes, OpenClaw, Codex, Claude Code, Kimi,
  generic local command, SSH, and bot relays.
- keep the shared protocol backward compatible by versioning payloads.
