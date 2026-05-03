# Taiei Hermes Pet

> **macOS-only MVP.** 本仓库发布面向 Hermes Agent 的 macOS 桌面宠物。
> Windows/Linux 桌面 renderer 不包含在当前 release 中。

Taiei Hermes Pet 是一个可移除的 Hermes Pet package。它会安装独立的
`hermes-pet` 命令和 Hermes skill wrapper，但不会修改用户的全局 `hermes`
命令或 Hermes checkout。

语言: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh.md) | [日本語](README.ja.md)

## Package

可安装 package 位于 `hermes-pet-macos/`。

## 安装

```bash
INSTALL_DIR="$HOME/.hermes/pet/taiei-hermes-pet"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  git clone https://github.com/ktkarchive/taiei-hermes-pet.git "$INSTALL_DIR"
fi
bash "$INSTALL_DIR/install.sh"
```

安装后验证:

```bash
hermes-pet --status
curl -fsS http://127.0.0.1:8768/health
```

详细使用方法请看 [`hermes-pet-macos/README.md`](hermes-pet-macos/README.md) 和
[`hermes-pet-macos/docs/i18n/README.zh.md`](hermes-pet-macos/docs/i18n/README.zh.md)。

## 让 Hermes 安装

```text
Install Hermes Pet from https://github.com/ktkarchive/taiei-hermes-pet.
Use the repository install.sh, start the local macOS desktop pet on port 8768,
then verify hermes-pet --status and http://127.0.0.1:8768/health.
Do not modify the global hermes command.
```

## 致谢

Hermes Pet 面向 Hermes Agent 用户构建。宠物图像选择和导入功能感谢并参考
[Codex Pet Share](https://codex-pet-share.pages.dev/) 社区的公开分享站点。
