"""CLI entry point and command handlers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from topgrade_update.core.autostart import disable_autostart, enable_autostart
from topgrade_update.core.checkers import check_all, total_updates
from topgrade_update.core.config import load_config
from topgrade_update.core.logging import setup_logging
from topgrade_update.core.models import CheckResult, Config
from topgrade_update.core.notifications import send_notification
from topgrade_update.core.quiet_hours import is_quiet_hours

APP_NAME = "Topgrade Update"


def _report_checker_errors(results: list[CheckResult]) -> bool:
    """Print checker failures to stderr and report whether any occurred."""
    errors = [result for result in results if result.error]
    for result in errors:
        print(f"Error checking {result.source}: {result.error}", file=sys.stderr)
    return bool(errors)


def cmd_check(cfg: Config, verbose: bool = False) -> int:
    """Check for updates and notify."""
    from topgrade_update.core.logging import get_logger

    log = get_logger("cli")
    if verbose:
        log.debug("Starting update check...")
    results = check_all(cfg)
    if verbose:
        for r in results:
            log.debug(
                "Checker %s: %d updates, %sms%s",
                r.source,
                len(r.updates),
                r.duration_ms,
                f" error={r.error}" if r.error else "",
            )
    has_errors = _report_checker_errors(results)
    total = total_updates(results)
    if total > 0:
        quiet = is_quiet_hours(
            cfg.notifications.quiet_hours_start,
            cfg.notifications.quiet_hours_end,
        )
        if not cfg.notifications.enabled:
            print("Notifications are disabled.")
        elif quiet:
            print("Notification suppressed during quiet hours.")
        else:
            send_notification(results)
        print(f"{total} update(s) available.")
        return 2 if has_errors else 1
    if has_errors:
        print("Update check incomplete; see errors above.", file=sys.stderr)
        return 2
    if not results:
        print("No update checkers are available.", file=sys.stderr)
        return 2
    print("System is up to date.")
    return 0


def cmd_list(cfg: Config, *, json_output: bool = False) -> int:
    """List available updates to stdout."""
    results = check_all(cfg)
    total = total_updates(results)
    has_errors = _report_checker_errors(results)

    if json_output:
        _print_json(results, total)
        return 2 if has_errors or not results else 0

    if total == 0:
        if has_errors:
            print("No updates found by successful checks.")
        elif not results:
            print("No update checkers are available.")
            return 2
        else:
            print("No updates available.")
        return 2 if has_errors else 0
    for r in results:
        if r.updates:
            print(f"\n{r.source} ({len(r.updates)}):")
            for up in r.updates:
                print(f"  {up.name} {up.old_version} -> {up.new_version}")
    print(f"\nTotal: {total} update(s)")
    return 2 if has_errors else 0


def _print_json(results: list[CheckResult], total: int) -> None:
    """Print results as JSON to stdout."""
    sources: dict[str, dict[str, object]] = {}
    for r in results:
        if r.updates or r.error:
            update_list: list[dict[str, str]] = []
            for up in r.updates:
                update_list.append({
                    "name": up.name,
                    "old_version": up.old_version,
                    "new_version": up.new_version,
                })
            entry: dict[str, object] = {"updates": update_list}
            if r.error:
                entry["error"] = r.error
            entry["duration_ms"] = r.duration_ms
            sources[r.source] = entry
    data: dict[str, object] = {
        "total": total,
        "sources": sources,
    }
    print(json.dumps(data, indent=2))


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
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose (debug) output to stderr",
    )
    parser.add_argument(
        "--json", action="store_true",
        dest="json_output",
        help="With --list: output results as JSON",
    )
    args = parser.parse_args(argv)

    if sum((args.check, args.list, args.tray)) > 1:
        parser.error("choose only one of --check, --list, or --tray")
    if args.enable and args.disable:
        parser.error("--enable and --disable cannot be used together")
    if (args.enable or args.disable) and not args.tray:
        parser.error("--enable and --disable require --tray")
    if args.json_output and not args.list:
        parser.error("--json requires --list")

    # Configure logging early
    setup_logging(verbose=args.verbose)

    if args.tray:
        if args.enable:
            enable_autostart()
            return 0
        if args.disable:
            disable_autostart()
            return 0
        return cmd_tray()

    if args.check or args.list:
        try:
            cfg = load_config()
        except (OSError, TypeError, ValueError) as exc:
            print(f"Error loading configuration: {exc}", file=sys.stderr)
            return 2
        if args.check:
            return cmd_check(cfg, verbose=args.verbose)
        return cmd_list(cfg, json_output=args.json_output)

    return cmd_run()


if __name__ == "__main__":
    sys.exit(main())
