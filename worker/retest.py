"""Check again: re-run the same journey after a fix and say what changed.

Two passes, and a comparison.

  Pass 1, independent. The retest runs as an ordinary visit (visit.first_visit). The agent is never told
  what the old findings were, so it is not biased toward finding or missing them.

  Pass 2, guided, only for old findings whose page or state pass 1 never reached. The original run's
  recorded route (its actions and the page each one reached, up to the step where the finding
  happened) is followed in a fresh browser; if every step of it can be followed and lands on the same
  page, the original action is tried again and what happens is recorded. If any step cannot be
  followed (the action has no effect, a page is not the one recorded, a login is needed and not
  given), the pass stops and the finding stays Not reached. A different route is never treated as
  equivalent proof.

  Comparison. Each old finding gets one of

    fixed          the relevant step was reached and the original failure could not be reproduced
                   under comparable conditions, with the evidence step
    still_present  the relevant step was reached and the failure reproduced, with the evidence step
    not_reached    the relevant state was never reached, so it is unverified (never "fixed")
    inconclusive   the state was reached but the evidence is not enough to decide

  and the pass that produced the label. Problems the retest found that were not in the original are
  "new". The judging is done in code from recorded signals, not by a model.

"Fixed" means "not reproduced under the tested conditions". It is not a guarantee.
"""

import re
from urllib.parse import urlsplit

import neatlogs

import trace_safety

LABELS = ("fixed", "still_present", "not_reached", "inconclusive", "new")
FIXED_MEANS = "Fixed means not reproduced under the tested conditions. It is not a guarantee."
MAX_GUIDED_FINDINGS = 3
MAX_ROUTE_STEPS = 12

_STOP = frozenset("the a an and or of to in on at for with into your its this that button link click tap press "
                  "type enter field box textbox then please".split())


# ----------------------------------------------------------------------------------------- small helpers

def page_key(url: str | None) -> str:
    """A page without its query, fragment or trailing slash: the unit "same page" is judged on."""
    if not url:
        return ""
    parts = urlsplit(url)
    return f"{parts.netloc.lower()}{(parts.path or '/').rstrip('/') or '/'}"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def instruction_similar(a: str, b: str) -> bool:
    """Whether two instructions ask for the same thing (the same words, give or take a few)."""
    first, second = _words(a), _words(b)
    if not first or not second:
        return False
    return len(first & second) / len(first | second) >= 0.6


