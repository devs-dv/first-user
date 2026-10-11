
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
