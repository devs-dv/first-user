
## 2026-10-10
- LLM span input shows "System Prompt template:" with no content. The agent uses the Anthropic SDK with prompt caching on the system prompt and tools. Tool spans and outputs display correctly.
so basically my question is - is this a display issue or are we missing a setup step?

<img width="813" height="871" alt="image" src="https://github.com/user-attachments/assets/81640948-b4bf-46f2-aad7-a17c2642a4e6" />

## 2026-10-10: Stagehand's model calls
- **Context:** Stagehand made its own model calls, which neatlogs could not see. We had been copying Stagehand's token counts onto our tool spans as custom attributes (`stagehand.prompt_tokens`, `stagehand.cost_usd`, ...).
- **Answer from the neatlogs team:** route library calls through the wrapped client rather than guessing custom attribute names.
- **What we did:**
  - Stagehand now calls a bring-your-own-LLM callback (`worker/lookup_model.py`) that uses our `neatlogs.wrap(AsyncAnthropic())` client, so every act, observe and extract inference is a real LLM span with tokens and prompt.
  - We removed the custom `stagehand.*` attributes.
  - Stagehand runs the callback in its own task, so the callback runs in a copy of the calling tool's context; that makes each LLM span nest under the `look` or `do` rung that triggered it.
  - On a saucedemo run, the LLM spans' token totals matched our own accounting and Stagehand's `metrics()` exactly (`worker/check_costs.py`).




- 2026-10-10 23:09: Traces stayed on "finalization" and would not load while the worker left open connection tasks at shutdown. After closing them cleanly, traces load within about two minutes. The blank system prompt also appears on the Stagehand lookup spans.

## 2026-10-11: Trace quality (screenshots, prompts, detections)
Answers from the neatlogs team, and what we did with each:

- **Screenshots.** A tool span shows an image preview when its output contains an image URL.
  - `do()` now uploads its screenshot first and puts the public URL in its output as `screenshot_url`.
  - Local runs with no database leave the field out.
  - The brain model never sees the URL.
