# Step 02 Initial Agent MVP Learning Record

## Date

2026-05-21

## Problem Solved

The project needed to move from brainstorming and manual Playwright validation into a maintainable first code base.

This step implements the initial Agent MVP around the first three testlines:

```text
7_5_UTE5G402T273
7_5_UTE5G402T272
7_5_UTE5G402T820
```

Each testline is configured for both `CIT` and `CRT` scans because the same testline can have both regression types.

## Files Changed And Why

```text
config/triage_config.json
```

Stores the Reporting Portal base URL, fixed group `org=VRF_HAZ_T06`, Playwright persistent profile path, CIT/CRT time rules, and the initial six scan scopes.

```text
agent/triage_agent/models.py
agent/triage_agent/config.py
```

Define typed config, health check result, row link, failed case evidence, and classification result models.

```text
agent/triage_agent/time_windows.py
agent/triage_agent/portal_urls.py
```

Implement CIT morning window calculation, CRT FB window calculation, and minimal filtered URL construction:

```text
limit=100
org=VRF_HAZ_T06
regression_status=CIT or CRT
test_line=<testline>
```

```text
agent/triage_agent/portal_health.py
```

Implements the Playwright persistent profile login health check before scans.

```text
agent/triage_agent/portal_collector.py
```

Adds the first collector for `Test Logs` and nearby report detail links from the filtered `test-runs` page.

```text
agent/triage_agent/log_extractor.py
agent/triage_agent/classifier.py
```

Adds the first `log.html` text parser and rule-based classification skeleton. The parser intentionally skips the top `Test Execution Errors` area and searches for case-level `Status: FAIL` evidence.

```text
agent/triage_agent/cli.py
agent/triage_agent/__main__.py
requirements.txt
README.md
docs/overview/roadmap.md
```

Expose CLI commands and update project recovery documentation.

## Core Call Flow

```text
triage_config.json
-> load_config()
-> build_test_runs_url()
-> check_portal_session()
-> collect_row_links_from_url()
-> extract_failed_cases_from_text()
-> classify_failed_case()
-> JSON output for later backend storage
```

## Key Fields

### Scan Scope

```text
name
regression_status
testline
```

### Portal URL

```text
base_url
limit
org
regression_status
test_line
```

### Login Health Result

```text
status: ok | expired | unknown
url
checked_at
body_text_length
console_messages
reason
```

### Failed Case Evidence

```text
full_name
tags
status
case_message
failed_keyword
failure_text
keyword_chain
raw_excerpt
```

## Server-Side Validation Commands

Run these on the Debian server from the project root after copying or syncing the project there.

### Install Dependency

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Expected result:

```text
playwright is installed
chromium browser binary exists
```

Common failure modes:

```text
Executable doesn't exist
```

Run `python -m playwright install chromium` again under the same Linux user that will run the Agent.

### Check URL Construction

```bash
PYTHONPATH=agent python -m triage_agent urls
```

Expected result:

```text
JSON list with 6 scopes
each URL contains org=VRF_HAZ_T06
each URL contains regression_status=CIT or regression_status=CRT
each URL contains one of the 3 configured testlines
```

Common failure modes:

```text
ModuleNotFoundError: No module named 'triage_agent'
```

Run with `PYTHONPATH=agent` from the project root, or install the package later after packaging is added.

### Check Persistent Login Health

```bash
PYTHONPATH=agent python -m triage_agent health
```

Expected result when login is valid:

```json
{
  "status": "ok",
  "reason": "Test Runs page loaded with a non-empty body."
}
```

Expected result when SSO expired:

```json
{
  "status": "expired",
  "reason": "The portal body is stuck at Loading..., which usually means the SSO session expired."
}
```

Common failure modes:

```text
No active accounts found
SSO LOG IN
Loading...
```

Use headed Playwright re-login with the same persistent profile, then rerun the health command.

### Collect Test Logs Links

```bash
PYTHONPATH=agent python -m triage_agent collect-links
```

Expected result:

```text
session_status is ok
6 configured scopes are scanned
each scope returns row_count and rows
rows include log_url when Test Logs links are visible
```

Common failure modes:

```text
row_count is 0 for all scopes
```

Check whether the filtered URL has matching rows for the selected date/FB, whether the session expired, or whether the page DOM text changed.

### Extract Saved log.html Text

```bash
PYTHONPATH=agent python -m triage_agent extract-log --file saved-log.html
```

Expected result:

```text
JSON list of failed case evidence
each item includes case_message, failed_keyword, failure_text, keyword_chain, and classification
```

Common failure modes:

```text
empty JSON list
```

The saved file may not contain expanded case-level failure text, or the Robot log text layout may differ from the first parser assumptions. Capture a small sanitized text sample around a failed case and update the parser rules.

## Review Questions

- Do the 6 generated URLs match the manually verified minimal URL format?
- Does `health` return `ok` after successful SSO re-login?
- Does `collect-links` find the same `Test Logs` links that were visible during manual browser validation?
- Does `extract-log` capture the case-level message and failed keyword while ignoring top-level `Test Execution Errors`?
- Which real failure messages should be added to the first rule classifier?
