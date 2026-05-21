# Step 01 Learning Record: SSO Session Health Check

## Problem Solved

During feasibility validation, Playwright persistent profile was proven usable while the `reporting_portal` SSO/MSAL session was valid. A later retry showed that the same profile can expire and leave the page stuck at `Loading...`, while browser console logs show:

```text
No active accounts found. Trying to login silently...
```

This step records the required design change: every scan must start with a login health check. If login state is expired, the agent must stop scanning and hand off a clear re-login action to the user.

## Files Changed

- `docs/overview/roadmap.md`
  - Added the SSO expiration finding.
  - Added `Phase 1: Login Health Check`.
  - Shifted later phases accordingly.
- `docs/overview/initial-plan-and-validation.md`
  - Added the session expiration finding under persistent profile validation.
  - Added concrete expired-session indicators.
  - Added login health check to the recommended architecture.
  - Updated Phase 0 and risk handling.
- `docs/steps/step-01-sso-session-health-check-learning-record.md`
  - This learning record.

## Core Flow

```text
scheduled scan / manual trigger
-> open baseline reporting_portal URL
-> watch console messages and page body
-> detect expired SSO/MSAL state
-> if expired: mark session_expired and stop
-> if valid: continue to filtered test-runs URL
```

## Key Fields

Suggested runtime status fields:

```text
portal_session_status: ok | expired | unknown
portal_session_checked_at
portal_session_error
last_successful_scan_at
relogin_required: true | false
```

Expired-session indicators:

```text
console contains "No active accounts found"
body text is only "Loading..." plus footer
body contains "SSO LOG IN"
Test Runs table is not loaded within 30 seconds
```

Expected handoff message:

```text
reporting_portal login expired, manual re-login required
```

## Validation Handoff

No server validation was run by the assistant. The user should continue validating on the Debian server.

Suggested server-side validation command after re-login:

```bash
source ~/pw-smoke/bin/activate
python <health-check-smoke-script>.py
```

Expected result:

```text
portal_session_status: ok
body contains Test Runs table text
filtered URL contains Test Logs
```

Common failure modes:

- `No active accounts found`: SSO session expired; re-login with persistent browser profile.
- `Loading...` only: treat as session expired or page API not loaded; do not interpret as no data.
- `SSO LOG IN`: profile is not authenticated.
- Timeout waiting for table: mark `unknown` or `expired`, stop scan, and expose action in Web UI.

## Review Questions

- Should the first implementation step be a standalone `portal_health_check.py` script?
- Should the Web dashboard show a dedicated banner for `login expired`?
- Should the re-login procedure be documented under `deploy/` once VNC/noVNC or headed browser usage is finalized?
