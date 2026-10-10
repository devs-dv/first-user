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
  - Stagehand Python SDK (`stagehand` 4.2.0) driving a local Chrome window. Its lookups go through our callback (`lookup_model.py`) to `claude-haiku-5-5` on the neatlogs-wrapped client. `LOOKUP_VIA=model_name` switches back to `anthropic/claude-haiku-4-5` called by Stagehand itself; that is the newest Haiku Stagehand 4.2.0 accepts by name.
  - neatlogs Python SDK (`neatlogs[anthropic]` 1.4.26), workflow `first-visit-test`
  - `pydantic` 2.14.0 for Stagehand extract schemas; `python-dotenv` for loading `worker/.env`
  - `supabase` 2.32.0 (Python) for the job queue: `main.py` claims queued runs, `enqueue.py` adds one from the command line.
  - `egress.py`: a local filtering proxy that every browser request goes through.
- `web/` — Next.js 16.4.0 / React 19.3.0 app with Tailwind 4. Landing form, `POST /api/runs`, `GET /api/runs/[id]` and a live run report. It talks to Supabase only from the server, with `@supabase/supabase-js` 2.117.2; no model calls.
- Supabase — Postgres (`runs`, `steps`, `frictions`, with RLS on and no policies, service role only) and a public Storage bucket `screenshots`. Schema in `supabase/schema.sql`.
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

### 2026-10-10 — Supabase job queue (committed as `6a08b29`)

Not logged at the time, so this entry is recorded afterwards.

Completed:
- `supabase/schema.sql`: `runs`, `steps` and `frictions` tables (RLS on, no policies, granted to `service_role` only), a `claim_run()` function using `FOR UPDATE SKIP LOCKED`, and a public `screenshots` bucket.
- `worker/db.py` (enqueue, claim, steps, frictions, finish/fail, stale-run sweep, screenshot upload) and a `RunRecorder` that writes each step, friction and screenshot as it happens. `run_once.py` still works without a database.
- `worker/main.py`: a worker loop that claims one run at a time inside `neatlogs.identify(session_id="run_<id>")`. It marks runs still running after 15 minutes as failed, and on the first Ctrl+C it finishes the current run before flushing neatlogs once. `worker/enqueue.py` queues a run from the command line.
- The builder committed this as `6a08b29` (2026-10-10 16:36 IST) with the trailer `Entire-Checkpoint: 01M4JQVWZEF4R78NT2M170VMW8`.

Tests that ran:
- The worker loop against an in-memory fake of `db.py`, with Ctrl+Break sent at step 2. The run finished (`achieved`, 9 steps, $0.0248) and every step reached the recorder. The worker then stopped without claiming another run, shut neatlogs down once, and exited 0.
- `run_once.py` with no database: `achieved` in 9 steps, $0.0243.

Not yet verified:
- Anything against a real Supabase project (schema, RPC, inserts, storage uploads).

### 2026-10-10 — Web app

Completed:
- `web/` is now the product front end. It reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from `web/.env.local` on the server only. The client module imports `server-only`, so the build fails if browser code ever imports it.
- Landing page (`/`): the one-line promise, a URL field, an optional goal, a required "This is my app or I have permission to test it" checkbox, and a plain note that we click around like a visitor, may create a test account, and never enter payment details.
- `POST /api/runs` validates the URL. It accepts only http(s) on the default port with no credentials. It rejects localhost and `.local`/`.internal`-style names, private, loopback, link-local, CGNAT and other reserved IPv4/IPv6 ranges (including IPv4-mapped and NAT64 forms), and hosts that resolve to any of them. An empty goal gets a default goal.
- Limits are enforced in one SQL function, `enqueue_web_run`, under an advisory lock so concurrent requests cannot race past them: at most 20 queued runs, and 5 runs per visitor per hour. Visitors are identified by an HMAC of the IP, stored as the new `runs.ip_hash` column; the raw IP is never stored.
- `GET /api/runs/[id]` returns the run, steps and frictions, without the IP hash or the raw worker error.
- `/run/[id]` polls every 2 seconds until the run is done or failed. While running it shows the status and each step as it arrives (thought, action, result, screenshot). When finished it shows a report: the outcome and reason, frictions split into "Problems with the site" and "Our agent's own issues", the step timeline, time, cost, a copy-link button, and the line "This is a simulated user. Treat findings as leads to check."
- Unhappy states each have their own message: invalid URL, queue full (503), rate limited (429 with Retry-After), run failed, run not found.

