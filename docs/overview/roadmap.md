# Project Roadmap

## Current Project

`CIT/CRT Morning Triage Agent`

## Main Goal

Build a Debian-hosted internal assistant that automates the repetitive part of daily CIT/CRT Robot result triage.

当前主路线恢复为“Playwright + Reporting Portal + 直接读取 `log.html`”：

```text
reporting_portal filtered page
-> not analyzed Robot cases
-> Test Logs / log.html
-> failed case message and failed keyword extraction
-> first-pass classification
-> Web Morning Report
-> human review
```

邮件结果源已探索，但暂不作为主路线：

```text
daily result email
-> report/log download links
-> robot_report.zip / reporting_portal.json
-> failed case summary extraction
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
- 原 Debian 服务器无法稳定打开部分 Windows 可访问的 `10.70.226.9` `log.html`。
- 换到 `10.57.159.149`（`tl813-agent`）后，Debian 浏览器可以直接打开同类 `log.html`。
- 手工浏览器首次打开会看到 `NET::ERR_CERT_AUTHORITY_INVALID` 隐私告警；Playwright 命令应使用 `ignore_https_errors=True` 处理该自签/内部证书问题。

Not yet validated:

- Stable extraction of case-level `Status: FAIL`, `Message`, failed keyword, failure text, and keyword chain from `log.html`.
- 在 `10.57.159.149` / `tl813-agent` 上执行 `extract-log-url`，确认 Playwright headless 能绕过证书告警并读取 `log.html` 正文。

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

### Phase 0.5: Server Selection And Direct Log Validation

优先在 `10.57.159.149`（`tl813-agent`）验证直接 `log.html` 读取。

Initial command:

```text
python -m triage_agent extract-log-url --url "<log.html URL>"
```

Expected behavior:

```text
status = ok
body_text_length > 0
failed_case_count is printed
failed_cases contains case-level evidence when the log has failed cases
```

Common failure modes:

```text
NET::ERR_CERT_AUTHORITY_INVALID
```

手工 Chrome 会显示隐私告警，这是内部证书问题。CLI 中的 Playwright context 已设置 `ignore_https_errors=True`，正常情况下不需要人工点击 Advanced。

```text
navigation_failed / ERR_CONNECTION_CLOSED / chrome-error://chromewebdata/
```

说明当前服务器仍无法访问对应日志静态服务器，需要换到可访问的 Debian 节点或继续排查网络路由。

### Phase 0.6: Email Result Source Validation

邮件结果源已经实现为备用探索路线，但当前不作为主路线。

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
