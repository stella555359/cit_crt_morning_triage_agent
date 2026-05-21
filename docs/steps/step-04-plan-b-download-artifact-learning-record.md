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

## Files Changed And Why

```text
agent/triage_agent/cli.py
```

Adds `inspect-detail-assets`, a command that opens a Reporting Portal detail URL, inspects links/buttons for download-like entries, optionally opens `More` menus, and can optionally attempt downloads.

```text
deploy/server_runtime_setup.md
```

Adds Plan B validation commands and expected results.

## Core Call Flow

```text
report_detail_url
-> Playwright persistent profile
-> open Reporting Portal detail page
-> detect SSO login expiry
-> collect links and buttons
-> click More menus unless disabled
-> identify download/zip/artifact/output candidates
-> optional: click candidates and save downloaded files
-> JSON output
```

## Key Fields

```text
candidate_count
download_candidate_count
candidates
download_candidates
opened_more
attempt_download
download_results
suggested_filename
saved_path
```

## Server-Side Validation Commands

First inspect candidates without clicking download:

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
PYTHONPATH=agent python -m triage_agent inspect-detail-assets \
  --url "https://rep-portal.ext.net.nokia.com/reports/test-runs/?test_instance_id=35764397&ordering=-end&end_db=365"
```

Expected result:

```text
status is ok
candidate_count is printed
download_candidate_count is printed
candidates and download_candidates are printed
```

If download candidates exist, attempt download:

```bash
PYTHONPATH=agent python -m triage_agent inspect-detail-assets \
  --attempt-download \
  --url "https://rep-portal.ext.net.nokia.com/reports/test-runs/?test_instance_id=35764397&ordering=-end&end_db=365"
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
download_candidate_count = 0
```

The detail page does not expose a visible download/zip/artifact entry in the DOM. Next step is to inspect network requests or search for hidden backend API calls.

```text
download_results.status = failed
```

The candidate was visible but did not trigger a browser download. Review the candidate text/href and try headed mode to observe the UI.

Validated result at `2026-05-21 16:27`:

```text
--attempt-download clicked Test Logs links
all attempts timed out while waiting for download
```

This happened because the first download-candidate rule was too broad: `log.html` URLs contain the path segment `artifact`, so they were mistaken for artifact downloads. The rule now excludes candidates whose text contains `Test Logs` or whose href contains `log.html`.

## Review Questions

- Does the detail page expose any zip/download/artifact/output candidates?
- Does clicking `More` reveal new candidates?
- Does `--attempt-download` save any file on Debian?
- If a zip is downloaded, does it contain `log.html` or `output.xml` for the failed case?
