# Judge Judy — the gate.
#
# `just check` is the single command that proves a checkpoint. It is the only
# command in this repository that a reviewer needs to know, so it is also the
# only one that has to be honest about what it checked.
#
# Two environment traps are handled here rather than left to a README, because
# both of them have already cost this project real time:
#
#   F-34  Docker Desktop is installed per-user, so `docker` was on no PATH at
#         all and `docker --version` reported NOT FOUND while the daemon was up
#         and healthy. DOIs are resolved by absolute path as a fallback, so a
#         stale shell cannot break the gate. A stale PATH is a stale PATH, not
#         a missing install — do not "fix" this by reinstalling Docker.
#
#   F-38  The ambient `python` on PATH is 3.14.6 with no Django installed. The
#         venv is 3.13.13. Every local recipe therefore names the interpreter
#         explicitly and asserts its version, rather than trusting `python` to
#         mean the right thing.
#
# run.py ALWAYS exits 0, even when every check FAILs (F-32). So the `check`
# recipe parses the report body. Gating on the exit code would report a green
# checkpoint for a completely broken portal.

# --- interpreter resolution ---------------------------------------------------
# `python` on PATH is 3.14.6 without Django (F-38). This is the venv, and it
# is named explicitly everywhere rather than trusting `python` to mean the
# right thing.
py := justfile_directory() / ".venv" / "Scripts" / "python.exe"

# The repository path contains a space ("Judge Judy"), so every invocation is
# quoted. Without the quotes cmd.exe parses `C:\Users\Aalok\Desktop\Judge` as
# the command and `Judy\...` as its first argument — a failure that looks like
# a missing interpreter rather than a quoting bug. Both shells honour the
# double quotes, so there is no need for two spellings.
pyq := '"' + py + '"'

# On Windows, just defaults to `sh`, which is not on the PATH of a stock
# PowerShell host. Declaring cmd.exe here is a HOST adaptation, not a project
# decision, so it is conditional: the `[windows]` attribute means the fork
# that a hackathon clones on a Mac or a Linux CI runner still gets `sh`, and
# still gets the same recipes.
#
# The recipes below are written to the intersection of POSIX sh and cmd.exe —
# `&&`, `||` and plain `echo` — so one body serves both shells rather than
# having a Windows fork and a Unix fork to drift apart.
[windows]
set shell := ["cmd.exe", "/c"]

[unix]
set shell := ["sh", "-uc"]

# `pyguard` asserts the interpreter is the 3.13 line before anything is built
# on it. F-38's suggested fix was to "invoke the venv explicitly" — naming the
# path is half of it; asserting the version is the half that turns a silent
# substitution into a clear message.
#
# It lives in a script rather than a `-c` one-liner because cmd.exe's handling
# of nested quotes inside `cmd /c` is the sort of thing that works on one
# machine and fails on the reviewer's. That was a real error from the first
# draft of this justfile, not a hypothetical one.
pyguard := pyq + " tools/guard_interpreter.py --expect 3.13"

# --- docker resolution --------------------------------------------------------
# tools/docker.py resolves the binary by absolute path first, because Docker
# Desktop is installed PER-USER on this machine (F-34) and a terminal opened
# before the PATH fix keeps its old PATH. The gate must not depend on when the
# shell was opened, and the failure message must name the real cause rather
# than implying Docker was never installed.
#
# `subprocess.run` inside that script means docker's own exit code passes
# through untouched, so this indirection cannot swallow a failure.
#
# It uses `pyq`, not `py`. The repository path contains a space ("Judge Judy"),
# and an unquoted path under cmd.exe is parsed as the command plus an argument —
# a failure that reads like a missing interpreter rather than a quoting bug.
compose_base := pyq + " tools/docker.py compose -f docker-compose.yml"

# ------------------------------------------------------------------ recipes ---
#
# DOC COMMENT CONVENTION. `just --list` renders the LAST line of a recipe's doc
# comment, not the first. A comment block written summary-first therefore shows
# its final wrapped fragment, so `accept` advertised itself as "never actually
# run" and `check` as "has to reach for is worth more than one somebody might
# leave on" (F-56). Verified empirically, not recalled: a two-line comment
# renders its second line.
#
# So every recipe below puts its one-sentence summary on the LAST line of a
# comment block that is CONTIGUOUS with the recipe name. A blank line between
# the comment and the name discards the doc comment entirely, so a recipe with
# prose and no summary shows up in `just --list` with a BLANK description --
# which is the same defect wearing a different hat. A long comment is fine. A
# summary that is not the last line is a defect, and the way to catch one is to
# read `just --list` and see whether the list is a lie.

# The first question about a repository is always "what can I run?", so listing
# the recipes is the default target.
#
# List the recipes, and show the first help.
default:
    @just --list --unsorted

# The difference between "Docker is not installed" (wrong, twice on this
# project) and "docker is on no PATH" (right). Run this before anything is
# built on the toolchain.

