"""The state of the element an action was aimed at, just before and just after it.

A visual change (a button turning green, a toggle switching on) has no new text and no new URL, so
a record that only says "the page changed" leaves the verifier guessing. tools.do() reads, in the
page, the interactive elements' text, class, ARIA state and computed colours before and after an
action; this module picks the target, describes the colours in words, finds what changed and writes
it into the record.

Nothing here is specific to a site: the target is the element whose own text best matches the
instruction (a quoted label first), and every other interactive element that changed is listed too.
Pure functions on plain dicts, so they are tested without a browser.
"""

import colorsys
import re

MAX_ELEMENTS = 80
MAX_OTHERS = 3
MAX_LABEL = 80

# One snapshot of the page's interactive elements, in the page. It keeps the elements themselves in
# window.__fuElements (not as attributes in the DOM), so the "after" read is of the same elements.
SNAPSHOT_JS = r"""((mode) => {
  const SELECTOR = 'a, button, input, select, textarea, summary, label, [role=button], [role=link], ' +
    '[role=checkbox], [role=switch], [role=tab], [role=menuitem], [role=option], [onclick], [aria-pressed], ' +
    '[aria-expanded]';
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  let elements;
  if (mode === 'before') {
    elements = [...document.querySelectorAll(SELECTOR)].filter(visible).slice(0, %d);
    window.__fuElements = elements;
  } else {
    elements = window.__fuElements;
    if (!elements) return null;
  }
  const clip = (text, n) => String(text || '').replace(/\s+/g, ' ').trim().slice(0, n);
  return elements.map((el, i) => {
    const st = getComputedStyle(el);
    const aria = {};
    for (const name of ['aria-pressed', 'aria-checked', 'aria-expanded', 'aria-selected', 'aria-disabled',
                        'aria-current', 'aria-busy']) {
      if (el.hasAttribute(name)) aria[name] = el.getAttribute(name);
    }
    return {
      i, connected: el.isConnected, tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
      label: clip(el.innerText || el.value || el.getAttribute('aria-label') || el.title || el.alt || '', %d),
      cls: clip(el.getAttribute('class'), 120), aria,
      disabled: !!el.disabled,
      checked: (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : null,
      color: st.color, background: st.backgroundColor,
    };
  });
})(%s)"""

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)")
_QUOTED = re.compile(r"""['"‘“]([^'"’”]{2,})['"’”]""")
_WORDS_NOT_TARGETS = frozenset((
    "click tap press hit push select choose open the a an on to of and then button link element item "
    "icon menu please that this into with for its your".split()))


def colour_name(value: str | None) -> str:
    """A computed CSS colour as a short phrase: 'rgb(40, 167, 69) (green)', or 'transparent'."""
    match = _RGB.match((value or "").strip())
    if not match:
        return value or "none"
    r, g, b = (float(match.group(i)) for i in (1, 2, 3))
    alpha_text = match.group(4)
    alpha = 1.0
    if alpha_text:
        alpha = float(alpha_text[:-1]) / 100 if alpha_text.endswith("%") else float(alpha_text)
    if alpha == 0:
        return "transparent"
    hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if light > 0.93:
        word = "white"
    elif light < 0.1:
        word = "black"
    elif sat < 0.15:
        word = "grey"
    else:
        degrees = hue * 360
        word = ("red" if degrees < 15 or degrees >= 345 else "orange" if degrees < 40 else "yellow" if degrees < 70
                else "green" if degrees < 165 else "teal" if degrees < 195 else "blue" if degrees < 255
                else "purple" if degrees < 290 else "pink")
        if word == "orange" and light < 0.3:
            word = "brown"
    plain = f"rgb({int(r)}, {int(g)}, {int(b)})"
    return f"{plain} ({word})" + (f" at {alpha:g} opacity" if alpha < 1 else "")


def _compact(state: dict) -> dict:
    """The part of one element's state that goes into the record."""
    return {
        "text": state["label"],
        "class": state["cls"],
        "aria": state["aria"],
        "disabled": state["disabled"],
        "checked": state["checked"],
        "text_colour": colour_name(state["color"]),
        "background": colour_name(state["background"]),
    }


