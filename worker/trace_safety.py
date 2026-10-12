"""Keep secrets and screenshots out of exported telemetry.

`mask` is passed to neatlogs.init(mask=...). neatlogs calls it on every span, just before
export, with the span as a dict (name, attributes, events, status, links). It is the last
line of defence: traced functions should not receive clients or configuration at all
(see check_trace_safety in test_trace_safety.py), but anything that still carries a
secret is redacted here.

What is redacted, in every string of the span:
  * key-shaped strings: Anthropic and other "sk-" keys, JWTs (Supabase service-role and
    anon keys), Supabase "sb_secret_" / "sb_publishable_" keys, "Bearer ..." tokens, and
    "x-api-key: ..." / "Authorization: ..." header text;
  * the exact value of any secret-named environment variable of this process
    (NEATLOGS_API_KEY, ANTHROPIC_API_KEY, SUPABASE_SERVICE_ROLE_KEY, ...), whatever its shape;
  * the value of any field named api_key, key, token, secret, password or authorization
    (and close variants), in attributes and in JSON text inside attribute values;
  * run-time secrets registered with register_secret(): a founder's test login and a
    generated test identity's password. Their values are replaced by a label such as
    "[test password]", here and in scrub() for text bound for a model, a step or a result.

Then trace_media.mask replaces inline screenshots with placeholders.
"""

import json
import os
import re

import trace_media

REDACTED = "[redacted]"

# Key-shaped strings. Each needs a recognisable prefix or structure, so ordinary text and
# ids (uuids, hashes, run ids) are left alone.
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),                       # Anthropic keys, any generation
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),                        # other "sk-" provider keys
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT: Supabase keys
    re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{8,}"),  # newer Supabase keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),       # Authorization header values
    re.compile(r"(?i)(x-api-key|api-key|authorization)(\"?\s*[:=]\s*\"?)([^\s\",}]{8,})"),
]
_HEADER_FORM = _PATTERNS[-1]

# Field names whose values are secrets. Exact names, plus a few suffixes (service_role_key,
# access_token, client_secret, ...). Plural and count-like names (max_tokens, token_count,
# prompt_key) are deliberately not matched.
_SECRET_NAMES = {
    "api_key", "apikey", "x_api_key", "key", "token", "secret", "password", "passwd", "authorization",
    "proxy_authorization", "credential", "credentials", "bearer", "private_key", "secret_key", "access_key",
    "service_role_key", "anon_key", "auth_token",
}
_SECRET_SUFFIXES = (
    "_api_key", "_secret", "_password", "_token", "_secret_key", "_access_key", "_service_role_key", "_private_key",
)
_ENV_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
_MIN_ENV_SECRET_CHARS = 8


def is_secret_name(name: str) -> bool:
    normalised = re.sub(r"[\s\-.]+", "_", str(name).strip().lower())
    return normalised in _SECRET_NAMES or normalised.endswith(_SECRET_SUFFIXES)


# Secrets registered while the process runs (a run's test login). Kept for the life of the process:
# spans are exported after the run ends, so they must still be redacted then. Capped, oldest first out.
_MAX_REGISTERED = 200
_MIN_REGISTERED_CHARS = 4
_registered: dict[str, str] = {}


def register_secret(value: str | None, label: str = REDACTED) -> None:
    """Redact `value` (case-insensitively for emails) from exported spans and from scrub()."""
    if not value or len(value) < _MIN_REGISTERED_CHARS:
        return
    _registered.pop(value, None)
    _registered[value] = label
    while len(_registered) > _MAX_REGISTERED:
        _registered.pop(next(iter(_registered)))


def forget_secrets() -> None:
    """Tests only: production keeps registered secrets, see above."""
    _registered.clear()


def _replace_registered(text: str) -> str:
    for value in sorted(_registered, key=len, reverse=True):
        label = _registered[value]
        if "@" in value:
            text = re.sub(re.escape(value), lambda _m, label=label: label, text, flags=re.IGNORECASE)
        elif value in text:
            text = text.replace(value, label)
    return text


def scrub_text(text: str) -> str:
    """Replace registered run-time secrets in a string with their labels."""
    return _replace_registered(text) if _registered and isinstance(text, str) else text


def scrub(value):
    """scrub_text over every string in a nested dict / list; other values are returned as they are."""
    if not _registered:
        return value
    if isinstance(value, str):
        return _replace_registered(value)
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    return value


def _env_secrets() -> list[str]:
    """Values of secret-named environment variables, longest first."""
    values = {
        value for name, value in os.environ.items()
        if _ENV_SECRET_NAME.search(name) and len(value.strip()) >= _MIN_ENV_SECRET_CHARS
    }
    return sorted(values, key=len, reverse=True)


