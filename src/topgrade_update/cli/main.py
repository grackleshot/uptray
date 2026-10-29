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
from topgrade_update.core.models import CheckResult, Config, SourceConfig, custom_checker_name
from topgrade_update.core.notifications import send_notification
from topgrade_update.core.quiet_hours import is_quiet_hours

APP_NAME = "Topgrade Update"


def _parse_bounded_int(value: str, *, minimum: int, maximum: int, label: str) -> int:
    """Parse an integer CLI value and enforce its supported range."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"{label} must be from {minimum} to {maximum}")
    return parsed


def _parse_source_name(value: str) -> str:
    """Normalize a checker name passed to a source enable/disable option."""
    source = value.strip().lower()
    if not source:
        raise argparse.ArgumentTypeError("source name cannot be empty")
    return source


def _parse_terminal(value: str) -> str:
    """Normalize and validate a terminal command passed on the CLI."""
    terminal = value.strip()
    if not terminal:
        raise argparse.ArgumentTypeError("terminal command cannot be empty")
    return terminal


def _apply_cli_overrides(
    cfg: Config,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    """Apply explicit CLI values over environment and file configuration."""
    if args.check_interval is not None:
        cfg.check_interval = args.check_interval
    if args.terminals is not None:
        cfg.terminals = args.terminals

    enabled_sources = set(args.enable_source or [])
    disabled_sources = set(args.disable_source or [])
    conflicts = enabled_sources & disabled_sources
    if conflicts:
        parser.error(f"cannot both enable and disable source(s): {', '.join(sorted(conflicts))}")
    for source in enabled_sources:
        cfg.sources.setdefault(source, SourceConfig()).enabled = True
    for source in disabled_sources:
        cfg.sources.setdefault(source, SourceConfig()).enabled = False
    for command in cfg.custom_commands:
        source = custom_checker_name(command.name)
        if source in enabled_sources:
            command.enabled = True
        elif source in disabled_sources:
            command.enabled = False

    if args.notifications_enabled is not None:
        cfg.notifications.enabled = args.notifications_enabled
    if args.no_quiet_hours:
        if args.quiet_hours_start is not None or args.quiet_hours_end is not None:
            parser.error("--no-quiet-hours cannot be combined with quiet-hour values")
        cfg.notifications.quiet_hours_start = None
        cfg.notifications.quiet_hours_end = None
    else:
        if args.quiet_hours_start is not None:
            cfg.notifications.quiet_hours_start = args.quiet_hours_start
        if args.quiet_hours_end is not None:
            cfg.notifications.quiet_hours_end = args.quiet_hours_end

    if args.tray_click_action is not None:
        cfg.tray.click_action = args.tray_click_action
    if args.snooze_hours is not None:
        cfg.tray.snooze_hours = args.snooze_hours


def _report_checker_errors(results: list[CheckResult]) -> bool:
    """Print checker failures to stderr and report whether any occurred."""
    errors = [result for result in results if result.error is not None]
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
                f" error={r.error}" if r.error is not None else "",
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
                branch = f" ({up.branch})" if up.branch else ""
                print(f"  {up.name}{branch} {up.old_version} -> {up.new_version}")
    print(f"\nTotal: {total} update(s)")
    return 2 if has_errors else 0


def _print_json(results: list[CheckResult], total: int) -> None:
    """Print results as JSON to stdout."""
    sources: dict[str, dict[str, object]] = {}
    for r in results:
        if r.updates or r.error is not None:
            update_list: list[dict[str, str]] = []
            for up in r.updates:
                update_list.append({
                    "name": up.name,
                    "old_version": up.old_version,
                    "new_version": up.new_version,
                })
                if up.branch:
                    update_list[-1]["branch"] = up.branch
            entry: dict[str, object] = {"updates": update_list}
            if r.error is not None:
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


def cmd_tray(cfg: Config | None = None) -> int:
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
    return run_tray(cfg)


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
    parser.add_argument(
        "--check-interval",
        type=lambda value: _parse_bounded_int(
            value, minimum=300, maximum=86400, label="check interval"
        ),
        help="Override the check interval in seconds (300–86400)",
    )
    parser.add_argument(
        "--terminal",
        dest="terminals",
        action="append",
        type=_parse_terminal,
        help="Override terminal priority (repeat for additional terminals)",
    )
    parser.add_argument(
        "--enable-source", action="append", type=_parse_source_name,
        help="Enable a checker source (repeatable)",
    )
    parser.add_argument(
        "--disable-source", action="append", type=_parse_source_name,
        help="Disable a checker source (repeatable)",
    )
    notifications_group = parser.add_mutually_exclusive_group()
    notifications_group.add_argument(
        "--enable-notifications", dest="notifications_enabled", action="store_true",
        help="Enable desktop notifications",
    )
    notifications_group.add_argument(
        "--disable-notifications", dest="notifications_enabled", action="store_false",
        help="Disable desktop notifications",
    )
    parser.set_defaults(notifications_enabled=None)
    parser.add_argument(
        "--quiet-hours-start",
        type=lambda value: _parse_bounded_int(value, minimum=0, maximum=23, label="hour"),
        help="Override quiet-hours start hour (0–23)",
    )
    parser.add_argument(
        "--quiet-hours-end",
        type=lambda value: _parse_bounded_int(value, minimum=0, maximum=23, label="hour"),
        help="Override quiet-hours end hour (0–23)",
    )
    parser.add_argument(
        "--no-quiet-hours", action="store_true",
        help="Disable quiet hours",
    )
    parser.add_argument(
        "--tray-click-action", choices=("default", "show_updates", "run_topgrade"),
        help="Override tray click behavior",
    )
    parser.add_argument(
        "--snooze-hours",
        type=lambda value: _parse_bounded_int(value, minimum=1, maximum=24, label="snooze hours"),
        help="Override the configured tray snooze duration (1–24 hours)",
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

    has_overrides = any(
        (
            args.check_interval is not None,
            args.terminals is not None,
            args.enable_source,
            args.disable_source,
            args.notifications_enabled is not None,
            args.quiet_hours_start is not None,
            args.quiet_hours_end is not None,
            args.no_quiet_hours,
            args.tray_click_action is not None,
            args.snooze_hours is not None,
        )
    )
    if has_overrides and not (args.check or args.list or args.tray):
        parser.error("configuration overrides require --check, --list, or --tray")
    if has_overrides and (args.enable or args.disable):
        parser.error("configuration overrides cannot be used with --enable or --disable")

    # Configure logging early
    setup_logging(verbose=args.verbose)

    if args.tray and args.enable:
        enable_autostart()
        return 0
    if args.tray and args.disable:
        disable_autostart()
        return 0

    if args.check or args.list or args.tray:
        try:
            cfg = load_config()
        except (OSError, TypeError, ValueError) as exc:
            print(f"Error loading configuration: {exc}", file=sys.stderr)
            return 2
        _apply_cli_overrides(cfg, args, parser)
        if args.tray:
            return cmd_tray(cfg)
        if args.check:
            return cmd_check(cfg, verbose=args.verbose)
        return cmd_list(cfg, json_output=args.json_output)

    return cmd_run()


if __name__ == "__main__":
    sys.exit(main())
