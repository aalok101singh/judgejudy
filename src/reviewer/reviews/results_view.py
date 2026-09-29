"""``/results/`` -- the public results page (REQ-T3-03).

**This is the last named T3 gap, and it is the capability the brief is most
careful about: "results hidden from everyone but organizers during the voting
window."** The predicate (`results.results_visible_to`) and the aggregate
(`results.leaderboard`) both existed and were both tested -- for the **API**. A
reviewer opening a browser never sees `/api/v1/results`, so for nine hours the
only enforced surface was one a human would have to know to ask for.

**The page calls the same two functions the API does, and a test asserts the two
surfaces agree row for row.** That assertion is the important one. Tallying a
ranking twice is how two shipped artefacts end up answering the same question
differently -- which is exactly F-84's second-order bug, where `voters` meant one
thing in the tally and another in the influence report. **One predicate, one
aggregate, two renderings.**

**Why the refusal is a 403 with an empty body and not an explanatory page.** A
judge who is refused a ranking must be *refused*, not shown a page that says the
results are not available yet: the first is an answer, the second is a page a
reader can screenshot and describe. D-02 applies, and the guard's name goes in
the header so a probe can tell this refusal from a CSRF rejection or a 404.

**What the page always says.** `results.NORMALIZATION` is rendered on every 200,
because a published ranking that does not say whether it is corrected is a
ranking a reader has to guess about. The aggregate is an unnormalized weighted
mean; judge-severity correction is FEAT-08, and this page is not allowed to imply
otherwise.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from reviewer.isolation import Actor, refusal
from reviewer.reviews import results as results_module

REFUSED_BY_RESULTS = "results_page.hidden"
REFUSED_BY_NO_EVENT = "results_page.no_event"


@require_http_methods(["GET"])
def results_page(request, event) -> HttpResponse:
    """``/results/`` -- the published ranking, or a refusal."""
    if event is None:
        return refusal.deny(REFUSED_BY_NO_EVENT)
    actor = Actor.for_request(request, event)
    if not results_module.results_visible_to(actor):
        return refusal.deny(REFUSED_BY_RESULTS)

    board = results_module.leaderboard(actor)
    return render(
        request,
        "reviews/results.html",
        {
            "event": event,
            "actor": actor,
            "rows": board,
            "normalization": results_module.NORMALIZATION,
            "results_state": event.results_state,
            # Whether this board covers the whole event or only the actor's own
            # reviews. **F-90: this must report what `leaderboard` ACTUALLY did,
            # not `not actor.can_read_all_reviews`.** Deriving it from the role
            # got it wrong in exactly the case F-89 introduced: a published
            # *visitor* is shown the WHOLE event (nothing of theirs to protect)
            # and was still told "your own reviews only" -- **a page asserting a
            # scope it did not apply**, which is the ninth-defect's shape wearing
            # a sentence instead of a number. The predicate is the same
            # `EXISTS` the aggregate branches on, so the label and the board
            # cannot disagree: if `leaderboard` narrowed, this says so; if it did
            # not, this does not.
            "scoped": not actor.can_read_all_reviews and results_module.has_own_reviews(actor),
        },
    )
