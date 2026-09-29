"""The one refusal primitive. A 403, an empty body, and a reason in a header.

**Why this lives in ``isolation`` and not in a view module.** D-02 is the highest-
value line in the project: a denial is a literal ``403`` with an empty body and no
``Location`` header, because ``run.py`` follows redirects and a ``302`` to a
login page comes back to the checker as a **200**. That is a scored check failing
while the portal looks correct in a browser.

The corollary is that the rule is only worth anything if there is exactly one
implementation of it. When the judge console built its own ``_deny``, that was one
implementation, and the API surface that FEAT-05 adds would have been the second
-- at which point "our denials are 403s" becomes a claim about two code paths, and
this project has a ledger full of claims drifting from code.

So: one function, imported by the console and the API alike. A reviewer reads
this file and knows what every refusal in the portal looks like.

**Why the body is empty and the reason is a header.** Those two requirements
looked like they were in tension, and they are not. The reason a refusal is named
at all is F-40: ``run.py`` accepts *any* 4xx for "closed event refuses
submissions", so a CSRF rejection, a 401 for an unrecognised credential and a
genuine deadline refusal are indistinguishable at the status line, and the
deadline check passes without the deadline ever being consulted. The fix was to
name the guard.

D-02 then says the body must be empty. Both are satisfiable because the *body*
is what ``run.py`` looks at for content and the *header* is what a probe, a test
and a human read. ``tools/expected_checks.json``'s ``submit_refused_by_deadline``
probe asserts the guard's name in a body because that refusal is an HTML form
page; the T2 refusals here are API responses and are probed through
``header_must_contain`` instead. **The marker moved to fit the medium, not to fit
the test.**

**What a refusal is not.** It is not a redirect, not a login page, and not an
empty ``200``. "You may not" and "there is nothing here" are different answers,
and conflating them is how a permission bug hides -- a peer-blind accessor that
returns an empty queryset is the failure the brief names by name.
"""

from __future__ import annotations

from django.http import HttpResponse

#: The header carrying the machine-readable reason for a refusal. ``X-`` rather
#: than a standard header because there is no standard for this, and the prefix
#: is the convention for "a header about this request's processing".
REFUSED_BY_HEADER = "X-Refused-By"


def deny(refused_by: str, *, status: int = 403) -> HttpResponse:
    """A refusal. Literal status, empty body, no ``Location``, reason in a header.

    **Written out longhand rather than with a redirect, a template, or DRF's
    exception handler** because the three properties that make it a refusal --
    the status, the empty body and the absence of ``Location`` -- are each
    something a convenience helper is likely to change. DRF's default
    ``exception_handler`` renders ``{"detail": ...}``, which is a non-empty body
    and would have made every API refusal a violation of D-02 the moment the API
    surface was added. That is the concrete reason the API is plain Django: see
    ``reviewer.reviews.api``.

    Three tests assert the properties separately rather than one test asserting
    all three, so a failure names *which* property broke.
    """
    response = HttpResponse(status=status)
    response[REFUSED_BY_HEADER] = refused_by
    return response
