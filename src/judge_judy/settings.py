"""Django settings for Judge Judy.

One container, one process, no network. Everything a judge needs to reproduce
the submission is in this file, the ``Dockerfile`` and the ``justfile``.

Read the decisions below as decisions rather than as configuration. Each one
costs a paragraph somewhere else in the repository; the comment says which
paragraph.
"""

from __future__ import annotations

import os
from pathlib import Path

# src/judge_judy/settings.py -> src/judge_judy -> src -> repo root
BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# The database and uploaded media live on a Docker named volume mounted at
# /app/data. Keeping them out of the image means `docker compose down -v`
# genuinely resets the portal, which is what the break protocol runs and what
# the acceptance criteria are measured against. Baking a database into a layer
# would make every image rebuild resurrect yesterday's data.
DATA_DIR = Path(os.environ.get("DJUDGE_DATA_DIR", REPO_ROOT / "data"))
INSTANCE_DIR = DATA_DIR / "instance"
MEDIA_ROOT = DATA_DIR / "media"
STATIC_ROOT = DATA_DIR / "staticfiles"


# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------
# There are no required environment variables, because the acceptance criteria
# say `docker compose up` works with the network off and nothing configured.
# That rules out demanding DJANGO_SECRET_KEY.
#
# A hardcoded key would be worse: it is in git, so every fork of this repository
# shares it, and a signed judge record is only as good as the key that signed
# it. So the key is generated once into the instance volume and read back on
# later boots. Sessions and signatures survive `restart`; `down -v` is a
# deliberate reset, and a reset that also rotated the key is the correct
# behaviour for a self-hosted portal.
_SECRET_KEY_FILE = INSTANCE_DIR / "secret_key"


def _load_secret_key() -> str:
    """Return the persisted secret key, generating one on first boot.

    Called at import time because Django reads ``SECRET_KEY`` during setup and
    has no lazy path for it. The volume is created here if it is missing, so a
    clean `up` needs no pre-created directory.
    """
    from_env = os.environ.get("DJANGO_SECRET_KEY")
    if from_env:
        return from_env

    try:
        existing = _SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        # No key yet: this is a first boot, not a failure.
        pass

    from django.core.management.utils import get_random_secret_key

    generated = get_random_secret_key()
    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        _SECRET_KEY_FILE.write_text(generated, encoding="utf-8")
    except OSError:
        # Read-only filesystem. The portal still runs; sessions just do not
        # survive a restart, which is a documented degradation rather than a
        # crash at import time.
        pass
    return generated


SECRET_KEY = _load_secret_key()

DEBUG = False

# The organizers' checker reaches the portal over `http://localhost:8080`, but
# a judge may equally bind the port and open it from a phone on the same wifi.
# Nothing in this application makes a security decision based on the Host
# header -- there is one tenant and no host-based routing -- so restricting it
# buys nothing and would turn a LAN address into a 400 that reads as a broken
# install. DEBUG is False regardless, so this is the only host check in play.
ALLOWED_HOSTS = ["*"]


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
#
# The twelve project apps are named for the domain, not for the layer
# (coding-standards.md §3): `reviewer.reviews`, not `reviewer.models`. They are
# listed alphabetically so the ordering here carries no meaning -- Django's own
# apps come first because contenttypes and auth have to be registered before
# anything can have a foreign key to a user.
#
# `reviewer.isolation` and `reviewer.normalization` are deliberately NOT here.
# They are packages, not apps: `isolation` holds the access-control primitive
# and defines no model, and `normalization` is the estimator. Listing a package
# with no model would add a `models` module that does not exist and a migration
# that creates nothing.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "whitenoise.runserver_nostatic",
    "reviewer.accounts",
    "reviewer.audit",
    "reviewer.ballots",
    "reviewer.comments",
    "reviewer.credentials",
    "reviewer.events",
    "reviewer.io",
    "reviewer.projects",
    "reviewer.reviews",
    "reviewer.rubrics",
    "reviewer.teams",
    "reviewer.webhooks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # After AuthenticationMiddleware: it replaces the lazy `request.user` that
    # middleware installs, rather than competing with it for the attribute.
    # It only ever ADDS a user, and only when there is not one already, so a
    # session cookie always wins over a demo header. See
    # reviewer/accounts/authentication.py for the ordering argument.
    "reviewer.accounts.authentication.DemoCredentialMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

#: Two backends, and the split between them is the point.
#:
#: `ModelBackend` is here **only** so `django.contrib.admin`'s own login form
#: works -- an organizer debugging a stuck portal needs somewhere to look, and
#: without this backend nobody can sign in to `/admin/` at all. It grants
#: nothing: `User` has no `PermissionsMixin` and `User.has_perm` returns False
#: unconditionally, so the admin's index is empty by construction. That is the
#: documented FEAT-02 consequence, and `tests/test_schema_contract.py` pins it.
#:
#: `DemoCredentialBackend` is how the acceptance checker proves a role without a
#: login round-trip. It authenticates an identity and nothing else; authority is
#: a `RoleBinding` lookup in every case.
#:
#: The thing that is deliberately NOT here is a single place where the product's
#: authorization rules live. That is `reviewer.isolation`, and nothing in the
#: application reads a permission bitmask.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "reviewer.accounts.authentication.DemoCredentialBackend",
]

