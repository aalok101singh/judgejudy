"""Authenticating a request from a demo credential, and nothing else.

**A backend, not a view-level check.** Two reasons, and the second is the one
that matters:

* ``Actor.for_request(request, event)`` is the only call site a view needs, and
  it reads ``request.user``. If the demo credential only worked on the submit
  view, every later surface -- the judge console, the export, the dashboard --
  would grow its own copy of the header parsing, and one of them would grow it
  wrong.
* Django's own session and admin machinery keeps working. A middleware that
  assigns ``request.user`` is indistinguishable, to everything downstream, from
  having logged in.

**The middleware only ever *adds* a user, and only when there is not one
already.** A session cookie always wins. That ordering is deliberate: if a
browser session and a demo header disagree, the session is the more specific
claim about who is asking, and letting a header override it would be an
authority-widening path that nobody would look for.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from reviewer.accounts import demo_tokens


class DemoCredentialBackend(BaseBackend):
    """Authenticate a ``demo_email`` kwarg to a real, active ``User`` row.

    **The backend does not verify the signature.** Verification happened in the
    middleware, which is the only thing that reads the header. A backend that
    re-verified would have to take the raw token as well, and two code paths
    that both decide "is this credential good" is one more of them to get wrong.

    It also cannot create a user. A credential for an address with no row is an
    anonymous request, not a registration: this portal has no registration path
    and inventing one on the strength of a header would be the kind of thing that
    survives into production.
    """

    def authenticate(self, request, demo_email=None, **kwargs):
        if not demo_email:
            return None
        model = get_user_model()
        return model.objects.filter(email=demo_email, is_active=True).first()

    def get_user(self, user_id):
        model = get_user_model()
        try:
            return model.objects.get(pk=user_id, is_active=True)
        except (model.DoesNotExist, ValueError, TypeError):
            return None


class DemoCredentialMiddleware:
    """Resolve an ``Authorization: JJ1...`` header into ``request.user``.

    Placed *after* ``AuthenticationMiddleware``, because it replaces the lazy
    object that middleware installs rather than competing with it for the
    attribute.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._authenticate(request)
        return self.get_response(request)

    @staticmethod
    def _authenticate(request) -> None:
        existing = getattr(request, "user", None)
        if existing is not None and getattr(existing, "is_authenticated", False):
            return

        # `request.headers` gives the header VALUE, which is the bare token:
        # `run.py` already split the `Name: value` pair out of `.dogfood.toml`
        # and attached the value itself. The first version of this line called
        # a helper that split on a colon again, and the token contains no colon
        # before the signature -- so every demo identity arrived anonymous and
        # the acceptance checker's participant header was silently ignored.
        email = demo_tokens.email_from_token(request.headers.get("Authorization"))
        if email is None:
            return

        from django.contrib.auth import authenticate

        user = authenticate(request, demo_email=email)
        if user is not None:
            request.user = user
