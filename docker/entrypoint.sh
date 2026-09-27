#!/bin/sh
# Container entrypoint.
#
# The ordering below is the contract with the organizers' checker, and it is
# not negotiable:
#
#   migrate  ->  collectstatic  ->  seed  ->  THEN gunicorn binds
#
# The checker has a 10 second timeout per request (run.py: TIMEOUT = 10). If
# gunicorn accepts a connection before seeding finishes, the first request
# races the loader and returns an empty gallery, and T1-2 fails for a reason
# that has nothing to do with the portal. So nothing binds the port until the
# database is ready.
#
# Every step is idempotent. `docker compose up` is run many times against the
# same volume, and a second run must converge rather than fail or duplicate.

set -eu

DATA_DIR="${DJUDGE_DATA_DIR:-/app/data}"
SETTINGS="${DJANGO_SETTINGS_MODULE:-judge_judy.settings}"
PORT="${PORT:-8080}"
MANAGE="python /app/src/manage.py"

log() { printf '[judge-judy] %s\n' "$*"; }

wait_for_exit() {
    # Forward SIGTERM/SIGINT to gunicorn so `docker compose down` stops the
    # workers instead of waiting for the 10 second kill timeout on every one.
    trap 'log "shutting down"; kill -TERM "$PID" 2>/dev/null || true' TERM INT
    wait "$PID"
}

case "${1:-serve}" in
    serve)
        # The volume is mounted over /app/data, so it exists — but a bind mount
        # from a host that has not created the directory can produce a
        # read-only or root-owned path. Creating it here means the failure
        # mode is a clear permission error in the log rather than a healthcheck
        # that never turns green.
        mkdir -p "$DATA_DIR/instance" "$DATA_DIR/media" "$DATA_DIR/staticfiles"

        log "applying migrations"
        $MANAGE migrate --noinput

        # collectstatic runs here as well as at build time. At build time it
        # bakes the admin's assets; here it picks up anything a bind-mounted
        # source tree changed, which is the normal local-development loop.
        log "collecting static files"
        $MANAGE collectstatic --noinput --clear >/dev/null

        # Seeding is idempotent and prints the session cookies the checker
        # needs. Its hash budget is deliberately tiny: only the five seeded
        # identities get a real password hash, because hashing all 121
        # fixture people costs about 48 seconds and the checker's timeout is
        # 10. (F-12.)
        #
        # `load_fixtures` does not exist yet — it lands in FEAT-03. The
        # existence check is here rather than a bare `||` so that the
        # pre-FEAT-03 boot is a normal line in the log instead of a Django
        # traceback, which would train us to ignore a red log line that later
        # means something.
        if $MANAGE help 2>/dev/null | grep -q 'load_fixtures'; then
            log "seeding fixtures"
            $MANAGE load_fixtures
        else
            log "no load_fixtures command yet (FEAT-03); starting with an empty database"
        fi

        log "starting gunicorn on :$PORT"
        # 2 workers + 1 thread each. SQLite in WAL mode allows concurrent
        # readers with a single writer, so more workers buy nothing and cost
        # memory on a 3.7 GiB engine. This is the documented engine allocation.
        gunicorn judge_judy.wsgi:application \
            --bind "0.0.0.0:${PORT}" \
            --workers 2 \
            --threads 2 \
            --timeout 30 \
            --graceful-timeout 10 \
            --access-logfile - \
            --error-logfile - \
            --log-level info &
        PID=$!
        wait_for_exit
        ;;

    # One-shot helpers. `docker compose run --rm web migrate` and friends.
    shell)
        exec /bin/sh
        ;;
    manage)
        shift
        exec $MANAGE "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
