# Taiei Hermes Pet

> **macOS only MVP.** This repository ships the Hermes Pet desktop companion for
> macOS. Windows and Linux desktop renderers are not included in this release.

Taiei Hermes Pet is distributed as a removable Hermes Pet package. It installs a
standalone `hermes-pet` command and a Hermes skill wrapper, without modifying
the user's global `hermes` command or Hermes checkout.

Languages: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh.md) | [日本語](README.ja.md)

## Package

The installable package is in `hermes-pet-macos/`.

## Install

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/install.sh"
```

After install:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

Detailed usage is in [`hermes-pet-macos/README.md`](hermes-pet-macos/README.md).

## Ask Hermes To Install

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository install.sh, start the local macOS desktop pet on port 8768,
then verify hermes-pet --status and http://127.0.0.1:8768/health.
Do not modify the global hermes command.
```

## Credits

Hermes Pet is built for Hermes Agent users and thanks the Codex Pet Share
community at https://codex-pet-share.pages.dev/ for the public pet artwork
sharing site used by the artwork picker/importer.