# Confirm the toolchain, and name what is missing.
doctor:
    @{{pyq}} tools/doctor.py

# The spec layer: the plan against the organizers' files. Stdlib only, so it
# needs no venv, no Docker and no network. Run after ANY edit to blueprint/ or
# AGENTS.md, and unlike run.py it EXITS NON-ZERO on failure, so unlike run.py it
# can actually gate.
#
# The spec gate: the plan against the organizers' files.
spec:
    @python tools/verify_spec.py

# Only the failures, because a screen of passing lines is noise while editing
# and one failing line is the entire message.
#
# The spec gate's failures, and nothing else.
spec-quiet:
    @python tools/verify_spec.py -q

# --- the container lifecycle --------------------------------------------------

# Build the image. Separate from `up` so a long build is visible as a build.
build:
    {{compose_base}} build

# The command the acceptance criteria name, run in the background until the
# healthcheck passes, which is a different failure from a server that came up
# and is serving 500s.
#
# Start the container and wait for the healthcheck.
up:
    {{compose_base}} up -d --wait --wait-timeout 120
    @echo "portal healthy: http://localhost:8080/"

# `down` KEEPS the volume, which is what makes it cheap; `clean` is the one that
# deletes it, and the two are not interchangeable.
#
# Stop and remove, keeping the data.
down:
    {{compose_base}} down

# The reset both the break protocol and the acceptance criteria start from,
# because "it works from a warm volume" is not the claim being made.

# Stop, remove, AND delete the volume.
clean:
    {{compose_base}} down -v --remove-orphans

# Build and start from absolutely nothing, and MEASURE the seconds to a serving
# page. This is the FEAT-01 acceptance line.
#
# The measurement lives in tools/coldstart.py rather than in a shell one-liner
# for two reasons. First, the number ends up in the README, and the rule this
# project works by is that shipped numbers are generated, not transcribed.
# Second, just's `{{` interpolation and a PowerShell `-f` format string fight
# over the same braces — which is a real error from the first draft of this
# file, not a hypothetical one.
#
# **F-48: the variadic default was `*args="{}"` and the recipe was
# un-typeable.** `just` treats a `*args` default as a literal string and
# interpolates it, so `just coldstart` ran `tools/coldstart.py {}` and argparse
# rejected it with `unrecognized arguments: {}`. Same defect in `accept`, so
# `just accept` -- the command every document tells a reader to run -- had
# never worked. A named verification command that cannot be typed is F-47 again
# one layer out, and it is the reason the recipes below take `*args` with no
# default at all.

# Cold start from a clean volume, timed against the budget.
coldstart *args:
    @{{pyq}} tools/coldstart.py {{args}}

# Cold start without rebuilding, to separate "the build is slow" from "the boot
# is slow". Run the full one first; this is the follow-up when it fails, and the
# two together are what turn one timing number into a diagnosis.
#
# Cold start WITHOUT rebuilding, to separate build time from boot time.
coldboot *args:
    @{{pyq}} tools/coldstart.py --skip-build {{args}}

# Follow the logs. The seed banner and the boot sequence appear here.
logs:
    {{compose_base}} logs -f --tail=100

# One-shot inside the running container. `just sh migrate` etc.
sh *args:
    {{compose_base}} exec portal sh -c "{{args}}"

# --- the acceptance checker ---------------------------------------------------

# The organizers' program, unmodified, against the running container. Output
# to the terminal, never to a file: acceptance-report.txt is generated by the
# break protocol with a redirect, and a hand-edited one is a lie.
#
# F-48: this recipe's variadic used to default to the literal string `{}`, so
# `just accept` -- named in AGENTS.md, in the README and in .dogfood.toml -- had
# never actually run. See the same note on `coldstart`.

# The organizers' checker, unmodified, against the running container.
accept *args:
    @{{pyq}} run.py .dogfood.toml {{args}}

# THE GATE.
#
# One command, from a clean volume, that proves a checkpoint. Six steps in the
# order that fails cheapest: spec first (no Docker needed), then the container,
# then the checker, then the proofs, then the suite.
#
# The run.py wrapper gates on the report BODY, because run.py returns 0
# unconditionally (F-32). It is a ratchet, not a pass/fail switch: a check
# that regresses, or an expectation that has gone stale, or a tier that is
# overclaimed all fail it. What does NOT fail it is a check that fails exactly
# as expected_checks.json says it will at this milestone.
#
# `--allow-false-passes` is GONE, and its removal is the FEAT-03 milestone.
#
# It existed because two of the organizers' checks reported PASS while testing
# nothing: `/projects/new` was a 404, and 404 is inside the "any 4xx" range the
# checker accepts, so the deadline guard was never called (F-40). FEAT-03 built
# the route, made the refusal a 403 produced by `assert_open_for_submission`,
# and added a precondition that re-sends the checker's own request — carrying the
# same credential, read out of the same `.dogfood.toml` — and requires the
# guard's name in the response BODY. That precondition can tell a deadline
# refusal from a CSRF rejection, a 401 and a 404, so there is nothing left to
# allow.
#
# The flag still exists in the tool and two tests still cover it, because
# FEAT-05 brings back the same class of problem for the judge-scores routes.
# What changed is that the gate no longer needs it — and an escape hatch nobody
# has to reach for is worth more than one somebody might leave on.

