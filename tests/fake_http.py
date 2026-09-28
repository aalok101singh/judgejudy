"""Deterministic replacement for the socket-based probe tests.

`run_probe` opens a real socket, and on Windows `http.server` aborts roughly one
connection in six with WSAECONNABORTED (10053) for reasons that belong to the
harness rather than to the code under test. A test that fails one run in six for
its own infrastructure is a test people learn to re-run, which is the same
failure mode as a flaky gate.

So `run_probe` is driven against a stub `urlopen` instead. The stub is a
*faithful* one -- it raises `HTTPError` for a 4xx exactly as `urlopen` does, and
it records the request -- so the code under test is the real code and the
assertions are still about the real logic. Only the socket is gone.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request


class FakeResponse(io.BytesIO):
    """The shape `urlopen` returns: a readable body plus ``status`` and ``headers``."""

    def __init__(self, status: int, body: str, headers: dict | None = None):
        super().__init__(body.encode())
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class Recorder:
    """A stub ``urlopen`` that answers from a table and remembers every request.

    ``answer`` is either ``(status, body, headers)`` or a callable taking the
    request. Requests are recorded on ``.requests`` so a test can assert on what
    was actually sent -- which is the only way to catch a probe that quietly
    dropped the credential and then "passed" against a portal that refuses
    everyone.
    """

    def __init__(self, answer, *, raise_http_error: bool = True) -> None:
        self.answer = answer
        self.raise_http_error = raise_http_error
        self.requests: list = []

    def __call__(self, request, timeout=None):  # urlopen's signature
        self.requests.append(request)
        status, body, headers = self.answer(request) if callable(self.answer) else self.answer
        if self.raise_http_error and 400 <= status < 600:
            raise urllib.error.HTTPError(
                request.full_url, status, "stub", dict(headers), io.BytesIO(body.encode())
            )
        return FakeResponse(status, body, headers)

    @property
    def last(self):
        return self.requests[-1]


def install(monkeypatch, answer, *, raise_http_error: bool = True) -> Recorder:
    """Point ``urllib.request.urlopen`` at a :class:`Recorder` for one test."""
    recorder = Recorder(answer, raise_http_error=raise_http_error)
    monkeypatch.setattr(urllib.request, "urlopen", recorder)
    return recorder
