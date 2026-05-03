# Hermes Pet

> **macOS only MVP.** Hermes Pet currently ships the native desktop pet for
> macOS only. Windows and Linux renderers are planned as separate future
> targets; this release does not provide equivalent Windows/Linux desktop
> overlay behavior.

Desktop companion pet for Hermes Agent. Hermes Pet lives on your macOS screen, reacts to local Hermes CLI/TUI activity, shows persistent notifications for waiting/done states, and can swap animated artwork from Codex Pet Share.

Language versions:

- [English](README.md)
- [한국어](docs/i18n/README.ko.md)
- [简体中文](docs/i18n/README.zh.md)
- [日本語](docs/i18n/README.ja.md)

## What It Is

Hermes Pet is a native desktop overlay for Hermes Agent. It is not a browser widget and not a web dashboard mascot. It runs as a transparent always-on-top macOS panel, similar in spirit to the Codex Desktop pet, and is controlled by the `hermes pet` command family.

The current MVP has two runtime layers:

1. Core runtime: `hermes pet`, native macOS helper, localhost event inlet, session registry, artwork importer, LaunchAgent support.
2. Skill wrapper: `skills/productivity/hermes-pet`, a Hermes skill that tells the agent how to start, stop, restart, install, inspect, and customize the pet safely.

The product direction is update-safe: the long-term desktop pet lives as a
separate macOS app, and Hermes support becomes a thin connector/skill/wrapper
that can be removed without patching upstream Hermes source files. See
[`docs/architecture/hermes-pet-architecture.md`](docs/architecture/hermes-pet-architecture.md)
and the app scaffold in [`apps/macos/HermesPet`](apps/macos/HermesPet).

Hermes Pet is localhost-only in this macOS MVP:

```bash
hermes pet --background --port 8768
```

## Features

- Native macOS desktop pet using AppKit `NSPanel`
- Localhost event inlet for Hermes CLI/TUI events
- Active and recent Hermes session menu
- Left-click focus for active CLI/TUI sessions
- Right-click menu for launching CLI/TUI, sessions, settings, artwork, runtime management, notifications, and quit
- Local desktop pet rendering and session-aware state updates
- Persistent notification badges for waiting and done states
- Codex-style animation mapping: idle, running-left, running-right, waiting, running, review, failed, waving, jumping
- Codex Pet Share artwork import and local artwork library
- Korean, English, Japanese, and Chinese native UI labels
- macOS LaunchAgent install/start/stop/status commands
- Skill wrapper and helper script for easy natural-language management

## Requirements

- macOS for the native screen pet
- macOS
- Apple Command Line Tools (`git`, `swiftc`, and system build tools)
- Python 3.11 or newer
- Internet access for first install and optional Codex Pet Share artwork downloads
- Optional: cmux, only if you want Hermes sessions opened/focused through cmux

The installer creates a project `venv/` and installs this repository's base
Hermes Agent runtime package from `pyproject.toml`. That footprint is currently
needed when the pet launches Hermes CLI/TUI sessions from this checkout so those
sessions include the pet event hooks. Optional extras such as messaging,
dashboard, voice, platform connectors, and third-party terminal integrations
are not installed by the macOS Pet connector.

The current MVP is macOS-first. The Tk fallback exists for basic development fallback, but the intended user experience is the native macOS overlay.

## Quick Start

One-command install and start from a fresh macOS machine with Hermes:

```bash
INSTALLER=/tmp/hermes-pet-install-from-git.sh
curl -fsSL https://raw.githubusercontent.com/ktkarchive/taiei-hermes-pet/main/connectors/hermes/install-from-git.sh -o "$INSTALLER"
bash "$INSTALLER"
```

Or clone manually:

```bash
git clone https://github.com/ktkarchive/taiei-hermes-pet.git
cd taiei-hermes-pet
bash connectors/hermes/install.sh
hermes-pet --background --port 8768
```

Check status:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

Restart:

```bash
hermes-pet --restart --port 8768
```

Stop:

```bash
hermes-pet --stop
```

## Ask Hermes To Install It

