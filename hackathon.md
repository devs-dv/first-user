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
  - Anthropic Python SDK (`anthropic` 1.13.0). Brain model: `claude-sonnet-5-5` by default, `claude-haiku-5-5` with `BRAIN_MODEL=haiku`. `hello.py` uses `claude-opus-5-5`.
  - Stagehand Python SDK (`stagehand` 4.2.0) driving a local Chrome window, with `anthropic/claude-haiku-4-5` as its lookup model. That is the newest Haiku Stagehand 4.2.0 accepts.
  - neatlogs Python SDK (`neatlogs[anthropic]` 1.4.26), workflow `first-visit-test`
  - `pydantic` 2.14.0 for Stagehand extract schemas; `python-dotenv` for loading `worker/.env`
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

### 2026-10-10 — Browsing agent v1 (committed as `ac3b598`)

Not logged at the time, so this entry is recorded afterwards.

Completed:
- Added `worker/config.py`, `browser.py`, `tools.py` (`look`, `do`, `scroll`, `go_back`, `note_friction`, `finish`), `browse.py` (a hand-written Messages API tool loop under an `AGENT` span) and `run_once.py` (a CLI under a `WORKFLOW` span). Each `do` saves a screenshot to `worker/runs/<run_id>/`, which is gitignored.
- The builder committed this as `ac3b598` (2026-10-10 14:50 IST) with the trailer `Entire-Checkpoint: 01M4JHT3GYPPTJFPFBYH9XCBX8`.

Tests that ran:
- Run `20261010-140746`: outcome `achieved` on saucedemo in 10 steps.
- Run `20261010-140943`: crashed at step 18 because the Anthropic account ran out of credits. Before that it looped, reporting "Add to cart" as successful while the cart stayed empty.

Fixes:
- One action per turn (`disable_parallel_tool_use`).
- API errors now end a run with `outcome: "error"` and a JSON result instead of a traceback.

### 2026-10-10 — Cost controls and reliable clicks

Completed (cost):
- Prompt caching uses an explicit breakpoint on the system prompt, which covers tools plus system, and automatic caching for the conversation tail. The goal moved from the system prompt into the first user message, so the cached prefix is identical across runs. Look-result stubbing edits only `messages`, after the system breakpoint, so the system and tools cache survives it.
- Per-turn `max_tokens` is 2048, effort is `low` (`BRAIN_EFFORT`), and `MAX_STEPS` defaults to 15.
- `look()` now makes one Stagehand `extract` call (summary plus up to 15 items), truncates the output, and gets the URL and title from the page API. When the page fingerprint is unchanged it returns "unchanged" with no model call.
- Stagehand token deltas from `metrics()` are recorded on each tool span as `stagehand.*` attributes. Model and Stagehand tokens, plus an estimated cost, are summed into the final result JSON (`worker/costs.py`).
- A `GUARDRAIL` span (`budget_check`) runs before every model call. It stops the run with `gave_up` / `budget` above `MAX_RUN_TOKENS` (400,000) or `MAX_RUN_COST_USD` ($0.30).
- `BRAIN_MODEL` takes a model id or the alias `sonnet` or `haiku`.

Completed (clicks):
- Root cause: Stagehand's coordinate-based clicks often had no effect on saucedemo. `act` chose the right button (confirmed from its returned selector), but the click did not register, while a DOM click event did. The display runs at 125% scaling (device pixel ratio 1.25). Chrome now launches at device scale factor 1 (`DEVICE_SCALE_FACTOR`); after that, `locator.click` worked, but `act` clicks still sometimes missed.
- `do()` now fingerprints the page (URL plus a hash of visible text and form values) before and after. If `act` reports success but nothing changed, the result is `no_effect`. It then works through a recovery ladder, with each rung in its own span:
  - (a) `act(instruction)`
  - (b) `observe` then `act(action)`
  - (c) the observed selector through the locator API: `locator.click`, then `send_click_event`

  The result reports the rung that worked. If every rung fails, the model is told plainly and the case is recorded as an `agent_issue`, not as site friction.

