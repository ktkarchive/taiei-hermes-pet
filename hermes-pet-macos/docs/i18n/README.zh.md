# Hermes Pet

> **macOS-only MVP.** 当前 Hermes Pet 发行版只提供 macOS 原生桌面宠物。
> Windows/Linux renderer 可以在后续版本中作为独立 target 扩展，但本 release
> 不包含等价的 Windows/Linux 桌面 overlay 行为。

Hermes Pet 是 Hermes Agent 的桌面宠物伴侣。它不是浏览器组件，而是生活在 macOS 屏幕上的原生透明悬浮窗口。它可以响应本地 Hermes CLI/TUI 的运行状态，显示等待/完成通知，支持多只宠物，并可从 Codex Pet Share 导入动画宠物图像。

语言:

- [English](../../README.md)
- [한국어](README.ko.md)
- [简体中文](README.zh.md)
- [日本語](README.ja.md)

## 概览

Hermes Pet 是面向 Hermes Agent 的 macOS 桌面宠物。当前发行版只安装可移除的 `hermes-pet` 命令和 Hermes skill wrapper，不修改用户的全局 `hermes` 命令或上游 Hermes checkout。

本地 MVP 默认只绑定 localhost:

```bash
hermes-pet --background --port 8768
```

## 功能

- 基于 AppKit `NSPanel` 的 macOS 原生桌面宠物
- Hermes CLI/TUI 事件的 localhost inlet
- 活动和最近 Hermes 会话菜单
- 左键聚焦当前活动 CLI/TUI 会话
- 右键菜单: CLI/TUI、会话、设置、图像、运行管理、通知、退出
- 本地桌面宠物显示和会话状态响应
- 等待、完成、失败通知徽章
- Codex Pet Share 图像搜索、下载、转换和应用
- 韩语、英语、日语、中文 UI
- macOS LaunchAgent 登录自动启动
- Hermes skill wrapper 和 `petctl.sh` helper

## 快速开始

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/install.sh"
```

手动 clone:

```bash
git clone https://github.com/ktkarchive/taiei-hermes-pet.git
cd taiei-hermes-pet/hermes-pet-macos
bash connectors/hermes/install.sh
hermes-pet --background --port 8768
```

检查状态:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

重启:

```bash
hermes-pet --restart --port 8768
```

停止:

```bash
hermes-pet --stop
```

## 让 Hermes 自动安装

在 macOS 上已经运行的 Hermes CLI/TUI 中，可以直接输入:

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository install.sh, start the local desktop pet on port 8768, then
verify status, health, and the installed hermes-pet skill doctor. Do not modify
my global hermes command.
```

安装器会把 repo clone 或 fast-forward update 到
`~/.hermes/pet/taiei-hermes-pet`，必要时 bootstrap `venv/`，安装可移除的
skill/wrapper connector，并启动 pet。

## Hermes Skill Wrapper

Skill 位置:

```text
skills/productivity/hermes-pet/SKILL.md
```

同步到 `~/.hermes/skills` 后，用户可以这样请求:

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

也可以在仓库中直接运行:

```bash
bash skills/productivity/hermes-pet/scripts/petctl.sh status
```

### 安装、更新、移除

安装或更新 Hermes 专用发行版:

```bash
bash connectors/hermes/install.sh
```

此安装脚本只做有限的事情:

- 如果 fresh clone 中缺少 `venv/bin/python3`，自动运行 `python3 -m venv venv`，并只安装 pet runtime 需要的 `PyYAML` 和 `python-dotenv`
- 安装 `~/.local/bin/hermes-pet`
- 安装 `~/.hermes/skills/productivity/hermes-pet`
- 写入 `.project-root`，让 skill 指向当前工作区
- 不替换、不重定向用户的全局 `hermes` 命令

如果想手动准备 virtualenv，请使用 `--no-bootstrap`。

安装后验证:

```bash
hermes-pet --status
HERMES_SKILL_DIR="$HOME/.hermes/skills/productivity/hermes-pet" \
  bash "$HOME/.hermes/skills/productivity/hermes-pet/scripts/petctl.sh" doctor
```

仅移除 connector:

```bash
bash connectors/hermes/uninstall.sh
```

同时移除 connector 和 Hermes Pet runtime/cache:

```bash
bash connectors/hermes/uninstall.sh --purge-runtime
```

