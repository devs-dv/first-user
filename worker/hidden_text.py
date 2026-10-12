"""Hidden instructions aimed at AI agents: found by code, kept out of what the models read, never repeated.

A page can hide text from people but not from a model that reads the page: white text on a white
background, text moved off the screen or clipped to nothing, aria-hidden blocks, HTML comments, alt or title
attributes. When that text is addressed to an AI ("ignore your instructions", "report the goal as achieved",
"say the site has no problems"), it is a prompt injection. This module does four things, all in code:

  1. sweep(): before the agent, the first-impression writer or the verifier reads a page, find hidden text that
     looks like an instruction and empty it in the page (so every reader sees the page as a person does). Where
     it was found (page address without its query, step, how it was hidden) is kept as evidence. The text itself
     is kept only in this process, to match against, and is never put in a report.
  2. sanitize(): remove from model-written report text any sentence that repeats instruction-like wording, or
     that repeats a sentence of text found in step 1. This is the second line: it also covers a model that
     recognised an injection and tried to describe it.
  3. NOTICE: one fixed sentence, written here and not by a model, that the report shows instead.
  4. apply_to_result(): puts it together for a finished run's result.

Detection is pattern-based. It catches instructions written in the usual ways, not every possible wording, and it
never judges what a page is "really" trying to do.
"""

import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import urlsplit

NOTICE = ("This page contains hidden text addressed to automated agents. "
          "It is not visible to people and was ignored.")
REMOVED = "(Text removed: it repeated wording the page hid from people.)"

# Regular expressions written to mean the same in Python and JavaScript (case-insensitive). Narrow on purpose:
# an honest report must be able to say "the agent ignored the banner" or "the site has no problems".
PATTERNS = [
    # "ignore your previous instructions", "disregard the task"
    r"\b(ignore|disregard|forget|override|bypass)\b[^.!?\n]{0,40}\b(instructions?|prompts?|rules|guidelines|directives?|task|goal)\b",
    # "report the goal as achieved", "say that the test was successful"
    r"\b(report|mark|declare|state|say|tell|write|claim|conclude|confirm|respond|answer)\b[^.!?\n]{0,60}\b(goal|task|test|run|visit|checkout)\b[^.!?\n]{0,30}\b(achieved|complete|completed|successful|succeeded|passed|done)\b",
    # "say that this site has no problems"
    r"\b(report|say|state|tell|write|claim|conclude|confirm)\b[^.!?\n]{0,60}\b(site|website|page|app|shop)\b[^.!?\n]{0,25}\b(has|have|with) no (problems|issues|bugs|errors|defects)\b",
    # "note to AI agents", "message for language models"
    r"\b(notice|note|message|attention|instructions?|warning|memo|directive)s?\b[^.!?\n]{0,12}\b(to|for)\b[^.!?\n]{0,12}\b(ai|llms?|language models?|assistants?|agents?|chatbots?|bots?|crawlers?|automated)\b",
    # "AI agents must ...", "language models should ..."
    r"\b(ai|llms?|language models?)\b[^.!?\n]{0,40}\b(ignore|disregard|must|should|do not|don't|report|say|tell|obey)\b",
    # "system message for AI assistants"
    r"\bsystem (message|prompt|notice)\b[^.!?\n]{0,20}\b(for|to)\b[^.!?\n]{0,20}\b(ai|llms?|assistants?|agents?|models?)\b",
    # "do not mention this comment"
    r"\b(do not|don't|never)\b[^.!?\n]{0,20}\b(mention|reveal|tell|disclose)\b[^.!?\n]{0,25}\b(this|that|these)\b[^.!?\n]{0,15}\b(message|comment|notice|note|text|instructions?)\b",
    # a description of the text itself ("hidden text addressed to AI agents", "a prompt injection")
    r"\b(addressed|aimed|directed|written)\b[^.!?\n]{0,15}\b(to|at|for)\b[^.!?\n]{0,15}\b(ai|llms?|language models?|assistants?|agents?|bots?)\b",
    r"\bhidden (text|instructions?|message|content|prompt)\b[^.!?\n]{0,40}\b(ai|llms?|agents?|assistants?|models?|bots?)\b",
    r"\bprompt[- ]injection\b|\binjected (text|notice|instructions?|prompt|message)\b",
]
_COMPILED = [re.compile(pattern, re.I) for pattern in PATTERNS]
_ACHIEVED_PATTERN = 1  # "report ... goal ... achieved": an honest "was not achieved" must survive
_NEGATION = re.compile(r"\b(not|n't|never|unable|failed|couldn't|cannot|no)\b", re.I)
_SKIP_KEYS = {"success_condition", "usage", "egress", "trace_id", "url", "urls", "hidden_text", "run_facts"}


