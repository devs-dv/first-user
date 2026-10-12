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

### 2026-10-11 — Trace quality: screenshots, prompt templates, detection strings

Completed:
- **Screenshots in traces.** `do()` uploads its screenshot through the run's recorder (`RunRecorder.upload_screenshot`) and puts the public URL in its output as `screenshot_url`, so neatlogs can show a preview on the tool span.
  - With no database (`run_once.py`, `check_costs.py`), the field is left out.
  - A failed upload is logged and the field is omitted; the action itself still counts.
  - The URL is removed from what the brain model sees. The same URL goes to the `steps` row, so the screenshot is uploaded only once.
- **Prompt templates.** Following the [neatlogs prompt-templates docs](https://docs.neatlogs.com/sdk/prompt-templates), every model call is wrapped in `neatlogs.trace(kind="LLM")` with a `SystemPromptTemplate` and a `UserPromptTemplate`.
  - Agent loop (`visitor_turn`): the static system prompt, and the first message with `{{goal}}` and `{{url}}`.
  - Lookup callback (`stagehand_<format>`): Stagehand's system prompt as sent, and `{{stagehand_request}}`, which holds Stagehand's instruction plus the page.
  - The system prompt is still sent as a cached block.
- `worker/repro_system_prompt.py` makes two tiny calls. Locally, A (`repro_A_system_as_string`) records the system message as plain text, and B (`repro_B_system_as_cached_blocks`) records it as a JSON list of blocks.
- **Fixed result shapes for detections** (below). `do()` always returns the same keys in the same order. The run result adds `stopped_by`, `friction_count` and `agent_issue_count`, and each friction and agent issue carries a `kind`. A tool exception now reaches the model as `{"kind": "tool_error", "error": ...}`. The custom `do.rung` / `do.via` span attributes are gone, because the same values are now in the output.
- **Shutdown crash fixed.** `check_costs.py` crashed at exit (access violation while garbage-collecting an asyncio transport, found with `-X faulthandler`). The brain and lookup Anthropic clients are now closed before the event loop ends.

Detection strings. Span outputs are `json.dumps` text: a space after each colon, lowercase `true`/`false`, and non-ASCII escaped. Tool results are in `neatlogs.tool.output`; the run result is in `neatlogs.agent.output` (`persona_run`) and `neatlogs.workflow.output` (`first_visit`).

| Match | Where | Meaning |
|---|---|---|
| `"changed": false` | `do` | No recovery rung changed the page |
| `"kind": "agent_issue"` | `do`, run result | Our browser tool failed, not the site |
| `"reason": "no_effect"` | `do` | A rung reported success but the page did not change |
| `"reason": "failed"` | `do` | Every rung errored or reported failure |
| `"reason": "worked_after_retry"` | `do` | Worked on rung b or c |
| `"rung": "b"` / `"rung": "c"` | `do` | Which retry worked (`"rung": "none"` when none did) |
| `"via": "locator.send_click_event"` | `do` | Only a DOM click event worked |
| `"unchanged": true` | `look` | The page had not changed since the last look |
| `"outcome": "achieved"` / `"gave_up"` / `"blocked"` / `"max_steps"` / `"error"` | run result | How the visit ended |
| `"stopped_by": "budget"` | run result | Stopped by the budget guardrail |
| `"stopped_by": "egress_guard"` | run result | Stopped by the egress guard |
| `"stopped_by": "max_steps"` | run result | Ran out of steps |
| `"stopped_by": "api_error"` / `"refusal"` / `"max_tokens"` | run result | A model call failed |
| `"stopped_by": "finish"` | run result | The agent called finish |
| `"agent_issue_count": [1-9]` (regex) | run result | At least one agent issue |
| `"friction_count": [1-9]` (regex) | run result | At least one site friction |
| `"severity": "high"` | `note_friction` input, run result | A blocking site problem |
| `"ok": false` | `budget_check` (GUARDRAIL) | The budget was exceeded |
| `"private": true` | `egress_check` (GUARDRAIL) | A private address was refused |

Tests that ran (cheap saucedemo visits, Haiku brain, `check_costs.py`):
- `check-20261011-071223` (no recorder) and `check-20261011-071322` (`--stub-recorder`, placeholder `https://stub.invalid/...` URLs; nothing was written to Supabase): both `achieved` in 9 steps, $0.0044 each, all 14 checks passed, exit code 0.
  - Cost: our accounting, Stagehand's `metrics()` and the LLM spans agree.
  - Nesting: every LLM call sits directly under exactly one `trace(kind="LLM")` span, and token counts appear only on the provider span.
  - Screenshots: with the stub, all 4 `do` outputs had `screenshot_url`; without it, none did. The brain model's inputs never contained it.
- Two earlier runs that day (`070720`, `071004`) ended in that exit crash before the client fix. The checks in `071004` passed.
- `python -m unittest test_egress`: 7 tests pass.
- `repro_system_prompt.py` ran: neatlogs 1.4.26, anthropic 1.13.0.

Evidence: `evidence/2026-10-11-trace-quality/`.

Found, not fixed:
- In neatlogs 1.4.26 the template text reaches 0 of 20 spans; only the template variables are recorded. The SDK adds template text only to spans whose kind or name marks them as LLM when they start, and the Anthropic wrapper's `anthropic.messages.create` span does not match. Details and a question for the neatlogs team are in `NEATLOGS_NOTES.md`.
- Each model call now exports as two `llm` spans: the internal `trace()` span and the provider span. Whether the dashboard merges them is not confirmed.
- The real Supabase upload path has not run. Only the stub has.
- In this run the agent recorded "the first Add to cart click had no effect" as low-severity site friction, although the retry message comes from our own ladder. The `do` message may need rewording so retries are not reported as site problems.

### 2026-10-11 — Plain-string system prompts, retry wording, first real queue run

Completed:
- **System prompt as a plain string.** The agent loop and the lookup callback now send `system` as a plain string, so neatlogs records it as text. The cache breakpoints moved off `system`: one on the last tool definition, and one on the first user message. The prefix order is tools, then system, then messages, so the system prompt stays inside a cached prefix. The agent loop also keeps its automatic breakpoint on the conversation tail.
- **Template wrapper removed.** The `neatlogs.trace(kind="LLM")` template wrapper is gone from both places. On neatlogs 1.4.26 it added a second LLM span per call and still did not record template text. The finding stays in `NEATLOGS_NOTES.md`.
- **Retry wording.** After a retry, `do()` now says: "The action worked. Our browser tool needed a retry to operate the element: that was a problem with our tool, not with the website. A real visitor would not have noticed it, so do not record it with note_friction and do not mention it as a problem with the site."
- **`check_costs.py`** now checks three more things: one LLM span per model call, the system prompt recorded as plain text, and a cache read on every agent turn after the first.

Tests that ran:
- Cost before and after, same saucedemo goal, Haiku brain:

| Run | Steps | Brain | Lookups | Total | Lookup cache write / read |
|---|---|---|---|---|---|
| Before: `check-20261011-071223` (cached system block) | 9 | $0.00123 | $0.00319 | $0.00442 | 0 / 8,085 |
| After: `check-20261011-072637` (plain-string system, new breakpoints) | 8 | $0.00131 | $0.00427 | $0.00558 | 22,983 / 1,998 |

  - **Agent loop:** caching still works. Every turn after the first read 2,110–3,330 tokens from the cache, and the cost per turn is about the same as before.
  - **Lookups:** 34% more expensive. Their first user message holds the page, which changes on almost every call. The breakpoint there writes about 2,000 tokens to the cache at 1.25× the input price each time, and the cache is rarely read back. Before, the breakpoint sat after Stagehand's system prompt, which repeats across calls.
  - **Option, not measured:** dropping the user-message breakpoint for lookups alone should land between the two runs (about $0.0039 by estimate), but the lookup system prompt would then not be cached.
  - **All checks:** 13 of 13 passed.
- **First real visit through the queue,** with `main.py` (Haiku brain) and `enqueue.py`, against the real Supabase project:
  - Run `e889c99a-b837-41b3-8775-a9fe97bb5ab5`: `achieved` in 8 steps, $0.00389, 0 frictions, 0 agent issues. The worker stopped cleanly on Ctrl+Break (exit code 0).
  - The four `do` steps each have `screenshot_url` in their result, equal to the `screenshot_path` column. Each is a public Storage URL that returns 200 `image/png` with no credentials. The last screenshot shows the backpack in the cart.
  - The "Add to cart" step again worked only on rung (c). With the new wording the agent did not record it as friction (0 frictions, compared with 1 low-severity friction in the earlier run).
  - The run's `agent_version` is `cea6d04`, the last commit; the changes from this session are not committed yet.
- `python -m unittest test_egress`: 7 tests pass.

Evidence: `evidence/2026-10-11-trace-quality/check-20261011-072637-costs.json`.

Not yet verified:
- How the plain-string system prompt and the single LLM spans look in the neatlogs dashboard.
- The web app's run page for this real run.

### 2026-10-11 — Lookup cache breakpoint on the tool only

Completed:
- The lookup callback no longer puts a cache breakpoint on the first user message. Only the tool definition carries one. The agent loop is unchanged: breakpoints on the last tool and the first user message, plus the automatic one on the conversation tail.

Tests that ran (same saucedemo goal, Haiku brain, `check_costs.py`):

| Lookup caching | Run | Steps | Brain | Lookups | Total | Lookup cache write / read |
|---|---|---|---|---|---|---|
| Cached system block (before) | `check-20261011-071223` | 9 | $0.00123 | $0.00319 | $0.00442 | 0 / 8,085 |
| Tool + first user message | `check-20261011-072637` | 8 | $0.00131 | $0.00427 | $0.00558 | 22,983 / 1,998 |
| Tool only (now) | `check-20261011-080803` | 8 | $0.00132 | $0.00374 | $0.00506 | 1,263 / 1,998 |

- `achieved` in 8 steps, all 13 checks passed, exit code 0, and no friction was recorded for the rung (c) retry.
- Lookups now cost about 17% more than with the cached system block ($0.00374 against $0.00319), because Stagehand's system prompt is no longer cached. That is the price of showing it as plain text in neatlogs.

Evidence: `evidence/2026-10-11-trace-quality/check-20261011-080803-costs.json`.

### 2026-10-11 — Eval harness and v0 baseline

Completed:
- `evals/sites.json`: 10 cases, 7 achievable and 3 broken (saucedemo's `locked_out_user`, `problem_user` and `error_user`).
  - Every URL was opened and every flow was carried out with plain browser actions, with no model calls, in the worker's own browser setup. All 10 are marked verified, with what was seen.
  - `uitestingplayground.com` works only over `http://` (its HTTPS certificate fails).
  - The two herokuapp login and dynamic-loading pages take about 35 s to load in Chrome, with or without the egress proxy, while `curl` gets them in under 2 s. They were kept, with a note.
- `evals/run.py --version V`: queues each case as a run with source `eval`, waits for the separately running worker, judges each broken case with one `claude-haiku-5-5` call (forced tool, `EVALUATOR` span, judged text printed), and writes `evals/results/V.json` and `V.md`. It flushes and shuts down neatlogs at the end.
- `supabase/schema.sql` gains `runs.eval_version`. The column is not in the live database yet, so v0's label is only in the results file.

v0 baseline (agent `ec2bbcc`, Haiku brain; no agent changes made for the eval):

| Metric | v0 |
|---|---|
| Completion rate (achievable) | 3/7 |
| False-praise rate (broken) | 0/3 (but see below) |
| Stopped by budget or step limit | 2 |
| agent_issue frictions | 11 |
| Median steps | 9.5 (2 runs had no steps) |
| Total cost | $0.0430 (runs $0.0426, judge $0.0004) |

- The two herokuapp cases failed before the first step: `page.goto` gave up after 15 s.
- `todomvc_react` (gave_up, 5 agent issues) and `uitesting_click` (blocked, 3 agent issues) failed through our browser tool on sites that plain actions completed.
- Both `problem_user` and `error_user` ran out of steps (15) without calling finish.
- **Judge caveat:** for `error_user`, the judge counted three `agent_issue` entries ("no_effect" on typing the last name and on Finish) as naming the known issue. The report files those as our own tool's problems, though, not the site's, so a founder would read them as our bug. By hand this is closer to false praise.

Evidence: `evals/results/v0.json`, `v0.md`, `v0.log` (includes the judged text).

### 2026-10-11 — Agent changes from the v0 baseline, and eval v1

Completed (uncommitted when v1 ran; the runs are labelled `a953b37`, the last commit):
- **Page loading** (`visit.py`): the first navigation waits for `domcontentloaded` with a 45 s cap (`PAGE_READY_TIMEOUT_MS`), not the full load event. After the cap, the visit continues with whatever has rendered.
- **Rung d** (`do.rung_d_mouse`): a trusted mouse click at the element's centre through `page.click(x, y)`, for elements that ignore scripted click events. With no observed element, it picks the checkbox or toggle whose surrounding text best matches the instruction. A zero-size checkbox is clicked through its label.
- **Change detection.** This was not on the requested list, but rung d needs it. The page fingerprint now also covers `class` and ARIA state attributes, and, for click actions, focus moving into a text field. Typing actions leave focus out, so moving into an empty field is not counted as typing into it.
- **Wrap-up** (`WRAP_UP_STEPS=2`): with 2 steps left, the agent is told to conclude and call finish. On its last step, it is told to call finish now.
- **Hidden errors** (`page_watch.py`): a script on every page records JS errors, unhandled rejections, `console.error`, fetch/XHR responses of 4xx/5xx and failed resource loads.
  - Each `do` result includes `page_error_count` and `page_errors`, and so does its step record. These cover the page's own site only, and the cross-origin "Script error." is ignored.
  - A `do` with no effect while page errors occurred is recorded as site friction (`"kind": "site_problem"`, `"reason": "page_errors"`), not `agent_issue`.
- **Verifier** (`verifier.py`, `EVALUATOR` span `verify_goal`, `claude-haiku-5-5`): after `finish(achieved)`, it gets only the goal and a fresh read of the final page (URL, title, visible text, form fields with passwords hidden, and a screenshot).
  - If it disagrees, the outcome becomes `unverified`, with its reason. The agent's own reason is kept as `agent_reason`, and `verification` is added to the run result.
  - Its cost is counted in `costs.py`, and `check_costs.py` checks it.
  - The web app shows `unverified` as "Said it reached the goal, but we could not confirm it".
- **Eval:** "completed" now requires the verifier to agree. `run.py --compare-to v0` adds side-by-side tables.

Tests that ran:
- Without a model, on real pages:
  - The fingerprint caught the uitesting button turning green, and rung d's mouse click worked.
  - Rung d found and ticked the todomvc "Buy milk" toggle from the instruction text.
  - On saucedemo `error_user`, each broken "Add to cart", the last-name field and "Finish" produced a JS error that was captured.
- `check_costs.py` on herokuapp login: `achieved` in 6 steps, verifier agreed, all checks passed, $0.0029.
- `python -m unittest test_egress`: 7 tests pass.
- **Eval v1:** the user's worker was stopped while idle, and a fresh worker ran the new code with the Haiku brain, like v0.

| Metric | v0 | v1 |
|---|---|---|
| Completion rate (achievable) | 3/7 | 2/7 |
| False-praise rate (broken) | 0/3 | 1/3 |
| Stopped by budget or step limit | 2 | 0 |
| agent_issue frictions | 11 | 2 |
| Site frictions found through page errors | – | 2 |
| Verifier disagreed with "achieved" | – | 2 |
| Failed runs | 2 | 0 |
| Median steps | 9.5 | 8.0 |
| Total cost | $0.0430 | $0.0470 |

Fixed:
- `herokuapp_login` completes.
- `herokuapp_dynamic_loading` no longer fails before step 1.
- `error_user` now names the site's JS error as a site problem and concludes as blocked.
- No run hit the step limit.
- `agent_issue` frictions fell from 11 to 2.

Not fixed or regressed:
- **Verifier too strict for process goals.** `herokuapp_dynamic_loading` and `herokuapp_add_remove` were marked unverified although their step records show the agent did the task. The verifier wanted evidence of the steps, which a final page cannot show.
- **`uitesting_click`.** The click worked on rung a, but the agent reads only page text, could not see the colour change and gave up.
- **`todomvc_react`.** Clicking the new-to-do input still had no effect on every rung. The agent gave up instead of typing, which worked in v0.
- **`practice_hammer` (regression).** The search changed the page, but the agent's next look described the unfiltered list. It logged that as site friction, took the category-filter route and was cut off by the wrap-up notice.
- **`saucedemo_problem_user` (new false praise).** Typing the last name changed the page (the bug moves it into the first-name field), so it counted as success. The agent never looked again. Its reason also dismissed two "Add to cart" retries as "browser-tool retries, which are not site problems", following the retry wording from the earlier session.

Possible next steps (not started): tell the verifier that the final state is the evidence for process goals; give the brain a screenshot after `do`; look again after typing into form fields; rethink the retry wording so broken site buttons are not dismissed.

Evidence: `evals/results/v1.json`, `v1.md`, `v1.log`.

### 2026-10-11 — Verifier with the run's factual record, three verdicts, and eval v2

Completed:
- **What the verifier sees** (`worker/verifier.py`). It still never sees the agent's thoughts, notes or finish reason. It now gets the factual record of the run (`ctx.record`, built by `record_step` in `browse.py`): each action's instruction, whether the page changed, the URL afterwards, any page errors, and the `look()` summaries. It also gets a fresh read of the final page (text, form fields, screenshot).
- **Three verdicts, each with a short reason:**
  - `verified` keeps the outcome `achieved`.
  - `contradicted` makes it `not_achieved`, with the verifier's reason shown and the agent's kept as `agent_reason`.
  - `unverified` makes it `achieved_unconfirmed`, shown in the web app as "Reached the goal, not independently confirmed".
- **Eval scoring** (`evals/run.py`). It reports "completed and verified" and "completed but unverified" separately, and contradicted counts as not completed. False praise counts both `achieved` and `achieved_unconfirmed` as claimed success. `--compare-to v0 v1` shows any number of versions side by side.

Tests that ran:
- `check_costs.py` on `herokuapp_add_remove`, the process goal v1's verifier wrongly rejected: `verified`, citing the three "Add Element" clicks that changed the page and the two remaining Delete buttons. All checks passed, $0.0037.
- **Eval v2:** a fresh worker on the new code with the Haiku brain, like v0 and v1.

| Metric | v0 | v1 | v2 |
|---|---|---|---|
| Completed and verified (achievable) | – | 2/7 | 4/7 |
| Completed but unverified (achievable) | 3/7 | – | 0/7 |
| Contradicted by the verifier | – | – | 0 |
| False-praise rate (broken) | 0/3 | 1/3 | 1/3 |
| Stopped by budget or step limit | 2 | 0 | 0 |
| agent_issue frictions | 11 | 2 | 5 |
| Site frictions found through page errors | – | 2 | 3 |
| Failed runs | 2 | 0 | 0 |
| Median steps | 9.5 | 8.0 | 7.5 |
| Total cost | $0.0430 | $0.0470 | $0.0490 |

v0 had no verifier, so its completions are the agent's own "achieved" and count here as unverified. v1's verifier was yes/no and looked only at the final page.

- **Verifier:** all 4 "achieved" verdicts were `verified`, none were `contradicted` or `unverified`, and none looked wrong when I read the step records.
- **`herokuapp_dynamic_loading`:** now completed and verified. v1's final-page-only verifier had rejected it.
- **`practice_hammer`:** completed and verified again, after giving up in v1. The difference came from the agent's own route, not from this change.
- **`herokuapp_add_remove` (blocked):** the page raised "Uncaught ReferenceError: $ is not defined" on each "Add Element" click. The site's slow jQuery had not loaded yet, so the agent correctly blamed the site. Run to run this case depends on herokuapp's script loading, not on the verifier.
- **Still failing:**
  - `todomvc_react`: input clicks have no effect.
  - `uitesting_click`: the agent cannot see the colour change.
  - `saucedemo_problem_user` (false praise again): the agent reported entering "Jane Doe" and never noticed that the last name had gone into the first-name field.

Evidence: `evals/results/v2.json`, `v2.md`, `v2.log`.

### 2026-10-11 — Trace integrity, four agent improvements, screenshot masking, and eval v3

Completed (Part A, trace integrity):
- `worker/check_traces.py` runs visits in one event loop, like the worker, and collects every span from the provider that exports to neatlogs. It checks: one trace per visit, no orphan or unexported parents, every span ended, nothing ending after the root, and no ERROR span on a normal run. It also runs guard scenarios: the guard outside a run, the guard closed mid-check, and a refusal inside a run.
- **The egress guard no longer traces host checks.** A refused request gets one `egress_refused` GUARDRAIL span, created synchronously in the run's context. A guard outside an active neatlogs run (tests, scripts) creates no spans. Each visit ends with one `egress_summary` span (hosts checked, allowed, unresolved, refused), and the summary is also in the run result.
- **Each run's neatlogs trace id** is returned as `trace_id` and saved in the new `runs.trace_id` column (`supabase/schema.sql`). Until that column exists, runs are saved without it and the worker prints one warning.

| | Before | After |
|---|---|---|
| Traces per visit | 1, 1, 1 | 1, 1, 1 and 1, 1, 1 |
| Orphan / ERROR / unended spans | 0 / 0 / 0 | 0 / 0 / 0 |
| Guard outside a run | 2 standalone traces | 0 spans |
| Guard closed mid-check | span cut off (UNSET) | no span |
| Spans in one uitesting visit | 60 | 23 |

The "Trace processing failed" state of runs `c350f9b9` and `ab9d9bd4` was not reproduced. The standalone 2-span traces came from the guard running outside a visit.

Completed (Part B, agent):
1. **Vision.** `look()` attaches a screenshot that the brain sees as an image.
2. **Typing.** A "click the text field" instruction with nothing to type returns "nothing to do, typing focuses the field" instead of running the ladder. Rung d can type: a trusted click to focus, then the keyboard.
3. **Read-back.** Typing results include the focused field's label and actual value, and flag when the typed text is not in it. The verifier's record includes it too.
4. **Readiness.** When an action has no effect and the page reports a "not loaded yet" error ("... is not defined", chunk-load errors), it waits up to 15 s for the page to finish loading and runs the ladder once more.

Completed (screenshot masking): `worker/trace_media.py` is passed as `neatlogs.init(mask=...)` in `main.py`, `run_once.py` and `check_costs.py`. It replaces inline base64 images in exported spans with `[screenshot omitted from trace, N KB: <public URL>]`. The model still gets the real image. `look()` and the verifier upload their screenshots when a database is configured.

| Exported LLM spans, one uitesting visit | Before | After |
|---|---|---|
| Brain call carrying a look() screenshot | 75-76 KB | 10-12 KB |
| Verifier call | 56 KB | 7 KB |
| All LLM spans in the visit | 321 KB | 78 KB |

Eval v3 (fresh worker, Haiku brain):

| Metric | v0 | v1 | v2 | v3 |
|---|---|---|---|---|
| Completed and verified (achievable) | – | 2/7 | 4/7 | 4/7 |
| Completed but unverified (achievable) | 3/7 | – | 0/7 | 0/7 |
| Contradicted by the verifier | – | – | 0 | 1 |
| False-praise rate (broken) | 0/3 | 1/3 | 1/3 | 0/3 |
| Stopped by budget or step limit | 2 | 0 | 0 | 0 |
| agent_issue frictions | 11 | 2 | 5 | 4 |
| Site frictions found through page errors | – | 2 | 3 | 2 |
| Failed runs | 2 | 0 | 0 | 2 |
| Median steps | 9.5 | 8.0 | 7.5 | 9.5 |
| Total cost | $0.0430 | $0.0470 | $0.0490 | $0.0504 |

- **Fixed in v3:**
  - `todomvc_react` completed and verified for the first time: the agent typed straight in.
  - `saucedemo_problem_user` named its bug, so there was no false praise: the read-back showed the Last Name field empty after typing 'Doe'.
  - `uitesting_click`: the agent saw the button turn green.
- **Verifier error:** for `uitesting_click` the verifier returned `contradicted`, while its own reason says the green button is "consistent with the click" and only the before-colour is undocumented. That is `unverified` at most.
- **Failed runs:** `herokuapp_dynamic_loading` and `herokuapp_add_remove` finished their visits, but closing Chrome raised the Windows profile-cleanup `PermissionError`, which failed both runs. In add/remove, the readiness retry waited, but jQuery never loaded on herokuapp, so the agent concluded blocked.
- **Uploads:** the Supabase `screenshots` bucket rejects `image/jpeg`, so `look()` screenshots were not uploaded in v3, and their placeholders had no URL.

Fixed after v3 (not yet run in an eval):
- `look()` screenshots are PNG, which the bucket accepts.
- A `PermissionError` from Chrome's profile cleanup is logged and no longer fails a finished run.
- `python -m unittest test_egress`: 7 tests pass.

Still open:
- The verifier's choice between `contradicted` and `unverified` when it lacks a before-state.
- herokuapp's slow and sometimes missing scripts.

Evidence: `evals/results/v3.json`, `v3.md`, `v3.log`.

### 2026-10-11 — Security fix: an API key in a trace; verifier calibration; eval v4

**Incident.** A neatlogs trace (12:04 PM) recorded an Anthropic API key as span input. Cause: `judge(client, ...)` in `evals/run.py` was a traced function that took the Anthropic client as its first argument. The neatlogs decorator records a function's arguments and walks an object's public attributes, so `client.api_key` was captured. All four evals (v0 to v3) ran that judge, 3 judge spans each. The key has been rotated; those 12 judge traces should be deleted in the neatlogs dashboard.

Completed:
- **Traced functions no longer receive secrets or live objects.**
  - `judge()` takes only strings (`case_id`, `known_issue`, `text`); its client is created inside the module and closed at the end.
  - `first_visit`, `run_persona` and `verify` take objects (a recorder, a run context, a page). They use `capture_input=False` and record their plain-value input explicitly with `trace_safety.set_input()`.
  - Every other traced function was checked: they take strings, numbers and dicts only.
- **The neatlogs mask now redacts secrets** (`worker/trace_safety.py`, installed in `main.py`, `run_once.py`, `check_costs.py` and `evals/run.py`), in every string of a span: attributes, events, status and name.
  - Key shapes: Anthropic and other `sk-` keys, JWTs (Supabase service and anon keys), `sb_secret_` and `sb_publishable_` keys, `Bearer` tokens, and `x-api-key:` and `Authorization:` header text.
  - The exact value of every secret-named environment variable of the process (names containing KEY, TOKEN, SECRET, PASSWORD, ...), whatever its shape. This covers the neatlogs key without reading `.env`.
  - Values of fields named `api_key`, `key`, `token`, `secret`, `password` or `authorization` and close variants, including inside JSON text.
  - Counts and ordinary names are untouched (`max_tokens`, `token_count`, `prompt_key`).
  - It then replaces inline screenshots (`trace_media.py`). It never raises: on failure it falls back to regex-only redaction, and drops the span if even that fails.
- **Tests** (`test_trace_safety.py`, 14 tests; fake keys are assembled at run time so no key-shaped string is in the repo). Spans go through neatlogs' own `MaskingSpanExporter` into an in-memory exporter, and the tests check that:
  - a client and a config object passed as traced arguments arrive redacted;
  - keys in free text, headers, exception events and span names arrive redacted;
  - an environment secret of any shape is redacted, and an unrelated variable is not;
  - a secret next to a screenshot is redacted and the screenshot is replaced;
  - ordinary telemetry is untouched;
  - a static scan of every traced function fails if one takes a client, config, context, page, recorder or similar without `capture_input=False`.
- **Negative controls:** with an identity mask, the fake key leaks; with the real mask it does not; the original `judge(client, ...)` signature is flagged by the scan.
- **End to end**, a real visit and the real judge, with a recording mask counting secrets before and after redaction: 24 spans in the visit and 4 in the judge, 0 secret values and 0 key-shaped strings before the mask (the leak is fixed at its source) and 0 after.
- **Search for key-shaped strings** (`worker/scan_secrets.py`: paths, line numbers and counts only, never values): the working tree (including `evals/results`, `evidence`, `hackathon.md` and the gitignored `worker/runs`), and every commit on every ref (38 at the time; rescanned after the docs were written: 49, same result).
  - **Result: 0 matches**, for key shapes and for the exact values of the 5 secret-named environment variables of the process. `worker/.env` and `web/.env.local` are gitignored and not tracked.
  - The scan loads `worker/.env` the way the worker does and does not read `web/.env.local`. It covers the web app's key only if that is the same value as the worker's.

Completed (verifier calibration):
- "contradicted" now needs positive evidence that is present: an error message, a wrong result, or an action that was tried and did not change the page. Missing evidence (no before-state, a thin record, a result that might already have been there) is "unverified". The prompt says so and gives examples.
- The verdict tool requires a quoted `contradicting_evidence`; a "contradicted" without it is downgraded to "unverified" in code. An empty record is shown as "nothing recorded; says nothing about success".
- Real-model check, 3 runs per case (`worker/calibrate_verifier.py`):

| Case | Expected | Before the change | After |
|---|---|---|---|
| Button turned green, no before-state | unverified (or verified) | contradicted in v3 | unverified 3/3 |
| Empty record, final page shows the result | unverified | contradicted 3/3 (first attempt at the prompt) | unverified 3/3 |
| Error "locked out" on the page | contradicted | | contradicted 3/3 |

- `test_verifier.py`, 7 tests with the model mocked: the downgrade guard, pass-through of the other verdicts, and that the agent's thoughts and finish reason never reach the verifier.

Eval v4 (fresh worker, Haiku brain; includes the PNG and cleanup-error fixes):

| Metric | v0 | v1 | v2 | v3 | v4 |
|---|---|---|---|---|---|
| Completed and verified (achievable) | – | 2/7 | 4/7 | 4/7 | **5/7** |
| Completed but unverified (achievable) | 3/7 | – | 0/7 | 0/7 | 0/7 |
| Contradicted by the verifier | – | – | 0 | 1 | 0 |
| False-praise rate (broken) | 0/3 | 1/3 | 1/3 | 0/3 | 0/3 |
| Stopped by budget or step limit | 2 | 0 | 0 | 0 | 0 |
| agent_issue frictions | 11 | 2 | 5 | 4 | 3 |
| Site frictions found through page errors | – | 2 | 3 | 2 | 4 |
| Failed runs | 2 | 0 | 0 | 2 | 0 |
| Median steps | 9.5 | 8.0 | 7.5 | 9.5 | 7.5 |
| Total cost | $0.0430 | $0.0470 | $0.0490 | $0.0504 | $0.0575 |

- **Fixed in v4:**
  - `uitesting_click`: completed and verified (contradicted in v3).
  - No failed runs: the Chrome cleanup error is now only logged (0 warnings in this run), and 0 JPEG upload errors.
  - `saucedemo_problem_user` and the other two broken cases all named the known issue (0 of 3 false praise).
  - All 10 runs saved their neatlogs `trace_id`.
- **Still failing:**
  - `herokuapp_add_remove`: blocked on "$ is not defined"; herokuapp's jQuery never loads here.
  - `herokuapp_dynamic_loading`: the "Start" button had no effect, with 3 agent issues.
  - Both are about herokuapp's slow or missing scripts in this Chrome, not about the agent's verdicts.
- **Cost:** $0.0575 against $0.0504 in v3, mostly the longer step counts on two cases and the todomvc run (13 steps).

Evidence: `evals/results/v4.json`, `v4.md`, `v4.log`.

### 2026-10-11 — Reports for apps behind a login: start link, test login, self sign-up, first impression

Completed:
- **Start link** (web form, `runs.start_url`). Optional. The visit goes to the app's address first (for the first impression), then to the start link, and the report says so. It gets the same address checks as the main address, in the API and again by the worker's egress guard.
- **Test login** (web form, optional email and password).
  - The form says it must be a throwaway account, and the API only takes it with https addresses, with the permission box ticked.
  - **Storage:** the login is stored in a separate table, `run_secrets`, which only the service role can use. It is deleted in the same statement that the worker reads it (`take_run_secrets()`), so it is gone from the database before the visit starts. A safety-net delete runs at the end of every run, success or failure, and unclaimed logins older than 30 minutes are swept. The web app never reads the table.
  - **Where it goes:** into the page being tested, typed by the new `sign_in` tool through Stagehand variables (the model sees `%email%` and `%password%`; caching is off for those calls). If a variable fill leaves the wrong value in the field, a local fill puts it there. The agent calls `sign_in` with no arguments.
- **Self sign-up** (`sign_up` tool). It fills an email-and-password form with a generated identity (`first.user.<hex>@example.com`, a random password with every character class) and ticks a required terms box. If the app asks for email verification, the run ends as blocked with that reason. It never uses Google, GitHub or any other third-party login: when those are the only options the run ends as blocked and names them, and `do` refuses an instruction that would use one.
- **First impression** (`first_impression.py`, its own `CHAIN` span). Written once per run from the public landing page (visible text and a screenshot) right after it loads, before the visit continues to a start link. It is a fixed structure: what it does, who it is for, whether the main action is obvious, up to four hesitations, up to three suggestions. It is saved as soon as it is written, so the live page and a blocked run show it. The report shows it first, under "First impression".
- **Report:** a "How the visitor got in" box (start link, test login used or not, account created, third-party options), and when a run is blocked at a login, the three options for a deeper run.
- `runs` gains `start_url`, `has_test_login`, `first_impression` and `entry`; `enqueue_web_run` takes three new arguments (the old five-argument version is dropped). The worker saves without a column that does not exist yet, with a warning, so it works before the SQL is run.

Keeping the test login away from everything:
- The holder has no `__dict__` and a hidden repr, cannot be copied or pickled, so a serializer that walks attributes (neatlogs does) finds nothing.
- Registered values are replaced by labels (`[test email]`, `[test password]`) in tool results, steps, frictions, the final result, error text, tracebacks, model requests (including the accessibility tree sent to the lookup model), the verifier's page read, and every exported span (the neatlogs mask).
- Screenshots and page reads are taken with the values swapped for labels inside the page, then put back (`credentials.redacted_page`). Shadow DOM and iframes are not reached.
- **Security review finding, fixed:** the first version of that swap sent the whole process-wide secret registry into the page as a script, so a hostile or third-party page could have hooked built-ins and read other runs' logins. Now no secret is ever sent into a page as part of a script: the page returns its own text, Python finds what to replace, and only node indexes and labels go back. `sign_in`'s check that a field holds the right value also compares in Python. A test with a recording stand-in page (another run's secret registered) and a live test (every script sent into a real page during four runs) both assert that no secret is in any script.
- A generated identity's email is shown to the founder on purpose (so they can delete the account); only its password is secret.

Tests that ran:
- `test_credentials.py`: 24 tests, all pass (15 unit and browser tests, 9 live end-to-end tests with the real model against a local site with a login, a sign-up, a verification page and a "Google only" page). After the runs, the login is searched for in: what the database would be given, every exported span (after the mask), every model request, the process's output, and what the page showed during screenshots. Zero hits in all, with the site confirming it received the right email and password, and the stand-in database holding no login afterwards.
- **Negative control:** with registration and scrubbing disabled, the email appears in database writes (2), spans (17), model requests (6) and process output (1), and 4 of 6 page reads showed it. The password stayed at 0 even then, since it only ever goes through variables or a local fill into a password field.
- Web: tsc and eslint clean; against a fake database API, the new fields validate (both-or-neither login, https only, private and ported start links refused), the values reach the database function intact, neither the app's log nor any response contains the password, no request touches `run_secrets`, and every run state renders at 390 px with no horizontal scroll.
- A sanity visit on saucedemo found a regression of mine: the new "never type credentials yourself" rule made the agent give up where it used to use the demo login written on the page. The prompt now says to use a login the page itself shows. Saucedemo (8 steps) and herokuapp login (6 steps) are achieved again.
- `python -m unittest test_trace_safety test_verifier test_credentials test_egress`: 52 tests, 9 live tests skipped when `SKIP_LIVE_TESTS=1`. `scan_secrets.py`: 0 matches in the working tree and 50 commits.

Not verified:
- The SQL has not been run against a real Supabase project, so `take_run_secrets`, the new `enqueue_web_run` and `run_secrets` are untested there. The worker's database calls were tested against a stand-in.
- No real app behind a login has been visited. The sign-in and sign-up detection is heuristic (form fields found by type, label and position; two-step logins handled), and was tested on one local site.
- The eval set (v4) has not been re-run with these changes.
- `PAGE_READY_TIMEOUT_MS` is now 75 s (was 45 s): herokuapp's pages take 36 s or more in Chrome and twice reached 45 s in a row.

### 2026-10-11 — Slow page changes are not "no effect"; the worker packaged for a Linux server

Part 1: a click whose navigation finished late was logged as an agent issue.
- **Cause:** after each attempt, `do()` compared the page after a fixed 1.6 s (three checks), and the ladder then clicked again on a page that had already moved. On friction-fixer.shivamtaneja.com every rung read "no effect" while the next step's URL was already `/auth`.
- **Fix** (`tools.py`):
  - After each attempt the page is polled every 0.15 s for up to 2 s, exiting at the first change. A URL change counts as a change even when the page looks the same, and once a change is seen the page is given a moment to hold still.
  - Before climbing to the next rung there is one more look, 1.5 s later, so nothing is clicked again on a page that has moved.
  - Before an agent issue is recorded there is a final 3 s check. If the page has changed since the action began, the result is a success on the rung that was running (`settled_late: true`), and nothing is recorded.
- **Tests** (`test_slow_change.py`, 9 tests, all pass): 7 unit tests with a stand-in page (a URL-only change, a change 1 s later, no change, a page that cannot be read mid-navigation, the recheck stopping the ladder, the final check recording nothing, and no change at all still being an agent issue), and 3 live tests with a real Chrome and the real model against a local page whose button navigates client-side after 1 s (DOM replaced, URL only) and after 2.5 s. Each is one click, `changed: true`, rung a, no agent issue.
- **What the tests do not show:** the live scenarios also pass on the old logic, because Stagehand's `act` already waits a little after the click, and the observe call in rung b takes seconds. Between 3 s and 4.5 s old and new behave alike; at 6 s both click a second time. The new paths are demonstrated by the unit tests. The actual incident's timing is unknown, so whether it is fully fixed needs the real app.
- **Regression checks:** `check_costs.py` on saucedemo (achieved, 8 steps) and todomvc (achieved, 14 steps), the 3-attempt click measurement (3/3, 12/12 steps changed the page), and the other suites all pass. A genuine no-effect click now takes about 15 s longer to give up on.

Part 2: packaging.
- `worker/Dockerfile`: `python:3.11-slim-bookworm`, Google Chrome stable from Google's apt repository (and fonts), a non-root user (uid 10001), the 97 pinned dependencies from `worker/requirements.lock.txt`, `CHROME_PATH` so Stagehand finds Chrome, a `HEALTHCHECK` on a heartbeat file, `STOPSIGNAL SIGTERM`. No secret is in the image: the env file is only passed at run time (`.dockerignore` also keeps `.env`, `.venv`, `runs` and the test scripts out).
- **Settings** (`config.py`): `HEADLESS`, `VIEWPORT_WIDTH` / `VIEWPORT_HEIGHT` (1280x800), `DEVICE_SCALE_FACTOR` (1.0), `CHROME_SANDBOX` (default on), `CLEAN_RUN_FILES`, `AGENT_VERSION`. The viewport is also set explicitly after launch, so a headed window on a scaled laptop display has the same size.
- **Measured locally:** in headless and in headed mode the page is 1280x800 at scale 1, a coordinate click at (620, 715) lands exactly there, and a screenshot is 1280x800.
- **Chrome flags** (listed with reasons in `DEPLOY.md`): `--headless`, `--window-size`, `--force-device-scale-factor`, no `--no-sandbox` (see the security review below), `--disable-gpu`, `--disable-dev-shm-usage` (only if `/dev/shm` is under 512 MB), the proxy flags for the egress guard, and the WebRTC policy flag.
- **Worker loop** (`worker_loop.py`, split out of `main.py`): one health line a minute while idle (state, idle time, runs since start, uptime, agent), a heartbeat file touched every 5 s, and graceful shutdown. SIGTERM, SIGINT or Ctrl+Break finishes and saves the run in progress, claims no further run, and exits 0. A second signal stops at once.
- `DEPLOY.md`: clone, env file, build, check the image, the `docker run` command (`--env-file`, `--restart unless-stopped`, `--shm-size=1g`, `--init`, `--stop-timeout 600`, `--cap-drop ALL`, log rotation), logs, update, stop, and troubleshooting.
- **Tests** (`test_server_mode.py`, 14 tests, all pass): health lines at the interval and none during a run, the heartbeat file, SIGTERM idle (exits promptly), SIGTERM during a run (finished and saved, no further claim), a second signal, the Chrome launch options, the health check script, run-file cleanup, and a static check that the Dockerfile has a non-root user, no secrets and an ignore file. All suites together: 76 tests, 12 live tests skipped under `SKIP_LIVE_TESTS=1`.
- **End to end locally (Windows, server settings, the real queue):** the worker started with `HEADLESS=true CLEAN_RUN_FILES=true` (and, at that point, `CHROME_SANDBOX=false`), logged an idle health line, ran a queued saucedemo visit to `achieved` in 8 steps, removed the run's local files, and exited 0 within half a second of a stop signal.
- **Prerequisites checked over HTTP:** the base image tag exists, Google's Chrome apt repository and signing key are reachable (amd64 and arm64), and every one of the 97 pinned packages has a Linux wheel for Python 3.11 (25 MB).

Security review finding, fixed: the first image turned Chrome's sandbox off (`CHROME_SANDBOX=false`, so `--no-sandbox`). Chrome runs as the same user as the worker, which holds the API keys in its environment, so a renderer exploit from a hostile page could have read them from `/proc/<pid>/environ`. A non-root user and `--cap-drop ALL` do not prevent that.
- The sandbox is now **on**. Docker's default seccomp profile only allows `clone` with namespace flags, `unshare`, `setns` and `chroot` to containers that hold `CAP_SYS_ADMIN`/`CAP_SYS_CHROOT`, so the run command passes `worker/chrome-seccomp.json`: Docker's current default profile (fetched from github.com/moby/profiles by `make_chrome_seccomp.py`) with exactly one allow rule appended for those four calls. `mount`, `ptrace`, `pivot_root` and the capabilities stay blocked.
- **Preflight:** `main.py` starts Chrome once before taking work and logs `[preflight] browser ok ...`. If Chrome cannot start it prints the likely causes (missing seccomp option, a host that forbids unprivileged user namespaces, `CI` set, root) and exits 3. If Chrome would run without its sandbox (`CHROME_SANDBOX=false`, `CI`, root) the line carries `WARNING:`.
- **Tests:** 7 more in `test_server_mode.py` (the Dockerfile does not disable the sandbox or set `CI`; the profile is the default plus the one rule and allows none of `mount`, `pivot_root`, `ptrace`, `bpf`, `init_module`; the generator refuses an allow-everything source; preflight ok / warns / reports a start failure with the fix). Everything: 83 tests, 12 live skipped; the scan finds no secrets. A real preflight on Windows with the sandbox on reports `browser ok`.
- **Not verified:** that Chrome's sandbox actually starts inside the container with this profile (needs Docker on Linux), and whether the host's AppArmor/sysctl settings allow unprivileged user namespaces. If they do not, the preflight says so and the options are fixing the host, a separate browser container with no keys, or knowingly accepting `CHROME_SANDBOX=false`.

Not verified:
- **The image itself:** Docker is not installed on this machine, so `docker build` and `docker run` have not been run. `DEPLOY.md` step 4 lists the checks to run on the server.
- SIGTERM as such (tested here with `signal.raise_signal` and with Ctrl+Break on Windows, which share the handler); and Chrome on Linux (only Chrome on Windows has been exercised).

### 2026-10-11 — A clear choice of way in, a verified login, and findings with fix prompts

**Part 1: "How should the visitor get in?"** (`web/app/run-form.tsx`, `web/app/api/runs/route.ts`)
- One choice replaces the loose optional fields: *No login* (default), *I have a demo or guest link* (shows the Start link field), *Use a test account* (shows email and password, with the throwaway-account note) and *Let it sign up by itself* (no fields, with the note about signup without email verification). Only the chosen option's fields exist in the form and are sent; the API ignores the others. A line for Google/GitHub-only apps says "Use a demo or guest link."
- The choice is saved as `runs.access_mode` and reaches the visitor in its first message. Only *sign up by itself* lets `sign_up` create an account; in the other modes it refuses (`signup_not_allowed`) and nothing is made. Older runs (no `access_mode`) are read from their fields, so "no login, no link" from before still means "may sign up".
- Checked in a real browser against a fake database: each of the four choices shows exactly its fields and notes, and each posts exactly its fields (`p_access_mode`, `p_start_url`, `p_test_email`, `p_test_password`); an empty link or incomplete account is refused in the form before any request. 5 unit tests (`test_access_modes.py`).

**Part 2: sign-in diagnosis** (`worker/login_diagnosis.py`, `worker/auth_tools.py`)
- After `sign_in` or `sign_up`, the result is decided from what the page shows and returns: **signed in**, **rejected** (the page's message, quoted, plus any 401, 403 or 429 from its own requests), **needs verification** (a code sent by email, a CAPTCHA or a two-factor prompt that appeared because of the submit) or **no effect**. A form that disappears is not taken as a login on its own.
- Not signed in means the run ends as `blocked` with that exact reason and structured evidence (step, URL, message, statuses). The same credentials are never submitted more than once more: a rejection or a verification step ends the visit at once; "no effect" gets one retry; a second ends it.
- A login written on the page itself is recorded as `entry.page_login`: `shown_on_page` when the password the visitor typed with `do` is in the page's visible text, `typed` when it is not. The report no longer says "No login was used" when one was.
- The report's "How the visitor got in" quotes the diagnosis (for example *The page rejected the test login (step 4): "Invalid email or password". The page's own request returned 401.*), the page login, and the chosen mode.
- Verified: 17 unit tests on the diagnosis and the retry rules, and live scenarios with the real model and a real browser against a local site (`credentials_harness.py`): a rejected login with an alert and a 401 from a script's request (one submission, evidence points at the sign-in step), a CAPTCHA, a two-factor prompt, a login button that does nothing (at most two attempts), and a demo login printed on the page. A real visit to saucedemo with a login written on the page reports `page_login: shown_on_page`.
- Known limit: a status is only seen for requests the page makes with `fetch` or XHR. A plain HTML form post that returns 401 shows the page's message but not the status. The CAPTCHA and two-factor detection is by visible wording and a large challenge frame; an unusual challenge would read as a rejection or no effect.

**Part 3: findings with fix prompts** (`worker/report_writer.py`, `web/app/run/[id]/run-view.tsx`)
- After a visit, a report-writer step (its own `report_writer` span) turns the factual record, the noted problems, the page's errors, the first-impression review and the verifier's verdict into at most five findings, ranked by how likely each is to stop a new user. Each has a title, severity, what was expected, what happened, evidence, steps to reproduce, a kind (site problem, unclear wording, hidden error) and a paste-ready fix prompt.
- The model writes the prose; code decides what must be true. A finding must point at a step that exists, or it is dropped. The screenshot and the console error or failed request are looked up from that step. The steps to reproduce are the visitor's own recorded actions up to it. A quote is kept only if it is in the record. Steps where our browser tool had no effect are shown to the model as "not evidence about the site", and a finding that points at one, or blames the tool, is dropped. A plain rejected login at its own step is not a site problem. The fix prompt always names the page and marks quoted page text as data, not instructions, since it will be pasted into another agent.
- Report page: findings sit after the verdict and the first impression, each with a "Copy fix prompt" button (clipboard, with a fallback) and the prompt shown below it. Verified in a real browser: the button puts the prompt on the clipboard, the step link goes to the step, the layout has no horizontal scroll at 390 px.
- Cost: about $0.0003 to $0.0005 per visit (the report model is `REPORT_MODEL`, default the verifier's Haiku).
- Quality, seen on real visits: a clean saucedemo visit produced 0 findings after the writer was told not to repeat the first-impression review (the first version padded two landing-page points); the harness's local site gave sensible findings (a button that does nothing and shows no message, a landing page with nothing to explain it). One early misreading was fixed: the writer took the redaction label `[test email]` for placeholder text on the site.

**The `first-user-evals` span showing "error"**
- Cause, reproduced: `evals/run.py` had no root span. The first traced call (the judge) found no active parent, so neatlogs invented a `first-user-evals` WORKFLOW root, and exported it with status `UNSET` while every span under it was `OK`. The dashboard shows that as an error. Each judge call also became its own one-span trace.
- Fix: `main()` is now an explicit WORKFLOW span named `first-user-evals`; it ends `OK` (or `ERROR` if the run raises) and all judge calls sit in one trace. Reproduced and confirmed with `NEATLOGS_LOG_SPANS`: root status `UNSET` before, `OK` after. The full eval set was not re-run.

**Verification**
- 128 tests (19 live ones skipped under `SKIP_LIVE_TESTS=1`), all passing; the live end-to-end set (16 checks over 9 scenarios) passes against a harness run. `check_traces.py` on saucedemo: one trace, no orphans, none unended, no ERROR spans, `report_writer` present. `scan_secrets.py`: 0 matches in the tree and 33 commits. Web: typecheck and lint clean.
- The run page falls back to the older columns if the schema has not been updated yet, so it does not fail before the SQL is run.

**Not done or not verified**
- The SQL (`supabase/schema.sql`, last block) has not been run against the real Supabase project by me. Until it is, the web app's request to queue a run fails (the new 9-argument `enqueue_web_run` does not exist yet) and findings are not saved (the worker warns once and saves runs without them).
- The eval set has not been re-run since these changes.

### 2026-10-12 — Four report fixes, from run 91e44505 (saucedemo, problem_user)

What the stored run showed (read from its row): `access_mode` was saved as `signup`, `entry.blocked_at_login` was true although `page_login` was `shown_on_page`, its finding had kind `hidden_error` with `page_errors` empty, and its one noted problem (step 13) was listed again under "Problems with the site".

1. **Login help shown after a successful login.**
   - Cause: `blocked_at_login` was true whenever a blocked run's reason matched a list of words, and the reason said "with the password shown on the page".
   - Worker: `do()` now notices when a login written on the page was accepted (the password field was there before the action, is gone after it, and the URL changed) and sets `entry.page_login_worked`. `blocked_at_login` is false when the visitor got in (test login used, account created, or page login worked); it is true only for a block at a login or sign-up step (a failed or unverified login, a visible login wall, or a reason about a login when nothing got the visitor in).
   - Web: `showLoginWallHelp` also hides the block when the entry says the visitor got in. For runs saved before the flag existed, a page login followed by steps on another page counts as having got in, which is what fixes the stored run on its report page.
2. **"You let the visitor sign up by itself" was never chosen.**
   - The form's state and what it posts were right: the default is "No login" and sends `access: "public"` (checked in a browser, and again through the API).
   - The cause was the server's fallback. A request with no `access` (a page still open from before the form changed) with no fields was read as `signup`. It is now `public`; a start link still gives `link`, a test login `account`; a bad value is a 400. The worker no longer reports a mode the founder did not choose: a run that carried none and nothing to infer one from has `entry.access_mode: null` and the report prints no mode line.
   - The stored run's `signup` cannot be told apart from a real choice, so its label stays as saved.
3. **"Hidden error" without a console error or failed request.** A finding keeps kind `hidden_error` only if the page's errors at its step (or the step before) are non-empty; otherwise code sets `site_problem`, whatever the model wrote. The prompt says the same.
4. **Repeats.**
   - Noted problems: a finding records which of the visitor's noted problems it covers (`covers_steps`): the step the model names if it is a noted problem, plus any noted within two steps after the finding's step whose words are mostly in the finding. "Problems with the site" lists only those not covered, and says "Everything the visitor noted is in the findings above" when none are left. Findings saved before this match by step.
   - Steps to reproduce: the closing line is now `Observe: <symptom>` and is dropped when it starts with, or soon contains, an action word (type, click, enter, check, ...) or when most of its words are already in the steps above. Identical consecutive steps are merged. On a real re-run of the same goal the closing lines were symptoms only ("Observe: First Name shows 'User' and Last Name is empty.").
5. **Step limit.** `MAX_STEPS` default 15 to 20. The budget guardrail (`MAX_RUN_TOKENS` 400000 and `MAX_RUN_COST_USD` 0.30, checked before every step) is unchanged and ends a run as `gave_up` whatever the step count. The wrap-up notice still comes two steps before the limit. Note that the old runs' "ran out of steps" counted model turns, including the note and the finish.

**Tests**
- Worker: 139 tests pass (19 live skipped under `SKIP_LIVE_TESTS=1`). New: kind rule for hidden_error, restating closing lines, repeated steps, covered problems, the chosen-mode label, `blocked_at_login` cases (signed in then blocked at checkout, real login blocks, other outcomes), the step limit and budget guard.
- Web: `npm test` runs `lib/report-logic.test.ts` (7 tests: login help for the stored run's shape and for real login blocks, covered problems with and without `covers_steps`); typecheck and lint are clean.
- Live: the harness's page-login scenario now also asserts `page_login_worked` and `blocked_at_login: false` (passes). A real saucedemo re-run of the same goal (20 steps, ended blocked at checkout): `page_login_worked: true`, `blocked_at_login: false`, both findings `site_problem`, each covering its noted problem, no restating closing step.

**Not done**
- The stored run 91e44505 itself is not rewritten; its page changes through the web rules above (login help, repeats) but its `access_mode` label and its `hidden_error` kind stay as saved until it is run again.
- The eval set has not been re-run.
- Two findings can still describe the same symptom at different steps (the re-run produced a pair for First/Last Name); the writer is told to merge, and nothing in code does.

### 2026-10-12 — The two herokuapp eval failures: cause found, v5, and merged findings

**Part 1: why `herokuapp_add_remove` and `herokuapp_dynamic_loading` failed**

What the v4 runs recorded: add_remove clicked "Add Element" and the page threw `$ is not defined` (twice, even after the worker's wait-and-retry); dynamic_loading's Start click had no effect, with no page error at all (its handler is registered by jQuery on document ready, so with no jQuery there is nothing to click).

Investigation (`probe`: every request of a page, with host, status and timing, over CDP, through the worker's own browser and guard, and again in a plain Chrome with no proxy; the guard's decision and connect time for every host):
- **Not the guard.** Every script, stylesheet and image is on `the-internet.herokuapp.com` itself, over https. The guard allowed every host (`hosts_refused: []`); the only unresolved host is `298279967.log.optimizely.com`, an analytics call that does not resolve in a plain Chrome either (`ERR_NAME_NOT_RESOLVED`). There is no http script on an https page and no third-party script host. Connections to the site's four addresses take 0.04 to 0.25 s.
- **Not the page-ready cap.** The failing loads end at about 30.2 s (under both the old 45 s and the 75 s cap), and the page-ready wait returns when they do.
- **The site itself.** Some of the site's own static files, a different subset each time, come back as `503` after exactly 30 s (Heroku's router timeout) and the browser aborts them. In the worker's browser, in 8 loads of the two pages, 6 had at least one of its scripts or stylesheets fail (jQuery in 5 of them). In a plain Chrome with no proxy, in 7 loads, 5 did. That is the same rate, so our setup is not the cause. A normal browser usually passes because it has jQuery cached; our browser always starts with an empty profile.
- What our setup did wrong was not to react: a person whose page looks broken presses reload. The visitor continued on the broken page and the agent was blamed (an agent issue) or got a misleading `$ is not defined`.

Fix (generic, nothing about this site, the guard untouched):
- `page_watch`: the in-page log now records which element failed (script, stylesheet, image); `failed_assets()` returns the page's own (same-site) scripts and stylesheets that failed in the current document. Images, fonts and other sites' files do not count.
- `visit.open_start_page`: after loading, if any of the page's own scripts or stylesheets failed, the page is reloaded, up to twice, through the same proxy and guard. The worker logs `[visit] N of the page's own files failed to load (...); reloading (1/2)`.
- `tools.do()`: when a page's scripts did not load (the existing "scripts not loaded yet" wait) it reloads too; and an action with no effect on a page whose own files failed to load, even after reloading, is now a site friction ("the page's own files failed to load, even after reloading: app.js"), not an agent issue.
- Tests (`test_broken_load.py`, 7): which assets count; and live, in a real Chrome behind the guard against a local server that fails a script N times: fails once -> loaded by the reload (2 requests); loads whole -> not reloaded (1 request); never loads -> reloaded twice then left alone (3 requests); a click that needs the missing script -> one site friction, no agent issue.

**v5 eval** (`evals/run.py --version v5 --compare-to v0 v4`, fresh Haiku worker, agent 907b4b3 plus the uncommitted change): 5/7 completed and verified, 1/7 completed but unconfirmed, 0/3 false praise, 0 failed runs, $0.0649. Not 7/7.

| Case | v0 | v4 | v5 |
|---|---|---|---|
| saucedemo_standard | completed, unverified | completed, verified | completed, verified |
| herokuapp_login | not completed (failed) | completed, verified | completed, verified |
| herokuapp_dynamic_loading | not completed (failed) | not completed (blocked) | completed, verified |
| herokuapp_add_remove | completed, unverified | not completed (blocked) | completed, verified |
| todomvc_react | not completed (gave_up) | completed, verified | completed, verified |
| uitesting_click | not completed (blocked) | completed, verified | completed, unverified |
| practice_hammer | completed, unverified | completed, verified | not completed (blocked) |
| saucedemo_locked_out / problem_user / error_user | named the issue | named the issue | named the issue |

Two things the table hides:
- **A second worker took half of the runs.** Five of the ten runs (saucedemo_standard, herokuapp_add_remove, todomvc_react, practice_hammer, saucedemo_error_user) were claimed by a worker that is not on this machine (the queue is shared; mine claimed the other five, and the two interleaved in time). Its code is not this change. So v5 is a mix and is not a clean test; in particular `herokuapp_add_remove` passed there without the reload, and `practice_hammer` was blocked by a Cloudflare "Verify you are human" check that appeared for that worker (a server address; from this machine it passes). **For a clean eval, stop the other worker first.** The runs have no worker id, so this could only be found from the claim log; recording one on each run is worth doing.
- **My worker's five** (herokuapp_login, herokuapp_dynamic_loading, uitesting_click, saucedemo_locked_out, saucedemo_problem_user): dynamic_loading needed both reloads (6 then 4 files failed) and then passed in 4 steps with no agent issues.
- **A clean local re-run of the other five** through this machine's code, same goals and Haiku brain, no queue: saucedemo_standard achieved/verified; herokuapp_add_remove achieved/verified (`jquery-ui.js` failed once, the reload fixed it); todomvc_react achieved/verified; practice_hammer achieved/verified; saucedemo_error_user blocked, naming the Last Name error. That is 6/7 verified for this code, with uitesting_click the seventh.
- **uitesting_click** is the open one, and it is not the herokuapp problem: the agent does not capture the button's colour before clicking, so the verifier cannot tell the green from a default. In 4 runs of this machine's code, 2 of 4 were verified (v4 was verified; v5 and two of three re-runs were "unverified"). The verifier is working as designed (unverified, never contradicted). The fix is on the agent's side: look before the click so the record has a before-state. Not done, as it is outside the herokuapp question.

**Part 2: merging findings that describe the same symptom** (`report_writer.merge_same_symptom`, in code, after validation and before the cap of five)
- Two findings are the same symptom when they are about the same page (host and path) and their title-plus-happened words, without articles and generic UI words, overlap by at least 0.35 (and share two words). Merging is transitive. The earliest step stays the main evidence, the other steps are listed under it as `also_seen_at` (with their screenshots), the severity is the highest of the group, the noted problems any of them covers are kept, and a merged group frees a slot for the next problem. The report page shows "Seen again at step 12, step 14", and a noted problem at one of those steps is not listed twice.
- Tests (6, `MergingTheSameSymptom`): the First Name / Last Name trio from the saucedemo problem_user run (steps 12, 11 and 14, the same page) becomes one finding with step 11 as evidence, steps 12 and 14 under it, severity high, the noted problem 13 covered; the same result in the reverse order; a different problem on the same page stays separate; the same words on another page are not merged; merging frees a slot for a sixth distinct problem; a single finding is untouched. Web: a problem noted at a merged step is covered (8 tests).
- Known limit: it is word overlap, not meaning. Two distinct problems described with mostly the same words on the same page would be merged; the first version of the tests did exactly that with templated sentences.

**Verification:** 152 worker tests (23 live skipped under `SKIP_LIVE_TESTS=1`; the 7 broken-load tests run live and pass), 8 web tests, typecheck and lint clean, `scan_secrets.py` 0 matches in the tree and 37 commits.

### 2026-10-12 — Measured element state for the verifier, worker ids, bot checks, and v6 / v6b: 7/7 twice

**1. uitesting_click, generically** (`worker/element_state.py`, `tools.do()`, `verifier.py`, `report_writer.py`)
- Why it stayed "unverified": a button turning green has no new text and no new URL; the record said only "page changed", and the page's own words ("becomes green after clicking") do not prove the change, so the verifier correctly would not guess.
- What is recorded now: before each non-typing action, `do()` reads the page's interactive elements (up to 80: text, class, ARIA state, disabled/checked, computed text colour and background colour) and reads the same elements again after the action. The target is the element whose own text best matches the instruction (a quoted label first, otherwise most of the label's words are in the instruction); any other element that changed is listed too. Colours are written in words ("rgb(0, 123, 255) (blue)"). The pair goes into the step record (`entry.element`), which the verifier and the report writer read. A navigation, no match, or nothing changed says nothing rather than something false.
- The verifier was not made more lenient: its rules for `contradicted` and `unverified` are untouched (the calibration cases give the same answers as before: unverified x3, unverified x3, contradicted x3), and its prompt gained one descriptive sentence saying what the new record field is and that no difference or no entry says nothing either way. Nothing names a site; the eval cases are unchanged.
- Tests (`test_element_state.py`): colour names; picking the target (quoted label exact then contained, words, nothing); what changed (green button, ARIA, text, checked, other elements, no snapshot); what the verifier reads; and live, in a real Chrome behind the guard and with the real model, a local page whose button turns green on click: the result carries blue -> green and the class change, and the record the verifier reads has it.
- Effect on the real case: three runs of uitesting_click before the change were verified once in three; after it, three of three, each citing the recorded class and colour change.

**2. Which worker claimed each run**
- `runs.worker_id` (host name and agent version) is set by `claim_run(p_worker_id text default null)` itself; the zero-argument function is dropped so one exists, and a worker still calling it with no argument keeps working. The worker passes `hostname@agent_version`; if the database is not updated it says so once and claims as before (and writes the id afterwards if the column exists). `schema.sql` stays safe to re-run.
- `evals/run.py` reads `worker_id`, prints `Worker: <id> (every run)`, or a WARNING when more than one worker took runs, and names the worker in the results file.
- **The SQL has not been run on the real Supabase project** (I cannot run DDL from here), so v6 and v6b say "Worker: not recorded". That a single worker took them is shown by the worker's own claim log instead: 20 of 20 runs claimed by it, the queue empty and no other worker process before each round (your AWS worker was stopped).

**3. Bot checks are never attempted** (`worker/bot_check.py`, `tools.look()` and `do()`)
- Detected by what the page shows (its title, its visible words such as "Verify you are human", "Checking your browser", "I'm not a robot", "Press and hold", and a challenge frame large enough to be one), so the invisible reCAPTCHA badge on an ordinary login is not a bot check.
- `look()` and `do()` check before anything else: the check is not clicked, not waited out, not solved. The run ends `blocked`, `stopped_by: "bot_check"`, with the phrase, URL, a screenshot and the step in `entry.bot_check`, and the reason says it was blocked by a bot check and that nothing was attempted. The system prompt tells the visitor the same. It is not treated as a login block, no findings are written for it (the site chose to block automated visitors), and the report page is headed "Blocked by a bot check".
- Eval results count it (`Blocked by a bot check`) and name such a case "not completed (blocked by a bot check)"; neither v6 nor v6b hit one.
- Tests: wording that is and is not a bot check; live: a challenge page where `look()` ends the visit with the checkbox untouched, and `do("click the 'Verify you are human' checkbox")` is refused with the checkbox untouched and no agent issue.

**4. v6 and v6b** (`evals/run.py --version v6 --compare-to v0 v4`, then `--version v6b` with no code changes; one local worker, Haiku brain, headless, agent 527d1d0 plus the uncommitted changes; the shared queue was empty beforehand)

| Case (kind) | v6 | v6b | Pass rate over the two rounds |
|---|---|---|---|
| saucedemo_standard (achievable) | completed, verified (9 steps) | completed, verified (8) | 2/2 |
| herokuapp_login (achievable) | completed, verified (6) | completed, verified (6) | 2/2 |
| herokuapp_dynamic_loading (achievable) | completed, verified (4) | completed, verified (4) | 2/2 |
| herokuapp_add_remove (achievable) | completed, verified (8) | completed, verified (8) | 2/2 |
| todomvc_react (achievable) | completed, verified (10) | completed, verified (12) | 2/2 |
| uitesting_click (achievable) | completed, verified (3) | completed, verified (3) | 2/2 |
| practice_hammer (achievable) | completed, verified (11) | completed, verified (12) | 2/2 |
| saucedemo_locked_out (broken) | named the issue (blocked) | named the issue (blocked) | 2/2 named it |
| saucedemo_problem_user (broken) | named the issue (gave_up, 20 steps) | named the issue (gave_up, 20 steps) | 2/2 named it |
| saucedemo_error_user (broken) | named the issue (blocked) | named the issue (blocked) | 2/2 named it |

| Metric | v4 | v6 | v6b |
|---|---|---|---|
| Completed and verified (achievable) | 5/7 | 7/7 | 7/7 |
| Completed but unverified | 0/7 | 0/7 | 0/7 |
| Contradicted by the verifier | 0 | 0 | 0 |
| False-praise rate (broken) | 0/3 | 0/3 | 0/3 |
| Stopped by budget or step limit | 0 | 0 | 0 |
| Blocked by a bot check | – | 0 | 0 |
| agent_issue frictions | 3 | 1 | 3 |
| Site frictions found through page errors | 4 | 3 | 2 |
| Failed runs | 0 | 0 | 0 |
| Median steps | 7.5 | 8.5 | 8.0 |
| Total cost | $0.0575 | $0.0752 | $0.0769 |

- Stable: all seven achievable cases passed in both rounds, with no failed runs, no false praise and no unconfirmed verdicts. Cost rose from $0.0575 (v4) to about $0.076 because there are more steps allowed (20) and a report-writer call.
- What varied: the agent_issue count (1, then 3, all on `saucedemo_problem_user`, whose Last Name field does not take typed text: the agent said in v6b that the browser tool may have caused part of it), steps on two cases (todomvc 10 vs 12, practice_hammer 11 vs 12), and the count of site frictions through page errors (3 vs 2).
- Not 7/7 yet in one sense: the three broken sites are not "passed" by completing; the rate is how often the report named the known issue, which was every time. `saucedemo_problem_user` ended `gave_up` after using all 20 steps in both rounds (v4 ended `blocked`); it still named the issue.
- Two rounds is a small sample. The earlier v5 round (a mix with another worker) had one case blocked by Cloudflare; none of these did, and this run could not have clicked one.

**Verification:** 173 worker tests (live ones included) pass, 9 web tests, typecheck and lint clean, `scan_secrets.py` 0 matches in the tree and 39 commits.

## Demo

- URL: pending
- Instructions: pending

## Known limitations and next steps

- The agent has been tested on one demo site (saucedemo) with one easy goal. Both brains found no friction there, so the friction report is untested on a site that has real problems.
- Stagehand lookups are still about 70% of a Haiku-brain run's cost ($0.0033 of $0.0047), down from about 94% on Haiku 4.5.
- With Sonnet at low effort, the `thought` field is often a fragment ("Open the cart.") rather than the first-person sentence the prompt asks for. Haiku followed the instruction.
- The worker side of the queue has run once against the real Supabase project (2026-10-11). The web app has not yet been tested against it.
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
- Entire: checkpoints on `ab7458b`, `ac3b598`, `51e480b`, `6a08b29`, `29543ae` (web app, egress guard and report fixes) and `cea6d04` (traced lookups and the clean egress shutdown). The trace-quality changes are uncommitted.
- cfo.ai: pending (not signed up).
- Business plan: pending. Measured cost per saucedemo run is $0.0047 with the Haiku brain and traced Haiku 5.5 lookups; it was $0.017–0.029 with Haiku 4.5 lookups. The Sonnet brain ($0.034 on the old path) has not been re-measured.
- Failure-recovery run: the recovery ladder recovered "Add to cart" in 5 of 5 measurement attempts. A full agent run that shows recovery is still pending.
- Building in public: pending (no posts recorded).
- Public repo: `origin` exists; visibility unconfirmed.
- Demo video: pending.
- Nothing has been registered, deployed, or submitted by Claude.

## Understand mode

### 2026-10-12 — "Understand this website": a sourced product brief that feeds the test form

Built on the `understand` branch, separate from the report and run-page work. Not committed.

What it does:
- A second run kind, `understand`, claimed from the same queue (`runs.kind`). `worker_run.execute` hands it to `understand_run.execute_understand`; a test run is unchanged.
- `site_reader.py` reads the homepage and up to 8 same-site pages chosen by link text and path (pricing, product, features, about, docs, FAQ, customers, blog index), one of each kind first. Every request goes through the egress guard as an HTTP proxy, so private, loopback, link-local and metadata addresses are refused and every redirect hop is vetted. Limits: robots.txt (and Crawl-delay), 1 s between requests, 9 pages, 600 kB per page, 120 s in all. The browser opens only for a page with under 400 characters of text, at most 3 times.
- `understand.py` writes the brief with one model call (`product_brief` span; `fetch_page` span per page; `understand_site` root). The model proposes and code decides: a claim needs a source URL that is a page read; "confirmed" needs a quote found in that page; a price is kept only if it is in the cited page; no pricing page and no verified price gives `not_published` with no tiers; the business model is always labelled inferred and needs quoted evidence; a journey must quote the call to action or claim it came from. Missing fields are `unknown`.
- Web: the home form has "Test my website" / "Understand this website"; `/brief/[id]` shows the brief with every claim's source and status; each suggested journey is editable in place and "Test this journey" opens the test form with url, goal and success prefilled. The test run stores `brief_run_id`. The test form is prefilled from a journey, including the success condition (see the 2026-10-12 note below).
- SQL: `supabase/schema.sql`, section "Understand mode" (`kind`, `brief`, `brief_run_id`, `enqueue_understand_run`). Must be run before the brief page works.

Verification:
- 35 new worker tests (`test_understand.py`): no pricing page gives `not_published` and no prices; private addresses (direct, metadata, loopback, a redirect, a link) are refused and never contacted; the page cap holds (9, and 3 when set); every claim has a source URL that was read; robots.txt, delay, byte and time caps; browser only when text is thin. One live test drives real Chrome through the guard.
- 7 new web tests (`brief-logic.test.ts`). Whole suites: 187 worker tests (24 live skipped with SKIP_LIVE_TESTS=1), 15 web tests, typecheck, lint and `next build` clean, `scan_secrets.py` 0 matches.
- Two real runs with the model, no queue: plausible.io (6 pages, 4 tiers verified against the homepage's text, 12 claims each with a source, 5 journeys, $0.003) and saucedemo.com (a script-drawn login page: one browser read, "unknown" for who it's for, `not_published`, 1 journey, $0.0006).

Not done / known limits:
- The brief page was type-checked and the home form's prefill was checked in the built app, but the brief page has not been looked at against a real database row; the SQL has not been run.
- A running worker from before this change would claim an understand run and treat it as a test run. Run the new worker, or hold the queue, before using the form.
- "Not published" means no pricing page was linked from the pages read, not that none exists.
- Word-level quote matching: a model could quote real words in a misleading context. The page link is there to check.
- No investor or accelerator assessment, competitor analysis or price analysis, by design.

### 2026-10-12 — Success condition and the second pass on the brief page

- **Success is its own value, not part of the goal; merged into the Report v2 field.** The brief's journeys carry `goal` and `success` separately. They reach the home page as `?goal=...&success=...&brief=...`, and the test form's **Report v2 "What does success look like?" input** (`successCondition`, stored as `runs.success_condition` through the 10-argument `enqueue_web_run`) is prefilled from `success`. The success text is never appended to the goal. This branch's own `success` textarea and body field were removed in the merge; `POST /api/runs` takes `successCondition` (main's) and `briefId` (the brief the test came from, stored as `brief_run_id`).
- **Checked against a real row** (`8ca3896f-a3d8-475f-b810-5c9b6b98bb9e`, plausible.io; made and processed by a one-off script that inserted it as `running`, so no queue claim): at 1280 and 390 px the page has no horizontal scroll; journeys come first, are editable, and the link follows the edited text; claims show status and a source link; pricing, business model, unknowns and pages read display. Fixed from that pass: descriptions were cut mid-word (now cut at a word with an ellipsis), a changelog was read as the product page (changelog, releases and status paths are no longer chosen).
- **Intermittent hollow briefs, found and fixed.** About half of the model's replies for this site left out `claims`, `pricing` or `suggested_journeys` (a reply that stopped early or hit `max_tokens` at 4000), which showed up as a brief with no claims and no goals. The reply is now checked for every required field and asked for again (up to 3 tries, then the run fails rather than saving a hollow brief); `max_tokens` is 8000 and the prompt asks for a compact answer. Goals that do not quote the pages get one more try with a stricter note.

## Report v2

*2026-10-12. Own section so it merges cleanly with the work on the "understand" branch. The schema change is the last block of `supabase/schema.sql`, headed REPORT V2.*

The report now answers three questions for a founder: will a new user understand my product, can they get value from it, and what should I fix first.

**1. One verdict per run** (`worker/verdict.py`, stored on the run result and in `runs.verdict`: `{kind, headline, where_step, where_url, evidence_quote, basis}`). Computed in code from the outcome, the independent check and our own-issue count, never from the model's prose. Decided in this order:
- `bot_check`: stopped by a "verify you are human" check. Nothing is said about the site.
- `our_failure`: an error, a refusal, or our browser tool having no effect with no sign of a site problem (no site friction, no page error, and the last steps were our issues). Nothing is said about the site. A visit with our issues *and* real site evidence (the saucedemo problem_user case) stays `stuck`.
- `login_wall`: stopped at a login or sign-up it could not pass; carries the three ways in.
- `got_through`: achieved and verified; the evidence quote is the verifier's evidence. Headline "A first-time visitor got through".
- `unconfirmed`: achieved, the check could not confirm; says what it could not see.
- `stuck`: blocked, gave up, ran out of steps, or a claim the check contradicted; the headline names the page ("... got stuck on shop.example/products") and `where_step` points at the step (the site's own evidence if there is one).
- `bot_check` and `our_failure` can produce no site findings: the report writer is not even asked (tested).

**2. Success condition.** The form has an optional "What does success look like?" (300 characters, plain text). It is passed to the visitor in its first message, to the independent check ("judge whether THIS condition is met; the task wording alone is not enough"), to the report writer, and saved as `runs.success_condition`. Without one, the report says "The goal was checked without a stated success condition." The check's rules for contradicted and unverified are unchanged.

**3. Three answers at the top** ("The short answer"): *Will a new user understand it?* from the first-impression review (clear when all three parts are clear; unclear when what it does is not clear or two of three are not; partly clear otherwise), with the review's own reasons; *Can they get value from it?* the verdict; *What should you fix first?* the top-ranked finding (or "Nothing, from this visit" for a bot check or a failure on our side).

**4. Evidence labels.** Each statement carries a basis, shown as a small label: *Observed in the run*, *Verified by an independent check*, *Our recommendation*. The verdict is verified only when the check backs it; findings are observed; fix prompts, acceptance criteria and first-impression suggestions are recommendations. Recommendations are never worded as facts and never promise an outcome: sentences with conversion, boost, percentages, "will increase" and the like are removed in code (`worker/claims.py`, and again in the page for older reports), not only asked of the model.

**5. Structured fix prompts.** Built in code from the validated parts, in this order: the observed issue with its evidence (step, page URL, screenshot, the page's error, the steps to reproduce); the expected behaviour; what to change; constraints (keep existing validation and business rules; no unrelated redesigns; change nothing that works); three to five acceptance criteria a person can check by looking; and the retest instruction, word for word: "Repeat the original journey in a fresh session and confirm the original issue no longer occurs, using visible page evidence. Report Not reached if the relevant state cannot be reached; do not report Fixed without testing it." No test code. Fewer than three criteria from the model are topped up from what is known (the expected behaviour, the steps no longer reproduce it, the error is gone), so a prompt never goes out without them.

**6. How this report was made** (a collapsed panel; `worker/run_facts.py`, stored in `runs.run_facts`): steps taken, actions that needed recovery and on which rung, our own issues, page reloads, page errors recorded, the check's verdict and quote, the success condition, cost, duration, agent version, worker id and the neatlogs trace ID as text. All counted from the run.

**7. Flags.** Worker: `REPORT_V2=false` skips the verdict and the facts and writes the old prompt format. Web (`lib/report-flags.ts`): `NEXT_PUBLIC_REPORT_V2=off` hides every Report v2 section; `..._ANSWERS`, `_VERDICT`, `_LABELS`, `_CRITERIA`, `_FACTS`, `_SUCCESS` hide one each; `?report=basic` on the report's address hides them all for that view with no rebuild.

**SQL** (last block of `schema.sql`, safe to re-run): `runs.success_condition`, `runs.verdict`, `runs.run_facts`, and `enqueue_web_run` now takes `p_success_condition` as its last argument (the 9-argument version is dropped). If another branch also changes `enqueue_web_run`, keep both sets of arguments. Until the SQL is run, queueing a web run fails (the 10-argument function does not exist yet), the worker saves a run without `verdict` and `run_facts` and warns once, and the report page falls back to the older columns.

**Checked**
- Worker: 200 tests (live ones included; the worker's main loop was never started). New: `test_report_v2.py`, 27 tests covering each verdict kind, our issues next to real site evidence, no site findings for `our_failure` and `bot_check` (and no model call), prompts always having 3 to 5 criteria and the retest, promises removed, the success condition reaching the check and the writer, run facts, the worker adding agent version, worker id and trace id, and the run row getting the verdict and facts.
- Web: 15 tests (the three answers, fix-first, each flag, the promise filter, the older-schema column list); typecheck and lint clean. In a browser against a fake database: the answers, verdict card, labels, criteria, collapsed facts panel and `?report=basic` render, with no horizontal scroll at 390 px.
- Real visit (direct call to `first_visit`, saucedemo error_user with a success condition): `stuck` on `/checkout-step-one.html`, step 13, the page's own error as evidence, success condition recorded and facts counted; two findings, each with a structured prompt, three to four criteria and the retest.
- `scan_secrets.py`: 0 matches in the tree and 42 commits.

**Not done / limits**
- The SQL has not been run on the real Supabase project.
- Screenshots in a prompt show as "not captured" for a visit made without the database (a direct call); with the worker they are the uploaded URLs.
- Two findings about the same symptom worded differently ("rejects typed text" and "gives no message") are still two findings: the merge is by word overlap.
- The understanding level is a rule over a model's reading of one landing page; it is labelled observed, not verified.
