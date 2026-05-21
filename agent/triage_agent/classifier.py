from __future__ import annotations

from .models import ClassificationResult, FailedCaseEvidence


RULES = [
    (
        "ue_or_radio_issue",
        "medium",
        ["ue lost", "ue disconnected", "ue is not reachable", "rach", "rrc connection", "attach failed"],
        "Check UE status, radio condition, and whether the failure reproduces on the same testline.",
    ),
    (
        "environment_issue",
        "medium",
        ["connection refused", "timeout", "no route to host", "ssh", "telnet", "resource busy"],
        "Check testline services, network reachability, and shared lab environment health.",
    ),
    (
        "testline_config_issue",
        "medium",
        ["missing parameter", "invalid config", "configuration", "topology", "ip address"],
        "Compare the testline configuration with a known passing run and recent environment changes.",
    ),
    (
        "robot_script_issue",
        "medium",
        ["keyword not found", "variable", "syntax", "no keyword with name", "attributeerror"],
        "Check Robot keyword implementation, library imports, and recent automation changes.",
    ),
    (
        "jenkins_or_infra_issue",
        "medium",
        ["workspace", "artifact", "permission denied", "disk", "executor", "jenkins"],
        "Check Jenkins executor, workspace, artifacts, and infrastructure logs.",
    ),
    (
        "product_bug_candidate",
        "low",
        ["assert", "expected", "actual", "not equal", "kpi", "alarm", "counter"],
        "Collect reproducible evidence and ask the feature owner whether this matches a product defect.",
    ),
]


def classify_failed_case(evidence: FailedCaseEvidence) -> ClassificationResult:
    haystack = "\n".join(
        value
        for value in [
            evidence.case_message or "",
            evidence.failure_text or "",
            evidence.failed_keyword or "",
            "\n".join(evidence.keyword_chain),
        ]
        if value
    ).lower()

    for category, confidence, keywords, action in RULES:
        matched = [keyword for keyword in keywords if keyword in haystack]
        if matched:
            return ClassificationResult(
                category=category,
                confidence=confidence,
                evidence=[f"Matched keyword: {keyword}" for keyword in matched[:5]],
                suggested_action=action,
            )

    return ClassificationResult(
        category="need_manual_check",
        confidence="low",
        evidence=["No first-pass rule matched the extracted failure evidence."],
        suggested_action="Open log.html and review the failed keyword chain manually.",
    )