Copy this prompt into an existing Hermes CLI/TUI session on macOS:

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository's connectors/hermes/install-from-git.sh installer, start the
local desktop pet on port 8768, then verify status, health, and the installed
hermes-pet skill doctor. Do not modify my global hermes command.
```

Hermes should run the same installer shown in Quick Start. The installer clones
or fast-forwards the repo under `~/.hermes/pet/taiei-hermes-pet`, bootstraps
`venv/` if needed, installs the removable skill/wrapper connector, starts the
pet, and leaves the upstream Hermes command untouched.

## Using the Hermes Skill Wrapper

This repository includes a bundled skill:

```text
skills/productivity/hermes-pet/SKILL.md
```

For the Hermes-specific MVP, install or update the connector without changing
the global `hermes` command:

```bash
bash connectors/hermes/install.sh
```

This installs `~/.local/bin/hermes-pet` and
`~/.hermes/skills/productivity/hermes-pet`, with the skill pinned to this
workspace through `.project-root`.
If `venv/bin/python3` is missing in a fresh clone, the installer bootstraps it
with `python3 -m venv venv` and `venv/bin/python3 -m pip install .`. Use
`--no-bootstrap` if you want to prepare the virtualenv manually, or set
`HERMES_PET_EDITABLE_INSTALL=1` for local development.

After Hermes syncs bundled skills to `~/.hermes/skills`, the agent can load the `hermes-pet` skill and manage the pet with natural-language requests such as:

- "Start Hermes Pet."
- "Restart the desktop pet."
- "Install Hermes Pet as a login item."
- "Search pet artwork for pixel cats."
- "Show current pet sessions."

The skill includes a helper:

```bash
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" status
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" start
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" restart
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" stop
```

Manual helper usage from the repo:

```bash
bash skills/productivity/hermes-pet/scripts/petctl.sh status
bash skills/productivity/hermes-pet/scripts/petctl.sh start
bash skills/productivity/hermes-pet/scripts/petctl.sh restart
```

Diagnose an installed connector:

```bash
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

### Install, Update, And Remove

Install or update the Hermes-specific distribution:

```bash
bash connectors/hermes/install.sh
```

This command is intentionally narrow:

- bootstraps `venv/` when needed;
- installs `~/.local/bin/hermes-pet`;
- installs `~/.hermes/skills/productivity/hermes-pet`;
- writes `.project-root` so the skill points back to this workspace;
- does not repoint or replace the user's global `hermes` command.

Verify after install:

```bash
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

Remove the connector:

```bash
bash connectors/hermes/uninstall.sh
```

Remove connector plus pet runtime/cache files:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

The uninstaller stops the running pet by default, unloads/removes
`ai.hermes.pet*.plist` LaunchAgents when present, then removes only the
standalone `hermes-pet` wrapper, installed skill, and known Hermes Pet runtime
files. It does not remove Hermes Agent itself.

## CLI Reference

### Runtime

```bash
hermes pet --status
hermes pet --background --port 8768
hermes pet --restart --port 8768
hermes pet --stop
```

`--background` replaces an existing pet process if one is already running.

### Local Sessions

```bash
hermes pet --sessions
```

The native right-click menu shows active and recent CLI/TUI sessions. Active sessions get a green dot. Left-clicking the pet focuses the active session when possible.

### Login Item

Install Hermes Pet as a macOS LaunchAgent:

```bash
hermes pet --install-launch-agent --port 8768 --force
```

Check:

```bash
hermes pet --launch-agent-status
```

Start/stop without removing the plist:

```bash
hermes pet --start-launch-agent
hermes pet --stop-launch-agent
```

Remove:

```bash
hermes pet --uninstall-launch-agent
```

The LaunchAgent plist is written under:

```text
~/Library/LaunchAgents/ai.hermes.pet.plist
```

### Artwork

Hermes Pet can use the bundled Hermes artwork or import animated pets from
[Codex Pet Share](https://codex-pet-share.pages.dev/), a public pixel companion
catalog. Imported entries are converted into Hermes Pet's local animation
format and stored under the Hermes runtime directory.

List and search Codex Pet Share:

```bash
hermes pet --share-list
hermes pet --share-search "pixel"
hermes pet --share-search "robot"
```

Apply artwork:

```bash
hermes pet --share-apply "<pet-id-or-url>" --size 84
```

The identifier may be a share pet id or a Codex Pet Share URL. After applying,
restart the pet if it is already running:

```bash
hermes pet --restart --port 8768
```

Inspect current and saved artwork:

```bash
hermes pet --share-current
hermes pet --share-installed
```

Use a saved local artwork entry:

```bash
hermes pet --share-use-installed "<asset-id>"
```

Return to bundled Hermes artwork:

```bash
hermes pet --share-clear
```

In the native right-click menu, use `Pet Artwork` to search Codex Pet Share,
apply a result, open the share site, switch to recent local artwork, or return
to the bundled Hermes art.

Imported artwork remains local to this Mac. If an artwork entry was created by
another community member on Codex Pet Share, keep their title/author metadata
visible when redistributing screenshots or demos.

## Right-Click Menu

The native pet menu currently includes:

- Hermes Mode: CLI and TUI only for MVP
- Active Sessions: focus or open local CLI/TUI sessions
- Pet Artwork: search/apply Codex Pet Share artwork, open the share site, use recent artwork
- Settings: language, terminal launcher, left-click behavior, session list count
- Pet Runtime: restart the pet and manage the macOS login item
- Clear Notifications
- Quit Hermes Pet

## Notifications

Hermes Pet uses badges for agent states:

- `!`: waiting for input, approval, clarification, or failed state
- `1`: completed response/review notification

Notifications persist until the pet is clicked or cleared. This matches the expectation that a completed response should remain visible until the user acknowledges it.

## Animation Behavior

Hermes Pet follows Codex-style animation mapping where possible:

- Idle: idle/blink loop
- Drag left/right: running-left or running-right
- Hover: jumping
- Tool/runtime activity: running
- Waiting for input: waiting
- Completion/review: review, then idle
- Failure: failed, then idle

Imported Codex Pet Share spritesheets provide rows for idle, running-right, running-left, waving, jumping, failed, waiting, running, and review.

## Safety Model

- Local CLI/TUI mode binds to `127.0.0.1` by default.
- The public macOS MVP installer does not require private-network or chat-relay
  tooling.
- Runtime state files are written with private user-only permissions where they
  contain process or session metadata.
- LaunchAgent install/remove is a persistent local setting and should be user-approved.

## Development

Run focused checks:

```bash
venv/bin/python3 -m py_compile hermes_cli/main.py hermes_cli/pet_overlay.py tests/hermes_cli/test_pet_overlay.py
/usr/bin/swiftc hermes_cli/assets/hermes_pet_macos.swift -o /tmp/hermes_pet_macos_test
venv/bin/python3 -m pytest -q tests/hermes_cli/test_pet_overlay.py tests/hermes_cli/test_pet_sessions.py
```

Run the broader pet regression set:

```bash
venv/bin/python3 -m pytest -q \
  tests/hermes_cli/test_pet_sessions.py \
  tests/hermes_cli/test_pet_overlay.py \
  tests/hermes_cli/test_pet_forwarder.py \
  tests/hermes_cli/test_pet_share.py