def _squash(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").replace("“", '"').replace("”", '"').split())


def normalise_error(text: str) -> set[str]:
    """An error message as the words that identify it: no prefix, no digits, URLs as their last segment."""
    text = re.sub(r"^(js_error|console_error|request):\s*", "", text or "", flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s]+", lambda m: urlsplit(m.group(0)).path.rsplit("/", 1)[-1], text)
    return {w for w in re.findall(r"[a-z_]+", text.lower()) if len(w) > 2}


def same_error(a: str, b: str) -> bool:
    first, second = normalise_error(a), normalise_error(b)
    if not first or not second:
        return False
    return len(first & second) / len(first | second) >= 0.5


# ----------------------------------------------------------------------------------------- the plan

def build_plans(old_findings: list[dict], old_steps: list[dict], start_url: str) -> list[dict]:
    """For each old finding: the route to its state, what was tried there, and how to tell if it failed.

    `old_steps` are the original run's recorded steps (idx, tool, input, result, url). The route is the
    actions that worked, in order, before the acting step; the acting step is the finding's own step
    if it was an action, or the latest action on the same page before it.
    """
    rows = {row["idx"]: row for row in old_steps if isinstance(row.get("idx"), int)}
    ordered = sorted(rows)
    plans = []
    for index, finding in enumerate(old_findings or []):
        evidence = finding.get("evidence") or {}
        step = evidence.get("step")
        page = page_key(evidence.get("url") or (rows.get(step) or {}).get("url"))
        plan = {
            "finding_index": index, "title": finding.get("title", ""), "kind": finding.get("kind"),
            "original_step": step, "target_page": page, "acting_idx": None, "acting_tool": None,
            "acting_instruction": None, "route": [], "route_error": None, "start_url": start_url,
            "signature": {"errors": [], "field_bad": False, "quote": None},
        }
        target = rows.get(step)
        acting = None
        if target is not None and target.get("tool") == "do":
            acting = target
        elif target is not None:
            for idx in reversed([i for i in ordered if i < step]):
                row = rows[idx]
                if row.get("tool") == "do" and page_key(row.get("url")) == page:
                    acting = row
                    break
        if acting is not None:
            plan["acting_idx"] = acting["idx"]
            plan["acting_tool"] = "do"
            plan["acting_instruction"] = str((acting.get("input") or {}).get("instruction", ""))
            result = acting.get("result") or {}
            plan["signature"]["errors"] = [str(e) for e in (result.get("page_errors") or []) if e]
            field = result.get("field") or {}
            plan["signature"]["field_bad"] = field.get("contains_typed_text") is False
            route_until = acting["idx"]
        else:
            route_until = step if isinstance(step, int) else 0
        quote = evidence.get("quote")
        if quote and finding.get("kind") == "unclear_wording":
            plan["signature"]["quote"] = str(quote)

        for idx in [i for i in ordered if i < route_until]:
            row = rows[idx]
            tool, result = row.get("tool"), row.get("result") or {}
            if tool in ("look", "note_friction", "finish", "scroll"):
                continue
            if tool == "go_back":
                plan["route_error"] = "the original route used Back, which is not replayed"
                break
            if tool in ("do", "sign_in", "sign_up"):
                if not result.get("success") or (tool == "do" and not result.get("changed")):
                    continue  # an attempt that did nothing is not part of the route
                plan["route"].append({
                    "idx": idx, "tool": tool,
                    "instruction": str((row.get("input") or {}).get("instruction", "")),
                    "url": row.get("url"),
                })
        if len(plan["route"]) > MAX_ROUTE_STEPS and not plan["route_error"]:
            plan["route_error"] = f"the route is {len(plan['route'])} steps long, more than the {MAX_ROUTE_STEPS} allowed"
        plans.append(plan)
    return plans


# ----------------------------------------------------------------------------------------- what was seen

def observed_from_record(entry: dict, own_issue_steps: set[int]) -> dict:
    """What a pass-1 record entry says about an action, in the form `judge` reads."""
    executed = "page_changed" in entry and "error" not in entry and entry.get("step") not in own_issue_steps
    return {
        "executed": executed,
        "changed": bool(entry.get("page_changed")),
        "page_errors": list(entry.get("page_errors") or []),
        "field_ok": entry.get("field_ok"),
    }


def observed_from_do(result: dict) -> dict:
    """The same, from a do() result."""
    ours = result.get("kind") == "agent_issue" or result.get("reason") in ("no_effect", "failed")
    field = result.get("field") or {}
    return {
        "executed": not ours,
        "changed": bool(result.get("changed")),
        "page_errors": list(result.get("page_errors") or []),
        "field_ok": field.get("contains_typed_text") if field else None,
    }


def judge(signature: dict, observed: dict | None, page_text: str | None = None) -> tuple[str, str]:
    """(label, reason) for one old finding, given what the retest saw where it was reached."""
    if observed is None:
        return "inconclusive", "the state was reached but nothing was recorded there"
    errors = signature.get("errors") or []
    if errors:
        if not observed["executed"]:
            return "inconclusive", "our browser tool could not carry out the action, so nothing can be said"
        if any(same_error(old, new) for old in errors for new in observed["page_errors"]):
            return "still_present", "the same page error appeared again"
        if observed["page_errors"]:
            return "inconclusive", "a different page error appeared; the original one did not"
        if observed["changed"]:
            return "fixed", "the action worked and the page reported no error this time"
        return "inconclusive", "no error was reported, but the page did not change either"
    if signature.get("field_bad"):
        if not observed["executed"]:
            return "inconclusive", "our browser tool could not carry out the action, so nothing can be said"
        if observed["field_ok"] is False:
            return "still_present", "the field again did not keep the typed text"
        if observed["field_ok"] is True:
            return "fixed", "the field kept the typed text this time"
        return "inconclusive", "the field's value could not be read back"
    quote = signature.get("quote")
    if quote:
        if not page_text:
            return "inconclusive", "the page's text was not read, so the wording cannot be compared"
        if _squash(quote) in _squash(page_text):
            return "still_present", "the same wording is still on the page"
        return "fixed", "the wording is no longer on the page"
    return "inconclusive", "the original gave nothing measurable to compare (no error, no field, no wording)"


def pass1_observation(plan: dict, record: list[dict], own_issue_steps: set[int],
                      page_texts: dict[str, str]) -> tuple[dict, int | None, str | None] | None:
    """What pass 1 saw at the old finding's state, or None if it never reached it.

    Reached means the page was visited and, for an action, the same action was tried there.
    """
    target = plan["target_page"]
    visited = any(page_key(e.get("url_after") or e.get("url")) == target for e in record)
    if not visited and not any(page_key(e.get("url")) == target for e in record):
        return None
    if plan["acting_tool"] == "do":
        tried = [e for e in record if e["tool"] == "do"
                 and instruction_similar(e.get("instruction", ""), plan["acting_instruction"] or "")]
        if not tried:
            return None
        entry = tried[-1]
        return observed_from_record(entry, own_issue_steps), entry["step"], page_texts.get(target)
    seen = [e for e in record if e["tool"] == "look" and page_key(e.get("url")) == target]
    if not seen:
        return None
    return {"executed": True, "changed": True, "page_errors": [], "field_ok": None}, seen[-1]["step"], \
        page_texts.get(target)


# ----------------------------------------------------------------------------------------- comparing

_RANK = {"got_through": 3, "unconfirmed": 2, "stuck": 1, "login_wall": 1}
_UNKNOWN = ("bot_check", "our_failure")


def compare_verdicts(before: dict | None, after: dict | None) -> dict:
    """The original and the retest verdicts side by side, and what changed."""
    def brief(v):
        return {"kind": v.get("kind"), "headline": v.get("headline"), "where_step": v.get("where_step"),
                "where_url": v.get("where_url")} if v else None

    out = {"before": brief(before), "after": brief(after), "change": "not_comparable", "summary": ""}
    if not before or not after:
        out["summary"] = "One of the two visits has no verdict, so they cannot be compared."
        return out
    if before["kind"] in _UNKNOWN or after["kind"] in _UNKNOWN:
        out["summary"] = ("One of the two visits says nothing about the site (a bot check or a failure on our "
                          "side), so they cannot be compared.")
        return out
    was, now = _RANK.get(before["kind"], 0), _RANK.get(after["kind"], 0)
    out["change"] = "improved" if now > was else "worse" if now < was else "same"
    out["summary"] = f"Before: {before['headline']}. After: {after['headline']}."
    return out


def same_problem(old: dict, new: dict) -> bool:
    """Whether a finding of the retest is the old finding again.

    The same symptom (report_writer.same_symptom), or, because both are about the same page and a person
    comparing a fix would call them one problem, the same page and at least two shared symptom words
    (the element and what went wrong, e.g. "Last Name" and "empty"). Looser than merging findings inside
    one report, on purpose: here the page is known to be the same journey.
    """
    from report_writer import _symptom_words, same_symptom

    if same_symptom(old, new):
        return True
    if page_key((old.get("evidence") or {}).get("url")) != page_key((new.get("evidence") or {}).get("url")):
        return False
    first, second = _symptom_words(old), _symptom_words(new)
    shared = first & second
    return len(shared) >= 2 and len(shared) / max(1, len(first | second)) >= 0.15


def fallback_verdict(row: dict, steps: list[dict] | None = None) -> dict | None:
    """A verdict for an original saved before verdicts existed, from what its row and result recorded.

    Rows from before the login fix can say "blocked at a login" because the reason mentioned a password,
    although a login written on the page was typed and accepted. If it was typed and the visit then moved
    to other pages, that is not a login block.
    """
    import verdict as verdict_module

    result = row.get("result") or {}
    entry = dict(row.get("entry") or {})
    pages = [page_key(s.get("url")) for s in steps or [] if s.get("url")]
    if entry.get("page_login") == "shown_on_page" and not entry.get("page_login_worked") and pages             and any(p != pages[0] for p in pages):
        entry["page_login_worked"] = True
        entry["blocked_at_login"] = False
    frictions = result.get("frictions") or []
    site = [f for f in frictions if f.get("kind") == "site"]
    own = [i.get("step") for i in result.get("agent_issues") or [] if isinstance(i.get("step"), int)]
    last = site[-1] if site else None
    try:
        return verdict_module.compute_verdict(
            outcome=row.get("outcome") or result.get("outcome") or "error",
            stopped_by=result.get("stopped_by"), reason=row.get("reason") or result.get("reason") or "",
            verification=result.get("verification"), entry=entry, own_issue_steps=own,
            site_friction_count=len(site),
            page_error_count=sum(1 for f in site if f.get("detected_by") == "page_errors"),
            last_step=last.get("step") if last else None, last_step_url=(last or {}).get("url"),
            site_evidence=(last.get("step"), str(last.get("happened") or "")) if last else None)
    except Exception:
        return None


def label_findings(plans: list[dict], old_findings: list[dict], *, record: list[dict], own_issue_steps: set[int],
                   page_texts: dict[str, str], new_findings: list[dict], guided: dict[int, dict]) -> dict:
    """The label of every old finding, and which pass produced it, plus the findings that are new."""
    labels, matched_new = [], set()
    for plan in plans:
        index = plan["finding_index"]
        old = old_findings[index]
        base = {"finding_index": index, "title": plan["title"], "kind": plan["kind"],
                "original_step": plan["original_step"], "original_url": (old.get("evidence") or {}).get("url"),
                "basis": "observed"}

        # The retest's own report found it again: that is the independent pass seeing it.
        # Every finding of the retest that is this old one again counts as it (a visit can write the same
        # problem up twice), and the earliest of them is the evidence.
        again_all = [j for j, new in enumerate(new_findings) if same_problem(old, new)]
        if again_all:
            matched_new.update(again_all)
            earliest = min(again_all, key=lambda j: new_findings[j]["evidence"]["step"])
            labels.append({**base, "label": "still_present", "pass": "independent",
                           "evidence_step": new_findings[earliest]["evidence"]["step"],
                           "reason": "the retest's own visit reported the same problem on the same page"})
            continue

        seen = pass1_observation(plan, record, own_issue_steps, page_texts)
        if seen is not None:
            observed, step, text = seen
            label, reason = judge(plan["signature"], observed, text)
            labels.append({**base, "label": label, "pass": "independent", "evidence_step": step, "reason": reason})
            continue

        followed = guided.get(index)
        if followed and followed.get("followed"):
            label, reason = judge(plan["signature"], followed["observed"], followed.get("page_text"))
            labels.append({**base, "label": label, "pass": "guided", "evidence_step": followed.get("evidence_step"),
                           "reason": reason + " (reached by following the original route)"})
            continue
        why = (followed or {}).get("why") or plan.get("route_error") or "the independent visit did not get there"
        labels.append({**base, "label": "not_reached", "pass": "guided" if followed else None,
                       "evidence_step": None,
                       "reason": f"{why}; so this is unverified, and it is not reported as fixed"})

    new = [{"title": f.get("title"), "evidence_step": f["evidence"]["step"], "label": "new", "basis": "observed",
            "severity": f.get("severity"), "kind": f.get("kind")}
           for j, f in enumerate(new_findings) if j not in matched_new]
    return {"labels": labels, "new": new}


# ----------------------------------------------------------------------------------------- the guided pass

@neatlogs.span(kind="AGENT", name="retest_guided", capture_input=False)
async def guided_pass(ctx, plans: list[dict], wanted: list[int]) -> dict[int, dict]:
    """Follow the original route to each wanted finding's state and try its action again.

    One fresh browser per finding (an earlier replay's login must not leak into the next route). Each
    replay stops at the first step that cannot be followed, and the finding is then Not reached. The
    pass shares the run's step count and budget: it never goes past MAX_STEPS recorded steps or the
    run's cost and token limits.
    """
    import browse
    import page_watch
    import tools
    from browser import close_browser, open_browser
    from config import MAX_STEPS
    from tools import RunContext, current_run, current_url

    trace_safety.set_input(findings=len(wanted), planned_route_steps=sum(len(plans[i]["route"]) for i in wanted))
    outcomes: dict[int, dict] = {}
    start_steps = ctx.tool_calls
    for index in wanted[:MAX_GUIDED_FINDINGS]:
        plan = plans[index]
        if plan["route_error"]:
            outcomes[index] = {"followed": False, "why": plan["route_error"]}
            continue
        if plan["acting_tool"] != "do" and not plan["signature"]["quote"]:
            outcomes[index] = {"followed": False, "why": "there is no recorded action to repeat there"}
            continue
        if any(item["tool"] == "sign_in" for item in plan["route"]) and ctx.credentials is None:
            outcomes[index] = {"followed": False, "why": "the original route signed in with a test account, "
                                                          "and none was given for this check"}
            continue
        if any(item["tool"] == "sign_up" for item in plan["route"]) and ctx.access_mode != "signup":
            outcomes[index] = {"followed": False, "why": "the original route signed up, which this check's way in "
                                                          "does not allow"}
            continue

        chrome, stagehand, page, guard = await open_browser()
        replay = RunContext(
            url=ctx.url, goal=ctx.goal, run_id=ctx.run_id, stagehand=stagehand, page=page, recorder=ctx.recorder,
            egress=guard, credentials=ctx.credentials, start_url=ctx.start_url, access_mode=ctx.access_mode,
            success_condition=ctx.success_condition,
        )
        replay.usage = ctx.usage          # one bill for the run
        replay.tool_calls = ctx.tool_calls  # steps keep counting, so evidence points at real recorded steps
        replay.step_shots, replay.step_urls = ctx.step_shots, ctx.step_urls
        token = current_run.set(replay)
        try:
            await page_watch.install(page)
            outcomes[index] = await _replay(replay, plan, browse, tools, current_url, MAX_STEPS)
        except Exception as error:
            outcomes[index] = {"followed": False, "why": f"the replay failed with {type(error).__name__}"}
        finally:
            current_run.reset(token)
            ctx.tool_calls = replay.tool_calls
            await close_browser(chrome, stagehand, guard)
        if ctx.tool_calls - start_steps >= MAX_STEPS:
            break
    for index in wanted:
        outcomes.setdefault(index, {"followed": False, "why": "the guided pass reached its step or cost limit"})
    return outcomes


async def _replay(rctx, plan: dict, browse, tools, current_url, max_steps: int) -> dict:
    """One replay in a fresh browser. Returns {"followed", "why"} or {"followed", "observed", ...}."""
    from visit import open_start_page

    limit = rctx.tool_calls + max_steps

    def stop(why: str) -> dict:
        return {"followed": False, "why": why}

    def over_budget() -> bool:
        return rctx.tool_calls >= limit or not browse.check_budget(
            rctx.usage.total_tokens, round(rctx.usage.total_cost, 5))["ok"]

    async def act(instruction: str) -> dict:
        rctx.tool_calls += 1
        result = trace_safety.scrub(await tools.do(instruction))
        if rctx.recorder is not None:
            try:
                await rctx.recorder.step(
                    rctx.tool_calls, "do", "Guided follow-up: repeating a step of the original route.",
                    {"instruction": instruction, "guided": True}, result, result.get("url"), result.get("screenshot_url"))
            except Exception:
                pass
        if result.get("screenshot_url"):
            rctx.step_shots[rctx.tool_calls] = result["screenshot_url"]
        return result

    await open_start_page(rctx.page, plan["start_url"], rctx.egress, rctx)
    for item in plan["route"]:
        if over_budget():
            return stop("the step or cost limit was reached before the route was finished")
        if item["tool"] == "do":
            result = await act(item["instruction"])
            if result.get("bot_check"):
                return stop("a bot check appeared on the route, and it is not attempted")
            if not (result.get("success") and result.get("changed")):
                return stop(f"the original step \"{item['instruction'][:70]}\" could not be followed: "
                            "it had no effect this time")
            got, wanted = page_key(result.get("url")), page_key(item.get("url"))
            if wanted and got != wanted:
                return stop(f"the flow has changed: that step led to {got}, and the original route led to {wanted}")
        else:
            import auth_tools

            rctx.tool_calls += 1
            result = await (auth_tools.sign_in() if item["tool"] == "sign_in" else auth_tools.sign_up())
            if not result.get("success"):
                return stop(f"the original route's {item['tool'].replace('_', ' ')} did not work this time "
                            f"({result.get('reason')})")

    here = page_key(await current_url())
    if plan["target_page"] and here != plan["target_page"]:
        return stop(f"the route ended on {here}, not on the page the problem was on ({plan['target_page']})")
    if over_budget():
        return stop("the step or cost limit was reached before the original action could be repeated")

    if plan["acting_tool"] == "do":
        result = await act(plan["acting_instruction"])
        if result.get("bot_check"):
            return stop("a bot check appeared, and it is not attempted")
        text = await _page_text(rctx.page)
        return {"followed": True, "observed": observed_from_do(result), "evidence_step": rctx.tool_calls,
                "page_text": text}
    text = await _page_text(rctx.page)
    return {"followed": True, "observed": {"executed": True, "changed": True, "page_errors": [], "field_ok": None},
            "evidence_step": rctx.tool_calls or None, "page_text": text}


async def _page_text(page) -> str | None:
    try:
        return trace_safety.scrub(str(await page.evaluate("document.body ? document.body.innerText : ''"))[:8000])
    except Exception:
        return None


# ----------------------------------------------------------------------------------------- the whole check

@neatlogs.span(kind="EVALUATOR", name="retest_compare", capture_input=False)
def compare(plans: list[dict], old_findings: list[dict], original_verdict: dict | None, *, ctx_view: dict,
            result: dict, guided: dict[int, dict]) -> dict:
    """Label every old finding, list the new ones, and compare the verdicts. Pure given its inputs."""
    trace_safety.set_input(old_findings=len(old_findings), guided=len(guided))
    labelled = label_findings(
        plans, old_findings, record=ctx_view["record"], own_issue_steps=ctx_view["own_issue_steps"],
        page_texts=ctx_view["page_texts"], new_findings=result.get("findings") or [], guided=guided)
    counts = {label: 0 for label in LABELS}
    for item in labelled["labels"]:
        counts[item["label"]] += 1
    counts["new"] = len(labelled["new"])
    return {
        "labels": labelled["labels"],
        "new": labelled["new"],
        "counts": counts,
        "verdict": compare_verdicts(original_verdict, result.get("verdict")),
        "fixed_means": FIXED_MEANS,
        "guided": {"attempted": len(guided), "followed": sum(1 for g in guided.values() if g.get("followed"))},
    }


async def run_checks(ctx, info: dict, result: dict) -> dict:
    """Pass 2 and the comparison, after the independent visit. `info` is the original run's findings, its
    verdict, its recorded steps and its start URL. Returns the result with `retest` added."""
    old_findings = info.get("findings") or []
    plans = build_plans(old_findings, info.get("steps") or [], info.get("start_url") or ctx.url)
    own_steps = {i["step"] for i in ctx.agent_issues if isinstance(i.get("step"), int)}
    view = {"record": ctx.record, "own_issue_steps": own_steps, "page_texts": getattr(ctx, "page_texts", {})}

    # Which old findings did the independent visit never reach (and so need the guided follow-up)?
    wanted = []
    for plan in plans:
        again = any(_matches(old_findings[plan["finding_index"]], new) for new in result.get("findings") or [])
        if not again and pass1_observation(plan, ctx.record, own_steps, view["page_texts"]) is None:
            wanted.append(plan["finding_index"])
    guided = await guided_pass(ctx, plans, wanted) if wanted else {}

    comparison = compare(plans, old_findings, info.get("verdict"), ctx_view=view, result=result, guided=guided)
    comparison["original_run_id"] = info.get("run_id")
    result = {**result, "retest": comparison, "usage": ctx.usage.summary()}
    facts = result.get("run_facts")
    if isinstance(facts, dict):  # the guided pass and the comparison cost something too
        facts["cost_usd"] = round(ctx.usage.total_cost, 5)
    return trace_safety.scrub(result)


def _matches(old: dict, new: dict) -> bool:
    return same_problem(old, new)
