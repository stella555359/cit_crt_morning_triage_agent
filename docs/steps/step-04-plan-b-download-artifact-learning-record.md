# Step 04 Plan B Download Artifact Learning Record

## Date

2026-05-21

## Problem Solved

Direct `log.html` access from the Debian server is blocked by an environment/network gap:

```text
Windows can open the Test Logs link.
Debian Chromium cannot open the same Test Logs link.
```

Plan B is to avoid direct access to `10.70.226.9/logs/...` and instead look for a Reporting Portal controlled download path, such as zip, artifact, output.xml, or result archive.

The initial brainstorming document already recorded a successful Reporting Portal download URL:

```text
https://rep-portal.ext.net.nokia.com/at/test-reports/45873334/download/
```

It downloaded:

```text
robot_report.zip
```

## Files Changed And Why

```text
agent/triage_agent/cli.py
```

Adds `download-report-zip`, a direct command for the known Reporting Portal pattern:

```text
/at/test-reports/<report_id>/download/
```

Adds `extract-report-json`, a command that reads `reporting_portal.json` directly or from a downloaded zip and extracts failed case summaries from `fail_message`, `steps`, and exception fields.

```text
deploy/server_runtime_setup.md
```

Adds Plan B validation commands and expected results.

## Core Call Flow

```text
report_id
-> build /at/test-reports/<report_id>/download/
-> Playwright persistent profile
-> expect browser download
-> save robot_report.zip under /tmp/cit_crt_morning_triage_agent_downloads
-> JSON output

robot_report.zip or reporting_portal.json
-> load reporting_portal.json
-> count suites and test cases
-> extract non-passed cases or cases with fail_message/steps/exceptions
-> JSON output
```

## Key Fields

```text
suggested_filename
saved_path
report_id
download_url
results
suite_count
test_case_count
failed_case_count
failed_cases
```

## Server-Side Validation Commands

If a report id is known, directly test the known download pattern:

```bash
PYTHONPATH=agent python -m triage_agent download-report-zip --report-id 45873334
```

Or extract report id from a matching URL:

```bash
PYTHONPATH=agent python -m triage_agent download-report-zip \
  --url "https://rep-portal.ext.net.nokia.com/details/test-report/45873334/"
```

If the downloaded zip only contains `reporting_portal.json`, inspect it:

```bash
PYTHONPATH=agent python -m triage_agent extract-report-json \
  --file /tmp/cit_crt_morning_triage_agent_downloads/robot_report.zip
```

Or inspect an extracted file:

```bash
PYTHONPATH=agent python -m triage_agent extract-report-json \
  --file docs/reporting_portal.json
```

Expected result when a download is available:

```text
download_results.status = downloaded
download_results.suggested_filename is not empty
download_results.saved_path points under /tmp/cit_crt_morning_triage_agent_downloads
```

## Common Failure Modes

```text
status = session_expired
```

The Reporting Portal session expired. Re-login with the persistent profile, run `health`, and retry.

```text
results.status = failed
```

The direct `/at/test-reports/<report_id>/download/` endpoint did not trigger a browser download. Verify the report id and session state.

```text
Page.goto: Download is starting
```

This is normal for a download URL in Playwright. It means the navigation triggered a browser download. `download-report-zip` now ignores this specific navigation exception and reads `download_info.value` to save the file.

Validated result at `2026-05-21 16:27`:

```text
--attempt-download clicked Test Logs links
all attempts timed out while waiting for download
```

This happened because the first DOM-candidate rule was too broad: `log.html` URLs contain the path segment `artifact`, so they were mistaken for artifact downloads.

Validated result at `2026-05-21 16:32`:

```text
detail page has no visible zip/download/artifact button
```

The detail page has no visible zip/download/artifact button after filtering out Test Logs links. Initial documentation recovery then found that `/at/test-reports/<report_id>/download/` had already been validated earlier. The DOM-candidate exploration was removed, and `download-report-zip` now tests the direct endpoint.

Validated user finding:

```text
downloaded zip only contains reporting_portal.json
```

This means the zip is a Reporting Portal structured summary, not the full raw Robot log. `extract-report-json` checks whether that summary contains enough failed-case evidence for triage.

## Review Questions

- Does `download-report-zip` save `robot_report.zip` on Debian?
- If a zip is downloaded, does it contain `log.html` or `output.xml` for the failed case?
- If the zip only contains `reporting_portal.json`, does it include useful `fail_message` or `steps` for failed cases?