def redact_text(text: str, env_secrets: list[str] | None = None) -> str:
    """Redact key-shaped strings and known secret values in a string."""
    text = _replace_registered(text)
    for secret in env_secrets if env_secrets is not None else _env_secrets():
        if secret in text:
            text = text.replace(secret, REDACTED)
    for pattern in _PATTERNS[:-1]:
        text = pattern.sub(REDACTED, text)
    return _HEADER_FORM.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)


def _walk(value, env_secrets: list[str]):
    """Redact a parsed JSON value: secret-named fields entirely, other strings by shape."""
    if isinstance(value, dict):
        return {
            key: REDACTED if is_secret_name(key) and not isinstance(val, (dict, list)) and val not in (None, "", 0)
            else _walk(val, env_secrets)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_walk(item, env_secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, env_secrets)
    return value


def _redact_value(value, env_secrets: list[str]):
    """Redact an attribute value: JSON text is parsed so field names can be checked."""
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, env_secrets) for item in value]
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped[:1] in ("{", "[") and len(value) > 2:
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(_walk(parsed, env_secrets), ensure_ascii=False)
    return redact_text(value, env_secrets)


def _redact_attributes(attributes: dict, env_secrets: list[str]) -> dict:
    result = {}
    for name, value in attributes.items():
        # An attribute whose own name is a secret field (e.g. "llm.api_key") is replaced whole.
        if is_secret_name(str(name).rsplit(".", 1)[-1]) and isinstance(value, str) and value:
            result[name] = REDACTED
        else:
            result[name] = _redact_value(value, env_secrets)
    return result


def redact_span(span: dict) -> dict:
    env_secrets = _env_secrets()
    if isinstance(span.get("name"), str):
        span["name"] = redact_text(span["name"], env_secrets)
    if isinstance(span.get("attributes"), dict):
        span["attributes"] = _redact_attributes(span["attributes"], env_secrets)
    for event in span.get("events") or []:
        if isinstance(event, dict):
            if isinstance(event.get("name"), str):
                event["name"] = redact_text(event["name"], env_secrets)
            if isinstance(event.get("attributes"), dict):
                event["attributes"] = _redact_attributes(event["attributes"], env_secrets)
    for link in span.get("links") or []:
        if isinstance(link, dict) and isinstance(link.get("attributes"), dict):
            link["attributes"] = _redact_attributes(link["attributes"], env_secrets)
    status = span.get("status")
    if isinstance(status, dict) and isinstance(status.get("description"), str):
        status["description"] = redact_text(status["description"], env_secrets)
    return span


def mask(span: dict) -> dict | None:
    """neatlogs mask: redact secrets, then screenshots. Never raises; on failure it falls
    back to redacting every string by shape, and drops the span if even that fails."""
    try:
        return trace_media.mask(redact_span(span))
    except Exception:
        try:
            return json.loads(redact_text(json.dumps(span, default=str)))
        except Exception:
            return None


def _active_span():
    """The active neatlogs span. In neatlogs' isolated mode it is not OpenTelemetry's current
    span, so neatlogs' own resolver is tried first (it is private API, hence the fallback)."""
    from opentelemetry import trace as otel_trace

    try:
        from neatlogs._wrap_utils import active_neatlogs_context

        context = active_neatlogs_context()
        if context is not None:
            return otel_trace.get_current_span(context)
    except Exception:
        pass
    return otel_trace.get_current_span()


def set_metadata(**values) -> bool:
    """Merge plain values into the active span's `metadata`, which neatlogs shows and can filter on.

    Used on a root span to say where a trace came from: environment=production for a real run,
    environment=eval for an eval run, environment=development for a script run by hand. Returns False when
    there is no active recording span.
    """
    span = _active_span()
    if span is None or not span.is_recording():
        return False
    current = {}
    try:
        current = json.loads((getattr(span, "attributes", None) or {}).get("metadata") or "{}")
    except (TypeError, ValueError):
        current = {}
    current.update({key: value for key, value in values.items() if value is not None})
    span.set_attribute("metadata", json.dumps(current, default=str, ensure_ascii=False))
    return True


def set_input(**values) -> bool:
    """Record the active span's input explicitly, as plain values.

    For traced functions that take objects (a run context, a page, a client) and so use
    capture_input=False: neatlogs walks an object's attributes when it captures arguments.
    Returns False when there is no active recording span.
    """
    span = _active_span()
    if span is None or not span.is_recording():
        return False
    span.set_attribute("input.value", json.dumps(values, default=str, ensure_ascii=False))
    span.set_attribute("input.mime_type", "application/json")
    return True
