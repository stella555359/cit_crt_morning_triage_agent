from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

from .models import TestRunLink, TestRunRowLinks, TimeWindow


ISO_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?")
NOT_ANALYZED_STATUSES = {"not analyzed", "not_analyzed", "not-analysis", "not analysis"}


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


def _normalize_status(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _non_empty_lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _metadata_from_log_url(log_url: str) -> dict[str, str | None]:
    parts = [part for part in urlparse(log_url).path.split("/") if part]
    build = next((part for part in parts if "_ENB_" in part or "_GNB_" in part), None)
    run_type = next((part for part in parts if part in {"CIT", "CRT"}), None)
    return {"build": build, "run_type": run_type}


def _parse_row_metadata(row_text: str | None, log_url: str) -> dict[str, object]:
    lines = _non_empty_lines(row_text)
    log_url_index = next((index for index, line in enumerate(lines) if line == log_url), None)
    test_logs_index = next((index for index, line in enumerate(lines) if line.lower() == "test logs"), None)

    robotcase = None
    if test_logs_index is not None and test_logs_index > 0:
        robotcase = lines[test_logs_index - 1]
    elif log_url_index is not None and log_url_index > 0:
        robotcase = lines[log_url_index - 1]

    end_time_raw = next((line for line in lines if ISO_DATETIME_PATTERN.fullmatch(line)), None)
    end_time = _parse_datetime(end_time_raw)
    result = None
    origin_result = None

    if end_time_raw in lines:
        end_time_index = lines.index(end_time_raw)
        status_candidates = lines[end_time_index + 1 : end_time_index + 3]
        if status_candidates:
            result = status_candidates[0]
        if len(status_candidates) > 1:
            origin_result = status_candidates[1]

    url_metadata = _metadata_from_log_url(log_url)
    return {
        "robotcase": robotcase,
        "end_time": end_time,
        "result": result,
        "origin_result": origin_result,
        "build": url_metadata["build"],
        "run_type": url_metadata["run_type"],
    }


def is_not_analyzed_row(row: TestRunRowLinks) -> bool:
    statuses = {
        _normalize_status(row.result),
        _normalize_status(row.origin_result),
    }
    return bool(statuses & NOT_ANALYZED_STATUSES) or "not analyzed" in _normalize_status(row.row_text)


def is_row_in_window(row: TestRunRowLinks, window: TimeWindow) -> bool:
    if row.end_time is None:
        return False
    row_end_time = row.end_time
    if row_end_time.tzinfo is None:
        row_end_time = row_end_time.replace(tzinfo=window.start.tzinfo)
    return window.start <= row_end_time < window.end


def filter_rows_for_triage(rows: list[TestRunRowLinks], window: TimeWindow) -> list[TestRunRowLinks]:
    return [row for row in rows if is_not_analyzed_row(row) and is_row_in_window(row, window)]


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
                row_index=None,
                row_text=None,
                **_parse_row_metadata(None, link.href),
            )
        )

    return _deduplicate_rows(rows)


def _build_test_run_row(
    *,
    log_url: str,
    report_detail_url: str | None,
    row_index: str | None,
    row_text: str | None,
) -> TestRunRowLinks:
    return TestRunRowLinks(
        log_url=log_url,
        report_detail_url=report_detail_url,
        test_instance_id=_test_instance_id_from_url(report_detail_url),
        row_index=row_index,
        row_text=row_text[:1000] if row_text else None,
        **_parse_row_metadata(row_text, log_url),
    )


def extract_row_links_from_page(page: object) -> list[TestRunRowLinks]:
    ag_rows = page.locator(".ag-row").evaluate_all(
        """rows => {
            const groupedRows = new Map();
            rows.forEach((row, fallbackIndex) => {
                const rowKey = row.getAttribute('row-index')
                    || row.getAttribute('aria-rowindex')
                    || row.getAttribute('data-row-index')
                    || String(fallbackIndex);
                const existing = groupedRows.get(rowKey) || {
                    rowIndex: rowKey,
                    textParts: [],
                    links: []
                };
                const text = (row.innerText || row.textContent || '').trim();
                if (text) {
                    existing.textParts.push(text);
                }
                Array.from(row.querySelectorAll('a')).forEach((element, linkIndex) => {
                    const href = element.href || element.getAttribute('href') || '';
                    if (!href) {
                        return;
                    }
                    existing.links.push({
                        index: existing.links.length + linkIndex,
                        text: (element.innerText || element.textContent || '').trim(),
                        href
                    });
                });
                groupedRows.set(rowKey, existing);
            });
            return Array.from(groupedRows.values()).map(row => ({
                rowIndex: row.rowIndex,
                text: Array.from(new Set(row.textParts)).join('\\n'),
                links: row.links
            })).filter(row => row.links.length > 0);
        }"""
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
                _build_test_run_row(
                    log_url=log_link.href,
                    report_detail_url=detail_link.href if detail_link else None,
                    row_index=str(ag_row["rowIndex"]) if ag_row.get("rowIndex") is not None else None,
                    row_text=ag_row.get("text", ""),
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
