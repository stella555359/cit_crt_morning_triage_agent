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

Common failure modes:

```text
row_count is still high with repeated log_url and same test_instance_id
```

This means AG Grid may render duplicated pinned/center rows. The next fix should include row text or row-id based deduplication.

```text
rows contain log_url but test_instance_id is null
```

This means the detail link is not present in the same `.ag-row` DOM node. The next fix should inspect row DOM or use Reporting Portal network responses.

## Review Questions

- Does the updated output replace `report_hash` with `test_instance_id`?
- Are duplicate `log_url` rows reduced?
- For a visible row in Reporting Portal, does the emitted `test_instance_id` match the row detail link?
- Do we need to extract row text fields next, such as result status, origin result, build, and case name?
- Does `--triage-only` return only yellow not analyzed rows for the target morning window?
