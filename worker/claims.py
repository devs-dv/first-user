"""What a recommendation may and may not say.

Every statement in a report has a basis: observed (from the run record), verified (confirmed by the
independent check) or recommendation (our suggestion). A recommendation is never worded as a fact
and never promises an outcome: not a conversion lift, not "users will", not a percentage. Nobody can
know that from one visit, and a founder should not be told so.

`strip_promises` removes the sentences that make such a claim, so it is enforced in code and not
only asked of the model.
"""

import re

BASES = ("observed", "verified", "recommendation")

PROMISE = re.compile(
    r"(\bconversions?\b|\bconvert(s|ed|ing)?\b (more|better|visitors|users)|\b(boost|lift|uplift|raise|grow)s?\b"
    r"|\b(increase|improve|reduce|cut|drive|double|triple)[sd]?\b[^.]{0,40}\b(sign-?ups?|revenue|sales|engagement|"
    r"retention|traffic|users|conversion|churn|bounce|activation|adoption|completion)\b"
    r"|\d+(\.\d+)?\s?(%|percent|x\b)|\bwill (result|lead|ensure|guarantee|increase|improve|boost|double|triple|"
    r"reduce|help you (win|get|gain|close))\b|\bguarantee[sd]?\b|\bproven\b|\bROI\b|\bgrow your\b|\bmore (customers|"
    r"sales|sign-?ups|revenue)\b)",
    re.IGNORECASE,
)


def strip_promises(text: str) -> str:
    """The text without any sentence that promises an outcome; empty if nothing is left."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
    kept = [sentence for sentence in sentences if sentence and not PROMISE.search(sentence)]
    return " ".join(kept)
