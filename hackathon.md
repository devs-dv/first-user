# neatHack — First User

## Project

- **Name:** First User
- **Purpose:** An AI agent that uses a founder's web app like a first-time customer and reports where it got stuck.
- **Problem:** Pending.

## Team

- **Team name:** test
- **Members:** Divyanshu Verma (solo)

## Stack

- `worker/` — Python 3.11 worker; the only service that calls a model.
  - Anthropic Python SDK (`anthropic` 1.13.0), model `claude-opus-5-5`
  - neatlogs Python SDK (`neatlogs[anthropic]` 1.4.26), workflow `first-visit-test`
  - `python-dotenv` for loading `worker/.env`
- `web/` — Next.js 16.4.0 / React 19.3.0 app (scaffold only so far; no model calls).
- Entire — repo is configured (`.entire/settings.json`); how it supports the agent is pending.
- cfo.ai — pending (not set up yet).

## Build log

### 2026-10-10 — neatHack setup and neatlogs tracing

Completed:
- Saved the neatHack skill from https://neatlogs.com/hackathon/skill to `.claude/skills/neathack/SKILL.md`.
- Created this `hackathon.md`.
- Installed `neatlogs[anthropic]` (1.4.26) into `worker/.venv` with `pip install -U`, as the [Python SDK docs](https://docs.neatlogs.com/sdk/python) instruct.
- Added tracing to `worker/hello.py` only: `neatlogs.init()` with `workflow_name="first-visit-test"` and the key read from `NEATLOGS_API_KEY` in the environment, `neatlogs.wrap()` around the Anthropic client, and `neatlogs.flush()` plus `neatlogs.shutdown()` at the end. `load_dotenv()` runs before `init()`, as the docs require. No other behavior changed.

Tests that ran:
- `python -m neatlogs doctor --local --json` passed (`neatlogs.doctor/v2`, schema `2`, 4 spans captured, 0 dropped).
- `python worker/hello.py` exited 0. The model replied and the SDK shut down cleanly.

Not yet verified:
- Whether the trace appears in the neatlogs dashboard under `first-visit-test`.
- `python -m neatlogs doctor --probe --json` (authenticated probe) has not run.

## Demo

- URL: pending
- Instructions: pending

## Known limitations and next steps

- The worker is still a single hello-world model call. The agent that browses a founder's app and reports where it got stuck has not been built yet.
- `web/` is an unmodified Next.js scaffold.
- Next: confirm the trace in the neatlogs dashboard, then build the first-visit agent loop in `worker/`.

## Submission

- Rules, deadlines, judging, and the submission link: pending. Check https://neatlogs.com/hackathon and https://luma.com/s5blr882.
- The neatHack skill says every project must use neatlogs, Entire, and cfo.ai, and that the submission must include a business plan made with cfo.ai. This is not yet confirmed against the published rules.
  - neatlogs: tracing is wired into `worker/` (see Build log).
  - Entire: configured in the repo; evidence pending.
  - cfo.ai: pending.
  - Business plan: pending.
- Nothing has been registered, deployed, or submitted.
