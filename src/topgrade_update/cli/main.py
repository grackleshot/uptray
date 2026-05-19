"""CLI entry point and command handlers."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from topgrade_update.core.autostart import disable_autostart, enable_autostart
from topgrade_update.core.checkers import check_all, total_updates
from topgrade_update.core.config import load_config
from topgrade_update.core.models import Config
from topgrade_update.core.notifications import send_notification

APP_NAME = "Topgrade Update"


def cmd_check(cfg: Config) -> int:
    """Check for updates and notify."""
    results = check_all(cfg)
    total = total_updates(results)
    if total > 0:
        send_notification(results)
        print(f"{total} update(s) available.")
    else:
        print("System is up to date.")
    return 0 if total == 0 else 1


def cmd_list(cfg: Config) -> int:
    """List available updates to stdout."""
    results = check_all(cfg)
    total = total_updates(results)
    if total == 0:
        print("No updates available.")
        return 0
    for r in results:
        if r.updates:
            print(f"\n{r.source} ({len(r.updates)}):")
            for up in r.updates:
                print(f"  {up.name} {up.old_version} -> {up.new_version}")
    print(f"\nTotal: {total} update(s)")
    return 0


def cmd_run() -> int:
    """Run topgrade in the current terminal."""
    topgrade = shutil.which("topgrade")
    if not topgrade:
        print("Error: topgrade not found in PATH.", file=sys.stderr)
        return 1
    os.execvp(topgrade, ["topgrade"])
    return 1  # unreachable


def cmd_tray() -> int:
    """Launch the system tray applet."""
    try:
        from topgrade_update.gui.tray import run_tray
    except ImportError as exc:
        print(
            f"Error: GUI dependencies not installed. Install with: "
            f"pip install 'topgrade-update[gui]'\n({exc})",
            file=sys.stderr,
        )
        return 1
    return run_tray()


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(
        prog="topgrade-update",
        description="An interactive update notifier & applier using topgrade.",
    )
    parser.add_argument(
        "-c", "--check", action="store_true",
        help="Check for available updates and send a desktop notification",
    )
    parser.add_argument(
        "-l", "--list", action="store_true",
        help="List available updates",
    )
    parser.add_argument(
        "--tray", action="store_true",
        help="Launch the system tray applet",
    )
    parser.add_argument(
        "--enable", action="store_true",
        help="With --tray: enable autostart at login",
    )
    parser.add_argument(
        "--disable", action="store_true",
        help="With --tray: disable autostart at login",
    )
    args = parser.parse_args(argv)

    if args.tray:
        if args.enable:
            enable_autostart()
            return 0
        if args.disable:
            disable_autostart()
            return 0
        return cmd_tray()

    cfg = load_config()

    if args.check:
        return cmd_check(cfg)
    if args.list:
        return cmd_list(cfg)

    return cmd_run()


if __name__ == "__main__":
    sys.exit(main())