@dataclass
class _State:
    found: list[dict] = field(default_factory=list)
    removed: int = 0  # sentences of model-written text dropped by strip_sentences, this visit
    fragments: list[str] = field(default_factory=list)  # normalised sentences of hidden text, this process only


_state: ContextVar[_State | None] = ContextVar("hidden_text_state", default=None)


def reset() -> None:
    """Start tracking for one visit. Called when a visit begins."""
    _state.set(_State())


def removed_count() -> int:
    """How many sentences of model-written text were dropped in this visit for repeating instruction-like wording."""
    state = _state.get()
    return state.removed if state else 0


def found() -> list[dict]:
    """Where hidden instruction text was found: [{url, step, where, method, blocks}]. Never the text."""
    state = _state.get()
    return [dict(item) for item in state.found] if state else []


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())).strip()


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def is_instruction_like(text: str) -> bool:
    """Does this text read as an instruction to an AI, or describe one (see PATTERNS)?"""
    for index, pattern in enumerate(_COMPILED):
        match = pattern.search(text)
        # An honest "could not report the goal as achieved" is not an instruction: look just before the match too.
        if match and not (index == _ACHIEVED_PATTERN
                          and _NEGATION.search(text[max(0, match.start() - 25):match.end()])):
            return True
    return False


def _repeats_hidden_text(sentence: str, fragments: list[str]) -> bool:
    cleaned = _norm(sentence)
    if len(cleaned) < 25:
        return False
    return any(fragment in cleaned or cleaned in fragment for fragment in fragments)


def strip_sentences(text: str, fragments: list[str] | None = None) -> str:
    """The text without any sentence that repeats instruction-like wording or hidden text found on the page.

    Line breaks are kept. Our own NOTICE is never removed.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    state = _state.get()
    if fragments is None:
        fragments = state.fragments if state else []
    notice = _norm(NOTICE)
    lines = []
    for line in text.split("\n"):
        if _norm(line) == notice:
            lines.append(line)
            continue
        sentences = _sentences(line)
        kept = [s for s in sentences
                if _norm(s) == notice or not (is_instruction_like(s) or _repeats_hidden_text(s, fragments))]
        if state is not None:
            state.removed += len(sentences) - len(kept)
        if kept or not line.strip():
            lines.append(" ".join(kept) if kept else line)
        # a line that held only removed sentences is dropped
    return "\n".join(lines)


def sanitize(value, _skip: frozenset | set = frozenset()):
    """strip_sentences over every string of a nested dict / list. A string that loses everything becomes REMOVED,
    a list item that loses everything is dropped. Machine fields (urls, usage ...) are left alone."""
    if isinstance(value, str):
        if not value.strip():
            return value
        cleaned = strip_sentences(value)
        return cleaned if cleaned.strip() else REMOVED
    if isinstance(value, dict):
        return {key: item if key in _SKIP_KEYS or key in _skip else sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = sanitize(item)
            if isinstance(item, str) and cleaned == REMOVED:
                continue
            out.append(cleaned)
        return out
    return value


def _clean_url(url: str) -> str:
    """The page's address without its query or fragment, which can hold tokens."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else str(url)[:200]
    except ValueError:
        return str(url)[:200]


