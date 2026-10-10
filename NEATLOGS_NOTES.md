
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