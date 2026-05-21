# Step 03 Collector Validation Learning Record

## Date

2026-05-21

## Problem Solved

The first server-side `collect-links` validation proved that the Agent can reuse the persistent SSO profile and collect `Test Logs` URLs from the filtered Reporting Portal page.

It also showed that the initial collector was too rough:

```text
global page links
-> nearby link guessing
-> duplicate log_url values
-> unstable report_detail_url pairing
-> report_hash incorrectly parsed as test-runs
```

This step improves the collector to prefer AG Grid row-level extraction and replaces `report_hash` with `test_instance_id`.

Follow-up validation at `2026-05-21 14:37` confirmed that `test_instance_id` is now emitted, but the collector can still pair the same `test_instance_id` with multiple `log_url` values. This indicates AG Grid may render pinned/center DOM fragments separately or the row-level extraction still needs more row context.

Follow-up validation at `2026-05-21 14:47` confirmed that `row_index`, `row_text`, `test_instance_id`, and `log_url` can now be aligned to the same table row. The sample rows are historical `passed/passed` results, so the next requirement is to parse structured row fields and filter to the target triage set.

Follow-up validation at `2026-05-21 14:53` confirmed that `--triage-only` works for `cit_7_5_UTE5G402T273` on report date `2026-05-21`: the raw page has 37 rows, the CIT morning window is `2026-05-20 22:00 ~ 2026-05-21 09:00`, and the filtered triage row count is 0. This means the collector ran successfully and this scope had no `not analyzed` rows in that window.

Follow-up validation at `2026-05-21 14:56` confirmed that scanning all 6 scopes works. `cit_7_5_UTE5G402T820` returned 2 triage rows in the CIT morning window. Both rows are `CB007949_B_B4_01_Scell_Change_From_T_3F_To_3` with `result=not analyzed`, `origin_result=failed`, `build=SBTS00_ENB_9999_260520_000007`, and `run_type=CIT`.

## Files Changed And Why

```text
agent/triage_agent/models.py
```

Changed `TestRunRowLinks.report_hash` to `test_instance_id`, because the useful identifier is the `test_instance_id` query parameter from Reporting Portal detail URLs.

```text
agent/triage_agent/portal_collector.py
```

Added row-level extraction from `.ag-row`, so `Test Logs` and detail links are paired from the same table row when possible. The collector still keeps the older global-link fallback if row-level extraction returns no rows.

The follow-up fix groups `.ag-row` fragments by `row-index`, adds `row_text` and `row_index` to output, and keeps row text truncated for debugging.

The next fix parses `robotcase`, `end_time`, `result`, `origin_result`, `build`, and `run_type` from row text and log URL. It also adds `--triage-only` to filter rows by the configured CIT/CRT time window and `not analyzed` status.

```text
agent/triage_agent/cli.py
```

Adds `--max-rows` for `collect-links`, so server validation can inspect a small sample without printing the full table output.

Adds `extract-log-url`, so the next validation can open a triage row's `log_url` directly with Playwright and run the `log.html` failed case extractor without manually saving the HTML file.

The first validation hit `Page.goto: net::ERR_CONNECTION_CLOSED` on the internal HTTPS log URL. The command now retries with `http://` automatically and returns structured `navigation_failed` output if both attempts fail.

Follow-up validation at `2026-05-21 15:05` confirmed that HTTPS fails with `ERR_CONNECTION_CLOSED` and HTTP fallback succeeds, but the response body is only 26 characters and `failed_case_count` is 0. The command now outputs `response_status`, `response_content_type`, `final_url`, `title`, and `body_text_sample` to identify whether the log server returned a short error page, redirect, or placeholder.

Follow-up validation at `2026-05-21 15:10` confirmed the short response is `404 Not Found` from nginx. The internal log host is reachable, but `http://10.70.226.9/logs/Auto/...` is not a valid HTTP path. The command now continues after HTTP 4xx responses and tries a `/logs`-prefix-stripped candidate such as `http://10.70.226.9/Auto/...`.