- **Readable prompts.** Use `neatlogs.trace(kind="LLM")` with `SystemPromptTemplate` and `UserPromptTemplate` ([docs](https://docs.neatlogs.com/sdk/prompt-templates)).
  - We did this in the agent loop (`visitor_turn`) and in the lookup callback (`stagehand_act`, `stagehand_extraction`, `stagehand_metadata`, `stagehand_observation`). Caching is still on.
  - **Repro:** `worker/repro_system_prompt.py`. Neatlogs 1.4.26 and anthropic 1.13.0, workflow `repro-system-prompt`.
    - A (`repro_A_system_as_string`): the system message is recorded as the plain text.
    - B (`repro_B_system_as_cached_blocks`): it is recorded as a JSON-encoded list of blocks.
  - **What we found in neatlogs 1.4.26:**
    - The template text is never recorded, on 0 of 20 model calls in a saucedemo run.
    - The SDK's span processor adds template text only to spans it recognises as LLM spans when they start. It checks for `openinference.span.kind == "LLM"`, or a name containing "chat", "completion", "generate" or "embedding".
    - The Anthropic wrapper's span is named `anthropic.messages.create` and gets its kind later. The `trace()` span also gets its kind after it starts. So neither span matches.
    - Only the template variables reach the `trace()` span, as `llm.prompt_template_variables` and `llm.user_prompt_template_variables`.
  - **Exported spans:** each model call exports as two spans of kind `llm`. One is the `trace()` span, marked `neatlogs.internal: true`, with the variables. The other is `anthropic.messages.create`, with tokens and messages. Token counts appear only on the second.
  - **Question for the neatlogs team:** does the dashboard merge or hide the internal `trace()` span? And is there a supported way to get template text onto Anthropic spans in 1.4.26, or a fix planned?
- **Detections.** Tool outputs and the run result now use fixed keys and values (listed in `hackathon.md`), so detections can match exact strings such as `"changed": false` and `"outcome": "gave_up"`.
- **Shutdown crash.** The worker sometimes crashed at exit on Windows, with an access violation while garbage-collecting an asyncio proactor transport. The cause was Anthropic clients left open after the event loop closed. Both clients are now closed before the loop ends, and two verification runs since then exited cleanly.

## 2026-10-11: Readable prompts, second approach
- **Template wrapper removed.** In neatlogs 1.4.26, `neatlogs.trace(kind="LLM")` with prompt templates added a second LLM span to every model call and still did not record the template text (finding above). We removed it from the agent loop and the lookup callback.
- **System prompt now a plain string.** `system` is sent as a plain string in both places. In the repro (`worker/repro_system_prompt.py`), a string system prompt is recorded on the span as its text, while cached content blocks are recorded as a JSON list.
- **Caching kept.** The cache breakpoints moved off `system`: one on the last tool definition and one on the first user message. The prompt prefix runs tools, then system, then messages, so the system prompt still sits inside the cached prefix.
- **Local check (saucedemo run `check-20261011-072637`):**
  - each model call is one LLM span;
  - the system message is recorded as plain text on all 19 spans;
  - every agent turn after the first read from the cache.
- **Still to confirm:** how the dashboard shows these spans.

## 2026-10-11: Trace integrity
- **Reported symptoms:** runs `c350f9b9-…` and `ab9d9bd4-…` showed "Trace processing failed". Each visit also seemed to produce standalone 2-span traces (one `egress_check` or `devtools_check`) and red rows with empty input and output.
- **Measured locally** with `worker/check_traces.py`. It runs visits in one event loop like the worker, collects every span from the provider that exports to neatlogs, and reads the `NEATLOGS_LOG_SPANS` export log. For each visit it checks:
  - one trace id per visit;
  - every parent exists in the same trace and was exported;
  - every span ended, and none ends after the root;
  - no ERROR status on a normal run.

| | Before | After |
|---|---|---|
| Traces per visit (3 visits, then 3 more after) | 1, 1, 1 | 1, 1, 1 and 1, 1, 1 |
| Orphan spans / ERROR spans / unended spans | 0 / 0 / 0 | 0 / 0 / 0 |
| Egress guard used outside a run (tests, scripts) | 2 standalone traces (auto-root + `egress_check`) | 0 spans |
| Guard closed while a host check was resolving | the check's span cut off, status UNSET | no span |
| Spans in one uitesting visit | 60 | 23 |

- **Causes found:**
  - **Standalone traces:** the guard traced every host check. Outside a visit (test_egress, measure_clicks, ad-hoc scripts), neatlogs bootstraps from `NEATLOGS_API_KEY` in the environment, and those spans became their own traces.
  - **Red rows:** a check still resolving when the guard closed was cancelled mid-span.
  - **Not reproduced:** the "Trace processing failed" state of the two named runs. Both ran on an older worker, and their run rows don't show why.
- **Fixes:**
  - **No span per host check.** One `egress_refused` GUARDRAIL span per refused request, created synchronously in the run's copied context, so cancellation cannot cut it off.
  - **No spans at all when no run is active.** The guard asks `neatlogs.inject_trace_context({})` at start.
  - **One `egress_summary` span per visit,** recording hosts checked, allowed, unresolved and refused.
  - **Everything ends inside the root:** the browser, the guard and the lookup client all close inside the `first_visit` span.
- **Trace id on the run:** `first_visit` reads the trace id from the `traceparent` that `neatlogs.inject_trace_context()` writes. It is returned as `trace_id`, matches the exported trace, and the worker saves it in `runs.trace_id`.

## 2026-10-11: Screenshots in LLM spans (mask)
- **Problem:** `look()` and the verifier send screenshots to the model as base64 image blocks. The Anthropic wrapper records request messages on the LLM span, images included. Each screenshot-carrying span exported at 56–76 KB, about 49–65 KB of it base64, in `neatlogs.llm.input_messages.N.content`.
- **Fix:** `worker/trace_media.py` is passed as `neatlogs.init(mask=...)`. The mask replaces each inline base64 `data` field with `[screenshot omitted from trace, 47 KB: <public URL>]`, using the URL when the run uploaded that screenshot. The model still receives the real image; only the exported span changes.
- **Measured on a uitesting visit**, recorded at export time inside the mask:

| Span | Before | After |
|---|---|---|
| Brain call with a look() screenshot | 75–76 KB | 10–12 KB |
| Verifier call with the final screenshot | 56 KB | 7 KB |
| All LLM spans in the visit | 321 KB | 78 KB |

- **Behaviour unchanged:** the agent still reported the button turning blue to green, and the verifier returned `verified`.
- **Side effect:** with a mask set, neatlogs skips its local `NEATLOGS_LOG_SPANS` file, so `check_traces.py` runs without the mask. The mask changes attributes only, never span ids or parents.
- **Follow-up from eval v3:** the screenshots bucket rejected `image/jpeg`, so `look()` screenshots in v3 were not uploaded, and their placeholders carried no URL. `look()` now sends and uploads PNG instead.

## 2026-10-11: A key in a trace (security)
- **What happened:** the 12:04 PM trace had an input beginning "Client: Api Key: sk ant usr ...". The eval judge was a traced function that took the Anthropic client as an argument.
- **How the SDK captures it:** the `@neatlogs.span` decorator records a function's bound arguments as `input.value`. For anything that is not a primitive, list or dict, it tries `model_dump` / `dict` / `to_dict` / `to_json` / `as_dict`, then walks the object's public `__dict__` recursively (`neatlogs/decorators/_base.py`, `_serialize_obj`). A client, a config or a run context is therefore recorded attribute by attribute, secrets included. This is the default (`capture_input` is on unless set to `False`).
- **Fixes:**
  - **Arguments:** traced functions take plain values only. The three that take objects (`first_visit`, `run_persona`, `verify`) use `capture_input=False` and set their input explicitly.
  - **Mask:** `neatlogs.init(mask=trace_safety.mask)` redacts key-shaped strings, secret-named fields and the exact values of secret-named environment variables in every string of a span before export. The mask is the only place a secret can still be stopped once it is in a span, so it also covers events, status text and span names.
  - **Tests:** a test sends fake secrets through neatlogs' own `MaskingSpanExporter`, and a static test fails if a traced function takes a client, config, context or page without `capture_input=False`.
- **Also learned while doing this:**
  - **Setting a span's input:** the public `neatlogs.span` has no `postprocess_result` (only the internal decorator does). In neatlogs' isolated mode the neatlogs span is not OpenTelemetry's current span. `neatlogs._wrap_utils.active_neatlogs_context()` finds it, and `trace_safety.set_input()` uses that with a fallback.
  - **A mask turns off the local span log:** with `mask` set, `NEATLOGS_LOG_SPANS` writes nothing (the file is skipped when a mask is installed).
- **Already exported:** the judge traces of evals v0 to v3 (3 judge spans each, about 09:16, 09:55, 11:10 and 12:04 IST on 2026-10-11) contain the old key. It has been rotated; delete those traces in the dashboard.
- **Question for the neatlogs team:** would it be possible to have argument capture opt-in for non-primitive objects, or to skip attributes that look like secrets (`api_key`, `token`, ...) by default?

## 2026-10-11: Eval v4
- **Trace ids:** all 10 runs saved their `trace_id`, taken from `neatlogs.inject_trace_context()`.
- **Spans:** each visit exports one trace with one `egress_summary` span, and `egress_refused` spans only for refused requests.
- **Screenshots:** with the Supabase bucket accepting PNG, `look()` and verifier screenshots are uploaded, and their trace placeholders carry the public URL.


- 2026-10-11 14:03: "Trace processing failed" on about half of my runs was a processing issue on the neatlogs side. The team reprocessed the records after I shared the project ID and three session IDs. Local checks (one trace id, no orphan spans, all spans ended) had shown my traces were structurally valid.


1. PII redaction is over-eager. It replaced ordinary words:

'Finish' became <NRP>. It read the button name as a nationality (“Finnish”).
status done became status <PERSON>.
js_error became <ORGANIZATION>.

feedback for the neatlogs team, and a nice specific example:

- 2026-10-11: PII redaction replaced non-personal words in span text: the button label 'Finish' became <NRP>, "done" became <PERSON>, "js_error" became <ORGANIZATION>. Makes eval traces harder to read.

2. The workflow shows “error” though the judge succeeded. The first-user-evals row is marked error and says “ended with error”, while its output is fine. That’s most likely the eval script’s outer step closing badly at exit. I’ll add it to tomorrow’s list for Claude Code. If the judge trace for saucedemo_locked_out shows no error mark, use that one for the screenshot instead. If they all show it, keep this one.

## 2026-10-11: the `first-user-evals` workflow span showed "error"
- **Reproduced:** a judge call (`@neatlogs.span(kind="EVALUATOR")` plus a wrapped Anthropic call) with no root span above it. neatlogs opens an auto-root named after `init(workflow_name=...)`. Exported with `NEATLOGS_LOG_SPANS`: root `first-user-evals` status **UNSET**, `false_praise_judge` OK, `anthropic.messages.create` OK.
- **Why it matters:** the auto-created root never gets an OK status (it ends when its first child ends), so a successful run's root is UNSET, which the dashboard shows as an error. Each judge call also became its own trace.
- **Fix:** `evals/run.py` `main()` is an explicit `@neatlogs.span(kind="WORKFLOW", name="first-user-evals")`. With it the root exports with status OK, and all judge calls share one trace.
- **General rule:** any script that makes traced or wrapped-client calls outside `first_visit` should open its own WORKFLOW root, or its auto-created root will read as an error.
- **Local span log:** `NEATLOGS_LOG_SPANS` writes nothing when `mask` is set (see above), so this check ran without the mask.
