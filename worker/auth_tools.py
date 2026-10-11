"""sign_in and sign_up: the two ways the visitor gets past a login form.

The agent calls them with no arguments and never sees a credential. Values are typed through
Stagehand variables (the model sees "%email%" and "%password%", Stagehand substitutes the
real values locally and, per its docs, they are not sent to the model; caching is turned off
for these calls because it would send them to a cache service). If the variable route does
not leave the right value in the field, a local fill puts it there. Results contain field
names, booleans and the page's own messages, scrubbed, never a value.

Never used, on purpose: Google, GitHub or any other third-party login. If those are the only
ways in, the run ends as blocked and says which options the page offered.
"""

import json

import neatlogs

import credentials as credentials_module
import login_diagnosis
import page_watch
import trace_safety
from config import ACT_TIMEOUT_MS
from tools import (
    _active_page,
    _changed_since,
    _screenshot,
    current_run,
    metered,
    page_fingerprint,
)

# Finds the form's fields and tags them with data-fu-field, so they can be addressed without
# the model. mode is "signin" or "signup". It reads the page; it never writes a value.
_SCAN_JS = r"""((mode) => {
  const TEXTLIKE = ['text', 'email', 'tel', 'search', 'url', ''];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && !el.disabled && el.type !== 'hidden';
  };
  const labelOf = (el) => [
    el.labels && el.labels[0] ? el.labels[0].innerText : '', el.getAttribute('aria-label') || '',
    el.placeholder || '', el.name || '', el.id || '', el.getAttribute('autocomplete') || '',
  ].join(' ').toLowerCase();
  document.querySelectorAll('[data-fu-field]').forEach((e) => e.removeAttribute('data-fu-field'));
  const inputs = [...document.querySelectorAll('input, textarea')].filter(visible);
  const order = new Map(inputs.map((el, i) => [el, i]));
  const passwords = inputs.filter((el) => el.type === 'password');
  const textlike = inputs.filter((el) => el.tagName === 'INPUT' && TEXTLIKE.includes(el.type));
  const formOf = (el) => el.closest('form') || document.body;
  const tag = (el, name) => { if (el) el.setAttribute('data-fu-field', name); return !!el; };
  const tagged = [];
  const note = (el, name) => { if (tag(el, name)) tagged.push(name); };

  let pw = null, identifier = null, confirmPw = null, submit = null;
  if (mode === 'signin') {
    pw = passwords.find((e) => /current-password/.test(e.autocomplete)) || passwords[0] || null;
    const scope = pw ? textlike.filter((e) => formOf(e) === formOf(pw) && order.get(e) < order.get(pw)) : textlike;
    const rank = (e) => (e.type === 'email' || /(e-?mail|user ?name|login|account|identifier|phone)/.test(labelOf(e))) ? 0 : 1;
    identifier = [...scope].sort((a, b) =>
      rank(a) - rank(b) || (pw ? order.get(b) - order.get(a) : order.get(a) - order.get(b)))[0] || null;
    note(identifier, 'identifier');
    note(pw, 'password');
  } else {
    pw = passwords.find((e) => /new-password/.test(e.autocomplete)) || passwords[0] || null;
    confirmPw = pw ? passwords.find((e) => e !== pw && formOf(e) === formOf(pw)) || null : null;
    const inForm = (e) => !pw || formOf(e) === formOf(pw);
    const email = textlike.find((e) => inForm(e) && (e.type === 'email' || /e-?mail/.test(labelOf(e)))) || null;
    const first = textlike.find((e) => inForm(e) && /(first|given)[ _-]?name|fname/.test(labelOf(e))) || null;
    const last = textlike.find((e) => inForm(e) && /(last|family|sur)[ _-]?name|lname/.test(labelOf(e))) || null;
    const full = first ? null : textlike.find((e) => inForm(e) && e !== email &&
      /(^|\s)(full[ _-]?name|your name|name)(\s|$)/.test(labelOf(e)) && !/user/.test(labelOf(e))) || null;
    const username = textlike.find((e) => inForm(e) && e !== email && e !== first && e !== last && e !== full &&
      /user ?name|handle|login/.test(labelOf(e))) || null;
    identifier = email;
    note(email, 'email'); note(first, 'first_name'); note(last, 'last_name'); note(full, 'full_name');
    note(username, 'username'); note(pw, 'password'); note(confirmPw, 'confirm_password');
    let k = 0;
    for (const box of inputs.filter((e) => e.type === 'checkbox' && inForm(e))) {
      const text = (labelOf(box) + ' ' + (box.closest('label') ? box.closest('label').innerText : '')).toLowerCase();
      if (/(terms|privacy|agree|accept|policy|consent)/.test(text)) { box.setAttribute('data-fu-field', 'terms' + k++); tagged.push('terms'); }
    }
  }

  const scopeEl = pw ? formOf(pw) : (identifier ? formOf(identifier) : document.body);
  const buttons = [...scopeEl.querySelectorAll('button, input[type=submit], [role=button]')].filter(visible);
  const text = (b) => (b.innerText || b.value || b.getAttribute('aria-label') || '').trim();
  submit = buttons.find((b) => b.type === 'submit') || buttons.find((b) =>
    /(sign ?in|log ?in|login|continue|next|submit|sign ?up|register|create|join|get started)/i.test(text(b))) || null;
  if (submit) tag(submit, 'submit');
  const submitText = submit ? text(submit).slice(0, 60) : '';

  const pageText = (document.body ? document.body.innerText : '');
  const headings = [...document.querySelectorAll('h1, h2, legend')].filter(visible).map((h) => h.innerText).join(' | ').toLowerCase();
  const signupish = !!confirmPw || (pw && /new-password/.test(pw.autocomplete)) ||
    /(sign ?up|register|create (your |an |a )?(free )?account|join)/i.test(submitText) ||
    (/(sign ?up|register|create (your |an |a )?(free )?account|join)/.test(headings) && !/(sign ?in|log ?in|welcome back)/.test(headings));

  // Third-party options: "Continue with Google", or a bare brand name on a button or link.
  const BRANDS = /^(google|github|gitlab|facebook|apple|microsoft|linkedin|twitter|x|okta|slack|discord|twitch|amazon|sso|single sign[- ]on)$/i;
  const options = [];
  for (const el of document.querySelectorAll('a, button, [role=button], input[type=submit], input[type=button]')) {
    if (!visible(el)) continue;
    const t = text(el);
    if (!t || t.length > 60) continue;
    const m = t.match(/(?:continue|sign ?in|sign ?up|log ?in|login|register|connect)\s+(?:with|using|via)\s+(.+)/i);
    const name = m ? m[1].trim() : (BRANDS.test(t) ? t : '');
    if (name && !options.includes(name)) options.push(name.slice(0, 30));
  }

  const alertEl = [...document.querySelectorAll('[role=alert], [aria-live=assertive], .error, .alert, [class*=error], [class*=invalid]')]
    .filter((e) => visible(e) && (e.innerText || '').trim()).map((e) => e.innerText.trim())[0] || '';

  const verification = /(verify your (e-?mail|account)|check your (e-?mail|inbox)|confirm(ation)? (e-?mail|link)|we(?:'ve| have) (?:just )?sent (?:you )?(?:an? )?(?:e-?mail|link|code)|verification (?:code|link|e-?mail)|enter the (?:6-digit )?code)/i
    .test(pageText.slice(0, 5000));

  // Steps the visitor cannot do. A CAPTCHA frame must be big enough to be a challenge (the invisible
  // reCAPTCHA badge is not one); the text patterns are the ones a challenge page uses.
  const bigFrame = [...document.querySelectorAll('iframe')].some((f) => {
    const r = f.getBoundingClientRect();
    return visible(f) && r.width > 150 && r.height > 100 &&
      /(recaptcha|hcaptcha|turnstile|captcha|challenge)/i.test((f.src || '') + ' ' + (f.title || ''));
  });
  const head = pageText.slice(0, 5000);
  const captcha = bigFrame || /(i'?m not a robot|verify (that )?you(?:'re| are)( a)? human|complete the (captcha|security check)|select all (images|squares)|press (and|&) hold|are you a robot)/i.test(head);
  const twoFactor = !!document.querySelector('input[autocomplete="one-time-code"]') ||
    /(two-?factor|\b2fa\b|2-step verification|two-step verification|authenticator app|one-time (pass)?code|security code|enter the (6|six)[- ]digit (code|number)|authentication code)/i.test(head);
  const challenge = captcha ? 'captcha' : twoFactor ? 'two_factor' : verification ? 'email_verification' : '';

  return JSON.stringify({
    has_password: !!pw, has_identifier: !!identifier, signupish, tagged, submit_text: submitText,
    third_party_options: options.slice(0, 6), page_message: alertEl.slice(0, 200),
    asks_for_verification: verification, challenge, form_title: headings.slice(0, 80),
  });
})(%s)"""