Tests that ran:
- `tsc`, ESLint and `next build` passed. A scan of the built browser bundle found no key, no Supabase client code and no server env variable names.
- 14 requests against the running app returned the expected rejection, among them localhost, `:8080`, 192.168.x.x, 169.254.169.254, `::ffff:127.0.0.1`, `2130706433`, a nonexistent domain, and `localtest.me` (a public name that resolves to 127.0.0.1).
- Against a local fake of Supabase's REST API: a normal enqueue (201), queue full (503), rate limited (429), and done, failed, queued and missing runs.
- Every run-page state rendered in Chrome at 390 px with no horizontal scroll. The running page picked up new steps and stopped polling when the run finished.

Not yet verified:
- `schema.sql` and the end-to-end flow (web → queue → worker → report) on a real Supabase project.
- Light mode, and the landing form's inline errors in a real browser.

Security note: an automated review flagged that the URL is checked only at submission. The worker's browser resolves names again and follows redirects, so it could still be steered to a private address. Fixed in the next entry.

### 2026-10-10 — Egress guard in the worker

Completed:
- `worker/egress.py`: a local proxy that every request from Chrome must go through. Chrome launches with `--proxy-server` pointing at it, `<-loopback>` to remove Chrome's built-in localhost bypass, and WebRTC limited to proxied connections.
- For each new host the guard resolves the name itself, refuses it if any address is not public, and then connects only to an address it checked. Not public means private, loopback, link-local (including the 169.254.169.254 metadata address), CGNAT, unique-local, multicast or reserved, with IPv4-mapped and NAT64 forms unwrapped. Connecting to the checked address, rather than resolving again, stops DNS rebinding. Because the check happens per connection, redirects, subresources and websockets are all covered.
- Each check runs in a neatlogs `GUARDRAIL` span (`egress_check`), once per host per run.
- A refused request ends the run as `blocked`, with a reason naming the host and address. The check runs before every model call and once more after the loop. A host that simply does not resolve is refused quietly and does not end the run.
- Stagehand's built-in extension connects from inside Chrome to Chrome's own DevTools port, so that tunnel is allowed, but only when its first request carries a `chrome-extension://` Origin. Pages cannot forge that header. The check runs in a `GUARDRAIL` span (`devtools_check`). This also closes a gap that existed before: Stagehand launches Chrome with `--remote-allow-origins=*`, so a page could previously have connected to DevTools.

Tests that ran (`python -m unittest test_egress`, 6 tests, all pass):
- Address rules for blocked and allowed addresses.
- Through the proxy, plain HTTP to 127.0.0.2, a tunnel to `localhost`, and the metadata IP all got 403, and the private test server received 0 requests.
- The DevTools port refused a page Origin and accepted an extension Origin.
- An unresolvable host got 502 and did not count as a safety block.
- Redirect test in a real Chrome window through `first_visit`: a public-looking origin returned a 302 to `127.0.0.2`. The private server received 0 requests, and the run ended `blocked` with 0 steps (no model call).
- Negative control: with Chrome's loopback bypass left on, the same redirect test fails (the private server got 2 requests), so the test depends on the guard.
- A real visit to saucedemo through the guard (Haiku brain): `achieved` in 9 steps, $0.0292, no requests refused.

Failure found and fixed during the session:
- The first real run failed with "CDP websocket failed to open". Once loopback went through the guard, Stagehand's extension could not reach Chrome's DevTools port. The fix is the extension-only DevTools rule above.

Not yet verified:
- Whether the `egress_check` and `devtools_check` spans nest under the run in the neatlogs dashboard. The guard copies the run's context when it starts so they should.

### 2026-10-10 — Stagehand lookups traced through our own client

