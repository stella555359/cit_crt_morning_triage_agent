from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .classifier import classify_failed_case
from .config import DEFAULT_CONFIG_PATH, load_config
from .log_extractor import extract_failed_cases_from_text
from .models import PortalSessionStatus
from .portal_collector import collect_row_links_from_url, filter_rows_for_triage
from .portal_health import check_portal_session
from .portal_urls import build_test_runs_url
from .time_windows import scope_window


REPORT_ID_PATTERN = re.compile(r"/details/test-report/(\d+)/|/at/test-reports/(\d+)/|test_report_id=(\d+)")


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


def _failed_case_payload(log_text: str) -> list[dict[str, Any]]:
    failed_cases = extract_failed_cases_from_text(log_text)
    return [
        {
            "evidence": asdict(failed_case),
            "classification": asdict(classify_failed_case(failed_case)),
        }
        for failed_case in failed_cases
    ]


def _http_fallback_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    return urlunparse(parsed._replace(scheme="http"))


def _drop_logs_prefix_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path.startswith("/logs/"):
        return None
    return urlunparse(parsed._replace(path=parsed.path.removeprefix("/logs")))


def _candidate_log_urls(url: str, allow_http_fallback: bool) -> list[str]:
    candidates = [url]
    if allow_http_fallback:
        http_url = _http_fallback_url(url)
        if http_url:
            candidates.append(http_url)

        for candidate in list(candidates):
            without_logs_prefix = _drop_logs_prefix_url(candidate)
            if without_logs_prefix:
                candidates.append(without_logs_prefix)

    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def _extract_report_ids_from_text(value: str) -> list[str]:
    report_ids: list[str] = []
    for match in REPORT_ID_PATTERN.finditer(value):
        report_id = next((group for group in match.groups() if group), None)
        if report_id and report_id not in report_ids:
            report_ids.append(report_id)
    return report_ids


def _build_report_download_url(report_id: str) -> str:
    return f"https://rep-portal.ext.net.nokia.com/at/test-reports/{report_id}/download/"


