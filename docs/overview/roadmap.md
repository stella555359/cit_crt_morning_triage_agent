# Project Roadmap

## Current Project

`CIT/CRT Morning Triage Agent`

## Main Goal

Build a Debian-hosted internal assistant that automates the repetitive part of daily CIT/CRT Robot result triage:

```text
reporting_portal filtered page
-> not analyzed Robot cases
-> Test Logs / log.html
-> failed case message and failed keyword extraction
-> first-pass classification
-> Web Morning Report
-> human review
```

## Current Status

Phase 0 feasibility is mostly complete, and the initial code MVP has started.

Validated:

- Playwright can access `reporting_portal`.
- Persistent browser profile can reuse SSO login.
- Filtered URL using `test_line` works.
- `Test Logs` links can be extracted.
- `log.html` can be opened and read.
- Report zip download can be triggered as a fallback.

Added finding:

- Persistent profile works only while the SSO/MSAL session is valid.
- The session can expire and leave the page stuck at `Loading...`.
- The agent must perform a login health check before each scan and stop with a clear re-login handoff if the session is expired.

Not yet validated:

- Stable extraction of case-level `Status: FAIL`, `Message`, failed keyword, failure text, and keyword chain from `log.html`.
- Real server execution of the first CLI commands added under `agent/triage_agent`.

Implemented locally in the project:

```text
config/triage_config.json
agent/triage_agent/config.py
agent/triage_agent/time_windows.py
agent/triage_agent/portal_urls.py
agent/triage_agent/portal_health.py
agent/triage_agent/portal_collector.py
agent/triage_agent/log_extractor.py
agent/triage_agent/classifier.py
agent/triage_agent/cli.py
```

## Execution Order

### Phase 1: Login Health Check

Build a pre-scan health check that opens a baseline `reporting_portal` URL and detects expired SSO state before any triage scan.

Initial command:

```text
python -m triage_agent health
```

Expired session indicators:

```text
console contains "No active accounts found"
body shows only "Loading..." plus footer
body contains "SSO LOG IN"
Test Runs table is not loaded within 30 seconds
```

Expected behavior:

```text
mark session_expired
stop scan
show re-login handoff in the Web UI
```

### Phase 2: Extractor MVP

Build a local script that accepts one `log.html` URL and returns structured failed case evidence.

Initial command for saved `log.html` text or HTML:

```text
python -m triage_agent extract-log --file saved-log.html
```

Output:

```text
full_name
tags
status
case_message
failed_keyword
failure_text
keyword_chain
```

### Phase 3: Portal Row Collector

Build a script that opens a filtered `reporting_portal` URL and extracts rows with:

```text
testline
build
run_type
robotcase
result
origin_result
log_url
report_detail_url
```

Initial command:

```text
python -m triage_agent collect-links
```

### Phase 4: Rule Classifier

Classify extracted evidence into:

```text
product_bug_candidate
ue_or_radio_issue
environment_issue
testline_config_issue
robot_script_issue
jenkins_or_infra_issue
known_issue
need_manual_check
```

### Phase 5: Backend + Storage

Use FastAPI + SQLite for:

- Manual triage trigger.
- Triage run storage.
- Triage case storage.
- Human review fields.

### Phase 6: Web Dashboard

Use React to show:

- Morning summary.
- Case list.
- Case detail.
- Human review fields.

### Phase 7: Scheduled Agent

Use systemd timer or cron on Debian to run every morning.

### Phase 8: LLM Explanation

Add LLM explanation only after rule-based extraction and classification are stable.

## Verification Policy

Do not proactively run long validation or server verification commands from the assistant. The user runs server commands and pastes results back for review.