# The tagged field's current value. It is compared with the secret here, in Python: a secret is
# never sent into the page as part of a script (see credentials.py).
_FIELD_VALUE_JS = r"""((field) => {
  const el = document.querySelector('[data-fu-field="' + field + '"]');
  return el ? el.value : null;
})(%s)"""
_FOCUS_JS = r"""((field) => {
  const el = document.querySelector('[data-fu-field="' + field + '"]');
  if (el) el.focus();
  return !!el;
})(%s)"""

async def _scan(page, mode: str) -> dict:
    return json.loads(await page.evaluate(_SCAN_JS.replace("%s", json.dumps(mode))))


async def _field_equals(page, field: str, value: str) -> bool:
    current = await page.evaluate(_FIELD_VALUE_JS.replace("%s", json.dumps(field)))
    return isinstance(current, str) and current == value


async def _enter_secret(ctx, page, field: str, instruction: str, variable: str, value: str) -> str:
    """Type a secret into a tagged field through a Stagehand variable; fall back to a local fill.

    Returns "variable", "local" or "failed". Nothing in the return value contains the secret.
    """
    try:
        await ctx.stagehand.act(
            instruction, page=page, variables={variable: value}, cache=False, timeout=ACT_TIMEOUT_MS
        )
    except Exception:
        pass  # the field is checked below, whatever happened
    if await _field_equals(page, field, value):
        return "variable"
    try:
        await page.locator(f'[data-fu-field="{field}"]').fill(value)
    except Exception:
        return "failed"
    return "local" if await _field_equals(page, field, value) else "failed"


