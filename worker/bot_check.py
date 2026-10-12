"""Bot checks: "Verify you are human", a Cloudflare interstitial, a CAPTCHA the visitor is shown.

The visitor never tries to get past one. It does not click the box, wait for it to pass, solve it or
look for another way in: a site that asks whether it is a robot has been answered, and the visit
ends as blocked, saying so. Detection is by what the page shows (its title, its visible words and a
challenge frame large enough to be one), so the invisible reCAPTCHA badge on an ordinary login page
is not a bot check.
"""

import json
import re

# What a challenge page says, in its title or its visible text.
PHRASES = re.compile(
    r"(verify (that )?you(?:'re| are)( a)? human|are you (a )?(human|robot)|i'?m not a robot|"
    r"checking (if|whether) (the site connection is secure|you are human)|checking your browser before|"
    r"complete the (captcha|security check)|performing security verification|"
    r"enable javascript and cookies to continue|press (and|&) hold|select all (images|squares)|"
    r"please (stand by|wait) while we (check|verify) (your browser|that you))",
    re.IGNORECASE,
)
TITLES = re.compile(r"^(just a moment|attention required|security check|access denied|verifying you are human)",
                    re.IGNORECASE)

_READ_JS = r"""(() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const frames = [...document.querySelectorAll('iframe')].filter((f) => {
    const r = f.getBoundingClientRect();
    return visible(f) && r.width > 150 && r.height > 50 &&
      /(challenges\.cloudflare\.com|hcaptcha\.com|turnstile|recaptcha\/(api2|enterprise)\/bframe|captcha)/i
        .test((f.src || '') + ' ' + (f.title || ''));
  }).length;
  const widget = !!document.querySelector('#challenge-form, #challenge-stage, .cf-turnstile, #cf-challenge-running, .g-recaptcha:not([data-size=invisible]), .h-captcha');
  return JSON.stringify({title: document.title || '', text: (document.body ? document.body.innerText : '').slice(0, 4000),
                         frames, widget});
})()"""


def classify(title: str, text: str, frames: int = 0, widget: bool = False) -> str | None:
    """The phrase that identifies a bot check on a page, or None. Pure, so it can be tested."""
    match = PHRASES.search(text or "")
    if match:
        return " ".join(match.group(0).split())
    if TITLES.search((title or "").strip()) and (frames or widget):
        return (title or "").strip()
    if frames and widget:
        return "a bot-check challenge"
    return None


async def detect(page) -> dict | None:
    """{"phrase", "url", "title"} if the page now shows a bot check, else None. Never raises."""
    try:
        read = json.loads(await page.evaluate(_READ_JS))
        phrase = classify(read["title"], read["text"], read["frames"], read["widget"])
        if phrase is None:
            return None
        return {"phrase": phrase[:120], "url": await page.url(), "title": read["title"][:120]}
    except Exception:
        return None


def reason(found: dict) -> str:
    """The reason a run ends blocked here. States what happened and that nothing was attempted."""
    return (f'The site showed a bot check ("{found["phrase"]}") at {found["url"]}. The visitor does not try to '
            "get past bot checks, so the visit stopped here: blocked by a bot check.")
