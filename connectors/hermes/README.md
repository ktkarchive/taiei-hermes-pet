# Hermes Connector

> **macOS only MVP.** This connector installs the native macOS desktop pet.
> Windows/Linux desktop overlays are future targets and are not included in this
> release.

The Hermes connector is the Hermes-specific package for Hermes Pet. It should be
installable as a skill/wrapper and should not modify upstream Hermes source files
in the default user path.

## Responsibilities

- Start or focus Hermes CLI/TUI.
- Pass local pet environment to Hermes sessions launched by the connector.
- Convert Hermes session/tool/waiting/done/error events to `hermes-pet.v1`.
- Keep active/recent session metadata for the pet menu.
- Install a standalone `hermes-pet` command that can run the pet workspace
  without repointing the user's global `hermes` command.

## Current MVP Compatibility

The repository still includes in-Hermes hooks used to prove the MVP behavior.
Those hooks are treated as development shims. The productized Hermes connector
should converge on wrappers and stable relay env vars so Hermes can update
without merge conflicts.

## Install

One-command public install on macOS:

```bash
INSTALLER=/tmp/hermes-pet-install-from-git.sh
curl -fsSL https://raw.githubusercontent.com/ktkarchive/taiei-hermes-pet/main/connectors/hermes/install-from-git.sh -o "$INSTALLER"
bash "$INSTALLER"
```

From this repository:

```bash
bash connectors/hermes/install.sh
```

This installs:

- `~/.local/bin/hermes-pet`
- `~/.hermes/skills/productivity/hermes-pet`
- `~/.hermes/skills/productivity/hermes-pet/.project-root`

It does not modify `~/.local/bin/hermes` or the upstream Hermes checkout.
By default the installer only writes the standard paths above. Custom paths
require `HERMES_PET_ALLOW_CUSTOM_INSTALL=1`, and destructive targets such as
`$HOME`, `/`, `/tmp`, or paths not ending in `hermes-pet` are rejected.
Fresh clones bootstrap `venv/` automatically unless `--no-bootstrap` is passed.
Production bootstrap uses a normal `pip install .`; set
`HERMES_PET_EDITABLE_INSTALL=1` only for local development.
The macOS MVP installer does not require private-network relay, chat-relay, or
third-party terminal tools. cmux is optional and only used when the user selects
it as a local terminal launcher. The Python bootstrap installs the repository's
base Hermes Agent runtime package so CLI/TUI sessions launched from the pet have
the same pet hooks as the desktop overlay; optional extras such as messaging,
web dashboard, voice, or platform connectors are not installed by this connector.

Verify:

```bash
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

Run the release gate before publishing or tagging:

```bash
bash connectors/hermes/release-check.sh
```

Remove:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

The remover first stops the pet and unloads/removes `ai.hermes.pet*.plist`
LaunchAgents when present. It then removes only the standalone wrapper, the
installed skill, and known Hermes Pet runtime/cache files.

## Local Runtime Default

The public macOS MVP stays on `127.0.0.1:8768`. The one-command installer starts
only the local desktop pet and verifies the local health endpoint.