async def _set_plain(page, field: str, value: str) -> bool:
    """Fill a field with a value that is not secret (a generated name)."""
    try:
        await page.locator(f'[data-fu-field="{field}"]').fill(value)
    except Exception:
        return False
    return await _field_equals(page, field, value)


async def _submit(page, before: str) -> bool:
    """Submit the form: Enter in the password field, else the form's submit button."""
    await page.evaluate(_FOCUS_JS.replace("%s", json.dumps("password")))
    await page.key_press("Enter")
    if await _changed_since(before):
        return True
    try:
        await page.locator('[data-fu-field="submit"]').click()
    except Exception:
        try:
            await page.locator('[data-fu-field="submit"]').send_click_event()
        except Exception:
            return False
    return await _changed_since(before)


async def _wait_for_password_field(page, seconds: float = 6.0) -> dict:
    scan = await _scan(page, "signin")
    waited = 0.0
    while not scan["has_password"] and waited < seconds:
        await page.wait_for_timeout(500)
        waited += 0.5
        scan = await _scan(page, "signin")
    return scan


def _note_login_wall(ctx, scan: dict) -> None:
    ctx.entry["login_wall_seen"] = True
    for option in scan.get("third_party_options", []):
        if option not in ctx.entry["third_party_options"]:
            ctx.entry["third_party_options"].append(option)


def _result(ctx, page_url: str, *, tool: str, success: bool, changed: bool, reason: str, message: str,
            screenshot=None, **extra):
    """A tool result with fixed leading keys. Scrubbed, though nothing here should hold a secret."""
    result = {
        "success": success,
        "changed": changed,
        "reason": reason,
        "kind": tool,
        "url": page_url,
        **extra,
        "message": message,
    }
    if screenshot:
        result["screenshot_url"] = screenshot
    return trace_safety.scrub(result)


MAX_ATTEMPTS = 2  # one try and one retry of the same credentials, and only after "no effect"


