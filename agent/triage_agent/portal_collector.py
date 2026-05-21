from __future__ import annotations

from urllib.parse import urljoin, urlparse

from .models import TestRunLink, TestRunRowLinks


def _report_hash_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts:
        return parts[-1]
    return None


def extract_links_from_page(page: object) -> list[TestRunLink]:
    anchors = page.locator("a").evaluate_all(
        """elements => elements.map((element, index) => ({
            index,
            text: (element.innerText || element.textContent || '').trim(),
            href: element.href || element.getAttribute('href') || ''
        }))"""
    )
    return [
        TestRunLink(text=item["text"], href=item["href"], index=int(item["index"]))
        for item in anchors
        if item.get("href")
    ]


def pair_log_and_detail_links(links: list[TestRunLink]) -> list[TestRunRowLinks]:
    rows: list[TestRunRowLinks] = []

    for link in links:
        href_lower = link.href.lower()
        text_lower = link.text.lower()
        if "log.html" not in href_lower and "test logs" not in text_lower:
            continue

        detail_link = next(
            (
                candidate
                for candidate in links
                if link.index < candidate.index <= link.index + 8
                and candidate.href != link.href
                and (
                    "/reports/" in candidate.href.lower()
                    or "test-runs" in candidate.href.lower()
                    or "test-run" in candidate.href.lower()
                )
            ),
            None,
        )

        rows.append(
            TestRunRowLinks(
                log_url=link.href,
                report_detail_url=detail_link.href if detail_link else None,
                report_hash=_report_hash_from_url(detail_link.href if detail_link else None),
            )
        )

    return rows


def collect_row_links_from_url(
    context: object,
    url: str,
    *,
    timeout_seconds: int = 30,
) -> list[TestRunRowLinks]:
    page = context.new_page()
    timeout_ms = timeout_seconds * 1000
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(timeout_ms)
    base_url = page.url

    links = extract_links_from_page(page)
    normalized_links = [
        TestRunLink(text=link.text, href=urljoin(base_url, link.href), index=link.index)
        for link in links
    ]
    rows = pair_log_and_detail_links(normalized_links)
    page.close()
    return rows
