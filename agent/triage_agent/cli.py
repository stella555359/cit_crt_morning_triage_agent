from __future__ import annotations

import argparse
import json
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


ASSET_CANDIDATE_KEYWORDS = (
    "download",
    "zip",
    "artifact",
    "archive",
    "output",
    "xml",
    "result",
    "more",
)
DOWNLOAD_CANDIDATE_KEYWORDS = (
    "download",
    "zip",
    "artifact",
    "archive",
    "output.xml",
    "output",
)


def _candidate_blob(item: dict[str, str]) -> str:
    return " ".join(
        [
            item.get("text", ""),
            item.get("href", ""),
            item.get("title", ""),
            item.get("aria_label", ""),
        ]
    ).lower()


def _matches_keywords(item: dict[str, str], keywords: tuple[str, ...]) -> bool:
    blob = _candidate_blob(item)
    return any(keyword in blob for keyword in keywords)


def _extract_clickable_assets(page: Any) -> dict[str, list[dict[str, str]]]:
    return page.evaluate(
        """() => {
            const normalize = value => (value || '').trim();
            const links = Array.from(document.querySelectorAll('a')).map((element, index) => ({
                kind: 'link',
                index: String(index),
                text: normalize(element.innerText || element.textContent),
                href: element.href || element.getAttribute('href') || '',
                title: normalize(element.getAttribute('title')),
                aria_label: normalize(element.getAttribute('aria-label'))
            }));
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]')).map((element, index) => ({
                kind: 'button',
                index: String(index),
                text: normalize(element.innerText || element.textContent),
                href: '',
                title: normalize(element.getAttribute('title')),
                aria_label: normalize(element.getAttribute('aria-label'))
            }));
            return { links, buttons };
        }"""
    )


def _asset_summary(page: Any, max_items: int) -> dict[str, Any]:
    assets = _extract_clickable_assets(page)
    all_items = assets["links"] + assets["buttons"]
    candidates = [item for item in all_items if _matches_keywords(item, ASSET_CANDIDATE_KEYWORDS)]
    download_candidates = [item for item in candidates if _matches_keywords(item, DOWNLOAD_CANDIDATE_KEYWORDS)]

    return {
        "link_count": len(assets["links"]),
        "button_count": len(assets["buttons"]),
        "candidate_count": len(candidates),
        "download_candidate_count": len(download_candidates),
        "candidates": candidates[:max_items],
        "download_candidates": download_candidates[:max_items],
        "links_sample": assets["links"][:max_items],
        "buttons_sample": assets["buttons"][:max_items],
    }


def _click_asset_candidate(page: Any, item: dict[str, str], timeout_ms: int) -> str | None:
    selector = "a" if item["kind"] == "link" else 'button, [role="button"]'
    try:
        page.locator(selector).nth(int(item["index"])).click(timeout=timeout_ms)
        return None
    except Exception as exc:
        return str(exc)


def _open_more_menus(page: Any, timeout_ms: int) -> list[dict[str, str]]:
    assets = _extract_clickable_assets(page)
    all_items = assets["links"] + assets["buttons"]
    more_items = [
        item
        for item in all_items
        if item.get("text", "").strip().lower() == "more"
        or item.get("aria_label", "").strip().lower() == "more"
        or item.get("title", "").strip().lower() == "more"
    ]
    results: list[dict[str, str]] = []
    for item in more_items[:3]:
        error = _click_asset_candidate(page, item, timeout_ms)
        page.wait_for_timeout(1000)
        results.append({**item, "click_error": error or ""})
    return results


def _attempt_asset_downloads(
    page: Any,
    candidates: list[dict[str, str]],
    *,
    download_dir: Path,
    timeout_ms: int,
    max_attempts: int,
) -> list[dict[str, str]]:
    download_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []

    for item in candidates[:max_attempts]:
        selector = "a" if item["kind"] == "link" else 'button, [role="button"]'
        locator = page.locator(selector).nth(int(item["index"]))
        try:
            with page.expect_download(timeout=timeout_ms) as download_info:
                locator.click(timeout=timeout_ms)
            download = download_info.value
            output_path = download_dir / download.suggested_filename
            download.save_as(str(output_path))
            results.append(
                {
                    **item,
                    "status": "downloaded",
                    "suggested_filename": download.suggested_filename,
                    "saved_path": str(output_path),
                }
            )
        except Exception as exc:
            results.append({**item, "status": "failed", "error": str(exc)})

    return results


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