def _already_tried(ctx, stage: str, tool: str, url: str):
    """A refusal, if this form was already tried and a second go cannot help; else None.

    Never the same credentials more than once more: a rejection or a verification step will not
    change by typing the same thing again, and a second "no effect" is final.
    """
    previous = ctx.entry.get("diagnosis")
    attempts = ctx.entry.setdefault("auth_attempts", {}).get(stage, 0)
    final = previous and previous["stage"] == stage and previous["result"] in ("rejected", "needs_verification")
    if not final and attempts < MAX_ATTEMPTS:
        return None
    return _result(
        ctx, url, success=False, changed=False, tool=tool, reason="already_tried",
        message="This form was already tried and did not work: " + login_diagnosis.describe(previous or {
            "stage": stage, "result": "no_effect"}) + " The same details are not tried again. Call finish with "
        "outcome blocked and give that reason.",
    )


def _conclude(ctx, *, stage: str, tool: str, diagnosis: dict, url: str, fields: list[str], errors: list[str],
              shot, changed: bool, signed_in_message: str, created_email: str | None = None):
    """Record the diagnosis and turn it into the tool's result. When the visitor is not in, the run
    ends as blocked with the exact reason and evidence (after one retry allowed for "no effect")."""
    entry = ctx.entry
    attempts = entry.setdefault("auth_attempts", {})
    attempts[stage] = attempts.get(stage, 0) + 1
    diagnosis = trace_safety.scrub(diagnosis)
    entry["diagnosis"] = diagnosis
    outcome = diagnosis["result"]
    state_key = "test_login" if stage == "sign_in" else "self_signup"

    if outcome == "signed_in":
        entry[state_key] = "used"
        entry["login_wall_seen"] = False
        extra = {"created_account_email": created_email} if created_email else {}
        return _result(
            ctx, url, success=True, changed=True, tool=tool, reason="signed_in" if stage == "sign_in" else "signed_up",
            fields_filled=fields, login_form_still_visible=False, page_errors=errors, screenshot=shot,
            message=signed_in_message, **extra,
        )

    reason = trace_safety.scrub(login_diagnosis.describe(diagnosis))
    detail = dict(
        fields_filled=fields, login_form_still_visible=diagnosis["form_still_visible"], page_errors=errors,
        page_message=diagnosis.get("page_message"), http_statuses=diagnosis.get("http_statuses"),
        challenge=diagnosis.get("challenge"), screenshot=shot,
    )
    if outcome == "no_effect" and attempts[stage] < MAX_ATTEMPTS:
        entry[state_key] = "failed"
        return _result(
            ctx, url, success=False, changed=changed, tool=tool, reason="no_effect", **detail,
            message=reason + " One more try with the same details is allowed, after you look at the page. "
            "If that also has no effect the visit ends as blocked.",
        )

    entry[state_key] = "blocked_verification" if (stage == "sign_up" and outcome == "needs_verification") else "failed"
    ctx.finished = {
        "outcome": "blocked", "stopped_by": f"{stage}_{outcome}", "reason": reason,
        "evidence": login_diagnosis.evidence(diagnosis),
    }
    return _result(
        ctx, url, success=False, changed=changed, tool=tool, reason=outcome, **detail,
        message=f"{reason} The visit is ending as blocked with that reason.",
    )


