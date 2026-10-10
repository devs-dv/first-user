"""Stagehand's lookup model as a bring-your-own-LLM callback on our neatlogs-wrapped Anthropic client.

Stagehand calls `generate` for every inference behind act, observe and extract
(see https://docs.stagehand.dev/v4/configuration/models.md, "Custom models").
Going through our own client makes each call a neatlogs LLM span with tokens,
cost and prompt, and lets us account for its cost ourselves.

Stagehand invokes the callback from a task its RPC reader starts, so the call
does not inherit the context of the tool that triggered it. Functions marked
with `@lookups_nest_here` (look and the do rungs) record their context, and
`generate` runs inside a copy of it: the LLM span then nests under that tool's
span, and `current_run` points at the run whose usage it adds to.
"""

import asyncio
import contextvars
import functools
import json
import re

import neatlogs
from anthropic import AsyncAnthropic
from stagehand import LLMStructuredGenerateResult

from config import LOOKUP_CALLBACK_MODEL, LOOKUP_MAX_TOKENS

_client = None
# The context of the innermost running `@lookups_nest_here` function. One
# Stagehand session runs at a time per worker process, so one slot is enough.
_caller_context: contextvars.Context | None = None


def _anthropic():
    global _client
    if _client is None:
        _client = neatlogs.wrap(AsyncAnthropic())
    return _client


def lookups_nest_here(function):
    """Make Stagehand model calls made while `function` runs nest under its span.

    Place it below the `@neatlogs.span` decorator so the recorded context includes that span.
    """

    @functools.wraps(function)
    async def wrapper(*args, **kwargs):
        global _caller_context
        previous, _caller_context = _caller_context, contextvars.copy_context()
        try:
            return await function(*args, **kwargs)
        finally:
            _caller_context = previous

    return wrapper


async def generate(params) -> LLMStructuredGenerateResult:
    """The callback passed to Stagehand.create as `model`."""
    if _caller_context is None:
        return await _generate(params)
    # A copy per call, because a Context can be entered by only one task at a time.
    return await asyncio.create_task(_generate(params), context=_caller_context.copy())


async def _generate(params) -> LLMStructuredGenerateResult:
    response_format = getattr(params, "response_format", None)
    if getattr(response_format, "type", None) != "json_schema":
        raise TypeError("Stagehand only issues structured generations")

    schema = response_format.schema_.model_dump(mode="json", by_alias=True, exclude_none=True)
    schema.pop("$schema", None)
    # A tool's input must be an object; wrap any other schema and unwrap the answer.
    wrapped = schema.get("type") != "object"
    input_schema = (
        {"type": "object", "properties": {"value": schema}, "required": ["value"]} if wrapped else schema
    )
    tool_name = re.sub(r"[^a-zA-Z0-9_-]", "_", response_format.name)[:64] or "respond"
    tool = {
        "name": tool_name,
        "description": response_format.description or "Return the requested result.",
        "input_schema": input_schema,
    }

    request = {
        "model": LOOKUP_CALLBACK_MODEL,
        "max_tokens": LOOKUP_MAX_TOKENS,
        "messages": [
            {"role": message.role.value, "content": _content(message.content)} for message in params.messages
        ],
        "tools": [tool],
        # Forcing the one tool makes the answer arrive as tool input that follows the schema.
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    # Stagehand's temperature is dropped: Claude Haiku 5.5 rejects non-default sampling parameters.
    if params.system_prompt:
        request["system"] = [
            {"type": "text", "text": params.system_prompt, "cache_control": {"type": "ephemeral"}}
        ]

    response = await _anthropic().messages.create(**request)
    _account(response)

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError(f"Lookup model returned no tool call (stop_reason={response.stop_reason})")
    structured = tool_use.input["value"] if wrapped else tool_use.input

    usage = response.usage
    cache_read = usage.cache_read_input_tokens or 0
    input_tokens = usage.input_tokens + (usage.cache_creation_input_tokens or 0) + cache_read
    return LLMStructuredGenerateResult.model_validate({
        "role": "assistant",
        "content": {"type": "text", "text": json.dumps(structured)},
        "stop_reason": response.stop_reason,
        "output_format": "json_schema",
        "structured_content": structured,
        # Stagehand counts cached tokens inside input tokens; Anthropic reports them separately.
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": input_tokens + usage.output_tokens,
            "cached_input_tokens": cache_read,
        },
    })


def _content(content) -> list[dict]:
    blocks = content if isinstance(content, list) else [content]
    return [_block(block.root) for block in blocks]


def _block(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "image":
        return {"type": "image", "source": {"type": "base64", "media_type": block.mime_type, "data": block.data}}
    raise TypeError(f"Unsupported content block for the lookup model: {block.type}")


def _account(response) -> None:
    # Imported here to avoid a cycle: tools imports this module.
    from tools import current_run

    ctx = current_run.get(None)
    if ctx is not None:
        ctx.usage.add_lookup_response(response)