# THE GATE. One command, from a clean volume, that proves a checkpoint.
check:
    @echo "=========================================================="
    @echo " 1/6  spec layer (no Docker). The check count is not quoted here on"
    @echo "=========================================================="
    @echo "      purpose: verify_spec prints the count it actually ran -- F-72"
    @python tools/verify_spec.py -q || (echo "SPEC GATE FAILED" & exit /b 1)
    @echo ""
    @echo "=========================================================="
    @echo " 2/6  clean volume, network-independent build"
    @{{compose_base}} down -v --remove-orphans
    @{{compose_base}} build
    @echo ""
    @echo "=========================================================="
    @echo " 3/6  up, wait for health"
    @{{compose_base}} up -d --wait --wait-timeout 120
    @echo ""
    @echo "=========================================================="
    @echo " 4/6  the organizers' checker (7 checks: 3x T1, 4x T2)"
    @echo "=========================================================="
    @{{pyq}} tools/run_acceptance.py .dogfood.toml
    @echo ""
    @echo "=========================================================="
    @echo " 5/6  isolation proof + census + assignment"
    @{{pyq}} tools/run_in_container.py isolation_proof --require-data
    @{{pyq}} tools/run_in_container.py verify_census
    @{{pyq}} tools/run_in_container.py verify_assignment
    @echo ""
    @echo "=========================================================="
    @echo " 6/6  extended suite"
    @echo "=========================================================="
    @{{pyq}} -m pytest -q
    @echo ""
    @echo "GATE GREEN — every step above actually ran."
    @echo "Not covered here, and run at every break: just prove-offline, just mutation-test."

# The brief says commit acceptance-report.txt whatever it says, and never
# hand-edit it: the panel runs the identical program.

# Regenerate acceptance-report.txt.
report:
    @{{pyq}} run.py .dogfood.toml > acceptance-report.txt
    @type acceptance-report.txt

# --- local development --------------------------------------------------------

# The container is the deliverable; this is the fast inner loop, and it is NOT
# a substitute -- the break protocol runs against the container.

# The suite on the host, against the pinned versions.
test *args:
    @{{pyq}} -m pytest {{args}}

# on its own, and so the rule's own tests can invoke it.

# Lint: ruff check, ruff format --check, and the isolation rule.
lint:
    @{{pyq}} -m ruff check src tests tools
    @{{pyq}} -m ruff format --check src tests tools
    @{{pyq}} tools/check_isolation.py

# and the reason there), so this is the check that stands in for it.

# Are the models and the migrations still in step?
lint-migrations:
    @{{pyq}} src/manage.py makemigrations --check --dry-run
    @echo "migrations are in step with the models"

# The isolation rule alone, which is cheap enough to run on every save once the
# primitive exists -- and that is the point of a syntactic rule, as opposed to
# a test you run when you remember.
#
# The unscoped-`Review` rule on its own.
lint-isolation:
    @{{pyq}} tools/check_isolation.py

# The container equivalent is step 5 of `just check`, same command.

# Prove the isolation primitive against the local database.
proof:
    @{{pyq}} src/manage.py isolation_proof

# Generate the OpenAPI 3.1 document. Additive, non-zero on failure.
schema:
    @{{pyq}} src/manage.py spectacular --file openapi.yaml

# Reset the local (host-side) database, which is not the container's.
reset-local:
    @powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue data"
    @{{pyq}} src/manage.py migrate --noinput

# --- the two gates `check` cannot hold ------------------------------------------------
#
# Both need a clean volume, which is why they are not in `check`: `check` must
# stay one command a reviewer runs, and these two add three more minutes of
# container lifecycle. They are run at every verification break and both are
# named in AGENTS.md, so they have to be runnable by name.
#
# Neither recipe existed until FEAT-02, while the two tools behind them did --
# the F-35 shape exactly: a command named in three documents that could not be
# typed. The archive for FEAT-01 recorded "proved" for an offline boot, and the
# way to produce that evidence did not exist as a command. Finding F-44.

# Boot the portal under `--network none` and probe it. Requirement 1 of 5 in the
# spec, and the first numbered disqualification, so it is the one that is worth
# proving before anything else in this file.
#
# Prove the portal boots and serves with no network at all.
prove-offline:
    @{{pyq}} tools/prove_offline.py

# A checker that has only ever passed is not evidence of anything (F-33), so
# this proves the gates can fail before we trust them at a break.

# Corrupt things on purpose, and assert every corruption is caught.
mutation-test:
    @{{pyq}} tools/mutation_test.py