@neatlogs.span(kind="TOOL", tool_name="sign_in")
@metered
async def sign_in() -> dict:
    """Sign in with the founder's test account, if one was given."""
    ctx = current_run.get()
    page = await _active_page()
    creds = ctx.credentials
    scan = await _scan(page, "signin")
    url = await page.url()
    if creds is not None and (refusal := _already_tried(ctx, "sign_in", "sign_in", url)) is not None:
        return refusal

    if creds is None:
        _note_login_wall(ctx, scan)
        unavailable = ctx.entry["test_login"] == "failed"
        return _result(
            ctx, url, success=False, changed=False, tool="sign_in",
            reason="test_login_unavailable" if unavailable else "no_test_credentials",
            third_party_options=scan["third_party_options"],
            message=(
                "The test login could not be loaded for this run. " if unavailable
                else "No test account was provided for this run. "
            ) + "If the page itself shows a demo login for visitors, type those with do. If the page has a "
            "sign-up form with an email and a password, call sign_up. If neither, call finish with outcome "
            "blocked and say the page needs a login. Never use Google, GitHub or other third-party login.",
        )

    if not scan["has_password"] and not scan["has_identifier"]:
        _note_login_wall(ctx, scan)
        only_third_party = bool(scan["third_party_options"])
        return _result(
            ctx, url, success=False, changed=False, tool="sign_in",
            reason="only_third_party_login" if only_third_party else "no_login_form",
            third_party_options=scan["third_party_options"],
            message=(
                "This page offers only third-party sign-in (" + ", ".join(scan["third_party_options"]) + "). "
                "Do not use those. If there is an email-and-password option behind another link, open it with do "
                "and call sign_in again; otherwise call finish with outcome blocked and name these options."
                if only_third_party
                else "No login form is visible on this page. Open the page that has the login form, then call "
                "sign_in again."
            ),
        )
    _note_login_wall(ctx, scan)

    since = await page_watch.now(page)
    how = {}
    if scan["has_identifier"]:
        how["email"] = await _enter_secret(
            ctx, page, "identifier", "type %email% into the email or username field of the sign-in form",
            "email", creds.email,
        )
    if not scan["has_password"]:
        # A two-step login: the password field appears after the first step.
        await page.key_press("Enter")
        scan = await _wait_for_password_field(page)
    if scan["has_password"]:
        how["password"] = await _enter_secret(
            ctx, page, "password", "type %password% into the password field of the sign-in form",
            "password", creds.password,
        )
    typed = [name for name, outcome in how.items() if outcome != "failed"]
    if "password" not in typed:
        diagnosis = login_diagnosis.diagnose(
            stage="sign_in", before=scan, after=scan, submitted=False, errors=[], before_url=url,
            after_url=await page.url(), step=ctx.tool_calls,
            detail="the test login could not be entered into the form.",
        )
        return _conclude(
            ctx, stage="sign_in", tool="sign_in", diagnosis=diagnosis, url=await page.url(), fields=typed,
            errors=[], shot=None, changed=False, signed_in_message="",
        )

    before_url = await page.url()
    after_fill = await page_fingerprint(page)
    submitted = await _submit(page, after_fill)
    after = await _scan(page, "signin")
    errors = await page_watch.collect(page, since)
    shot = await _screenshot_redacted(ctx, page)
    after_url = await page.url()
    diagnosis = login_diagnosis.diagnose(
        stage="sign_in", before=scan, after=after, submitted=submitted, errors=errors,
        before_url=before_url, after_url=after_url, step=ctx.tool_calls,
    )
    return _conclude(
        ctx, stage="sign_in", tool="sign_in", diagnosis=diagnosis, url=after_url, fields=typed, errors=errors,
        shot=shot, changed=submitted,
        signed_in_message="Signed in with the test account. Look at the page to see where you are.",
    )