Completed:
- `worker/lookup_model.py`: a bring-your-own-LLM `generate` callback, written to the contract in the Stagehand docs ([Custom models](https://docs.stagehand.dev/v4/configuration/models.md), Python tab). Stagehand calls it for every act, observe and extract inference. It calls `claude-haiku-5-5` through a `neatlogs.wrap(AsyncAnthropic())` client, so every lookup is now a real neatlogs LLM span with tokens and prompt.
  - Text and image content blocks are mapped to Anthropic blocks.
  - The answer is reliable JSON: the requested schema becomes the input schema of one tool, and `tool_choice` forces that tool. A schema whose root is not an object is wrapped and unwrapped.
  - Stagehand's system prompt is cached (`cache_control`). Stagehand's temperature is dropped, because Claude Haiku 5.5 rejects non-default sampling parameters.
  - Token usage goes back to Stagehand in the result's `usage` field. Cached tokens are counted inside input tokens, as Stagehand expects.
- `LOOKUP_VIA` in `config.py` picks the path: `callback` (default) or `model_name`, the old path where Stagehand calls `anthropic/claude-haiku-4-5` itself.
- Nesting: Stagehand runs the callback in a task started by its RPC reader, so it does not inherit the calling tool's context. `look` and do rungs (a) and (b) are marked `@lookups_nest_here`; the callback runs in a copy of the calling function's context, so each LLM span sits under the tool span that caused it.
- `costs.py`: each model call is now counted once. Lookup cost comes from our own callback responses; Stagehand's `metrics()` is kept only to cross-check it. On the old path, cost comes from `metrics()` as before. The `stagehand.*` token and cost attributes on tool spans are gone, because the LLM spans now carry those numbers.
- `worker/check_costs.py`: runs one visit and compares three sources: our accounting, Stagehand's `metrics()`, and the LLM spans, collected locally from the same tracer provider that exports to neatlogs (passed to `neatlogs.init(tracer_provider=...)`).

Tests that ran:
- `measure_clicks.py --mode ladder --attempts 5`: 5/5 end-to-end, 20/20 steps changed the page, 0 reported success with no change. That is the same rung pattern as before: "Add to cart" worked on rung (c) every time. 72,335 lookup tokens for $0.0063, compared with 53,139 tokens on Haiku 4.5. Claude Haiku 5.5 counts the same text as about 30% more tokens, but costs a tenth as much per token. Our token count equals Stagehand's `metrics()` exactly.
- `check_costs.py` on saucedemo (Haiku brain, run `check-20261010-220653`): `achieved` in 9 steps, $0.00468 in total (brain $0.0014, lookups $0.00328). The earlier Haiku-brain run on the old path cost $0.0292. All 8 checks passed:
  - lookup calls (11) and tokens are equal in our accounting and in the spans;
  - our lookup input, output and cache reads equal Stagehand's prompt, completion and cached tokens;
  - brain tokens are equal in our accounting and in the spans;
  - the cost computed from the spans equals the run total;
  - every lookup span's parent is a tool span: 6 under `look`, 4 under `do.rung_a_act` and 1 under `do.rung_b_observe_act`.
- `LOOKUP_VIA=model_name`, 1 attempt: 4/4 steps changed the page, $0.0115. The old path still works.
- `python -m unittest test_egress`: 6 tests pass.

Evidence: `evidence/2026-10-10-traced-lookups/` holds the measurement and the cost check JSON.

Not yet verified:
- How the nested lookup spans look in the neatlogs dashboard.

### 2026-10-10 — Egress guard shuts down cleanly

Completed:
- `EgressGuard` now keeps track of each open connection's task. `close()` stops accepting connections, cancels the open ones and waits for them to finish. Before this, a run could end with "Task was destroyed but it is pending!" for `EgressGuard._handle`.

Tests that ran:
- The new test `test_close_cancels_open_connections` checks that closing the guard with an idle connection open finishes within 2 seconds and leaves no handler task running.
- `python -m unittest test_egress`: 7 tests (the 6 earlier ones plus the new one), run 4 times, with no pending-task warnings.
  - Runs 2–4: all tests passed.
  - Run 1: the real-browser redirect test errored with a Windows `PermissionError`. Chrome's temporary profile folder could not be deleted inside `browser.close()`, which runs before the guard closes. That test passed on its own right after, and in runs 2–4.
- `measure_clicks.py --mode ladder --attempts 5`: 5/5 end-to-end, 20/20 steps changed the page, no pending-task warnings.

Not yet fixed:
- The occasional `PermissionError` when Stagehand deletes Chrome's temporary profile on Windows.

## Demo

- URL: pending
- Instructions: pending

## Known limitations and next steps

- The agent has been tested on one demo site (saucedemo) with one easy goal. Both brains found no friction there, so the friction report is untested on a site that has real problems.
- Stagehand lookups are still about 70% of a Haiku-brain run's cost ($0.0033 of $0.0047), down from about 94% on Haiku 4.5.
- With Sonnet at low effort, the `thought` field is often a fragment ("Open the cart.") rather than the first-person sentence the prompt asks for. Haiku followed the instruction.
- Nothing has run against a real Supabase project yet, including the schema and the web-to-worker flow.
- The rate limit trusts `X-Forwarded-For`. That is only safe behind a proxy that sets it, such as Vercel.
- Screenshots are in a public bucket, so anyone with a screenshot's URL can open it. A private bucket with signed URLs is safer before real users.
- Any refused request ends the run, including a stray third-party resource on a private address, such as a leftover `localhost` dev script. That is safe but strict.
- The egress guard runs inside the worker process. A firewall or egress policy on the worker host would be a second layer; none is set up.
- Next steps (planned, not started):
  1. Confirm the `first-visit-test` traces and span attributes in the neatlogs dashboard, and run `doctor --probe`.
  2. Run the agent on a site with real friction to test the friction report and the agent-issue path.
  3. Sign up at cfo.ai/neathacks and draft the business plan (pricing, costs, revenue, runway). Per-run cost numbers are now available from the result JSON.
  4. Share progress publicly with #neatHack and keep the links here.

## Submission

Confirmed from https://neatlogs.com/hackathon (read 2026-10-10):
- **Window:** submissions open Monday, 12 October 2026, 7:00 PM IST and close at 11:55 PM IST. Winners are announced 16 October.
- **How to submit:** quote the official neatlogs post on X with team, name, project, public repo and demo. That post is not yet published, so the link is pending.
- **Track:** one track. Build an agent, or a team of agents, that completes a substantial task from start to finish.
- **Required tools:** neatlogs, Entire and cfo.ai. Use neatlogs and Entire to build and improve the agent, and cfo.ai to plan its business. The business plan must be part of the submission.
- **Judging weights:** agent 30%, use of neatlogs/Entire/cfo.ai 25%, demo video 20%, building in public 15%, usefulness and originality 10%.
- **Evidence judges expect:** a before-and-after pair of traces with the compared numbers, neatlogs trace links or screenshots, Entire checkpoints or entire-graph output, a cfo.ai business plan, a run showing recovery from a failed action, #neatHack public posts, and a public repo with commits dated during the hackathon.

Status of each item:
- neatlogs: every agent run is traced (`WORKFLOW` → `AGENT` → LLM, TOOL and `GUARDRAIL` spans), and Stagehand's lookups are LLM spans under the tool that caused them. Dashboard not yet confirmed. Before-and-after numbers for the click fix are in the build log; matching trace links are pending.
- Entire: checkpoints on `ab7458b`, `ac3b598`, `51e480b`, `6a08b29` and `29543ae` (web app, egress guard and report fixes). The traced-lookup change is uncommitted.
- cfo.ai: pending (not signed up).
- Business plan: pending. Measured cost per saucedemo run is $0.0047 with the Haiku brain and traced Haiku 5.5 lookups; it was $0.017–0.029 with Haiku 4.5 lookups. The Sonnet brain ($0.034 on the old path) has not been re-measured.
- Failure-recovery run: the recovery ladder recovered "Add to cart" in 5 of 5 measurement attempts. A full agent run that shows recovery is still pending.
- Building in public: pending (no posts recorded).
- Public repo: `origin` exists; visibility unconfirmed.
- Demo video: pending.
- Nothing has been registered, deployed, or submitted by Claude.