卸载脚本默认会停止正在运行的 pet，卸载并移除存在的
`ai.hermes.pet*.plist` LaunchAgent，然后只删除 standalone `hermes-pet`
wrapper、已安装的 skill 和已知 Hermes Pet runtime 文件。它不会删除 Hermes
Agent 本身。

## CLI 命令

运行管理:

```bash
hermes-pet --status
hermes-pet --background --port 8768
hermes-pet --restart --port 8768
hermes-pet --stop
```

会话:

```bash
hermes-pet --sessions
```

登录项:

```bash
hermes-pet --install-launch-agent --port 8768 --force
hermes-pet --launch-agent-status
hermes-pet --start-launch-agent
hermes-pet --stop-launch-agent
hermes-pet --uninstall-launch-agent
```

plist 路径:

```text
~/Library/LaunchAgents/ai.hermes.pet.plist
```

## 图像

Hermes Pet 可以使用内置 Hermes 图像，也可以从
[Codex Pet Share](https://codex-pet-share.pages.dev/) 这个公开 pixel
companion catalog 导入动画图像:

```bash
hermes-pet --share-list
hermes-pet --share-search "pixel"
hermes-pet --share-apply "<pet-id-or-url>" --size 84
hermes-pet --share-current
hermes-pet --share-installed
hermes-pet --share-use-installed "<asset-id>"
hermes-pet --share-clear
```

参考站点:

```text
https://codex-pet-share.pages.dev/
```

也可以通过右键菜单的 Pet Artwork 搜索、应用、打开网站和切换最近使用的图像。
CLI 中 `--share-apply` 可以接受 pet id 或 Codex Pet Share URL:

```bash
hermes-pet --share-apply "https://codex-pet-share.pages.dev/#/pets/<pet-id>" --size 84
```

导入后的图像会保存在本机 Hermes runtime 目录下。如果截图、演示或文档中使用了
Codex Pet Share 上其他创作者发布的宠物，请尽量保留宠物名称和作者信息。

## 右键菜单

当前菜单包含:

- Hermes Mode: 启动或聚焦 CLI/TUI
- Active Sessions: 打开活动/最近 CLI/TUI 会话
- Pet Artwork: Codex Pet Share 搜索、应用和最近图像
- Settings: 语言、终端、左键行为、会话数量
- Pet Runtime: 重启宠物，管理登录项
- Clear Notifications
- Quit Hermes Pet

## 通知和动画

通知:

- `!`: 等待选择、审批、输入或失败
- `1`: 完成或 review 状态

通知会保留到用户点击宠物或手动清除。

动画:

- idle: 空闲/眨眼
- drag left/right: running-left / running-right
- hover: jumping
- 工作中: running
- 等待输入: waiting
- 完成/review: review 后回到 idle
- 失败: failed 后回到 idle

## 安全模型

- 默认绑定 `127.0.0.1`
- public macOS MVP installer 不需要网络转发或聊天集成工具。
- runtime 状态文件在包含进程或会话 metadata 时使用用户私有权限保存。
- LaunchAgent 安装/移除需要用户同意

## 开发验证

```bash
venv/bin/python3 -m py_compile hermes_pet/cli.py hermes_cli/pet_overlay.py
/usr/bin/swiftc hermes_cli/assets/hermes_pet_macos.swift -o /tmp/hermes_pet_macos_test
git diff --check
```

发布前完整 release gate:

```bash
bash connectors/hermes/release-check.sh
```

该检查会运行 shell syntax、Python import、AppKit helper compile、
`git diff --check`、minimal runtime smoke 以及已安装的 `hermes-pet --status`。
public lean 版本不包含 test suite，因此会自动跳过 pytest。

## 发布方向

此仓库目前只发布 Hermes 专用包。通用 App/DMG 不包含在这个 public MVP 中。默认安装路径不会修改上游 Hermes 源码。

## 参考

- Hermes Agent upstream: https://github.com/NousResearch/hermes-agent
- Codex Pet Share: https://codex-pet-share.pages.dev/
- Notice 和 attribution: [NOTICE.md](../../NOTICE.md)

## 致谢

Hermes Pet 基于 Nous Research 的 Hermes Agent 生态工作，同时保持可移除
connector 的方向，避免修改 upstream Hermes。动画宠物导入功能得益于 Codex
Pet Share 的公开 pixel companion catalog 以及社区创作者分享的宠物图像。感谢
站点维护者和发布宠物作品的作者。桌面宠物的状态和动画体验参考了 Codex
Desktop pet。

## License

MIT. See [LICENSE](../../LICENSE).
