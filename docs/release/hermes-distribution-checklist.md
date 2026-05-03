# Hermes Pet Distribution Checklist

Use this checklist before publishing the Hermes-specific MVP distribution.

## Repository

- Confirm the public release remote points to
  `https://github.com/ktkarchive/taiei-hermes-pet.git`.
- Do not push directly to `NousResearch/hermes-agent`.
- Publish from a clean release branch or orphan initial commit, and make that
  public branch `main` unless `connectors/hermes/install-from-git.sh` and docs
  are intentionally changed to another branch. This workspace started as a
  Hermes Agent checkout, so pushing the current local history directly would
  expose the full upstream/development history rather than a focused Hermes Pet
  release.
- Keep local-only artifacts out of the public repo:
  - `output/`
  - `.harness/`
  - `work_status.md`
  - `reviewed_kimi.md`
  - `venv/`
  - runtime logs, tokens, and screenshots
- Confirm `LICENSE` still reflects the upstream MIT license.

## Install / Update

```bash
bash connectors/hermes/install.sh
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

Expected:

- fresh clones can bootstrap `venv/` through the installer;
- global `hermes` command remains unchanged;
- `~/.local/bin/hermes-pet` exists;
- `~/.hermes/skills/productivity/hermes-pet/.project-root` points to the release workspace;
- live local pet binds to `127.0.0.1:8768`.
- no public install or README path requires private-network relay tools.

## Runtime

```bash
hermes-pet --background --port 8768
curl -fsS http://127.0.0.1:8768/health
hermes-pet --relay-test --relay-test-message release-check
```

Expected:

- health returns `{"ok":true,"name":"hermes-pet"}`;
- relay-test shows a desktop notification badge;
- `~/.hermes/runtime/pet_overlay.json` is `0600`;
- no token appears in `ps` command output.

## Public Surface

```bash
bash connectors/hermes/release-check.sh
```

Expected:

- public docs do not describe private-network relay setup;
- public `hermes-pet --help` only shows local macOS pet commands.

## Artwork

```bash
hermes-pet --share-list
hermes-pet --share-search "pixel"
hermes-pet --share-current
hermes-pet --share-installed
```

Expected:

- Codex Pet Share catalog is reachable;
- applied pets convert to local animation frames;
- right-click `Pet Artwork` can search/apply/open the share site;
- docs credit Codex Pet Share and community artists.

## Release Gate

```bash
bash connectors/hermes/release-check.sh
```

This must pass before publishing. It covers:

- shell syntax;
- Python imports;
- focused Hermes Pet regression tests;
- web/dashboard safety tests;
- AppKit helper compile;
- SwiftPM app scaffold build;
- `git diff --check`;
- installed `hermes-pet --status`.

## Uninstall

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

Expected:

- live pet stops;
- `ai.hermes.pet*.plist` LaunchAgents are unloaded/removed when present;
- `~/.local/bin/hermes-pet` is removed;
- `~/.hermes/skills/productivity/hermes-pet` is removed;
- global `hermes` command remains intact.

Reinstall after uninstall testing if continuing local development.
