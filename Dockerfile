# syntax=docker/dockerfile:1
#
# Judge Judy — one image, one process, no network at runtime.
#
# FROM is pinned by digest, not by tag. `python:3.13-slim` is a moving target,
# and the whole submission is a claim that a judge can reproduce; a tag would
# quietly let the base change underneath the README's numbers. The digest is
# the one already in this machine's image cache, so a rebuild on the reviewer's
# laptop does not need a pull either.
#
# The digest is asserted by `python tools/verify_spec.py --env`, which is how a
# drifted pin becomes a failing check rather than a surprise at a break.
FROM python@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b

# ---------------------------------------------------------------------------
# Build-time environment
# ---------------------------------------------------------------------------
# PYTHONDONTWRITEBYTECODE keeps __pycache__ out of the layers, which matters
# because the app directory is bind-mounted or copied at runtime and a stale
# .pyc in a layer is a source of "why is this not what I just wrote".
#
# PYTHONUNBUFFERED means the container's stdout is unbuffered, so `docker
# compose logs` shows the boot sequence in real time and the seed banner is
# visible while you are still watching the build. A buffered portal that logs
# nothing for two minutes looks identical to a portal that hung.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies first, in their own layer
# ---------------------------------------------------------------------------
# requirements.txt only. requirements-dev.txt is deliberately NOT installed:
# it carries pytest, hypothesis and ruff, none of which the running portal
# uses, and dev dependencies in a production image are a dependency-confusion
# surface for zero benefit. The test suite runs on the host against the same
# pinned versions.
#
# The compiler is not installed. Every runtime package ships a manylinux wheel
# for cp313, so a toolchain here would be ~150 MB of build-essential that
# never runs — and if a wheel were ever missing, that is a finding to fix in
# requirements.txt rather than to paper over in the image.
COPY requirements.txt /app/requirements.txt
RUN python -m pip install -r /app/requirements.txt \
    && python -c "import django, rest_framework, whitenoise, cryptography; \
print('runtime imports ok:', django.get_version())"

# ---------------------------------------------------------------------------
# Non-root user
# ---------------------------------------------------------------------------
# Created before the app is copied so the COPY --chown does not need sudo and
# so the ownership is decided once.
#
# The uid is fixed rather than allocated, because a named volume is created
# with the uid that owned the mount point at creation time. A random uid would
# make `docker compose down -v && up` fail to write to a fresh volume roughly
# half the time, which is precisely the "healthcheck must pass from a clean
# volume, not a warm one" acceptance line.
RUN groupadd --gid 10001 judge \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin judge

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
# src/ contains the Django project. It is copied --chown to the non-root user
# so nothing in the image is owned by root and writable by the app.
COPY --chown=judge:judge src/ /app/src/
COPY --chown=judge:judge fixtures.json /app/fixtures.json
COPY --chown=judge:judge run.py /app/run.py
COPY --chown=judge:judge docker/entrypoint.sh /app/entrypoint.sh
COPY --chown=judge:judge docker/healthcheck.py /app/healthcheck.py

# The instance and media directories have to exist and be owned by the app
# user before the volume is mounted over them. When Docker creates a named
# volume for a path that exists in the image, it seeds the volume from the
# image's contents *including ownership* — so creating them here is what makes
# a clean volume writable. This is the single most common way a
# non-root Django container fails on first boot and it is why F-12's siblings
# tend to appear at hour 40 rather than hour 2.
RUN mkdir -p /app/data/instance /app/data/media /app/data/staticfiles \
    && chown -R judge:judge /app/data \
    && chmod +x /app/entrypoint.sh

# ---------------------------------------------------------------------------
# Static files, collected at build time
# ---------------------------------------------------------------------------
# Run as the app user and before the server starts, because whitenoise serves
# from disk and a missing collectstatic is a page with no stylesheet. Doing it
# here rather than in the entrypoint means `docker compose up` does less work
# and the 60-second budget is spent on the port, not on the filesystem.
USER judge
RUN python src/manage.py collectstatic --noinput \
    && test -f /app/data/staticfiles/css/portal.css

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
ENV DJUDGE_DATA_DIR=/app/data \
    DJANGO_SETTINGS_MODULE=judge_judy.settings \
    PYTHONPATH=/app/src \
    PORT=8080

EXPOSE 8080

# The healthcheck lives in compose.yaml rather than here, so that `docker run`
# and `docker compose up` do not disagree about what "healthy" means. This
# HEALTHCHECK is the fallback for a bare `docker run`, and it calls the same
# script.
#
# `--start-period=45s` matches compose exactly, and both are asserted by
# tests/test_healthcheck_contract.py. The first draft of this line said 10s,
# which is BELOW the measured cold start — the container would have reported
# itself unhealthy during normal operation on a slow machine, and passed on a
# fast one. That is the worst kind of wrong: a defect that looks correct
# everywhere you happen to look.
#
# 45s is generous against a 6.2s measured start because the first boot on a
# reviewer's machine unpacks every image layer, which is not a number we
# control.
HEALTHCHECK --interval=5s --timeout=4s --start-period=45s --retries=12 \
    CMD ["python", "/app/healthcheck.py"]

USER judge
WORKDIR /app

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["serve"]
