"""Public comments on a project (REQ-T3-02).

**The security property is the whole feature, and it is a negative one: a comment
body must never reach the page as markup.** ``bible/07`` V-8 calls this "escaped
output, no raw HTML, ``pending`` moderation queue, rate limits, length caps",
and P-4 says the same thing from the other side: *"Comments are plain text by
design."*

Four controls, and each is a separate promise so a failure names itself:

1. **Escaping.** Django autoescapes every template expression and this module
   adds no ``|safe`` and no ``mark_safe`` anywhere. The tests assert the *absence*
   of a live ``<script>`` in rendered bytes rather than the presence of an
   escaped one -- "it is escaped" and "it is not present" are different claims
   and only the second is what a browser acts on.
2. **``pending`` by default.** ``Comment.status`` defaults to
   ``COMMENT_PENDING`` in the schema, so a comment is **not visible** until a
   human says so. A comment that was filtered and a comment that was never posted
   are different states, and the model keeps the row either way.
3. **Length cap**, enforced here because the column is a ``TextField`` and a
   schema CHECK on length is not portable in a way the ORM would enforce for us.
   A 200k-character comment is a denial of service on the gallery.
4. **Rate limiting — SHIPPED, and how it is weak.** ``V-8`` asks for it. It was cut
   for most of this build and disclosed here, in the README and in the cut ledger
   rather than quietly missing; it now lives in
   :mod:`reviewer.comments.ratelimit`. It is **count-derived**, keyed on the
   account when there is one and on a **hash of the session key** when there is
   not.

   **The anonymous weakness is stated, not hidden:** clearing cookies resets the
   limit. IP was the alternative, and this project refuses it everywhere else
   because it is a poor identity that gets innocent people in trouble. A limit a
   private window resets is still a limit against the naive case, and the strong
   case is reachable by giving people accounts -- which is what
   ``manage.py invite`` is for. The refusal is a bare 403 like every other
   denial, because a rate limit refuses a *well-formed* claim and must not look
   like the 400 a malformed one gets (F-40).

**Why comments are their own route and not a field on the gallery.** ``run.py``
reads ``projects[:3]`` **positionally** from the gallery and checks that one of
those titles appears in the body. Anything added to the gallery markup is a
change to the page the T1 checks read, for no benefit; a separate route is
additive and cannot move the gallery's ordering.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from reviewer.comments import ratelimit
from reviewer.comments.models import COMMENT_HIDDEN, COMMENT_VISIBLE, Comment
from reviewer.isolation import Actor
from reviewer.isolation.refusal import deny
from reviewer.projects.models import Project

REFUSED_BY_NO_EVENT = "comments.no_event"
REFUSED_BY_NO_PROJECT = "comments.no_project"
REFUSED_BY_EMPTY_BODY = "comments.empty_body"
REFUSED_BY_TOO_LONG = "comments.body_too_long"
REFUSED_BY_RATE_LIMITED = "comments.rate_limited"
REFUSED_BY_NOT_ORGANIZER = "comments.moderate_role"
REFUSED_BY_UNKNOWN_ACTION = "comments.unknown_action"

#: The length cap. 2000 characters is roughly 300 words -- long enough for a
#: substantive comment, short enough that a gallery page stays readable. **It is
#: a legibility constant, not a security one**, and the honest reason it is not
#: tuned further is that there is no measurement yet of what real comments look
#: like, because this surface has never been used by anyone but us.
MAX_BODY_CHARS = 2000


def _visible(event) -> list[Comment]:
    """Comments anyone may read: ``visible`` only, newest project order.

    **``pending`` and ``hidden`` are excluded here and nowhere else**, so a
    template cannot accidentally render a comment nobody has approved. The
    organizer sees the rest through :func:`_moderation_queue`, which is a
    separate query on purpose -- a moderation view that shared this filter would
    be a moderation view that could not see the queue.
    """
    return (
        Comment.objects.filter(event=event, status=COMMENT_VISIBLE)
        .select_related("author", "project")
        .order_by("project_id", "created_at")
    )


def _moderation_queue(event) -> list[Comment]:
    """Everything not yet visible, for an organizer."""
    return (
        Comment.objects.filter(event=event)
        .exclude(status=COMMENT_VISIBLE)
        .select_related("author", "project")
        .order_by("project_id", "created_at")
    )


@require_http_methods(["GET", "POST"])
def thread(request, event, project_id: str) -> HttpResponse:
    """``/projects/<id>/comments/`` -- the thread, and the form that posts to it.

    **POST is CSRF-enforced through ``projects.views``' existing wrapper**, for
    the same reason the ballot's is: a second implementation of that check is a
    second thing to get wrong in the layer that stops somebody posting as you.
    """
    from reviewer.projects.views import _csrf_enforced, _requires_csrf

    if _requires_csrf(request):
        return _csrf_enforced(lambda r: _thread(r, event, project_id))(request)
    return _thread(request, event, project_id)


@require_http_methods(["GET", "POST"])
def _thread(request, event, project_id: str) -> HttpResponse:
    if event is None:
        return deny(REFUSED_BY_NO_EVENT)
    project = Project.objects.filter(event=event, pk=project_id).first()
    if project is None:
        # 404, not 403: the project does not exist in this event, which is a
        # different answer from "you may not". Nothing is being hidden here.
        return HttpResponse(status=404)

    actor = Actor.for_request(request, event)
    context = {
        "event": event,
        "project": project,
        "actor": actor,
        "comments": _visible(event).filter(project=project),
        "error": "",
        "posted": False,
        "max_body": MAX_BODY_CHARS,
        # The queue is attached for organizers and ONLY for organizers, on GET as
        # well as after a moderation action. An empty list renders to nothing, so
        # a non-organizer's page has no trace that a queue exists.
        "queue": _moderation_queue(event) if actor.can_read_all_reviews else [],
    }

    if request.method == "POST":
        action = request.POST.get("action", "post")
        if action == "moderate":
            return _moderate(request, event, actor, context)
        body = (request.POST.get("body") or "").strip()
        if not body:
            context["error"] = "A comment needs a body."
            return render(request, "comments/thread.html", context, status=400)
        if len(body) > MAX_BODY_CHARS:
            context["error"] = (
                f"A comment is limited to {MAX_BODY_CHARS} characters; yours is {len(body)}."
            )
            return render(request, "comments/thread.html", context, status=400)

        # **V-8's fourth control, shipped.** The check is AFTER the length cap
        # because a cap breach is the poster's own malformed request (a 400 they
        # can fix), while a rate limit is a refusal of a well-formed claim (a 403
        # they cannot fix by editing). F-40: the two must not look alike.
        #
        # The refusal is `deny(...)`, so it is a bare 403 with an empty body and
        # the guard in `X-Refused-By` -- the same shape as every other denial in
        # this portal. A rendered "you are posting too fast" page would be a body
        # a caller has to parse, and it would invite the client to retry, which is
        # exactly what a rate limiter is meant to discourage.
        if ratelimit.too_many_recently(request, actor):
            return deny(REFUSED_BY_RATE_LIMITED)
        # `status` is NOT set here, on purpose: the schema default is
        # `pending`, and a comment is only visible once a human says so. Naming
        # the constant at the call site would be a second place to get it wrong
        # -- and the fact that it is the DEFAULT is the property, so the test
        # asserts the column's default rather than this call site.
        Comment.objects.create(
            event=event,
            project=project,
            # **Empty string, never ``None``.** The column is `NOT NULL` with
            # `default=""`, and passing `None` explicitly *bypasses the default* and
            # raises IntegrityError -- so every signed-in comment 500'd. This is
            # the exact hazard the model's own comment records: `null=True` and
            # blank would be two ways to say "no anonymous key", so blank was
            # chosen -- and then the call site reached for `None` anyway. The
            # `or ""` is not defensive padding; it is the second half of the same
            # decision.
            author_session_hash=(
                ""
                if actor.is_authenticated
                else (ratelimit.session_hash(request, create=True) or "")
            ),
            body=body,
            author=actor.user if actor.is_authenticated else None,
            author_label=(
                actor.user.email if actor.is_authenticated else (request.POST.get("label") or "")
            )[:120],
        )
        context["posted"] = True
        return render(request, "comments/thread.html", context)

    return render(request, "comments/thread.html", context)


def _moderate(request, event, actor, context) -> HttpResponse:
    """Approve or hide one comment. Organizer only.

    **A refusal here is a refusal, not an empty queue.** A participant who posts
    a moderation action gets a 403 naming the guard, because a page that quietly
    ignores the request is indistinguishable from a page that worked -- and this
    is exactly the confusion the isolation matrix exists to prevent.
    """
    if not actor.can_read_all_reviews:
        return deny(REFUSED_BY_NOT_ORGANIZER)
    comment_id = request.POST.get("comment")
    status = request.POST.get("status")
    if status not in (COMMENT_VISIBLE, COMMENT_HIDDEN):
        return deny(REFUSED_BY_UNKNOWN_ACTION)
    updated = Comment.objects.filter(event=event, pk=comment_id).update(
        status=status, moderated_by=actor.user
    )
    if not updated:
        return HttpResponse(status=404)
    # Both halves of the page are rebuilt, not just the queue: approving a comment
    # must make it appear in the thread, and hiding one must make it disappear.
    # A moderation action that updated the database and re-rendered the stale
    # context would be the F-85 shape -- right in the database, wrong on the page.
    context["queue"] = _moderation_queue(event)
    context["comments"] = _visible(event).filter(project=context["project"])
    context["moderated"] = True
    return render(request, "comments/thread.html", context)
