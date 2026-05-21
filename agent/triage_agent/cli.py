from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from .classifier import classify_failed_case
from .config import DEFAULT_CONFIG_PATH, load_config
from .log_extractor import extract_failed_cases_from_text
from .models import PortalSessionStatus
from .portal_collector import collect_row_links_from_url
from .portal_health import check_portal_session
from .portal_urls import build_test_runs_url
from .time_windows import scope_window


def _json_default(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


def command_urls(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    report_date = date.fromisoformat(args.report_date) if args.report_date else date.today()

    payload = []
    for scope in config.scopes:
        window = scope_window(
            regression_status=scope.regression_status,
            report_date=report_date,
            rules=config.time_rules,
        )
        payload.append(
            {
                "scope": scope.name,
                "regression_status": scope.regression_status.value,
                "testline": scope.testline,
                "window": {
                    "name": window.name,
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "display_label": window.display_label,
                },
                "url": build_test_runs_url(config.portal, scope),
            }
        )

    _print_json(payload)


def command_health(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    health_url = args.url or build_test_runs_url(config.portal, config.scopes[0])
    result = check_portal_session(
        config.portal,
        health_url=health_url,
        headless=not args.headed,
        timezone=config.time_rules.timezone,
    )
    _print_json(asdict(result))


def command_extract_log(args: argparse.Namespace) -> None:
    log_text = Path(args.file).read_text(encoding=args.encoding, errors="ignore")
    failed_cases = extract_failed_cases_from_text(log_text)
    payload = []

    for failed_case in failed_cases:
        payload.append(
            {
                "evidence": asdict(failed_case),
                "classification": asdict(classify_failed_case(failed_case)),
            }
        )

    _print_json(payload)


def command_collect_links(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for collect-links. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    scopes = [scope for scope in config.scopes if args.scope in {None, scope.name}]
    if not scopes:
        raise ValueError(f"No matching scope found: {args.scope}")

    health_url = build_test_runs_url(config.portal, scopes[0])
    health = check_portal_session(
        config.portal,
        health_url=health_url,
        headless=not args.headed,
        timezone=config.time_rules.timezone,
    )
    if health.status is not PortalSessionStatus.OK:
        _print_json(
            {
                "session_status": health.status.value,
                "reason": health.reason,
                "health": asdict(health),
                "scopes": [],
            }
        )
        return

    payload = {
        "session_status": health.status.value,
        "health": asdict(health),
        "scopes": [],
    }

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config.portal.profile_dir,
            headless=not args.headed,
            ignore_https_errors=True,
            viewport={"width": 1800, "height": 1200},
        )
        try:
            for scope in scopes:
                url = build_test_runs_url(config.portal, scope)
                rows = collect_row_links_from_url(
                    context,
                    url,
                    timeout_seconds=config.portal.health_timeout_seconds,
                )
                output_rows = rows[: args.max_rows] if args.max_rows else rows
                payload["scopes"].append(
                    {
                        "scope": scope.name,
                        "regression_status": scope.regression_status.value,
                        "testline": scope.testline,
                        "url": url,
                        "row_count": len(rows),
                        "rows": [asdict(row) for row in output_rows],
                    }
                )
        finally:
            context.close()

    _print_json(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CIT/CRT Morning Triage Agent CLI")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to triage_config.json.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    urls_parser = subparsers.add_parser("urls", help="Print configured filtered Reporting Portal URLs.")
    urls_parser.add_argument(
        "--report-date",
        help="Morning report date in YYYY-MM-DD. Defaults to today.",
    )
    urls_parser.set_defaults(func=command_urls)

    health_parser = subparsers.add_parser("health", help="Check persistent Reporting Portal login state.")
    health_parser.add_argument("--url", help="Override health check URL.")
    health_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    health_parser.set_defaults(func=command_health)

    extract_parser = subparsers.add_parser("extract-log", help="Extract failed case evidence from saved log text.")
    extract_parser.add_argument("--file", required=True, help="Path to a saved log.html text or HTML file.")
    extract_parser.add_argument("--encoding", default="utf-8", help="File encoding. Defaults to utf-8.")
    extract_parser.set_defaults(func=command_extract_log)

    collect_parser = subparsers.add_parser(
        "collect-links",
        help="Health check the session, then collect Test Logs links from configured scopes.",
    )
    collect_parser.add_argument("--scope", help="Optional scope name from triage_config.json.")
    collect_parser.add_argument(
        "--max-rows",
        type=int,
        help="Limit rows printed per scope for debugging. row_count still shows the full count.",
    )
    collect_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    collect_parser.set_defaults(func=command_collect_links)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