def _read_log_body_with_fallback(
    context: Any,
    url: str,
    *,
    timeout_ms: int,
    wait_seconds: int,
    allow_http_fallback: bool,
) -> tuple[str | None, dict[str, Any] | None, list[dict[str, str]]]:
    attempted_urls = _candidate_log_urls(url, allow_http_fallback=allow_http_fallback)

    errors: list[dict[str, str]] = []

    for candidate_url in attempted_urls:
        page = context.new_page()
        try:
            response = page.goto(candidate_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(wait_seconds * 1000)
            body_text = page.locator("body").inner_text(timeout=timeout_ms)
            diagnostics = {
                "effective_url": candidate_url,
                "final_url": page.url,
                "title": page.title(),
                "response_status": response.status if response else None,
                "response_content_type": response.headers.get("content-type") if response else None,
            }
            page.close()
            if response and response.status >= 400:
                errors.append(
                    {
                        "url": candidate_url,
                        "error": f"HTTP {response.status}: {body_text[:200]}",
                    }
                )
                continue
            return body_text, diagnostics, errors
        except Exception as exc:  # Playwright rewrites network failures into library-specific errors.
            errors.append({"url": candidate_url, "error": str(exc)})
            page.close()

    return None, None, errors


def _extract_log_links_from_current_page(page: Any) -> list[dict[str, str]]:
    return page.locator("a").evaluate_all(
        """elements => elements.map((element, index) => ({
            index: String(index),
            text: (element.innerText || element.textContent || '').trim(),
            href: element.href || element.getAttribute('href') || ''
        })).filter(link => link.href && (
            link.href.toLowerCase().includes('log.html')
            || link.text.toLowerCase().includes('test logs')
            || link.text.toLowerCase().includes('logs')
        ))"""
    )


def _looks_like_sso_login(url: str, title: str, body_text: str) -> bool:
    normalized_body = " ".join(body_text.split()).lower()
    normalized_title = title.strip().lower()
    return (
        "login.microsoftonline.com" in url
        or normalized_title == "sign in to your account"
        or "enter password" in normalized_body
        or "sign in with another account" in normalized_body
    )


def _download_report_zip(
    context: Any,
    download_url: str,
    *,
    download_dir: Path,
    timeout_ms: int,
) -> dict[str, str]:
    download_dir.mkdir(parents=True, exist_ok=True)
    page = context.new_page()
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            try:
                page.goto(download_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as exc:
                if "Download is starting" not in str(exc):
                    raise
        download = download_info.value
        output_path = download_dir / download.suggested_filename
        download.save_as(str(output_path))
        page.close()
        return {
            "status": "downloaded",
            "download_url": download_url,
            "suggested_filename": download.suggested_filename,
            "saved_path": str(output_path),
        }
    except Exception as exc:
        page.close()
        return {"status": "failed", "download_url": download_url, "error": str(exc)}


def _read_log_by_clicking_link(
    page: Any,
    link_index: str,
    *,
    timeout_ms: int,
    wait_seconds: int,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    selector = f"a >> nth={int(link_index)}"
    before_pages = set(page.context.pages)

    try:
        page.locator("a").nth(int(link_index)).click(timeout=timeout_ms)
        page.wait_for_timeout(wait_seconds * 1000)
        after_pages = set(page.context.pages)
        new_pages = [candidate for candidate in after_pages if candidate not in before_pages]
        log_page = new_pages[-1] if new_pages else page
        log_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        body_text = log_page.locator("body").inner_text(timeout=timeout_ms)
        diagnostics = {
            "click_selector": selector,
            "click_final_url": log_page.url,
            "click_title": log_page.title(),
            "click_opened_new_page": bool(new_pages),
        }
        if log_page.url.startswith("chrome-error://"):
            return None, diagnostics, "Click opened a Chrome error page."
        if not body_text.strip():
            return None, diagnostics, "Click opened an empty page."
        return body_text, diagnostics, None
    except Exception as exc:
        return None, None, str(exc)


def command_extract_log_url(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for extract-log-url. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    timeout_ms = args.timeout_seconds * 1000

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config.portal.profile_dir,
            headless=not args.headed,
            ignore_https_errors=True,
            viewport={"width": 1800, "height": 1200},
        )
        try:
            body_text, diagnostics, errors = _read_log_body_with_fallback(
                context,
                args.url,
                timeout_ms=timeout_ms,
                wait_seconds=args.wait_seconds,
                allow_http_fallback=not args.no_http_fallback,
            )
        finally:
            context.close()

    if body_text is None:
        _print_json(
            {
                "url": args.url,
                "status": "navigation_failed",
                "errors": errors,
            }
        )
        return

    _print_json(
        {
            "url": args.url,
            "status": "ok",
            **(diagnostics or {}),
            "navigation_errors": errors,
            "body_text_length": len(body_text),
            "body_text_sample": body_text[: args.sample_chars],
            "failed_case_count": len(extract_failed_cases_from_text(body_text)),
            "failed_cases": _failed_case_payload(body_text),
        }
    )


def command_extract_detail_log(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for extract-detail-log. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    timeout_ms = args.timeout_seconds * 1000

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config.portal.profile_dir,
            headless=not args.headed,
            ignore_https_errors=True,
            viewport={"width": 1800, "height": 1200},
        )
        try:
            detail_page = context.new_page()
            response = detail_page.goto(args.url, wait_until="domcontentloaded", timeout=timeout_ms)
            detail_page.wait_for_timeout(args.wait_seconds * 1000)
            detail_body_text = detail_page.locator("body").inner_text(timeout=timeout_ms)
            log_links = _extract_log_links_from_current_page(detail_page)
            detail_diagnostics = {
                "detail_url": args.url,
                "detail_final_url": detail_page.url,
                "detail_title": detail_page.title(),
                "detail_response_status": response.status if response else None,
                "detail_body_text_length": len(detail_body_text),
                "detail_body_text_sample": detail_body_text[: args.sample_chars],
            }
            if _looks_like_sso_login(detail_page.url, detail_page.title(), detail_body_text):
                _print_json(
                    {
                        "status": "session_expired",
                        **detail_diagnostics,
                        "reason": "Reporting Portal redirected to Microsoft SSO login page.",
                        "log_link_count": 0,
                        "log_links": [],
                    }
                )
                detail_page.close()
                return

            detail_diagnostics.update(
                {
                    "log_link_count": len(log_links),
                    "log_links": log_links[: args.max_links],
                }
            )
            if not log_links:
                _print_json(
                    {
                        "status": "no_log_link_found",
                        **detail_diagnostics,
                    }
                )
                return

            log_url = log_links[0]["href"]
            body_text, log_diagnostics, errors = _read_log_body_with_fallback(
                context,
                log_url,
                timeout_ms=timeout_ms,
                wait_seconds=args.wait_seconds,
                allow_http_fallback=not args.no_http_fallback,
            )
            click_body_text = None
            click_diagnostics = None
            click_error = None
            if body_text is None and not args.no_click_fallback:
                click_body_text, click_diagnostics, click_error = _read_log_by_clicking_link(
                    detail_page,
                    log_links[0]["index"],
                    timeout_ms=timeout_ms,
                    wait_seconds=args.wait_seconds,
                )
                if click_body_text is not None:
                    body_text = click_body_text
                    log_diagnostics = click_diagnostics

            detail_page.close()
        finally:
            context.close()

    if body_text is None:
        _print_json(
            {
                "status": "log_navigation_failed",
                **detail_diagnostics,
                "selected_log_url": log_url,
                "errors": errors,
                "click_diagnostics": click_diagnostics,
                "click_error": click_error,
            }
        )
        return

    _print_json(
        {
            "status": "ok",
            **detail_diagnostics,
            "selected_log_url": log_url,
            **(log_diagnostics or {}),
            "navigation_errors": errors,
            "click_fallback_used": click_body_text is not None,
            "click_error": click_error,
            "body_text_length": len(body_text),
            "body_text_sample": body_text[: args.sample_chars],
            "failed_case_count": len(extract_failed_cases_from_text(body_text)),
            "failed_cases": _failed_case_payload(body_text),
        }
    )


def command_download_report_zip(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for download-report-zip. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    timeout_ms = args.timeout_seconds * 1000
    download_dir = Path(args.download_dir)

    report_ids = [args.report_id] if args.report_id else _extract_report_ids_from_text(args.url or "")
    if not report_ids:
        raise ValueError(
            "No report id found. Provide --report-id or a URL containing /details/test-report/<id>/, "
            "/at/test-reports/<id>/, or test_report_id=<id>."
        )

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config.portal.profile_dir,
            headless=not args.headed,
            ignore_https_errors=True,
            accept_downloads=True,
            viewport={"width": 1800, "height": 1200},
        )
        try:
            results = [
                _download_report_zip(
                    context,
                    _build_report_download_url(report_id),
                    download_dir=download_dir,
                    timeout_ms=timeout_ms,
                )
                for report_id in report_ids
            ]
        finally:
            context.close()

    _print_json(
        {
            "status": "ok" if any(item["status"] == "downloaded" for item in results) else "failed",
            "report_ids": report_ids,
            "download_dir": str(download_dir),
            "results": results,
        }
    )


def command_collect_links(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for collect-links. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    report_date = date.fromisoformat(args.report_date) if args.report_date else date.today()
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
                window = scope_window(
                    regression_status=scope.regression_status,
                    report_date=report_date,
                    rules=config.time_rules,
                )
                rows = collect_row_links_from_url(
                    context,
                    url,
                    timeout_seconds=config.portal.health_timeout_seconds,
                )
                filtered_rows = filter_rows_for_triage(rows, window) if args.triage_only else rows
                output_rows = filtered_rows[: args.max_rows] if args.max_rows else filtered_rows
                payload["scopes"].append(
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
                        "url": url,
                        "raw_row_count": len(rows),
                        "row_count": len(filtered_rows),
                        "triage_only": args.triage_only,
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

    extract_url_parser = subparsers.add_parser(
        "extract-log-url",
        help="Open a log.html URL with Playwright and extract failed case evidence.",
    )
    extract_url_parser.add_argument("--url", required=True, help="log.html URL.")
    extract_url_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Navigation and locator timeout. Defaults to 60.",
    )
    extract_url_parser.add_argument(
        "--wait-seconds",
        type=int,
        default=10,
        help="Extra wait after domcontentloaded before reading body text. Defaults to 10.",
    )
    extract_url_parser.add_argument(
        "--sample-chars",
        type=int,
        default=500,
        help="Number of body text characters to include for debugging. Defaults to 500.",
    )
    extract_url_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    extract_url_parser.add_argument(
        "--no-http-fallback",
        action="store_true",
        help="Disable automatic https to http fallback for internal log URLs.",
    )
    extract_url_parser.set_defaults(func=command_extract_log_url)

    detail_log_parser = subparsers.add_parser(
        "extract-detail-log",
        help="Open a Reporting Portal detail URL, find Test Logs link, and extract failed case evidence.",
    )
    detail_log_parser.add_argument("--url", required=True, help="Reporting Portal detail URL.")
    detail_log_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Navigation and locator timeout. Defaults to 60.",
    )
    detail_log_parser.add_argument(
        "--wait-seconds",
        type=int,
        default=10,
        help="Extra wait after domcontentloaded before reading page text. Defaults to 10.",
    )
    detail_log_parser.add_argument(
        "--sample-chars",
        type=int,
        default=500,
        help="Number of body text characters to include for debugging. Defaults to 500.",
    )
    detail_log_parser.add_argument(
        "--max-links",
        type=int,
        default=20,
        help="Maximum log-like links to print from the detail page. Defaults to 20.",
    )
    detail_log_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    detail_log_parser.add_argument(
        "--no-http-fallback",
        action="store_true",
        help="Disable automatic URL fallbacks for internal log URLs.",
    )
    detail_log_parser.add_argument(
        "--no-click-fallback",
        action="store_true",
        help="Disable clicking the Test Logs link when direct log URL navigation fails.",
    )
    detail_log_parser.set_defaults(func=command_extract_detail_log)

    download_zip_parser = subparsers.add_parser(
        "download-report-zip",
        help="Download robot_report.zip from Reporting Portal /at/test-reports/<id>/download/.",
    )
    download_zip_parser.add_argument(
        "--report-id",
        help="Reporting Portal test report id, for example 45873334.",
    )
    download_zip_parser.add_argument(
        "--url",
        help="URL containing a report id, such as /details/test-report/<id>/ or /at/test-reports/<id>/download/.",
    )
    download_zip_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Download timeout. Defaults to 60.",
    )
    download_zip_parser.add_argument(
        "--download-dir",
        default="/tmp/cit_crt_morning_triage_agent_downloads",
        help="Directory for captured downloads. Defaults to /tmp/cit_crt_morning_triage_agent_downloads.",
    )
    download_zip_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    download_zip_parser.set_defaults(func=command_download_report_zip)

    collect_parser = subparsers.add_parser(
        "collect-links",
        help="Health check the session, then collect Test Logs links from configured scopes.",
    )
    collect_parser.add_argument("--scope", help="Optional scope name from triage_config.json.")
    collect_parser.add_argument(
        "--report-date",
        help="Morning report date in YYYY-MM-DD. Defaults to today.",
    )
    collect_parser.add_argument(
        "--triage-only",
        action="store_true",
        help="Only print rows inside the configured time window whose result/origin_result is not analyzed.",
    )
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