Follow-up validation at `2026-05-21 15:18` confirmed that direct access to all generated log URL candidates still fails. The next approach is to open the Reporting Portal `report_detail_url`, inspect the detail page, find the actual `Test Logs` / `log.html` link from there, and then run the log extractor.

Follow-up validation at `2026-05-21 15:22` confirmed the detail page is accessible and contains 23 Test Logs links, but those links still point to the same unreachable internal log URLs. `extract-detail-log` now tries to click the first Test Logs link from the detail page when direct URL navigation fails, to test whether browser click behavior, Referer, or popup handling changes access.

Follow-up validation at `2026-05-21 16:01` showed `extract-detail-log` redirecting to `login.microsoftonline.com` with title `Sign in to your account`. This is an expired SSO session, not a missing Test Logs link. The command now detects this and returns `status=session_expired`.

Follow-up validation at `2026-05-21 16:09` showed that clicking the Test Logs link from the detail page opens a new page with `click_final_url=chrome-error://chromewebdata/` and empty body text. This means click behavior, Referer, and popup handling do not solve access to `10.70.226.9` from the Debian Chromium session. The command now treats `chrome-error://` and empty click pages as failure diagnostics instead of successful log extraction.

Manual comparison at `2026-05-21 16:17` confirmed that Windows can open the same Test Logs link while the Debian server cannot. The blocker is therefore Debian network/path access to the internal log static server, not Reporting Portal row extraction or Playwright click behavior.

```text
deploy/server_runtime_setup.md
```

Recorded the successful server validation and the observed duplicate/pairing issue.

## Core Call Flow

```text
collect-links
-> health check
-> open filtered URL
-> extract .ag-row links
-> group AG Grid fragments by row-index
-> find log.html or Test Logs link in the same row
-> find test_instance_id detail link in the same row
-> parse robotcase/end_time/result/origin_result/build/run_type
-> optionally filter by time window and not analyzed status
-> deduplicate by log_url + test_instance_id/detail_url
-> JSON output

extract-log-url
-> open log.html URL with Playwright
-> if HTTPS internal log URL is closed, retry with HTTP
-> if HTTP /logs path returns 404, retry without the /logs prefix
-> wait for Robot log text
-> extract failed case evidence
-> classify evidence with first-pass rules
-> JSON output

extract-detail-log
-> open Reporting Portal detail URL
-> detect Microsoft SSO login page and return session_expired if needed
-> collect Test Logs/log.html links from the detail page
-> try the selected log link with URL fallback
-> if direct navigation fails, click the Test Logs link from the detail page
-> extract failed case evidence if the log page is reachable
-> JSON output
```

## Key Fields

```text
log_url
report_detail_url
test_instance_id
row_index
row_text
robotcase
end_time
result
origin_result
build
run_type
failed_case_count
failed_cases
effective_url
final_url
response_status
response_content_type
body_text_sample
navigation_errors
detail_url
detail_body_text_sample
log_links
selected_log_url
click_fallback_used
click_final_url
click_title
click_opened_new_page
click_diagnostics
click_error
session_expired
```

## Server-Side Validation Commands

After pulling this change on the Debian server, run:

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
git -c http.proxy=http://10.144.1.10:8080 \
    -c https.proxy=http://10.144.1.10:8080 \
    pull --ff-only
PYTHONPATH=agent python -m triage_agent collect-links
```

For focused debugging:

```bash
PYTHONPATH=agent python -m triage_agent collect-links --scope cit_7_5_UTE5G402T273 --max-rows 5
```

For focused triage filtering:

```bash
PYTHONPATH=agent python -m triage_agent collect-links --scope cit_7_5_UTE5G402T273 --triage-only --report-date 2026-05-21 --max-rows 5
```

For the first log parser validation:

```bash
PYTHONPATH=agent python -m triage_agent extract-log-url \
  --url "https://10.70.226.9/logs/Auto/SBTS00/SBTS00_ENB_9999_260520_000007/348/CIT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-1/ca_cases/log.html"
