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
- Entire — checkpoints are on (`.entire/settings.json`, git-refs storage). Commits carry an `Entire-Checkpoint` trailer.
- GitHub — `origin` is https://github.com/devs-dv/first-user (visibility not confirmed).
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

### 2026-10-10 — First commit, Entire checkpoint, published rules checked

Completed:
- The builder committed and pushed the setup as `ab7458b` ("Add worker with neatlogs tracing, neathack skill and build log") to `origin/main`. The commit is dated 2026-10-10 13:48 IST, inside the hackathon window.
- `.gitignore` now ignores `*.egg-info/`, so the generated packaging metadata stays out of the repo.
- Read the published rules at https://neatlogs.com/hackathon and https://luma.com/s5blr882, and recorded the confirmed requirements under Submission below.

Evidence:
- Entire: commit `ab7458b` carries the trailer `Entire-Checkpoint: 01M4JE8CYXZ6X24DWSCN9SJM0C`. This is the first Entire evidence for the project.
- Secrets check: `git ls-files` lists no `.env` file. `worker/.env` is ignored by the root `.gitignore`.

Tests that ran:
- None this session. No code changed after `ab7458b`.

Still open from the previous entry:
- The neatlogs dashboard trace for `first-visit-test` is not yet confirmed, and `doctor --probe` has not run.

Decisions pending from the builder:
- The one-sentence problem statement for the Project section.
- Whether the GitHub repo is public. The rules require a public repository, and visibility could not be checked from this machine because the `gh` CLI is not installed.

## Demo

- URL: pending
- Instructions: pending

## Known limitations and next steps

- The worker is still a single hello-world model call. The agent that browses a founder's app and reports where it got stuck has not been built yet.
- `web/` is an unmodified Next.js scaffold.
- Next steps (planned, not started):
  1. Confirm the `first-visit-test` trace in the neatlogs dashboard and run `doctor --probe`.
  2. Build the first-visit agent loop in `worker/`. It should plan, act in the founder's app, recover from failed actions, and report where it got stuck. Wrap the entry point in a `WORKFLOW` span so each run is one trace.
  3. Capture a before-and-after pair of neatlogs traces around one agent fix, plus one run where an action failed and the agent recovered.
  4. Sign up at cfo.ai/neathacks and draft the business plan (pricing, costs, revenue, runway).
  5. Share progress publicly with #neatHack and keep the links here.

## Submission

Confirmed from https://neatlogs.com/hackathon (read 2026-10-10):
- **Window:** submissions open Monday, 12 October 2026, 7:00 PM IST and close at 11:55 PM IST. Winners are announced 16 October.
- **How to submit:** quote the official neatlogs post on X with team, name, project, public repo and demo. That post is not yet published, so the link is pending.
- **Track:** one track. Build an agent, or a team of agents, that completes a substantial task from start to finish.
- **Required tools:** neatlogs, Entire and cfo.ai. Use neatlogs and Entire to build and improve the agent, and cfo.ai to plan its business. The business plan must be part of the submission.
- **Judging weights:** agent 30%, use of neatlogs/Entire/cfo.ai 25%, demo video 20%, building in public 15%, usefulness and originality 10%.
- **Evidence judges expect:** a before-and-after pair of traces with the compared numbers, neatlogs trace links or screenshots, Entire checkpoints or entire-graph output, a cfo.ai business plan, a run showing recovery from a failed action, #neatHack public posts, and a public repo with commits dated during the hackathon.

Status of each item:
- neatlogs: tracing is wired into `worker/`. Dashboard trace not yet confirmed. Before-and-after traces pending.
- Entire: one checkpoint on `ab7458b`. More checkpoints will come as work continues.
- cfo.ai: pending (not signed up).
- Business plan: pending.
- Failure-recovery run: pending (no agent yet).
- Building in public: pending (no posts recorded).
- Public repo: `origin` exists; visibility unconfirmed.
- Demo video: pending.
- Nothing has been registered, deployed, or submitted by Claude.