@neatlogs.span(kind="TOOL", tool_name="sign_up")
@metered
async def sign_up() -> dict:
    """Create a throwaway test account on an email-and-password sign-up form."""
    ctx = current_run.get()
    page = await _active_page()
    scan = await _scan(page, "signup")
    url = await page.url()
    _note_login_wall(ctx, scan)

    if ctx.access_mode != "signup":
        # The founder chose another way in; the visitor does not create accounts on its own.
        return _result(
            ctx, url, success=False, changed=False, tool="sign_up", reason="signup_not_allowed",
            third_party_options=scan["third_party_options"],
            message="The founder did not let this visit sign up by itself, so no account was made. Carry on with "
            "what is public, or call finish with outcome blocked and say the page needs a login and none was given.",
        )

    usable = scan["has_password"] and scan["has_identifier"] and scan["signupish"]
    if not usable:
        only_third_party = bool(scan["third_party_options"]) and not scan["has_password"]
        if only_third_party:
            ctx.entry["self_signup"] = "blocked_third_party"
            options = ", ".join(scan["third_party_options"])
            ctx.finished = {
                "outcome": "blocked", "stopped_by": "third_party_login_only",
                "reason": f"The only ways in offered were third-party sign-in options ({options}). "
                "The visitor never uses Google, GitHub or other third-party login, so it stopped here.",
            }
            return _result(
                ctx, url, success=False, changed=False, tool="sign_up", reason="only_third_party_login",
                third_party_options=scan["third_party_options"],
                message="Only third-party sign-in is offered. The run is ending as blocked and will say which "
                "options were offered.",
            )
        return _result(
            ctx, url, success=False, changed=False, tool="sign_up", reason="no_signup_form",
            login_form_visible=scan["has_password"] and not scan["signupish"],
            third_party_options=scan["third_party_options"],
            message="There is no email-and-password sign-up form on this page. Open the page that has it (a "
            "'Sign up' or 'Create account' link) with do, then call sign_up again.",
        )

    if (refusal := _already_tried(ctx, "sign_up", "sign_up", url)) is not None:
        return refusal

    identity = credentials_module.generate_identity()
    identity.credentials.register(include_email=False)  # the generated email is shown to the founder on purpose
    since = await page_watch.now(page)
    how = {
        "email": await _enter_secret(
            ctx, page, "email", "type %email% into the email field of the sign-up form", "email",
            identity.credentials.email,
        ),
        "password": await _enter_secret(
            ctx, page, "password", "type %password% into the password field of the sign-up form", "password",
            identity.credentials.password,
        ),
    }
    if "confirm_password" in scan["tagged"]:
        how["confirm_password"] = await _enter_secret(
            ctx, page, "confirm_password", "type %password% into the confirm password field of the sign-up form",
            "password", identity.credentials.password,
        )
    for field, value in (("first_name", identity.first_name), ("last_name", identity.last_name),
                         ("full_name", identity.full_name), ("username", "firstuser" + identity.email.split("@")[0][-8:])):
        if field in scan["tagged"]:
            how[field] = "local" if await _set_plain(page, field, value) else "failed"
    terms = [name for name in scan["tagged"] if name == "terms"]
    for index in range(len(terms)):
        try:
            await page.locator(f'[data-fu-field="terms{index}"]').click()
        except Exception:
            pass

    fields = [name for name, outcome in how.items() if outcome != "failed"]
    if how.get("email") == "failed" or how.get("password") == "failed":
        diagnosis = login_diagnosis.diagnose(
            stage="sign_up", before=scan, after=scan, submitted=False, errors=[], before_url=url,
            after_url=await page.url(), step=ctx.tool_calls, detail="the sign-up form could not be filled in.",
        )
        return _conclude(
            ctx, stage="sign_up", tool="sign_up", diagnosis=diagnosis, url=await page.url(), fields=fields,
            errors=[], shot=None, changed=False, signed_in_message="",
        )

    before_url = await page.url()
    after_fill = await page_fingerprint(page)
    submitted = await _submit(page, after_fill)
    after = await _scan(page, "signup")
    errors = await page_watch.collect(page, since)
    shot = await _screenshot_redacted(ctx, page)
    after_url = await page.url()
    ctx.entry["created_account_email"] = identity.email
    diagnosis = login_diagnosis.diagnose(
        stage="sign_up", before=scan, after=after, submitted=submitted, errors=errors,
        before_url=before_url, after_url=after_url, step=ctx.tool_calls,
    )
    return _conclude(
        ctx, stage="sign_up", tool="sign_up", diagnosis=diagnosis, url=after_url, fields=fields, errors=errors,
        shot=shot, changed=submitted, created_email=identity.email,
        signed_in_message="A test account was created. Look at the page to see where you are.",
    )


async def _screenshot_redacted(ctx, page):
    """A step screenshot taken with the test login hidden in the page."""
    try:
        async with credentials_module.redacted_page(page):
            return await _screenshot(ctx, page)
    except Exception:
        return None


AUTH_FUNCTIONS = {"sign_in": sign_in, "sign_up": sign_up}

_THOUGHT = {
    "type": "string",
    "description": "One complete first-person sentence saying what you see and why you are doing this.",
}


def _no_arguments_schema() -> dict:
    return {
        "type": "object",
        "properties": {"thought": _THOUGHT},
        "required": ["thought"],
        "additionalProperties": False,
    }


AUTH_SCHEMAS = [
    {
        "name": "sign_in",
        "description": (
            "Sign in on the login form that is on the page now, using the test account the founder provided. "
            "It takes no arguments: you never see or type the email or password. If no test account was "
            "provided it says so; a demo login written on the page itself you can type with do instead. "
            "Never use Google, GitHub or any other third-party login."
        ),
        "input_schema": _no_arguments_schema(),
        "strict": True,
    },
    {
        "name": "sign_up",
        "description": (
            "Create a throwaway test account on the email-and-password sign-up form that is on the page now. "
            "It takes no arguments: it makes up the name, email and password itself. If the app needs the email "
            "verified, or only offers Google, GitHub or other third-party sign-in, the run ends as blocked."
        ),
        "input_schema": _no_arguments_schema(),
        "strict": True,
    },
]