```

Expected result:

```text
session_status is ok
rows contain log_url
rows contain test_instance_id when Reporting Portal detail links are available in the same AG Grid row
sample rows contain row_index and row_text
sample rows contain robotcase, end_time, result, origin_result, build, and run_type
with --triage-only, row_count only includes target-window rows whose result/origin_result is not analyzed
duplicate rows are reduced compared with the first validation
```

Validated result:

```text
2026-05-21 14:53
command: collect-links --scope cit_7_5_UTE5G402T273 --triage-only --report-date 2026-05-21 --max-rows 5
session_status: ok
raw_row_count: 37
row_count: 0
meaning: no not analyzed rows in the configured morning window for this scope
2026-05-21 14:56
command: collect-links --triage-only --report-date 2026-05-21 --max-rows 5
session_status: ok
scope with triage rows: cit_7_5_UTE5G402T820
raw_row_count: 35
row_count: 2
robotcase: CB007949_B_B4_01_Scell_Change_From_T_3F_To_3
```

Common failure modes:

```text
row_count is still high with repeated log_url and same test_instance_id
```

This means AG Grid may render duplicated pinned/center rows. The next fix should include row text or row-id based deduplication.

```text
rows contain log_url but test_instance_id is null
```

This means the detail link is not present in the same `.ag-row` DOM node. The next fix should inspect row DOM or use Reporting Portal network responses.

```text
extract-log-url returns failed_case_count = 0
```

This means the first `log.html` text parser did not match the real Robot log layout. Capture `body_text_length` and a sanitized excerpt around the failed case, then adjust the parser to the actual page text.

```text
Page.goto: net::ERR_CONNECTION_CLOSED
```

This may happen when the internal log server closes HTTPS connections. `extract-log-url` now automatically retries with HTTP and reports attempted URL errors in JSON.

```text
body_text_length is very small, such as 26
```

This means navigation technically succeeded, but the response is not the full Robot log. Inspect `response_status`, `response_content_type`, `final_url`, `title`, and `body_text_sample` to decide whether the URL is blocked, redirected, missing, or requires a different access path.

```text
response_status = 404 and body_text_sample contains nginx
```

The internal log host is reachable but the path is wrong for that protocol. `extract-log-url` now retries a candidate URL without the `/logs` prefix.

```text
all direct log URL candidates fail
```

Use `extract-detail-log` with the `report_detail_url` from the triage row to inspect the Reporting Portal detail page and find the actual Test Logs link.

```text
detail page contains Test Logs links, but all direct candidates fail
```

The command now clicks the first Test Logs link in the detail page as a final fallback.

```text
click_final_url = chrome-error://chromewebdata/
```

The browser click reached a Chrome error page. At this point, the Reporting Portal extraction works, but the Debian server cannot open the internal log static page. Investigate server network/path access or switch to an alternative artifact path such as download zip.

```text
Windows can open the Test Logs link, Debian cannot
```

This confirms an environment/network gap. The next implementation path should either restore Debian access to `10.70.226.9`, or avoid direct log static URLs and use a Reporting Portal download zip/artifact path that the Debian server can access.

```text
detail_final_url contains login.microsoftonline.com
```

The Reporting Portal session expired. Re-login with the persistent profile, rerun `health`, then rerun `extract-detail-log`.

## Review Questions

- Does the updated output replace `report_hash` with `test_instance_id`?
- Are duplicate `log_url` rows reduced?
- For a visible row in Reporting Portal, does the emitted `test_instance_id` match the row detail link?
- Do we need to extract row text fields next, such as result status, origin result, build, and case name?
- Does `--triage-only` return only yellow not analyzed rows for the target morning window?
- Does `extract-log-url` extract the failed case message and failed keyword from the first real triage row?
