from __future__ import annotations

import re

from .models import FailedCaseEvidence


STOP_MESSAGE_PREFIXES = (
    "Documentation:",
    "Tags:",
    "Setup:",
    "Teardown:",
    "KEYWORD",
    "TEST",
    "SUITE",
    "Start / End / Elapsed:",
    "Elapsed:",
)


def _strip_test_execution_errors(text: str) -> str:
    markers = [
        "Case Execution Detail",
        "Test Execution Detail",
        "\nTEST ",
        "\nTEST\n",
    ]
    for marker in markers:
        index = text.find(marker)
        if index >= 0:
            return text[index:]
    return text


def _compact_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n")]


def _find_next_value(lines: list[str], index: int, label: str) -> str | None:
    current = lines[index]
    if current.startswith(label):
        inline = current.removeprefix(label).strip()
        if inline:
            return inline
        for value in lines[index + 1 : index + 6]:
            if value:
                return value
    return None


def _extract_case_message(lines: list[str], status_index: int) -> str | None:
    for index in range(status_index, min(len(lines), status_index + 80)):
        current = lines[index]
        if not current.startswith("Message:"):
            continue

        inline_value = current.removeprefix("Message:").strip()
        collected: list[str] = []
        next_index = index + 1

        if inline_value:
            collected.append(inline_value)
        else:
            for value_index in range(index + 1, min(len(lines), index + 6)):
                if lines[value_index]:
                    collected.append(lines[value_index])
                    next_index = value_index + 1
                    break

        if not collected:
            return None

        for extra_line in lines[next_index : index + 8]:
            if not extra_line:
                break
            if extra_line.startswith(STOP_MESSAGE_PREFIXES):
                break
            collected.append(extra_line)

        return "\n".join(collected).strip()
    return None


def _extract_full_name(lines: list[str], status_index: int) -> str | None:
    start = max(0, status_index - 80)
    for index in range(status_index, start, -1):
        value = _find_next_value(lines, index, "Full Name:")
        if value:
            return value

    for index in range(status_index, start, -1):
        line = lines[index]
        if not line or line in {"TEST", "Status:", "FAIL", "PASS"}:
            continue
        if line.startswith(("KEYWORD", "Message:", "Tags:", "Start / End / Elapsed:")):
            continue
        if len(line) > 3:
            return line

    return None


def _extract_tags(lines: list[str], status_index: int) -> list[str]:
    start = max(0, status_index - 80)
    for index in range(status_index, start, -1):
        value = _find_next_value(lines, index, "Tags:")
        if value:
            return [tag for tag in re.split(r"[\s,]+", value) if tag]
    return []


def _extract_failed_keyword(lines: list[str], status_index: int) -> str | None:
    start = max(0, status_index - 120)
    end = min(len(lines), status_index + 120)
    fail_indexes = [
        index
        for index in range(status_index, end)
        if lines[index] == "FAIL" or lines[index].startswith("FAIL ")
    ]
    anchor = fail_indexes[1] if len(fail_indexes) > 1 else (fail_indexes[0] if fail_indexes else status_index)

    for index in range(anchor, start, -1):
        line = lines[index]
        if line.startswith("KEYWORD"):
            return line

    return None


def _extract_failure_text(lines: list[str], status_index: int) -> str | None:
    end = min(len(lines), status_index + 160)
    for index in range(status_index + 1, end):
        line = lines[index]
        if line == "FAIL" or line.startswith("FAIL "):
            collected = [line]
            for extra_line in lines[index + 1 : min(len(lines), index + 25)]:
                if not extra_line:
                    break
                if extra_line.startswith(("KEYWORD", "TEST", "SUITE", "INFO", "DEBUG", "TRACE")):
                    break
                collected.append(extra_line)
            return "\n".join(collected).strip()
    return None


def _extract_keyword_chain(lines: list[str], status_index: int) -> list[str]:
    start = max(0, status_index - 160)
    end = min(len(lines), status_index + 20)
    keywords = [line for line in lines[start:end] if line.startswith("KEYWORD")]
    return keywords[-8:]


def _status_fail_indexes(lines: list[str]) -> list[int]:
    indexes: list[int] = []
    for index, line in enumerate(lines):
        if line == "Status:" and any(candidate == "FAIL" for candidate in lines[index + 1 : index + 5]):
            indexes.append(index)
        elif line.startswith("Status:") and "FAIL" in line:
            indexes.append(index)
    return indexes


def extract_failed_cases_from_text(log_text: str) -> list[FailedCaseEvidence]:
    case_text = _strip_test_execution_errors(log_text)
    lines = _compact_lines(case_text)
    failed_cases: list[FailedCaseEvidence] = []

    for status_index in _status_fail_indexes(lines):
        start = max(0, status_index - 80)
        end = min(len(lines), status_index + 160)
        excerpt = "\n".join(line for line in lines[start:end] if line)

        failed_cases.append(
            FailedCaseEvidence(
                full_name=_extract_full_name(lines, status_index),
                tags=_extract_tags(lines, status_index),
                status="FAIL",
                case_message=_extract_case_message(lines, status_index),
                failed_keyword=_extract_failed_keyword(lines, status_index),
                failure_text=_extract_failure_text(lines, status_index),
                keyword_chain=_extract_keyword_chain(lines, status_index),
                raw_excerpt=excerpt[:5000],
            )
        )

    return failed_cases