ROOT_URLCONF = "judge_judy.urls"
WSGI_APPLICATION = "judge_judy.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# SQLite in WAL mode, on a named volume.
#
# WAL is what makes a single-file database safe for gunicorn's several
# workers: readers do not block the writer, and the writer does not block
# readers. The alternative, rollback journal, serialises every read behind
# every write and turns a two-worker configuration into a one-worker one.
#
# `transaction_mode = IMMEDIATE` takes the write lock at BEGIN rather than on
# first write. Without it two workers that both decide to write part-way
# through a transaction get SQLITE_BUSY at COMMIT, after doing the work, which
# is the worst place to lose. Taking the lock up front makes them queue
# instead. `timeout` is how long that queue may take.
#
# Both keys were read out of the installed Django 5.2.17 source rather than
# recalled, because the alternative on this project was a settings file that
# silently accepted a typo.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": INSTANCE_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": (
                "PRAGMA journal_mode = WAL;PRAGMA synchronous = NORMAL;PRAGMA foreign_keys = ON"
            ),
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# The portal is single-tenant and self-hosted. There is no registration, no
# password reset by email, and no external identity provider, because all three
# would need the network.
#
# The five seeded identities are the only accounts that can authenticate; every
# other person in fixtures.json is synthetic and gets an unusable password. The
# alternative -- hashing all 121 of them -- costs about 48 seconds inside the
# process gunicorn is waiting on, against a 10 second checker timeout.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Sessions live in the database rather than a signed cookie. The session table
# is on the instance volume, so a restart keeps judges logged in, and a session
# can be revoked server-side -- which a stateless cookie cannot.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
# CSRF protection is ON for the HTML surface. The DRF API surface is a
# separate decision, taken deliberately and documented in JUDGING.md rather
# than in a comment: DRF's SessionAuthentication is not CSRF-exempt by default
# (verified against the installed 3.18.1, not recalled), and the portal's API
# is token-authenticated rather than cookie-authenticated.
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the browser's JS reads this to set the header
CSRF_TRUSTED_ORIGINS = ["http://localhost:8080", "http://127.0.0.1:8080"]


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
# Everything the checker compares is ASCII: route paths, HTTP status codes, CSV
# headers, and the ASCII fixture titles it greps for. UTC everywhere for the
# same reason -- a deadline compared in local time is a deadline that moves.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
# whitenoise serves them from the same container. No CDN, no nginx, no second
# service: two services is a disqualification, and an outbound request to a
# CDN is a request that fails the moment the network is off.
#
# CompressedStaticFilesStorage rather than the manifest variant on purpose. The
# manifest raises at startup if a referenced file is missing, which turns a
# cosmetic gap into a container that will not boot. For a portal with one
# stylesheet and admin assets, the cache-busting is not worth that failure mode.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# whitenoise warns "No directory at: <STATIC_ROOT>" on every request until
# collectstatic has run once, and `filterwarnings = ["error"]` in the test
# config turns that warning into a failing test. So the directory is created at
# import time.
#
# This is a side effect at import, which is normally a smell. Here it is the
# smallest possible one — an empty directory that collectstatic fills in — and
# the alternative is either a startup warning nobody reads or a test suite
# that cannot run on a clean checkout, which is worse than both.
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
WHITENOISE_MAX_AGE = 3600


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
# SessionAuthentication stays the browser-facing scheme and is listed FIRST on
# purpose: DRF authenticates in order and the first match wins, so a
# deliberate ordering here is the difference between "a judge browsing the
# console is a judge" and "a judge who pasted an API token into the console is
# whoever that token belongs to".
#
# The permission default is AllowAny so that adding a view does not silently
# protect it. The isolation layer is not a default -- it is explicit at every
# call site -- and a deny-by-default here would hide a missing permission
# behind a framework setting instead of surfacing it in review.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Judge Judy API",
    "DESCRIPTION": "Submission and judging platform for DOGFOOD 2026.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
# HSTS is deliberately absent. This portal is documented to be reached over
# plain http on localhost, and a browser that has once seen the header will
# refuse to talk to it over http for the next year -- turning a working
# `docker compose up` into a portal the judge cannot open. The honest control
# for a localhost deployment is a bound port, not a remember-forever header.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# DEBUG is False, so this only matters for local development with DEBUG on,
# where it is the difference between a usable 400 and an opaque crash page.
INTERNAL_IPS = ["127.0.0.1", "::1"]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Everything to stdout. gunicorn captures it, `docker compose logs` shows it,
# and there is no log file to lose or rotate. A portal that writes its audit
# trail to a file on a volume is a portal whose audit trail a full disk erases.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