```

Check formatting hazards:

```bash
git diff --check
```

Run the full Hermes Pet release gate:

```bash
bash connectors/hermes/release-check.sh
```

The release gate checks shell syntax, Python imports, focused pet regressions,
web/dashboard safety tests, the native AppKit helper build, the SwiftPM app
scaffold, `git diff --check`, and installed `hermes-pet --status`.

For the full publish checklist, see
[`docs/release/hermes-distribution-checklist.md`](docs/release/hermes-distribution-checklist.md).

## Packaging Direction

Hermes Pet now has two parallel distribution tracks:

1. Hermes-specific package: skill/wrapper plus `hermes pet ...` compatibility commands for existing Hermes users.
2. Universal macOS app: future signed `.dmg` with status-bar controls, connector selection, independent login item management, and support for Hermes/OpenClaw/Codex/Claude Code/Kimi-style connectors.

The default install target should not modify upstream Hermes source files. The
existing in-repo Hermes hooks remain useful for MVP validation and local
development, but the user-facing package should converge on the universal app
plus a removable Hermes connector.

Hermes connector install/update:

```bash
bash connectors/hermes/install.sh
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

Hermes connector removal:

```bash
hermes-pet --uninstall-launch-agent
bash connectors/hermes/uninstall.sh --purge-runtime
```

The connector installer/remover only uses the default skill and wrapper paths
unless `HERMES_PET_ALLOW_CUSTOM_INSTALL=1` is set. It still refuses dangerous
targets such as `$HOME`, `/`, `/tmp`, or paths that do not end in
`hermes-pet`.

Hermes connector release gate:

```bash
bash connectors/hermes/release-check.sh
```

## References

- Hermes Agent upstream: https://github.com/NousResearch/hermes-agent
- Codex Pet Share catalog: https://codex-pet-share.pages.dev/
- Notice and attribution: [NOTICE.md](NOTICE.md)

## Acknowledgements

Hermes Pet builds on Hermes Agent from Nous Research and keeps the Hermes
connector removable so upstream Hermes can keep updating cleanly. The animated
pet import workflow is made possible by Codex Pet Share and its community pet
artwork catalog; thank you to the site maintainers and artists who publish pets
there. The animation state mapping and desktop-pet behavior are inspired by the
Codex Desktop pet experience.

## License

MIT. See [LICENSE](LICENSE).