def command_inspect_detail_assets(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for inspect-detail-assets. "
            "Install it with `python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    config = load_config(args.config)
    timeout_ms = args.timeout_seconds * 1000
    download_dir = Path(args.download_dir)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config.portal.profile_dir,
            headless=not args.headed,
            ignore_https_errors=True,
            accept_downloads=True,
            viewport={"width": 1800, "height": 1200},
        )
        try:
            page = context.new_page()
            response = page.goto(args.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(args.wait_seconds * 1000)
            body_text = page.locator("body").inner_text(timeout=timeout_ms)
            diagnostics = {
                "detail_url": args.url,
                "detail_final_url": page.url,
                "detail_title": page.title(),
                "detail_response_status": response.status if response else None,
                "detail_body_text_length": len(body_text),
                "detail_body_text_sample": body_text[: args.sample_chars],
            }

            if _looks_like_sso_login(page.url, page.title(), body_text):
                _print_json(
                    {
                        "status": "session_expired",
                        **diagnostics,
                        "reason": "Reporting Portal redirected to Microsoft SSO login page.",
                    }
                )
                return

            before_more = _asset_summary(page, args.max_items)
            opened_more = _open_more_menus(page, timeout_ms) if not args.no_open_more else []
            after_more = _asset_summary(page, args.max_items)
            download_results = []

            if args.attempt_download:
                download_results = _attempt_asset_downloads(
                    page,
                    after_more["download_candidates"],
                    download_dir=download_dir,
                    timeout_ms=timeout_ms,
                    max_attempts=args.max_download_attempts,
                )
        finally:
            context.close()

    _print_json(
        {
            "status": "ok",
            **diagnostics,
            "opened_more": opened_more,
            "before_more": before_more,
            "after_more": after_more,
            "attempt_download": args.attempt_download,
            "download_dir": str(download_dir),
            "download_results": download_results,
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

    inspect_assets_parser = subparsers.add_parser(
        "inspect-detail-assets",
        help="Inspect a Reporting Portal detail page for download/zip/artifact entries.",
    )
    inspect_assets_parser.add_argument("--url", required=True, help="Reporting Portal detail URL.")
    inspect_assets_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Navigation, locator, and download timeout. Defaults to 60.",
    )
    inspect_assets_parser.add_argument(
        "--wait-seconds",
        type=int,
        default=10,
        help="Extra wait after domcontentloaded before inspecting the page. Defaults to 10.",
    )
    inspect_assets_parser.add_argument(
        "--sample-chars",
        type=int,
        default=500,
        help="Number of detail page text characters to include for debugging. Defaults to 500.",
    )
    inspect_assets_parser.add_argument(
        "--max-items",
        type=int,
        default=30,
        help="Maximum candidates, links, and buttons to print. Defaults to 30.",
    )
    inspect_assets_parser.add_argument(
        "--no-open-more",
        action="store_true",
        help="Do not click More menus before collecting candidates.",
    )
    inspect_assets_parser.add_argument(
        "--attempt-download",
        action="store_true",
        help="Click download-like candidates and save downloads.",
    )
    inspect_assets_parser.add_argument(
        "--max-download-attempts",
        type=int,
        default=3,
        help="Maximum download-like candidates to click when --attempt-download is used. Defaults to 3.",
    )
    inspect_assets_parser.add_argument(
        "--download-dir",
        default="/tmp/cit_crt_morning_triage_agent_downloads",
        help="Directory for captured downloads. Defaults to /tmp/cit_crt_morning_triage_agent_downloads.",
    )
    inspect_assets_parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    inspect_assets_parser.set_defaults(func=command_inspect_detail_assets)

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
