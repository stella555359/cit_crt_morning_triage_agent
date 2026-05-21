# CIT/CRT Morning Triage Agent

## Project Goal

This project builds an internal morning triage assistant for daily CIT/CRT Robot Framework regression analysis.

The agent will run on a Debian server that can access the internal Robot `log.html` static server. The current preferred source is the original Playwright route: open `reporting_portal`, collect `Test Logs` links, read `log.html`, extract failed case evidence, classify likely failure categories, and expose a Morning Report through a web UI.

The email result source was explored as a fallback, but it is not the main route now. The current target server candidate is `10.57.159.149` / `tl813-agent`, because it can open `log.html` links that failed on the previous Debian server.

## Scope

The agent helps with:

- Reading filtered `reporting_portal` test run pages.
- Collecting `not analyzed` rows for target testlines and builds.
- Opening `Test Logs` / `log.html` pages.
- Extracting failed case message, failed keyword, failure text, and keyword chain.
- Applying rule-based first classification.
- Optionally generating LLM explanations from structured evidence.
- Persisting results for Web review.

The agent does not:

- Use Jenkins API or Jenkins tokens.
- Submit PRs.
- Create tickets.
- Modify `reporting_portal` status.
- Replace human triage decisions.

## Current Status

The initial feasibility validation has been recorded in:

```text
docs/overview/initial-plan-and-validation.md
```

Key validated points:

- Debian can access `reporting_portal`.
- Playwright can run headless on the server.
- Persistent browser profile can reuse SSO login.
- Filtered `test-runs` URL works with `test_line`.
- `Test Logs` links can be extracted from the filtered page.
- `log.html` can be opened and read by Playwright.
- `10.57.159.149` / `tl813-agent` can open internal `log.html` links directly after the browser certificate warning is bypassed.

Initial implementation has started with:

```text
config/triage_config.json
agent/triage_agent/
```

The first configured testlines are:

```text
7_5_UTE5G402T273
7_5_UTE5G402T272
7_5_UTE5G402T820
```

Each testline is scanned as both `CIT` and `CRT` because the same testline can have both regression types in `reporting_portal`.

## Planned Architecture

```text
systemd timer / manual trigger
-> Playwright persistent profile
-> reporting_portal filtered URL
-> extract not analyzed rows
-> open log.html
-> parse failed case message and failed keyword
-> rule-based classifier
-> optional LLM explanation
-> SQLite
-> FastAPI
-> React Morning Report dashboard
-> Nginx HTTPS
-> Windows browser
```

## First MVP

The first code MVP provides CLI commands for URL generation, login health check, Test Logs link collection, and local `log.html` text extraction:

```text
python -m triage_agent urls
python -m triage_agent health
python -m triage_agent collect-links
python -m triage_agent extract-log --file saved-log.html
python -m triage_agent extract-email-links --file samples/result-mail.eml
python -m triage_agent download-email-reports --file samples/result-mail.eml --extract-json
```

The extractor output includes `full_name`, `tags`, `status`, `case_message`, `failed_keyword`, `failure_text`, `keyword_chain`, and a first-pass rule classification.
