from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RegressionStatus(str, Enum):
    CIT = "CIT"
    CRT = "CRT"


class PortalSessionStatus(str, Enum):
    OK = "ok"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PortalConfig:
    base_url: str
    org: str
    limit: int
    profile_dir: str
    health_timeout_seconds: int = 30


@dataclass(frozen=True)
class CitTimeRule:
    start_time: str
    end_time: str


@dataclass(frozen=True)
class CrtTimeRule:
    anchor_fb: str
    anchor_start_date: str
    duration_days: int


@dataclass(frozen=True)
class TimeRules:
    timezone: str
    cit: CitTimeRule
    crt: CrtTimeRule


@dataclass(frozen=True)
class ScopeConfig:
    name: str
    regression_status: RegressionStatus
    testline: str


@dataclass(frozen=True)
class AgentConfig:
    portal: PortalConfig
    time_rules: TimeRules
    scopes: list[ScopeConfig]


@dataclass(frozen=True)
class TimeWindow:
    name: str
    start: datetime
    end: datetime
    display_label: str


@dataclass(frozen=True)
class PortalHealthResult:
    status: PortalSessionStatus
    url: str
    checked_at: datetime
    body_text_length: int
    console_messages: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True)
class TestRunLink:
    text: str
    href: str
    index: int


@dataclass(frozen=True)
class TestRunRowLinks:
    log_url: str
    report_detail_url: str | None = None
    test_instance_id: str | None = None
    row_index: str | None = None
    row_text: str | None = None
    robotcase: str | None = None
    end_time: datetime | None = None
    result: str | None = None
    origin_result: str | None = None
    build: str | None = None
    run_type: str | None = None


@dataclass(frozen=True)
class EmailLinkCandidate:
    original_url: str
    normalized_url: str
    category: str
    reason: str


@dataclass(frozen=True)
class EmailAttachmentSummary:
    filename: str | None
    content_type: str | None
    size_bytes: int | None = None


@dataclass(frozen=True)
class EmailParseResult:
    source: str
    subject: str | None
    from_address: str | None
    to_addresses: list[str]
    sent_at: str | None
    body_text_length: int
    body_text_sample: str
    link_count: int
    download_candidates: list[EmailLinkCandidate]
    portal_links: list[EmailLinkCandidate]
    jenkins_links: list[EmailLinkCandidate]
    all_links: list[EmailLinkCandidate]
    attachments: list[EmailAttachmentSummary]


@dataclass(frozen=True)
class FailedCaseEvidence:
    full_name: str | None
    tags: list[str]
    status: str | None
    case_message: str | None
    failed_keyword: str | None
    failure_text: str | None
    keyword_chain: list[str]
    raw_excerpt: str


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    confidence: str
    evidence: list[str]
    suggested_action: str


JsonDict = dict[str, Any]