Tests that ran (`python measure_clicks.py`, no brain model; log in, then add one item to the cart, 5 fresh browsers):

| | End-to-end success | Steps that changed the page | Reported success, nothing changed | Stagehand tokens |
|---|---|---|---|---|
| Before (plain `act`, scale 1.25) | 0/5 | 15/20 | 5 (every "Add to cart") | 40,786 |
| After (ladder, scale 1.0) | 5/5 | 20/20 | 0 | 53,139 |

After the change, "Add to cart" succeeded on rung (c) in all 5 attempts. Rung (a) failed every time even at scale 1.0, so the ladder, not the scale fix, is what made it reliable.

Brain comparison on the saucedemo goal (estimated cost uses list prices in `config.py`):

| Brain | Run | Outcome | Steps | Total tokens | Estimated cost |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | `20261010-150417` | achieved | 8 | 36,914 | $0.0172 (model $0.0010, Stagehand $0.0162) |
| `claude-sonnet-5-5` | `20261010-150521` | achieved | 8 | 36,509 | $0.0345 (model $0.0181, Stagehand $0.0163) |

- Caching worked in both runs: about 2,100 tokens were cache reads from step 2, and each later turn wrote only about 130–220 new tokens.
- A guardrail check with `MAX_RUN_COST_USD=0.001` stopped the run with `gave_up` / `budget` after 1 step (total $0.0021). That run's first request read the 2,127-token prefix from the cache, which shows reuse across runs.

Not yet verified:
- Whether the `stagehand.*` and `do.rung` span attributes show up in the neatlogs dashboard. They are set through OpenTelemetry's current span, which the neatlogs SDK itself uses.
- The ladder's agent-issue path in a full agent run. In both brain runs every action worked on rung (a).

## Demo

- URL: pending
- Instructions: pending

## Known limitations and next steps

- The agent has been tested on one demo site (saucedemo) with one easy goal. Both brains found no friction there, so the friction report is untested on a site that has real problems.
- Stagehand lookups are about 94% of a Haiku-brain run's cost: Stagehand 4.2.0 does not accept Claude Haiku 5.5, so lookups run on Haiku 4.5.
- With Sonnet at low effort, the `thought` field is often a fragment ("Open the cart.") rather than the first-person sentence the prompt asks for. Haiku followed the instruction.
- `web/` is an unmodified Next.js scaffold.
- Next steps (planned, not started):
  1. Confirm the `first-visit-test` traces and span attributes in the neatlogs dashboard, and run `doctor --probe`.
  2. Run the agent on a site with real friction to test the friction report and the agent-issue path.
  3. Try routing Stagehand's lookups through a cheaper model (Stagehand accepts an LLM callback in place of a model name).
  4. Sign up at cfo.ai/neathacks and draft the business plan (pricing, costs, revenue, runway). Per-run cost numbers are now available from the result JSON.
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
- neatlogs: every agent run is traced (`WORKFLOW` → `AGENT` → LLM, TOOL and `GUARDRAIL` spans). Dashboard not yet confirmed. Before-and-after numbers for the click fix are in the build log; matching trace links are pending.
- Entire: checkpoints on `ab7458b` and `ac3b598`. This session's work is uncommitted.
- cfo.ai: pending (not signed up).
- Business plan: pending. Measured cost per saucedemo run is about $0.017 (Haiku brain) and $0.034 (Sonnet brain).
- Failure-recovery run: the recovery ladder recovered "Add to cart" in 5 of 5 measurement attempts. A full agent run that shows recovery is still pending.
- Building in public: pending (no posts recorded).
- Public repo: `origin` exists; visibility unconfirmed.
- Demo video: pending.
- Nothing has been registered, deployed, or submitted by Claude.
