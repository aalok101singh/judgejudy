"""Two views: the widget's HTML and the widget's JSON.

**Gating is ``results_state`` and nothing else**, which is what makes it a
*widget* rather than another authenticated surface. An embedder is a third party:
they cannot hold a judge credential, they are not a participant, and they are
certainly not an organizer. So the widget is public exactly when the ranking is
published, and refuses with the same 403-with-an-empty-body the rest of the
system uses.

**It is an event-wide board, deliberately.** A published page already serves the
whole event to a visitor (F-89: narrow the board only when narrowing protects
somebody, and a visitor has nothing of their own to protect). The widget has no
actor at all -- there is nobody to scope to -- so it uses the event-wide actor
explicitly rather than reaching for an unscoped read. That is the difference
between a decision and an oversight, and it is why the actor is constructed here
with a comment instead of being left implicit.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from reviewer.events.models import RESULTS_PUBLISHED
from reviewer.isolation import Actor, refusal
from reviewer.widget import build

#: Re-exported so a caller does not have to know which module owns the name.
REFUSED_BY_NO_EVENT = "no-event"
REFUSED_BY_NOT_PUBLISHED = "not-published"


@require_http_methods(["GET"])
def widget(request, event) -> HttpResponse:
    """``/widget/results/`` -- the embeddable document."""
    return _serve(request, event, html=True)


@require_http_methods(["GET"])
def widget_json(request, event) -> HttpResponse:
    """``/widget/results.json`` -- the same ranking as data."""
    return _serve(request, event, html=False)


def _serve(request, event, *, html: bool) -> HttpResponse:
    if event is None:
        return refusal.deny(REFUSED_BY_NO_EVENT)
    if event.results_state != RESULTS_PUBLISHED:
        return refusal.deny(REFUSED_BY_NOT_PUBLISHED)

    # **Named, constructed, and not an oversight.** There is no request actor here
    # -- an embedder has none -- and the ranking is public now, so the board is the
    # event's. Saying that in a comment is what stops the next reader from
    # "simplifying" this into an unscoped read.
    actor = Actor.anonymous(event)

    payload = build.widget_payload(event, actor)
    if html:
        return HttpResponse(build.build_document(payload), content_type="text/html; charset=utf-8")
    return HttpResponse(build.build_json(payload), content_type="application/json; charset=utf-8")
