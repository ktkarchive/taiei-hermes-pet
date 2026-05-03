# Hermes Pet Connectors

Connectors are the update-safe integration layer between a desktop pet app and
agent runtimes. They should emit `hermes-pet.v1` events without requiring source
patches to the target agent.

## Connector Contract

Each connector should provide:

- discovery of running sessions or available commands;
- launch and focus actions when the desktop app asks for them;
- event mapping into `hermes_pet.protocol`;
- stable `source_id` and display label;
- cleanup of stale source state.

## Tracks

- `hermes/`: Hermes CLI/TUI skill/wrapper connector.
- `generic/`: template for other local CLI agents.

Future connector packs can be added without changing the renderer.

## Universal App Binding Model

The universal app should bind connectors per pet, not globally. One desktop app
instance may own up to four `PetSlot` records, and each slot can point at a
different connector/session/artwork combination:

- local Hermes CLI session A;
- local Hermes TUI session B;
- generic local CLI command such as Codex, Kimi, Claude Code, or opencode.

Connector packs should expose enough metadata for the app to show a session
picker, but they should not require the app renderer to understand each
agent's internal state.
