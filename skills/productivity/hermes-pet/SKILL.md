---
name: hermes-pet
description: Manage the desktop Hermes Pet companion. Start, stop, restart, install the macOS login item, inspect active CLI/TUI sessions, and apply Codex Pet Share artwork.
version: 1.0.0
author: Taiei
license: MIT
platforms: [macos]
prerequisites:
  commands: [hermes, curl]
metadata:
  hermes:
    tags: [productivity, desktop-companion, pet, macos, cli, tui, launch-agent, codex-pet-share]
    requires_toolsets: [terminal]
---

# Hermes Pet

Use this skill when the user asks to manage the desktop Hermes Pet companion:

- start, stop, restart, or check the pet
- make the pet start at login
- connect the pet to local Hermes CLI/TUI sessions
- inspect active/recent pet sessions
- change pet artwork from Codex Pet Share

The pet is a native screen overlay. It should live on the user's desktop, not inside a browser.

## Operating Model

Keep local MVP usage localhost-only:

```bash
hermes pet --background --port 8768
```

The public macOS MVP does not require network forwarding tools. Keep the
desktop pet on `127.0.0.1`.

## Helper

If this skill is loaded from a standard Hermes skill directory, prefer the helper script:

```bash
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" status
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" start
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" restart
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" stop
```

The helper uses `HERMES_PET_PORT` when set; otherwise it defaults to `8768`.
If `HERMES_PET_PROJECT_ROOT` is set, or if the installed skill directory
contains a `.project-root` file, the helper runs that workspace's
`venv/bin/python3 -m hermes_cli.main pet` instead of the global `hermes`
command. This keeps the Hermes Pet connector pinned to the installed pet
workspace without changing the user's upstream Hermes command.

## Quick Reference

| User intent | Command |
|---|---|
| Check whether the pet is running | `hermes pet --status` |
| Start local pet in background | `hermes pet --background --port 8768` |
| Restart local pet | `hermes pet --restart --port 8768` |
| Stop pet | `hermes pet --stop` |
| Health check | `curl -fsS http://127.0.0.1:8768/health` |
| List active/recent CLI/TUI sessions | `hermes pet --sessions` |
| Check login item | `hermes pet --launch-agent-status` |
| Install login item | `hermes pet --install-launch-agent --port 8768 --force` |
| Start installed login item | `hermes pet --start-launch-agent` |
| Stop installed login item | `hermes pet --stop-launch-agent` |
| Remove login item | `hermes pet --uninstall-launch-agent` |
| List saved artwork | `hermes pet --share-installed` |
| Search artwork | `hermes pet --share-search "<query>"` |
| Apply artwork | `hermes pet --share-apply "<pet-id-or-url>" --size 84` |
| Return to bundled artwork | `hermes pet --share-clear` |
| Diagnose installed connector | `bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" doctor` |

## Install / Update

For the Hermes-specific MVP connector, install or update from the pet workspace
instead of repointing the user's global `hermes` command:

```bash
bash connectors/hermes/install.sh
```

This installs `~/.local/bin/hermes-pet` and the `hermes-pet` skill wrapper, then
pins the skill to the current workspace using `.project-root`.
The installer intentionally refuses custom destructive paths unless
`HERMES_PET_ALLOW_CUSTOM_INSTALL=1` is set.

To remove the connector:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

Removal unloads/removes the Hermes Pet LaunchAgent first, then removes the
standalone wrapper, installed skill, and known pet runtime/cache files. It must
not remove or repoint the global `hermes` command.

## Procedure

1. Start by checking current status:

   ```bash
   hermes pet --status
   ```

2. If the user wants the pet running locally, use:

   ```bash
   hermes pet --background --port 8768
   ```

   If a pet is already running, this replaces it.

3. If the user asks to refresh, reload, or restart the pet, use:

   ```bash
   hermes pet --restart --port 8768
   ```

4. Verify the runtime:

   ```bash
   hermes pet --status
   curl -fsS http://127.0.0.1:8768/health
   ```

5. If the user asks for automatic startup, explain that this installs a macOS LaunchAgent login item. Only proceed after the user's explicit approval for this persistent local setting:

   ```bash
   hermes pet --install-launch-agent --port 8768 --force
   hermes pet --launch-agent-status
   ```

## Right-Click Menu

The native pet right-click menu includes:

- Hermes Mode: launch/focus CLI or TUI
- Active Sessions: focus or open recent CLI/TUI sessions
- Pet Artwork: search/apply Codex Pet Share artwork and switch recent local artwork
- Settings: language, left-click terminal fallback, terminal launcher, session list count
- Pet Runtime: restart the pet and manage the macOS login item
- Clear Notifications / Quit

If the user quits the pet from the right-click menu, restart it with:

```bash
hermes pet --background --port 8768
```

or, if using the login item:

```bash
hermes pet --start-launch-agent
```

## Artwork

Hermes Pet can import animation sheets from Codex Pet Share:

- Site: https://codex-pet-share.pages.dev/
- In-app menu: right-click the pet -> Pet Artwork
- CLI:

```bash
hermes pet --share-list
hermes pet --share-search "pixel"
hermes pet --share-apply "<pet-id-or-url>" --size 84
hermes pet --share-installed
hermes pet --share-use-installed "<asset-id>"
```

## Safety Rules

- Do not bind to non-localhost for local-only usage.
- Do not install, remove, start, or stop the LaunchAgent unless the user explicitly asks for startup management.

## Verification

After changes, report:

- `hermes pet --status`
- health endpoint result
- whether the URL is localhost
- any LaunchAgent status if startup management was touched
- any artwork id if artwork was changed
