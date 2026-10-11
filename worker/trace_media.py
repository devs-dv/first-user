"""Keep screenshots out of exported traces.

look() and the verifier send screenshots to the model as base64 image blocks, and the
neatlogs Anthropic wrapper records the request messages, images included, on the LLM
span: about 65 KB of base64 per screenshot. `mask` is passed to neatlogs.init(mask=...)
and runs on each span just before export. It replaces inline base64 image data with a
short placeholder, plus the screenshot's public URL when the run uploaded it. Only the
exported telemetry changes; the model still receives the real image.
"""

import hashlib
import re
from collections import OrderedDict

# A base64 "data" field in a serialized image block, as the wrapper records it.
_INLINE_IMAGE = re.compile(r'("data":\s*")([A-Za-z0-9+/=]{256,})(")')
_MAX_URLS = 500
_urls: "OrderedDict[str, str]" = OrderedDict()


def _key(data: str) -> str:
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def register_url(data: str, url: str) -> None:
    """Remember the public URL of a screenshot sent to the model as `data` (base64)."""
    _urls[_key(data)] = url
    _urls.move_to_end(_key(data))
    while len(_urls) > _MAX_URLS:
        _urls.popitem(last=False)


def _placeholder(match: re.Match) -> str:
    data = match.group(2)
    url = _urls.get(_key(data))
    note = f"[screenshot omitted from trace, {len(data) * 3 // 4 // 1024} KB" + (f": {url}]" if url else "]")
    return match.group(1) + note + match.group(3)


def mask(span: dict) -> dict:
    """neatlogs mask: replace inline base64 images in span attributes. Never drops a span."""
    try:
        attributes = span.get("attributes") or {}
        for key, value in attributes.items():
            if isinstance(value, str) and len(value) > 1000 and '"data"' in value:
                attributes[key] = _INLINE_IMAGE.sub(_placeholder, value)
    except Exception:
        pass
    return span
