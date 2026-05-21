# Project Roadmap

## Current Project

`CIT/CRT Morning Triage Agent`

## Main Goal

Build a Debian-hosted internal assistant that automates the repetitive part of daily CIT/CRT Robot result triage.

当前主路线调整为“邮件结果源优先，Reporting Portal 页面扫描保留为备用验证路线”：

```text
daily result email
-> report/log download links
-> robot_report.zip / reporting_portal.json
-> failed case summary extraction
-> first-pass classification
-> Web Morning Report
-> human review
```

原始 Reporting Portal 页面路线仍保留：

```text
reporting_portal filtered page
-> not analyzed Robot cases
-> Test Logs / log.html
-> failed case message and failed keyword extraction
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
- Debian 服务器无法稳定打开部分 Windows 可访问的 `10.70.226.9` `log.html`。
- 邮件里如果包含 nightly result 的下载链接，应优先从邮件解析下载入口，减少对 Reporting Portal 页面和 SSO 持久登录态的依赖。

Not yet validated:

- Stable extraction of case-level `Status: FAIL`, `Message`, failed keyword, failure text, and keyword chain from `log.html`.
- Real server execution of the first CLI commands added under `agent/triage_agent`.
- 从真实 nightly 结果邮件 `.eml/.msg` 中提取下载链接，并在 Debian 上成功下载 report/log 包。

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
agent/triage_agent/email_collector.py
agent/triage_agent/cli.py
```

## Execution Order

### Phase 0.5: Email Result Source Validation

先验证一封真实 nightly 结果邮件是否能作为更稳定的数据入口。

Initial commands:

```text
python -m triage_agent extract-email-links --file samples/result-mail.eml
python -m triage_agent download-email-reports --file samples/result-mail.eml --extract-json
```

Expected behavior:

```text
extract subject / sent_at / download_candidates / portal_links / jenkins_links
unwrap Outlook Safe Links when present
convert Reporting Portal report ids to /at/test-reports/<id>/download/
download candidate report/log packages with the existing Playwright profile
parse reporting_portal.json when the downloaded package contains it
```

Common failure modes:

```text
email contains only a Reporting Portal page link and no download link
download link still requires interactive SSO
.msg can only be parsed best-effort unless optional extract_msg is installed
downloaded zip contains only passed cases, so failed evidence cannot be validated
```

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
