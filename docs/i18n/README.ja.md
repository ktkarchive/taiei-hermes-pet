# Hermes Pet

> **macOS-only MVP.** 現在の Hermes Pet 配布版は macOS ネイティブデスクトップ
> pet のみを提供します。Windows/Linux renderer は将来別 target として拡張
> できますが、この release には同等の Windows/Linux desktop overlay 機能は
> 含まれていません。

Hermes Pet は Hermes Agent 用のデスクトップペットです。ブラウザ内のウィジェットではなく、macOS の画面上に常駐するネイティブ透明オーバーレイとして動きます。ローカル Hermes CLI/TUI の状態に反応し、待機/完了通知を表示し、Codex Pet Share からアニメーションアートワークを取り込めます。

言語:

- [English](../../README.md)
- [한국어](README.ko.md)
- [简体中文](README.zh.md)
- [日本語](README.ja.md)

## 概要

現在の MVP は `hermes pet` コマンド群と `hermes-pet` skill wrapper を使います。長期方針は、Hermes 本体を変更しない独立 macOS アプリと薄い Hermes connector に分けることです。

アーキテクチャ文書:

- [`docs/architecture/hermes-pet-architecture.md`](../architecture/hermes-pet-architecture.md)
- [`apps/macos/HermesPet`](../../apps/macos/HermesPet)

ローカル MVP はデフォルトで localhost のみを使います。

```bash
hermes pet --background --port 8768
```

## 機能

- AppKit `NSPanel` ベースの macOS ネイティブデスクトップペット
- Hermes CLI/TUI イベント用 localhost inlet
- アクティブ/最近の Hermes セッションメニュー
- 左クリックでアクティブ CLI/TUI セッションをフォーカス
- 右クリックメニュー: CLI/TUI、セッション、設定、アートワーク、実行管理、通知、終了
- ローカルデスクトップペット表示とセッション状態への反応
- 待機、完了、失敗の通知バッジ
- Codex Pet Share アートワークの検索、ダウンロード、変換、適用
- 韓国語、英語、日本語、中国語 UI
- macOS LaunchAgent ログイン自動起動
- Hermes skill wrapper と `petctl.sh` helper

## クイックスタート

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/connectors/hermes/install-from-git.sh"
```

手動 clone:

```bash
git clone https://github.com/ktkarchive/taiei-hermes-pet.git
cd taiei-hermes-pet
bash connectors/hermes/install.sh
hermes-pet --background --port 8768
```

状態確認:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

再起動:

```bash
hermes-pet --restart --port 8768
```

停止:

```bash
hermes-pet --stop
```

## Hermes にインストールを依頼する

macOS 上で既に動いている Hermes CLI/TUI に次のように依頼できます。

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository's connectors/hermes/install-from-git.sh installer, start the
local desktop pet on port 8768, then verify status, health, and the installed
hermes-pet skill doctor. Do not modify my global hermes command.
```

installer は repo を `~/.hermes/pet/taiei-hermes-pet` に clone または
fast-forward update し、必要なら `venv/` を bootstrap して、取り外し可能な
skill/wrapper connector をインストールし、pet を起動します。

## Hermes Skill Wrapper

スキルの場所:

```text
skills/productivity/hermes-pet/SKILL.md
```

`~/.hermes/skills` に同期されると、次のように依頼できます。

- "Start Hermes Pet."
- "Restart the desktop pet."
- "Install Hermes Pet as a login item."
- "Search pixel pet artwork."
- "Show current pet sessions."

Helper:

```bash
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" status
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" start
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" restart
bash "${HERMES_SKILL_DIR}/scripts/petctl.sh" stop
```

リポジトリ内で直接実行することもできます。

```bash
bash skills/productivity/hermes-pet/scripts/petctl.sh status
```

### インストール、更新、削除

Hermes 専用配布版をインストールまたは更新します。

```bash
bash connectors/hermes/install.sh
```

この installer は意図的に狭い範囲だけを変更します。

- fresh clone に `venv/bin/python3` がない場合、`python3 -m venv venv` と `venv/bin/python3 -m pip install .` で自動 bootstrap
- local development で editable install が必要な場合は `HERMES_PET_EDITABLE_INSTALL=1` を使用
- `~/.local/bin/hermes-pet` をインストール
- `~/.hermes/skills/productivity/hermes-pet` をインストール
- `.project-root` で現在の workspace を固定
- グローバルな `hermes` コマンドは変更しない

virtualenv を手動で準備したい場合は `--no-bootstrap` を使ってください。

インストール後の確認:

