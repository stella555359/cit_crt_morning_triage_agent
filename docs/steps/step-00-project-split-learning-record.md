# Step 00 Learning Record: Split To Independent Project

## Problem Solved

The initial `CIT/CRT Morning Triage Agent` plan was first recorded inside the resume knowledge base. Because the agent will become a deployable project with code, server runtime, browser profile handling, backend, frontend, and Git-based management, it should live as an independent project under `C:\TA`, similar to `jenkins_robotframework`.

## Files Changed

- `README.md`
  - New project entry point and scope summary.
- `.gitignore`
  - Ignores runtime data, browser profiles, databases, environment files, Playwright state, frontend build output, and Python caches.
- `docs/overview/initial-plan-and-validation.md`
  - Main brainstorming and feasibility record migrated into the independent project.
- `docs/overview/roadmap.md`
  - Project-level roadmap and phase order.
- `docs/steps/step-00-project-split-learning-record.md`
  - This learning record.

The earlier knowledge-base copy under `C:\TA\resume` was intentionally left in place to avoid unapproved deletion.

## Core Flow

```text
Debian server
-> Playwright persistent reporting_portal profile
-> filtered test-runs URL
-> not analyzed Robot case rows
-> Test Logs / log.html
-> failed case evidence extraction
-> rule classification
-> optional LLM explanation
-> SQLite / FastAPI
-> React Morning Report
-> Windows browser review
```

## Key Fields

Planned triage case fields:

```text
testline
build
run_type
robotcase
result
origin_result
log_url
report_detail_url
full_name
tags
status
case_message
failed_keyword
failure_text
keyword_chain
suggested_category
confidence
human_final_category
pr_id
ticket_id
review_note
```

## Validation Handoff

This step created documentation and project skeleton only. No server validation is required.

Optional local checks for the user:

```powershell
cd C:\TA\cit_crt_morning_triage_agent
Get-ChildItem -Recurse
```

Expected result:

```text
README.md
.gitignore
docs\overview\initial-plan-and-validation.md
docs\overview\roadmap.md
docs\steps\step-00-project-split-learning-record.md
agent\
backend\
frontend\
deploy\
samples\
```

Common failure modes:

- Project directory missing: confirm `C:\TA\cit_crt_morning_triage_agent` exists.
- Markdown opened with encoding issues: reopen as UTF-8.
- Confusion with old resume copy: use this independent project as the source for future implementation.

## Review Questions

- Should the project name remain `cit_crt_morning_triage_agent`?
- Should Phase 1 start with a pure parser script in `agent/`?
- Should FastAPI and React be implemented from scratch here, or reuse patterns from `jenkins_robotframework`?
