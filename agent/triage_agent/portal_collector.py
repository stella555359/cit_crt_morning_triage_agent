from __future__ import annotations

from urllib.parse import parse_qs, urljoin, urlparse

from .models import TestRunLink, TestRunRowLinks


def _test_instance_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("test_instance_id")
    return values[0] if values else None


def _is_log_link(link: TestRunLink) -> bool:
    href_lower = link.href.lower()
    text_lower = link.text.lower()
    return "log.html" in href_lower or "test logs" in text_lower


def _is_detail_link(link: TestRunLink) -> bool:
    return "test_instance_id=" in link.href.lower()


def _deduplicate_rows(rows: list[TestRunRowLinks]) -> list[TestRunRowLinks]:
    unique_rows: list[TestRunRowLinks] = []
    seen: set[tuple[str, str | None]] = set()

    for row in rows:
        key = (row.log_url, row.test_instance_id or row.report_detail_url)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    return unique_rows


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
        if not _is_log_link(link):
            continue

        detail_link = next(
            (
                candidate
                for candidate in links
                if link.index < candidate.index <= link.index + 8
                and candidate.href != link.href
                and _is_detail_link(candidate)
            ),
            None,
        )

        rows.append(
            TestRunRowLinks(
                log_url=link.href,
                report_detail_url=detail_link.href if detail_link else None,
                test_instance_id=_test_instance_id_from_url(detail_link.href if detail_link else None),
            )
        )

    return _deduplicate_rows(rows)


def extract_row_links_from_page(page: object) -> list[TestRunRowLinks]:
    ag_rows = page.locator(".ag-row").evaluate_all(
        """rows => rows.map((row, rowIndex) => ({
            rowIndex,
            text: (row.innerText || row.textContent || '').trim(),
            links: Array.from(row.querySelectorAll('a')).map((element, linkIndex) => ({
                index: linkIndex,
                text: (element.innerText || element.textContent || '').trim(),
                href: element.href || element.getAttribute('href') || ''
            })).filter(link => link.href)
        })).filter(row => row.links.length > 0)"""
    )

    rows: list[TestRunRowLinks] = []
    for ag_row in ag_rows:
        links = [
            TestRunLink(text=item["text"], href=item["href"], index=int(item["index"]))
            for item in ag_row["links"]
            if item.get("href")
        ]
        log_links = [link for link in links if _is_log_link(link)]
        detail_link = next((link for link in links if _is_detail_link(link)), None)

        for log_link in log_links:
            rows.append(
                TestRunRowLinks(
                    log_url=log_link.href,
                    report_detail_url=detail_link.href if detail_link else None,
                    test_instance_id=_test_instance_id_from_url(detail_link.href if detail_link else None),
                )
            )

    return _deduplicate_rows(rows)


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

    rows = extract_row_links_from_page(page)
    if not rows:
        links = extract_links_from_page(page)
        normalized_links = [
            TestRunLink(text=link.text, href=urljoin(base_url, link.href), index=link.index)
            for link in links
        ]
        rows = pair_log_and_detail_links(normalized_links)

    page.close()
    return rows