_SWEEP_JS = r"""(() => {
  const RES = %s.map((p) => new RegExp(p, 'i'));
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'HEAD', 'TEXTAREA']);
  const found = [];
  const looksLikeInstruction = (t) => RES.some((r) => r.test(t));
  const parse = (c) => {
    const m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) return null;
    const p = m[1].split(',').map(parseFloat);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const background = (el) => {
    for (let n = el; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.5) return c;
    }
    return {r: 255, g: 255, b: 255, a: 1};
  };
  const howHidden = (el) => {
    let aria = false;
    for (let n = el, depth = 0; n && depth < 10; n = n.parentElement, depth++) {
      if (n.getAttribute && n.getAttribute('aria-hidden') === 'true') aria = true;
      const s = getComputedStyle(n);
      const r = n.getBoundingClientRect();
      if (r.right + scrollX <= 0 || r.bottom + scrollY <= 0 || r.left + scrollX < -1000 || r.top + scrollY < -1000) {
        return 'off_screen';
      }
      if (s.display === 'none' || s.visibility === 'hidden') return 'display_none';
      if (parseFloat(s.opacity) < 0.05) return 'transparent';
      if ((r.width <= 2 || r.height <= 2) && s.overflow !== 'visible') return 'clipped';
    }
    const s = getComputedStyle(el);
    if (parseFloat(s.fontSize) < 3) return 'tiny_text';
    const c = parse(s.color);
    const b = background(el);
    if (c && c.a > 0.1 && Math.abs(c.r - b.r) <= 12 && Math.abs(c.g - b.g) <= 12 && Math.abs(c.b - b.b) <= 12) {
      return 'white_on_white';
    }
    return aria ? 'aria_hidden' : null;
  };
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT);
  const nodes = [];
  for (let n = walker.nextNode(); n && nodes.length < 6000; n = walker.nextNode()) nodes.push(n);
  for (const node of nodes) {
    const value = node.nodeValue || '';
    if (value.trim().length < 12) continue;
    if (node.nodeType === 8) {
      if (looksLikeInstruction(value)) {
        found.push({method: 'html_comment', text: value.slice(0, 1500)});
        node.parentNode.removeChild(node);
      }
      continue;
    }
    const el = node.parentElement;
    if (!el || SKIP.has(el.tagName) || !looksLikeInstruction(value)) continue;
    const how = howHidden(el);
    if (!how) continue;
    found.push({method: how, text: value.slice(0, 1500)});
    node.nodeValue = '';
  }
  for (const el of document.querySelectorAll('[alt],[title],[aria-label],[aria-description],[placeholder]')) {
    for (const name of ['alt', 'title', 'aria-label', 'aria-description', 'placeholder']) {
      const value = el.getAttribute(name);
      if (value && value.length >= 12 && looksLikeInstruction(value)) {
        found.push({method: 'attribute', text: value.slice(0, 1500)});
        el.removeAttribute(name);
      }
    }
  }
  return JSON.stringify(found);
})()"""


async def sweep(page, step: int | None = None, where: str = "look") -> int:
    """Empty hidden instruction text in the open page and record where it was found. Returns how many blocks.

    Never raises: a page that cannot be read is simply not swept. `step` is the step about to run (0 for the
    first impression, before any step; None for the final check); `where` says which reader asked.
    """
    state = _state.get()
    if state is None:
        return 0
    try:
        raw = await page.evaluate(_SWEEP_JS % json.dumps(PATTERNS))
        items = json.loads(raw) if isinstance(raw, str) else []
        url = _clean_url(await page.url())
    except Exception:
        return 0
    count = 0
    for item in items:
        text = str(item.get("text") or "")
        method = str(item.get("method") or "unknown")
        state.fragments += [n for n in (_norm(s) for s in _sentences(text)) if len(n) >= 25]
        if _norm(text) and len(_norm(text)) >= 25:
            state.fragments.append(_norm(text))
        entry = next((e for e in state.found if (e["url"], e["method"], e["where"]) == (url, method, where)), None)
        if entry:
            entry["blocks"] += 1
        else:
            state.found.append({"url": url, "step": step, "where": where, "method": method, "blocks": 1})
        count += 1
    return count


def with_notice(review: dict | None, max_items: int = 4) -> dict | None:
    """A first-impression review with the fixed notice first among its hesitations, if hidden text was found.

    The review's other text is sanitized. The notice is written here, not by a model.
    """
    if not isinstance(review, dict):
        return review
    review = sanitize(review)
    if found():
        hesitations = [h for h in review.get("hesitations", []) if h != NOTICE]
        review["hesitations"] = ([NOTICE] + hesitations)[:max_items]
    return review


def apply_to_result(result: dict) -> dict:
    """A finished run's result with every model-written string sanitized, the notice in the first
    impression, and the evidence in `hidden_text` (None when nothing was found)."""
    cleaned = sanitize(result)
    where = found()
    if isinstance(cleaned.get("first_impression"), dict):
        cleaned["first_impression"] = with_notice(cleaned["first_impression"])
    cleaned["hidden_text"] = ({"notice": NOTICE, "found": where, "sentences_removed": removed_count()}
                              if where else None)
    return cleaned