def _differences(before: dict, after: dict) -> list[str]:
    """What changed between two compact states, as short phrases."""
    changes = []
    if before["text"] != after["text"]:
        changes.append(f"text: {before['text']!r} -> {after['text']!r}")
    if before["class"] != after["class"]:
        changes.append(f"class: {before['class']!r} -> {after['class']!r}")
    if before["aria"] != after["aria"]:
        changes.append(f"ARIA state: {before['aria']} -> {after['aria']}")
    if before["disabled"] != after["disabled"]:
        changes.append(f"disabled: {before['disabled']} -> {after['disabled']}")
    if before["checked"] != after["checked"]:
        changes.append(f"checked: {before['checked']} -> {after['checked']}")
    if before["background"] != after["background"]:
        changes.append(f"background colour: {before['background']} -> {after['background']}")
    if before["text_colour"] != after["text_colour"]:
        changes.append(f"text colour: {before['text_colour']} -> {after['text_colour']}")
    return changes


def best_match(instruction: str, states: list[dict]) -> tuple[dict, str] | None:
    """The element an instruction is about, by its own text: (state, how it was matched) or None.

    A quoted label wins (exact, then contained); otherwise the element whose text shares the most
    words with the instruction, and only when most of the element's words are in the instruction.
    Returning None is normal: nothing is claimed about an element that cannot be told.
    """
    quoted = [q.strip().lower() for q in _QUOTED.findall(instruction)]
    labelled = [s for s in states if s["label"]]
    for wanted in quoted:
        exact = [s for s in labelled if s["label"].lower() == wanted]
        if exact:
            return exact[0], "its text matches the quoted label"
        inside = [s for s in labelled if wanted in s["label"].lower()]
        if inside:
            return min(inside, key=lambda s: len(s["label"])), "its text contains the quoted label"
    words = {w for w in re.findall(r"[a-z0-9]+", instruction.lower()) if len(w) > 2} - _WORDS_NOT_TARGETS
    best, best_key = None, (0, 0.0)
    for state in labelled:
        label_words = {w for w in re.findall(r"[a-z0-9]+", state["label"].lower()) if len(w) > 2}
        if not label_words:
            continue
        shared = len(label_words & words)
        score = shared / len(label_words)
        # The most of the instruction's words in the label first, then the label with the least left over.
        if shared and score >= 0.6 and (shared, score) > best_key:
            best, best_key = state, (shared, score)
    return (best, "its text shares most of its words with the instruction") if best else None


def describe_change(instruction: str, before: list[dict] | None, after: list[dict] | None) -> dict | None:
    """The record entry for one action: the target element's state before and after, and what else changed.

    `before` and `after` are SNAPSHOT_JS results over the same elements. None when nothing can be said
    (no snapshot, a navigation that reset the page, no matching element and nothing changed).
    """
    if not before or not after or len(before) != len(after):
        return None
    pairs = [(b, a) for b, a in zip(before, after) if a.get("connected", True)]
    target = best_match(instruction, [b for b, _ in pairs])
    entry: dict = {}
    if target is not None:
        state, how = target
        after_state = next(a for b, a in pairs if b["i"] == state["i"])
        was, now = _compact(state), _compact(after_state)
        entry["target"] = {"label": state["label"], "matched_by": how, "before": was, "after": now,
                           "changed": _differences(was, now)}
    others = []
    for b, a in pairs:
        if target is not None and b["i"] == target[0]["i"]:
            continue
        changes = _differences(_compact(b), _compact(a))
        if changes:
            others.append({"label": b["label"] or f"<{b['tag']}>", "changed": changes})
    if others:
        entry["others_changed"] = others[:MAX_OTHERS]
    return entry or None


def format_for_record(entry: dict | None) -> str:
    """The entry as a sentence for the verifier's and the report writer's record."""
    if not entry:
        return ""
    parts = []
    target = entry.get("target")
    if target:
        before, after = target["before"], target["after"]

        def show(state: dict) -> str:
            bits = [f"text {state['text']!r}", f"class {state['class']!r}", f"background {state['background']}",
                    f"text colour {state['text_colour']}"]
            if state["aria"]:
                bits.append(f"ARIA {state['aria']}")
            if state["disabled"]:
                bits.append("disabled")
            if state["checked"] is not None:
                bits.append("checked" if state["checked"] else "not checked")
            return ", ".join(bits)

        parts.append(
            f"the element acted on, {target['label']!r} ({target['matched_by']}), before: {show(before)}; "
            f"after: {show(after)}; " + ("changed: " + "; ".join(target["changed"]) if target["changed"]
                                         else "nothing about it changed")
        )
    for other in entry.get("others_changed", []):
        parts.append(f"another element, {other['label']!r}, changed: " + "; ".join(other["changed"]))
    return "; ".join(parts)
