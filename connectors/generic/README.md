# Generic CLI Connector

This is the template track for non-Hermes local agents such as OpenClaw, Codex,
Claude Code, Kimi CLI, or custom command-line runtimes.

## Expected Inputs

- command to launch;
- optional process/session discovery rule;
- optional terminal target;
- event parser, log watcher, or adapter script;
- source label and artwork mapping.

## Output

Every connector posts the same `hermes-pet.v1` payload to the local desktop app
relay. The renderer should not need source-specific conditionals beyond artwork
or menu labels.

## Initial Connector Classes

| Connector | Local | Online | Notes |
|---|---:|---:|---|
| OpenClaw | yes | later | Treat as its own connector. Do not reuse Hermes session registry assumptions unless OpenClaw exposes compatible metadata. |
| Codex CLI | yes | no MVP | Prefer structured logs/events if available; otherwise map process lifecycle to idle/running/review/failed. |
| Kimi CLI | yes | no MVP | Same generic CLI path; avoid brittle prompt parsing where possible. |
| Claude Code CLI | yes | no MVP | Launch/focus is feasible, but state fidelity depends on supported output hooks. |
| opencode CLI | yes | no MVP | Same generic command connector; confirm structured output before claiming rich states. |

## Generic CLI State Mapping

Use conservative defaults until a connector has a structured event source:

- process started: `running`;
- prompt/input wait detected: `waiting`;
- process exit 0 or known completion marker: `review`;
- non-zero exit or known error marker: `failed`;
- stale heartbeat: `idle` or disconnected.

Do not parse secrets, full transcripts, or customer content into pet events.
