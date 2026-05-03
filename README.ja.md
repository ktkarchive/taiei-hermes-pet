# Taiei Hermes Pet

> **macOS-only MVP.** このリポジトリは Hermes Agent 向けの macOS
> デスクトップペットを配布します。Windows/Linux デスクトップ renderer は
> 現在の release には含まれていません。

Taiei Hermes Pet は取り外し可能な Hermes Pet package です。独立した
`hermes-pet` コマンドと Hermes skill wrapper をインストールしますが、ユーザーの
グローバル `hermes` コマンドや Hermes checkout は変更しません。

言語: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh.md) | [日本語](README.ja.md)

## Package

インストール可能な package は `hermes-pet-macos/` にあります。

## インストール

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/install.sh"
```

インストール後の確認:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

詳しい使い方は [`hermes-pet-macos/README.md`](hermes-pet-macos/README.md) と
[`hermes-pet-macos/docs/i18n/README.ja.md`](hermes-pet-macos/docs/i18n/README.ja.md)
を参照してください。

## Hermes にインストールを依頼する

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository install.sh, start the local macOS desktop pet on port 8768,
then verify hermes-pet --status and http://127.0.0.1:8768/health.
Do not modify the global hermes command.
```

## Thanks

Hermes Pet は Hermes Agent ユーザー向けに作られています。ペット artwork の
選択/インポート機能は [Codex Pet Share](https://codex-pet-share.pages.dev/)
コミュニティの公開共有サイトに感謝し、参考にしています。