```bash
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

connector のみ削除:

```bash
bash connectors/hermes/uninstall.sh
```

connector と Hermes Pet runtime/cache を削除:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

uninstall はデフォルトで実行中の pet を止め、存在する
`ai.hermes.pet*.plist` LaunchAgent を unload/remove し、standalone
`hermes-pet` wrapper、インストール済み skill、既知の Hermes Pet runtime
ファイルだけを削除します。Hermes Agent 本体は削除しません。

## CLI コマンド

実行管理:

```bash
hermes pet --status
hermes pet --background --port 8768
hermes pet --restart --port 8768
hermes pet --stop
```

セッション:

```bash
hermes pet --sessions
```

ログイン項目:

```bash
hermes pet --install-launch-agent --port 8768 --force
hermes pet --launch-agent-status
hermes pet --start-launch-agent
hermes pet --stop-launch-agent
hermes pet --uninstall-launch-agent
```

plist:

```text
~/Library/LaunchAgents/ai.hermes.pet.plist
```

## アートワーク

Hermes Pet は同梱 Hermes アートワークを使えるほか、
[Codex Pet Share](https://codex-pet-share.pages.dev/) という公開 pixel
companion catalog からアニメーションアートワークを取り込めます。

```bash
hermes pet --share-list
hermes pet --share-search "pixel"
hermes pet --share-apply "<pet-id-or-url>" --size 84
hermes pet --share-current
hermes pet --share-installed
hermes pet --share-use-installed "<asset-id>"
hermes pet --share-clear
```

参考サイト:

```text
https://codex-pet-share.pages.dev/
```

右クリックメニューの Pet Artwork からも検索、適用、サイトを開く、最近のアートワーク切り替えができます。
CLI では pet id または Codex Pet Share URL を `--share-apply` に渡せます。

```bash
hermes pet --share-apply "https://codex-pet-share.pages.dev/#/pets/<pet-id>" --size 84
```

取り込んだアートワークはこの Mac の Hermes runtime にローカル保存されます。
Codex Pet Share の他の作者が公開した pet をスクリーンショット、デモ、配布文書
で使う場合は、できるだけ pet 名と作者情報を残してください。

## 右クリックメニュー

現在のメニュー:

- Hermes Mode: CLI/TUI の起動またはフォーカス
- Active Sessions: アクティブ/最近の CLI/TUI セッションを開く
- Pet Artwork: Codex Pet Share 検索、適用、最近のアートワーク
- Settings: 言語、ターミナル、左クリック動作、セッション数
- Pet Runtime: 再起動、ログイン項目管理
- Clear Notifications
- Quit Hermes Pet

## 通知とアニメーション

通知:

- `!`: 選択、承認、入力待ち、失敗
- `1`: 完了または review

通知はユーザーがクリックするか手動で消すまで残ります。

アニメーション:

- idle: 待機/まばたき
- drag left/right: running-left / running-right
- hover: jumping
- 作業中: running
- 入力待ち: waiting
- 完了/review: review 後 idle
- 失敗: failed 後 idle

## 安全モデル

- デフォルトは `127.0.0.1`
- public macOS MVP installer は private-network relay tool を必要としません。
- runtime 状態ファイルはプロセス/セッション metadata を含む場合、ユーザー専用権限で保存します。
- LaunchAgent のインストール/削除はユーザー承認後

## 開発確認

```bash
venv/bin/python3 -m py_compile hermes_cli/main.py hermes_cli/pet_overlay.py tests/hermes_cli/test_pet_overlay.py
/usr/bin/swiftc hermes_cli/assets/hermes_pet_macos.swift -o /tmp/hermes_pet_macos_test
venv/bin/python3 -m pytest -q tests/hermes_cli/test_pet_overlay.py tests/hermes_cli/test_pet_sessions.py
git diff --check
```

配布前の full release gate:

```bash
bash connectors/hermes/release-check.sh
```

この gate は shell syntax、Python import、pet regression、web/dashboard
tests、AppKit helper compile、SwiftPM app scaffold build、`git diff --check`、
インストール済み `hermes-pet --status` を確認します。

## 配布方針

配布は 2 つのトラックで進めます。

1. Hermes 専用パッケージ: skill/wrapper と既存の `hermes pet ...` 互換コマンド
2. 汎用 macOS App: 将来的な署名付き `.dmg`、ステータスバー、connector 選択、独立したログイン項目、Hermes/OpenClaw/Codex/Claude Code/Kimi 系 connector 対応

デフォルトのインストール経路では upstream Hermes のソースを変更しません。repo 内の Hermes hook は MVP 検証とローカル開発用として扱い、ユーザー向け配布は独立 App + 取り外し可能な Hermes connector に収束させます。

## 参考

- Hermes Agent upstream: https://github.com/NousResearch/hermes-agent
- Codex Pet Share: https://codex-pet-share.pages.dev/
- Notice と attribution: [NOTICE.md](../../NOTICE.md)

## 謝辞

Hermes Pet は Nous Research の Hermes Agent エコシステム上で動作しつつ、
upstream Hermes を変更しない取り外し可能な connector 方針を維持しています。
アニメーション pet の取り込みは、Codex Pet Share の公開 pixel companion
catalog とコミュニティ作者が共有した pet artwork によって可能になりました。
サイト運営者と作品を公開している作者に感謝します。デスクトップ pet の状態と
アニメーション UX は Codex Desktop pet の体験を参考にしています。

## License

MIT. See [LICENSE](../../LICENSE).
