from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import PortalConfig, PortalHealthResult, PortalSessionStatus


def _is_loading_only(body_text: str) -> bool:
    normalized = " ".join(body_text.split())
    return normalized.startswith("Loading...") and len(normalized) < 300


def _detect_expired_session(body_text: str, console_messages: list[str]) -> str | None:
    body_upper = body_text.upper()
    console_text = "\n".join(console_messages)

    if "No active accounts found" in console_text:
        return "MSAL reports no active account in the persistent browser profile."
    if "SSO LOG IN" in body_upper:
        return "The portal shows the SSO login page."
    if _is_loading_only(body_text):
        return "The portal body is stuck at Loading..., which usually means the SSO session expired."

    return None


def check_portal_session(
    portal: PortalConfig,
    health_url: str | None = None,
    *,
    headless: bool = True,
    timezone: str = "Asia/Shanghai",
) -> PortalHealthResult:
    """Open reporting_portal with the persistent profile and classify login state."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for portal health checks. "
            "Install it with `python -m pip install playwright` and `python -m playwright install chromium`."
        ) from exc

    url = health_url or portal.base_url
    timeout_ms = portal.health_timeout_seconds * 1000
    console_messages: list[str] = []
    checked_at = datetime.now(ZoneInfo(timezone))

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                portal.profile_dir,
                headless=headless,
                ignore_https_errors=True,
                viewport={"width": 1800, "height": 1200},
            )
            page = context.new_page()

            def collect_console_message(message: object) -> None:
                text = getattr(message, "text", "")
                if text:
                    console_messages.append(text)

            page.on("console", collect_console_message)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(timeout_ms)
            body_text = page.locator("body").inner_text(timeout=timeout_ms)
            context.close()
    except PlaywrightTimeoutError as exc:
        return PortalHealthResult(
            status=PortalSessionStatus.EXPIRED,
            url=url,
            checked_at=checked_at,
            body_text_length=0,
            console_messages=console_messages,
            reason=f"Portal did not finish loading within {portal.health_timeout_seconds} seconds: {exc}",
        )

    expired_reason = _detect_expired_session(body_text, console_messages)
    if expired_reason:
        return PortalHealthResult(
            status=PortalSessionStatus.EXPIRED,
            url=url,
            checked_at=checked_at,
            body_text_length=len(body_text),
            console_messages=console_messages,
            reason=expired_reason,
        )

    if "Test Runs" in body_text and len(body_text) > 300:
        return PortalHealthResult(
            status=PortalSessionStatus.OK,
            url=url,
            checked_at=checked_at,
            body_text_length=len(body_text),
            console_messages=console_messages,
            reason="Test Runs page loaded with a non-empty body.",
        )

    return PortalHealthResult(
        status=PortalSessionStatus.UNKNOWN,
        url=url,
        checked_at=checked_at,
        body_text_length=len(body_text),
        console_messages=console_messages,
        reason="The page loaded, but the expected Test Runs content was not detected.",
    )
