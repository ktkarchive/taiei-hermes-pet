"""Standalone command line entrypoint for the Hermes Pet distribution."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_environment() -> None:
    try:
        from hermes_cli.config import get_hermes_home
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv(hermes_home=get_hermes_home(), project_env=PROJECT_ROOT / ".env")
    except Exception:
        pass


def cmd_pet(args: argparse.Namespace) -> None:
    """Launch or manage the native desktop pet overlay."""
    from hermes_cli.pet_overlay import (
        install_pet_launch_agent,
        pet_launchd_status,
        pet_overlay_status,
        relay_token_file,
        resolve_relay_token,
        resolve_tailscale_host,
        run_pet_overlay,
        start_pet_launch_agent,
        start_pet_overlay_background,
        stop_pet_launch_agent,
        stop_pet_overlay,
        uninstall_pet_launch_agent,
    )

    try:
        pet_host = resolve_tailscale_host() if getattr(args, "tailscale", False) else args.host
    except RuntimeError as exc:
        print(f"Could not resolve Tailscale address: {exc}", file=sys.stderr)
        sys.exit(1)

    allow_non_loopback = getattr(args, "insecure", False) or getattr(args, "tailscale", False)
    use_token_file = bool(
        getattr(args, "use_token_file", False)
        or getattr(args, "rotate_token", False)
        or getattr(args, "tailscale", False)
    )
    try:
        pet_token = resolve_relay_token(
            args.token,
            use_token_file=use_token_file,
            rotate=getattr(args, "rotate_token", False),
        )
    except Exception as exc:
        print(f"Could not prepare Hermes Pet relay token: {exc}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "status", False):
        status = pet_overlay_status()
        if status.get("running"):
            print(f"Hermes Pet running: pid={status.get('pid')} url={status.get('url')}")
        else:
            reason = status.get("reason") or "not running"
            print(f"Hermes Pet not running: {reason}")
        return

    if getattr(args, "remote_env", False):
        status = pet_overlay_status()
        if not status.get("running"):
            reason = status.get("reason") or "not running"
            print(f"Hermes Pet not running: {reason}", file=sys.stderr)
            sys.exit(1)
        url = status.get("url")
        token = status.get("token")
        if not url or not token:
            print("Active Hermes Pet runtime has no relay URL/token", file=sys.stderr)
            sys.exit(1)
        import urllib.parse

        parsed = urllib.parse.urlparse(str(url))
        if (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}:
            print(
                "Active Hermes Pet is localhost-only; remote-env would not be reachable from another PC.",
                file=sys.stderr,
            )
            print(
                "Start a remote relay explicitly when needed: hermes-pet --background --tailscale",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"export HERMES_PET_RELAY_URL={shlex.quote(str(url))}")
        print(f"export HERMES_PET_RELAY_TOKEN={shlex.quote(str(token))}")
        print('export HERMES_PET_SOURCE_ID="remote-hermes-$(hostname -s 2>/dev/null || hostname)"')
        print('export HERMES_PET_LABEL="Hermes $(hostname -s 2>/dev/null || hostname)"')
        print("# Optional, after saving an artwork entry locally on this Mac:")
        print("# export HERMES_PET_ASSET_ID=<saved-artwork-asset-id>")
        return

    if getattr(args, "token_status", False):
        token_exists = relay_token_file().exists()
        print(f"Relay token file: {relay_token_file()}")
        print(f"Exists: {token_exists}")
        if token_exists:
            print("Token: configured")
        return

    if getattr(args, "relay_test", False):
        from hermes_cli.pet_forwarder import run_relay_test

        ok, message = run_relay_test(args.relay_test_message)
        print(message)
        if not ok:
            sys.exit(1)
        return

    if getattr(args, "restart", False):
        import urllib.parse

        status = pet_overlay_status()
        restart_host = pet_host
        restart_port = args.port
        restart_token = pet_token
        if status.get("running"):
            parsed = urllib.parse.urlparse(str(status.get("url") or ""))
            restart_host = parsed.hostname or restart_host
            restart_port = parsed.port or restart_port
            restart_token = str(status.get("token") or restart_token or "")
            stopped, stop_message = stop_pet_overlay()
            if not stopped:
                print(f"Could not stop existing Hermes Pet: {stop_message}", file=sys.stderr)
                sys.exit(1)

        non_loopback = restart_host not in {"127.0.0.1", "localhost", "::1"}
        started, message = start_pet_overlay_background(
            host=restart_host,
            port=restart_port,
            token=restart_token,
            label=args.label,
            size=args.size,
            show_local=not args.no_local,
            insecure=allow_non_loopback or non_loopback,
            initial_x=args.x,
            initial_y=args.y,
        )
        print(message)
        if not started:
            sys.exit(1)
        return

    def restart_running_pet_if_needed() -> None:
        status = pet_overlay_status()
        if not status.get("running"):
            return

        import urllib.parse

        parsed = urllib.parse.urlparse(str(status.get("url") or ""))
        restart_host = parsed.hostname or pet_host
        restart_port = parsed.port or args.port
        restart_token = str(status.get("token") or pet_token or "")
        non_loopback = restart_host not in {"127.0.0.1", "localhost", "::1"}
        stopped, stop_message = stop_pet_overlay()
        if not stopped:
            print(f"Could not stop existing Hermes Pet: {stop_message}", file=sys.stderr)
            sys.exit(1)
        started, message = start_pet_overlay_background(
            host=restart_host,
            port=restart_port,
            token=restart_token,
            label=args.label,
            size=args.size,
            show_local=not args.no_local,
            insecure=allow_non_loopback or non_loopback,
            initial_x=args.x,
            initial_y=args.y,
        )
        print(message)
        if not started:
            sys.exit(1)

    if getattr(args, "share_current", False):
        from hermes_cli.pet_share import format_current_pet_manifest

        print(format_current_pet_manifest())
        return

    if getattr(args, "share_installed", False):
        from hermes_cli.pet_share import list_installed_pet_assets

        assets = list_installed_pet_assets()
        if not assets:
            print("No saved Hermes Pet artwork entries.")
            return
        for asset in assets:
            owner = f" by {asset.owner_name}" if asset.owner_name else ""
            print(f"{asset.asset_id}: {asset.display_name} ({asset.pet_id}){owner}")
        return

    if getattr(args, "share_list", False) or getattr(args, "share_search", None):
        from hermes_cli.pet_share import format_pet_share_page, list_share_pets

        try:
            page = list_share_pets(
                query=args.share_search or "",
                page=args.share_page,
                page_size=args.share_page_size,
                sort=args.share_sort,
                content=args.share_content,
            )
        except Exception as exc:
            print(f"Could not load Codex Pet Share catalog: {exc}", file=sys.stderr)
            sys.exit(1)
        print(format_pet_share_page(page))
        return

    if getattr(args, "share_show", None):
        from hermes_cli.pet_share import fetch_share_pet

        try:
            pet = fetch_share_pet(args.share_show)
        except Exception as exc:
            print(f"Could not load Codex Pet Share pet: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"{pet.display_name} ({pet.id})")
        print(f"Owner: {pet.owner_name or '?'}")
        print(f"Likes: {pet.like_count}  Views: {pet.view_count}")
        if pet.tags:
            print(f"Tags: {', '.join(pet.tags)}")
        if pet.description:
            print(pet.description)
        print(f"Download: {pet.download_url}")
        return

    if getattr(args, "share_apply", None):
        from hermes_cli.pet_share import apply_share_pet

        try:
            result = apply_share_pet(args.share_apply, size=args.size)
        except Exception as exc:
            print(f"Could not apply Codex Pet Share pet: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Applied Codex Pet Share pet: {result.pet.display_name} ({result.pet.id})")
        print(f"Asset dir: {result.asset_dir}")
        if result.backup_dir:
            print(f"Previous artwork moved to: {result.backup_dir}")
        restart_running_pet_if_needed()
        return

    if getattr(args, "share_use_installed", None):
        from hermes_cli.pet_share import activate_installed_pet_asset

        try:
            asset = activate_installed_pet_asset(args.share_use_installed)
        except Exception as exc:
            print(f"Could not apply saved Hermes Pet artwork: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Applied saved Hermes Pet artwork: {asset.display_name} ({asset.pet_id})")
        restart_running_pet_if_needed()
        return

    if getattr(args, "source_skins", False):
        from hermes_cli.pet_share import list_source_pet_skins

        skins = list_source_pet_skins()
        if not skins:
            print("No Hermes Pet source-specific artwork mappings.")
            return
        for skin in skins:
            owner = f" by {skin.asset.owner_name}" if skin.asset.owner_name else ""
            print(
                f"{skin.source_id}: {skin.asset.asset_id} "
                f"({skin.asset.display_name}/{skin.asset.pet_id}){owner}"
            )
        return

    if getattr(args, "source_skin_set", None):
        from hermes_cli.pet_share import set_source_pet_skin

        raw = str(args.source_skin_set)
        if "=" not in raw:
            print("Use --source-skin-set SOURCE_ID=ASSET_ID", file=sys.stderr)
            sys.exit(2)
        source_id, asset_id = raw.split("=", 1)
        try:
            skin = set_source_pet_skin(source_id, asset_id)
        except Exception as exc:
            print(f"Could not set Hermes Pet source skin: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Mapped {skin.source_id} to {skin.asset.display_name} ({skin.asset.asset_id})")
        return

    if getattr(args, "source_skin_clear", None):
        from hermes_cli.pet_share import clear_source_pet_skin

        try:
            existed = clear_source_pet_skin(args.source_skin_clear)
        except Exception as exc:
            print(f"Could not clear Hermes Pet source skin: {exc}", file=sys.stderr)
            sys.exit(1)
        if existed:
            print(f"Cleared Hermes Pet source skin: {args.source_skin_clear}")
        else:
            print(f"No Hermes Pet source skin was set for: {args.source_skin_clear}")
        return

    if getattr(args, "share_clear", False):
        from hermes_cli.pet_share import clear_active_pet_assets

        backup = clear_active_pet_assets()
        if backup:
            print(f"Cleared custom Hermes Pet artwork; previous assets moved to: {backup}")
        else:
            print("Hermes Pet is already using the bundled Hermes artwork.")
        restart_running_pet_if_needed()
        return

    if getattr(args, "rotate_token", False) and not (
        getattr(args, "background", False)
        or getattr(args, "install_launch_agent", False)
    ):
        print(f"Rotated Hermes Pet relay token: {relay_token_file()}")
        status = pet_overlay_status()
        if status.get("running"):
            print("Restart Hermes Pet for the rotated token to take effect.")
        return

    if getattr(args, "stop", False):
        stopped, message = stop_pet_overlay()
        print(message)
        if not stopped:
            sys.exit(1)
        return

    if getattr(args, "background", False):
        started, message = start_pet_overlay_background(
            host=pet_host,
            port=args.port,
            token=pet_token,
            label=args.label,
            size=args.size,
            show_local=not args.no_local,
            insecure=allow_non_loopback,
            initial_x=args.x,
            initial_y=args.y,
        )
        print(message)
        if not started:
            sys.exit(1)
        return

    if getattr(args, "launch_agent_status", False):
        status = pet_launchd_status()
        print(f"LaunchAgent label: {status.get('label')}")
        print(f"LaunchAgent plist: {status.get('plist_path')}")
        print(f"Installed: {bool(status.get('installed'))}")
        print(f"Loaded: {bool(status.get('loaded'))}")
        if status.get("reason"):
            print(f"Reason: {status.get('reason')}")
        if status.get("launchctl"):
            print(str(status.get("launchctl")))
        return

    if getattr(args, "install_launch_agent", False):
        ok, message = install_pet_launch_agent(
            host=pet_host,
            port=args.port,
            token=pet_token,
            label=args.label,
            size=args.size,
            show_local=not args.no_local,
            insecure=allow_non_loopback,
            initial_x=args.x,
            initial_y=args.y,
            force=getattr(args, "force", False),
        )
        print(message)
        if not ok:
            sys.exit(1)
        return

    if getattr(args, "uninstall_launch_agent", False):
        ok, message = uninstall_pet_launch_agent()
        print(message)
        if not ok:
            sys.exit(1)
        return

    if getattr(args, "start_launch_agent", False):
        ok, message = start_pet_launch_agent()
        print(message)
        if not ok:
            sys.exit(1)
        return

    if getattr(args, "stop_launch_agent", False):
        ok, message = stop_pet_launch_agent()
        print(message)
        if not ok:
            sys.exit(1)
        return

    if getattr(args, "sessions", False):
        from hermes_cli.pet_sessions import list_active_pet_sessions

        sessions = list_active_pet_sessions()
        if not sessions:
            print("No active Hermes CLI/TUI sessions registered for Hermes Pet.")
            return
        for session in sessions:
            mode = str(session.get("mode") or "?").upper()
            sid = str(session.get("session_id") or "?")
            cwd = str(session.get("cwd") or "")
            pid = session.get("pid") or "?"
            print(f"{mode} pid={pid} session={sid} cwd={cwd}")
        return

    if getattr(args, "relay_telegram", False):
        from hermes_cli.pet_telegram_relay import run_telegram_relay

        bot_token = args.telegram_bot_token or os.getenv("HERMES_TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("Telegram bot token required: pass --telegram-bot-token or set HERMES_TELEGRAM_BOT_TOKEN", file=sys.stderr)
            sys.exit(2)
        if not args.telegram_chat_id and not getattr(args, "telegram_allow_any_chat", False):
            print(
                "Telegram chat id required: pass --telegram-chat-id or explicitly use --telegram-allow-any-chat",
                file=sys.stderr,
            )
            sys.exit(2)
        run_telegram_relay(
            bot_token=bot_token,
            chat_id=args.telegram_chat_id,
            allow_any_chat=getattr(args, "telegram_allow_any_chat", False),
            relay_url=args.relay_url,
            relay_token=args.relay_token or pet_token,
            offset_path=args.telegram_offset_file,
            poll_interval=args.telegram_poll_interval,
            once=args.telegram_once,
        )
        return

    run_pet_overlay(
        host=pet_host,
        port=args.port,
        token=pet_token,
        label=args.label,
        size=args.size,
        show_local=not args.no_local,
        insecure=allow_non_loopback,
        initial_x=args.x,
        initial_y=args.y,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-pet",
        description=(
            "Launch a transparent, always-on-top Hermes pet that lives on the screen. "
            "It also opens a small localhost HTTP inlet for local Hermes events."
        ),
    )
    manage = parser.add_mutually_exclusive_group()
    manage.add_argument("--status", action="store_true", help="Show the active Hermes Pet process and exit")
    manage.add_argument("--remote-env", action="store_true", help=argparse.SUPPRESS)
    manage.add_argument("--token-status", action="store_true", help=argparse.SUPPRESS)
    manage.add_argument("--relay-test", action="store_true", help=argparse.SUPPRESS)
    manage.add_argument("--stop", action="store_true", help="Stop the active Hermes Pet process and exit")
    manage.add_argument("--restart", action="store_true", help="Restart Hermes Pet as a detached background process")
    manage.add_argument("--background", action="store_true", help="Start Hermes Pet as a detached background process")
    manage.add_argument("--sessions", action="store_true", help="List active CLI/TUI sessions registered for Hermes Pet")
    manage.add_argument("--launch-agent-status", action="store_true", help="Show macOS LaunchAgent status")
    manage.add_argument("--install-launch-agent", action="store_true", help="Install and load a macOS LaunchAgent")
    manage.add_argument("--uninstall-launch-agent", action="store_true", help="Unload and remove the macOS LaunchAgent")
    manage.add_argument("--start-launch-agent", action="store_true", help="Start the installed macOS LaunchAgent")
    manage.add_argument("--stop-launch-agent", action="store_true", help="Stop the macOS LaunchAgent")
    manage.add_argument("--relay-telegram", action="store_true", help=argparse.SUPPRESS)
    manage.add_argument("--share-current", action="store_true", help="Show currently applied Codex Pet Share artwork")
    manage.add_argument("--share-installed", action="store_true", help="List locally saved Hermes Pet artwork")
    manage.add_argument("--share-list", action="store_true", help="List pets from codex-pet-share.pages.dev")
    manage.add_argument("--share-search", metavar="QUERY", help="Search pets from codex-pet-share.pages.dev")
    manage.add_argument("--share-show", metavar="ID_OR_URL", help="Show one Codex Pet Share pet by id or URL")
    manage.add_argument("--share-apply", metavar="ID_OR_URL", help="Download and apply one Codex Pet Share pet")
    manage.add_argument("--share-use-installed", metavar="ASSET_ID", help="Apply a saved Hermes Pet artwork entry")
    manage.add_argument("--source-skins", action="store_true", help=argparse.SUPPRESS)
    manage.add_argument("--source-skin-set", metavar="SOURCE_ID=ASSET_ID", help=argparse.SUPPRESS)
    manage.add_argument("--source-skin-clear", metavar="SOURCE_ID", help=argparse.SUPPRESS)
    manage.add_argument("--share-clear", action="store_true", help="Return Hermes Pet to bundled artwork")

    parser.add_argument("--host", default="127.0.0.1", help="Event inlet bind host (default 127.0.0.1)")
    parser.add_argument("--tailscale", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=8768, help="Event inlet port (default 8768)")
    parser.add_argument("--token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--use-token-file", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rotate-token", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--label", default="Hermes Local", help="Label shown for the local Hermes pet")
    parser.add_argument("--size", type=int, default=84, help="Pet size in pixels (default 84)")
    parser.add_argument("--no-local", action="store_true", help="Start without the default local Hermes pet")
    parser.add_argument("--x", type=int, default=None, help="Initial window X position")
    parser.add_argument("--y", type=int, default=None, help="Initial window Y position")
    parser.add_argument("--insecure", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="Replace an existing LaunchAgent definition")
    parser.add_argument("--relay-url", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--relay-token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--relay-test-message", default="relay test", help=argparse.SUPPRESS)
    parser.add_argument("--telegram-bot-token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--telegram-chat-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--telegram-allow-any-chat", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--telegram-offset-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--telegram-poll-interval", type=float, default=2.0, help=argparse.SUPPRESS)
    parser.add_argument("--telegram-once", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--share-page", type=int, default=1, help="Codex Pet Share page")
    parser.add_argument("--share-page-size", type=int, default=12, help="Codex Pet Share page size")
    parser.add_argument("--share-sort", choices=["new", "popular", "views"], default="new", help="Codex Pet Share sort")
    parser.add_argument("--share-content", choices=["safe", "all"], default="safe", help="Codex Pet Share content mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    _load_environment()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:1] == ["pet"]:
        raw_argv = raw_argv[1:]
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    cmd_pet(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
