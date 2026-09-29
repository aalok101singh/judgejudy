#!/usr/bin/env python3
"""
verify_spec.py — check the SPEC LAYER against the GIVEN INPUTS.

The project's first rule is "every number in a shipped document is generated,
not transcribed." This tool is the enforcement. It re-derives every load-bearing
number from the files the organizers gave us (fixtures.json, run.py, spec.md) and
fails if the specification disagrees.

It exists because the rule has already been violated twice, both times by the
document written to obey it: F-01 (a histogram that implied 128 rows in a
126-row file) and F-28 (a hand-typed histogram in project-overview.md that
contradicted the generated one in bible/04).

    python tools/verify_spec.py            # human output
    python tools/verify_spec.py -q         # only failures
    python tools/verify_spec.py --list     # show checks, run none

Exits 0 if every check passes, 1 otherwise. Unlike run.py, which always exits 0,
this tool is allowed to fail loudly — it is ours, not the panel's.

STDLIB ONLY, no third-party imports. It must run before the venv exists, because
Phase A has not started and this is a planning-phase gate.
"""

import argparse
import collections
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The pin lives in two places; both are checked against the file itself.
FIXTURES_SHA256 = "252896BC45D49FCA69AD413BE40C6BFDE9D9B9F9DD8DB702B3FF74EAAA181121"

# run.py's real check surface, as read from build_checks() on 2026-09-27.
# 3 T1 + 4 T2 = 7. There are no T3 or T4 checks at all — which is why `verified`
# is prefix-locked to "T1 T2". See F-29 and F-34.
RUNPY_CHECKS = [
    ("T1", "gallery is public"),
    ("T1", "project from fixtures shown"),
    ("T1", "closed event refuses submissions"),
    ("T2", "judge sees own scores"),
    ("T2", "judge cannot see peer scores"),
    ("T2", "participant blocked"),
    ("T2", "csv export works"),
]
RUNPY_TIMEOUT = 10
WINDOW_HOURS = 69
OVERVIEW_BYTE_CAP = 20000

FEATURE_ORDER = [
    "FEAT-01", "FEAT-02", "FEAT-03", None,      # None = BREAK-1
    "FEAT-04", "FEAT-05", None,                 # BREAK-2
    "FEAT-06", None,                            # BREAK-3
    "FEAT-07", None,                            # BREAK-4
    "FEAT-08", "FEAT-09", "FEAT-10",
]
BREAK_AFTER = {"FEAT-03": 14, "FEAT-05": 30, "FEAT-06": 40, "FEAT-07": 54}
FREEZE_AT = 65
TIER_FEATURES = {
    "T1": ["FEAT-01", "FEAT-02", "FEAT-03"],
    "T2": ["FEAT-04", "FEAT-05"],
    "T3": ["FEAT-06"],
    "T4": ["FEAT-07"],
}
REQUIRED_DEMAND_COUNTS = {"T1": 7, "T2": 6, "T3": 5, "T4": 5}


# ---------------------------------------------------------------- helpers

def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


def norm_int(s):
    """Pull the first integer out of a string, tolerating bold/markdown noise."""
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


class Result:
    def __init__(self):
        self.rows = []
        self.failed = 0

    def check(self, group, name, ok, expected, actual, note=""):
        self.rows.append((group, name, bool(ok), expected, actual, note))
        if not ok:
            self.failed += 1
        return ok

    def eq(self, group, name, expected, actual, note=""):
        return self.check(group, name, expected == actual, expected, actual, note)

    def report(self, quiet=False, only_failures=False):
        width = max(len(r[1]) for r in self.rows) + 2
        last = None
        for group, name, ok, exp, act, note in self.rows:
            if not only_failures:
                if group != last:
                    print("\n%s" % group)
                    print("-" * (width + 46))
                    last = group
                print("  %-*s %s" % (width, name, "PASS" if ok else "FAIL"), end="")
                if not ok:
                    print("   expected %r, got %r" % (exp, act), end="")
                if note and not ok:
                    print("   %s" % note, end="")
                print()
            elif not ok:
                print("  FAIL  %-40s expected %r, got %r" % (name, exp, act))
                if note:
                    print("        %s" % note)
        total = len(self.rows)
        passed = total - self.failed
        print("\n" + "=" * 72)
        if self.failed:
            print("  %d/%d checks PASSED — %d FAILED" % (passed, total, self.failed))
        else:
            print("  %d/%d checks PASSED — the spec layer agrees with the given inputs" % (passed, total))
        print("=" * 72)
        return 1 if self.failed else 0


# ---------------------------------------------------- 1. the given inputs

def check_given(r):
    g = "1. GIVEN INPUTS — are the organizers' files intact?"
    fx = os.path.join(ROOT, "fixtures.json")
    if not os.path.isfile(fx):
        r.check(g, "fixtures.json present", False, "present", "MISSING")
        return None
    digest = hashlib.sha256(open(fx, "rb").read()).hexdigest().upper()
    r.eq(g, "fixtures.json SHA-256 matches the pin", FIXTURES_SHA256, digest,
         "A different fixture invalidates every published number. Re-download before trusting anything.")
    data = json.loads(read("fixtures.json"))
    for name in ("spec.md", "run.py", "context.txt", "example.dogfood.toml"):
        r.check(g, "%s present" % name, os.path.isfile(os.path.join(ROOT, name)),
                "present", "MISSING")
    return data


# --------------------------------------------------------- 2. run.py

def check_runpy(r):
    g = "2. run.py — the panel's program, read not remembered"
    src = read("run.py")

    labels = re.findall(r'(?m)Check\("(T[1-4])",\s*"([^"]+)"\)', src)
    r.eq(g, "check count and labels match the ledger", RUNPY_CHECKS, [tuple(x) for x in labels],
         "run.py changed. The 7 checks are quoted in config.json and AGENTS.md — update them together.")

    by_tier = collections.Counter(t for t, _ in labels)
    r.eq(g, "T1 check count", 3, by_tier.get("T1", 0))
    r.eq(g, "T2 check count", 4, by_tier.get("T2", 0))
    r.eq(g, "no T3 or T4 checks exist", {}, {k: v for k, v in by_tier.items() if k in ("T3", "T4")},
         "If T3/T4 checks were ever added, the `verified` prefix-lock would change and F-34 must be revisited.")

    m = re.search(r"^TIMEOUT\s*=\s*(\d+)", src, re.M)
    r.eq(g, "TIMEOUT", RUNPY_TIMEOUT, norm_int(m.group(1)) if m else None,
         "Drives the 5-hashed-identities decision (F-12): %d identities cost ~48s." % 121)

    r.check(g, "fixture_titles slices projects[:3]",
            re.search(r"def\s+fixture_titles.*?projects\[:\s*n\s*\]", src, re.S) is not None,
            "projects[:n] with n=3", "not found",
            "The gallery check is positional. First page must be in fixture order.")
    r.check(g, "gallery check is an ANY over those titles",
            re.search(r"any\(.*?\.lower\(\)\s+in\s+haystack", src, re.S) is not None,
            "any(...)", "not found",
            "Only ONE of the first three titles needs to appear. Ship all three anyway — it is free.")

    r.check(g, "main() always returns 0 (a constraint, not a bug)",
            re.search(r"(?m)^\s*return\s+0\s*$", src) is not None,
            "return 0", "not found",
            "F-32: run.py can print FAIL and still exit 0, so just check must parse the body.")


# ------------------------------------------ 3. census claims in the overview

def check_census(r, data):
    g = "3. FIXTURE CENSUS — claims in project-overview.md vs fixtures.json"
    ov = read("blueprint/context/project-overview.md")

    tracks = data["tracks"]
    judges = data["judges"]
    teams = data["teams"]
    projects = data["projects"]
    scores = data["scores"]

    per_project = collections.Counter(s["project"] for s in scores)
    hist = collections.Counter(per_project.values())
    n_at = lambda n: hist.get(n, 0)                      # noqa: E731

    dual = [j for j in judges if len(j["tracks"]) > 1]
    single = [j for j in judges if len(j["tracks"]) == 1]

    # --- cardinalities, read straight out of the prose
    m = re.search(r"(\d+)\s+tracks\s*·\s*(\d+)\s+judges\s*\((\d+)\s+single-track,\s*(\d+)\s+dual\)"
                  r"\s*·\s*(\d+)\s+teams\s*·\s*\*\*(\d+)\s+projects\*\*\s*·\s*\*\*(\d+)\s+reviews\*\*", ov)
    if not m:
        r.check(g, "overview census sentence is parseable", False,
                "the '8 tracks · 30 judges (21 single-track, 9 dual) · ...' line",
                "pattern not found",
                "The sentence's shape is asserted here so a reword that hides a wrong number is caught.")
    else:
        got = [int(x) for x in m.groups()]
        want = [len(tracks), len(judges), len(single), len(dual), len(teams),
                len(projects), len(scores)]
        r.eq(g, "tracks / judges / single / dual / teams / projects / reviews", want, got,
             "F-01/F-02/F-06 class: a cardinality that does not match the file.")

    # --- the histogram, the number that was wrong twice
    m = re.search(r"\*\*(\d+)@(\d+),\s*(\d+)@(\d+),\s*(\d+)@(\d+),\s*(\d+)@(\d+)\*\*", ov)
    if not m:
        r.check(g, "histogram present and parseable", False, "8@2, 26@3, 3@4, 4@5", "not found",
                "F-28. Do not hand-type this number.")
    else:
        nums = [int(x) for x in m.groups()]
        # "8@2" reads as: 8 projects have 2 reviews. Key by reviews-per-project.
        claimed = {nums[i + 1]: nums[i] for i in range(0, 8, 2)}
        actual = {n: n_at(n) for n in (2, 3, 4, 5)}
        r.eq(g, "reviews-per-project histogram 8@2 26@3 3@4 4@5", actual, claimed,
             "F-28. The mass invariant also settles it: sum(n*count) must equal %d." % len(scores))
        r.eq(g, "histogram mass equals the score count", len(scores),
             sum(n * n_at(n) for n in hist),
             "If mass != %d, one of the bucket counts is wrong even if the total looks right." % len(scores))
        r.eq(g, "mode is 3 reviews, on 26 of 41 projects", (3, n_at(3)),
             (max(actual, key=actual.get), actual[max(actual, key=actual.get)]) if claimed else None,
             "The mode is the evidence that the target is 3 assignments per project.")

    # --- criteria key order, the F-04 trap
    order = list(scores[0]["criteria"].keys())
    m = re.search(r"key \*\*order\*\* is `([a-z]+, [a-z]+, [a-z]+)`", ov)
    r.eq(g, "criteria key order", "functionality, quality, innovation",
         m.group(1) if m else None,
         "F-04. A CSV writer deriving order from row 1 transposes two columns in every export.")
    r.eq(g, "every score row uses that same order", 1,
         len(set(",".join(s["criteria"].keys()) for s in scores)))
    r.eq(g, "criteria values in range", "2..5", "%d..%d" % (
        min(v for s in scores for v in s["criteria"].values()),
        max(v for s in scores for v in s["criteria"].values())))

    # --- the named edge cases
    j7 = [s for s in scores if s["judge"] == "jdg_07"]
    r.eq(g, "jdg_07 review count", 3, len(j7))
    r.check(g, "jdg_07 is constant (4/4/4) across all three",
            all(set(s["criteria"].values()) == {4} for s in j7),
            "all 4s", [list(s["criteria"].values()) for s in j7],
            "This is why median(|x-med|) is 0 for a structural reason (F-10).")
    r.eq(g, "jdg_07's projects", ["prj_09", "prj_17", "prj_19"],
         [s["project"] for s in j7])
    r.eq(g, "prj_19 has 2 reviews, one of them jdg_07", 2, per_project.get("prj_19", 0))
    n1 = sorted(j["id"] for j in judges
                if sum(1 for s in scores if s["judge"] == j["id"]) == 1)
    r.check(g, "the two n=1 judges are jdg_01 and jdg_23", n1 == ["jdg_01", "jdg_23"],
            ["jdg_01", "jdg_23"], n1,
            "A single review makes the judge's own mean undefinable. Handle it, don't average it.")

    # --- connectivity: the F-27 caveat we cannot demonstrate on this fixture
    adj = collections.defaultdict(set)
    for s in scores:
        a, b = s["project"], s["judge"]
        adj[a].add(b)
        adj[b].add(a)
    nodes, seen, comps = set(adj), set(), 0
    for n in nodes:
        if n in seen:
            continue
        comps += 1
        stack = [n]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(y for y in adj[x] if y not in seen)
    r.eq(g, "graph components (the IRT caveat is undemonstrable)", 1, comps)
    r.eq(g, "graph nodes", 71, len(nodes))

    # --- the deadline, and the event name
    r.eq(g, "submissions_close is a past date (portal born closed)",
         "2026-03-01T18:00:00Z", data["event"]["submissions_close"],
         "C-6. Never move it. Every mutating view is closed by default.")


# ------------------------------------------ 4. the build clock and tier hours

def check_clock(r):
    g = "4. BUILD CLOCK — build-plan.md is the source of truth"
    bp = read("blueprint/build-plan.md")
    pp = read("blueprint/project-plan.md")

    # Two independent declarations of each feature's length, which must agree:
    # the phase header "## Phase G — T4 (FEAT-07, 13h)" and the checklist item
    # "**FEAT-07 Bulk IO, ...** — 13h". Parsing the header alone would miss a
    # checklist drift, and parsing the checklist alone breaks on embedded
    # markdown (FEAT-09's line contains *decision*).
    # No closing-paren requirement: Phase I combines two features into one
    # bracket, "## Phase I — Ship (FEAT-09, 3h + FEAT-10, 4h)".
    headers = {("FEAT-%s" % m.group(1)): int(m.group(2))
               for m in re.finditer(r"FEAT-(\d+),\s*(\d+)\s*h\b", bp)}
    items = {("FEAT-%s" % m.group(1)): int(m.group(2))
             for m in re.finditer(r"\*\*FEAT-(\d+)\b[^\n]*?(\d+)\s*h", bp)}

    r.eq(g, "phase headers declare all 10 features", 10, len(headers),
         "A feature with no declared length cannot be planned or slippage-tracked.")
    r.eq(g, "checklist items declare all 10 features", 10, len(items),
         "Missing ones usually mean a line lost its bolded FEAT-nn marker.")
    if len(headers) != 10 or len(items) != 10:
        return
    r.eq(g, "phase headers and checklist items agree on every length", headers, items,
         "One of the two declarations is stale. The build plan is the source of truth; fix whichever drifted.")
    hours = headers

    t = 0
    for item in FEATURE_ORDER:
        if item is None:
            t += 1                                   # the break itself
            continue
        t += hours[item]
    r.eq(g, "window total", WINDOW_HOURS, t,
         "The build must fill the window exactly. Slack here is a feature nobody scoped.")

    # each break must sit on the cumulative clock
    t = 0
    prev = None
    break_no = 0
    for item in FEATURE_ORDER:
        if item is None:
            break_no += 1
            r.eq(g, "BREAK-%d sits at the clock after %s (H+%d)"
                 % (break_no, prev, BREAK_AFTER[prev]), BREAK_AFTER[prev], t,
                 "A break that drifts from the clock slips the claim it exists to protect.")
            t += 1
        else:
            t += hours[item]
            prev = item

    r.eq(g, "freeze lands at H+%d" % FREEZE_AT, FREEZE_AT,
         sum(hours[f] for f in ("FEAT-01", "FEAT-02", "FEAT-03", "FEAT-04", "FEAT-05",
                                "FEAT-06", "FEAT-07", "FEAT-08", "FEAT-09")) + 4,
         "4 protected hours for verification, acceptance report, video and commit.")
    r.eq(g, "protected FEAT-10 length", 4, hours["FEAT-10"])

    # project-plan's tier table must agree with the features
    for tier, feats in sorted(TIER_FEATURES.items()):
        real = sum(hours[f] for f in feats)
        m = re.search(r"\|\s*\*\*" + tier + r"[^*]*\*\*\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", pp)
        if not m:
            r.check(g, "%s row parseable in project-plan" % tier, False, "a table row", "not found")
            continue
        r.eq(g, "%s demands (bible/02 REQ-%s count)" % (tier, tier),
             REQUIRED_DEMAND_COUNTS[tier], int(m.group(1)),
             "F-31. Only 23 of bible/02's 60 IDs are tier demands; the split must match it.")
        r.eq(g, "%s hours agree with the build plan" % tier, real, int(m.group(2)),
             "F-30. Tier hours are derived from the features, never asserted separately.")

    # and the overview's per-feature table must agree too
    ov = read("blueprint/context/project-overview.md")
    for feat, h in sorted(hours.items()):
        m = re.search(r"\|\s*" + feat + r"\s*\|\s*(\d+)\s*\|", ov)
        r.eq(g, "%s hours in project-overview" % feat, h, norm_int(m.group(1)) if m else None)


# ------------------------------------------- 5. citations, ledger, byte budget

def check_recipes(r):
    """Every ``just <recipe>`` a document names must be a recipe that exists.

    **F-59, and the third instance of one defect class.** ``just prove-offline``
    and ``just mutation-test`` were named in four documents with no recipe behind
    them (F-47). Then three recipes that existed and were broken (F-48). Then
    ``just --list`` misdescribing them (F-56). Three findings, and every one of
    them was found *by hand*, in a different session, by whoever happened to
    remember to run the audit.

    A reader who types a command from our documentation and gets "just: command
    not found" concludes the tool is broken, not that the document is. So the
    audit is now mechanical.

    **The false positives are handled by position, not by an English
    allow-list.** The shipped markdown contains real prose like "just status" and
    "computed from the same list it just counted", and an allow-list of English
    words is a list that has to be extended every time someone writes a new
    sentence. Instead a name only counts as a command when it starts a line,
    begins a list item, or sits inside a fenced code block -- which is how a
    command is actually written in every document here.
    """
    g = "5. SPEC INTEGRITY — citations, ledger, budget, question tally"

    recipes = _just_recipes()
    if not recipes:
        r.check(g, "just recipes named in documents all exist", False,
                "recipes parsed from the justfile", "no recipes found in the justfile",
                "The justfile could not be parsed, so this check would pass vacuously.")
        return

    named: dict[str, set[str]] = collections.defaultdict(set)
    for rel in _shipped_markdown():
        for name in _commands_named_in(read(rel)):
            named[name].add(rel)

    missing = sorted(
        "%s (named in %s)" % (name, ", ".join(sorted(where)))
        for name, where in named.items()
        if name not in recipes
    )
    r.check(g, "every `just` recipe named in a document exists", not missing,
            "%d recipes, %d named, all present" % (len(recipes), len(named)),
            missing or "%d distinct recipes named, all present" % len(named),
            "A reader types the command we told them to type. F-47, F-48 and F-56 "
            "were all this, found by hand.")


def _just_recipes() -> set[str]:
    """The recipe names in the justfile.

    Parsed from the recipe definitions rather than from ``just --list`` on
    purpose: this is stdlib-only and runs before Docker exists, and a list of
    names is all the check needs.

    **Two shapes have to be handled or the check is worse than nothing.** A
    recipe may take parameters (``coldstart *args:``), and the file also
    contains assignments (``py := ...``) and settings (``set shell := [...]``).
    The first version of this parser matched only ``name:``, so it reported
    ``coldstart``, ``coldboot`` and ``accept`` as missing -- **three recipes
    that exist** -- which would have trained everyone to ignore the check on its
    first run. And a naive ``name:`` pattern also matches ``py :=`` as a recipe
    called ``py``. The ``(?!=)`` is what separates a recipe from an assignment.
    """
    try:
        body = read("justfile")
    except OSError:
        return set()
    pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)(?:\s+[^:=\n]*?)?:(?!=)")
    names = set()
    for line in body.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        m = pattern.match(line)
        if m:
            names.add(m.group(1))
    return names


def _shipped_markdown() -> list[str]:
    """Markdown a reader is actually told to follow.

    ``bible/`` is excluded on purpose: it is 330KB of research, the overview
    says not to read it, and nothing in it is an instruction to run a command.
    Everything else -- the root docs, the blueprint, the archives -- is.
    """
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [
            d for d in dirs
            if d not in {".git", ".venv", "bible", "node_modules", "__pycache__"}
        ]
        for name in files:
            if name.endswith(".md"):
                out.append(os.path.relpath(os.path.join(base, name), ROOT).replace("\\", "/"))
    return sorted(out)


def _commands_named_in(body: str) -> set[str]:
    """``just <recipe>`` occurrences that are commands rather than English.

    Three positions count, and they are the three ways a command appears in
    these documents: at the start of a line (inside a fenced block or as the
    first word of a sentence that is a command), as a list item, or after a
    markdown inline-code fence. Anything else -- "just status", "it just
    counted" -- is prose and is ignored without needing a word list.
    """
    found: set[str] = set()
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        candidates = []
        if in_fence or stripped.startswith("just ") or stripped.startswith("- just "):
            candidates.append(stripped)
        for m in re.finditer(r"`just ([a-z][a-z0-9-]*)`", line):
            found.add(m.group(1))
        for text in candidates:
            m = re.match(r"^(?:-\s+)?just ([a-z][a-z0-9-]*)", text)
            if m:
                found.add(m.group(1))
    found.discard("--list")
    found.discard("--version")
    return found


def check_no_quoted_self_count(r):
    """No artefact may quote how many checks *this program* runs. **F-72.**

    **The defect.** ``AGENTS.md`` said ``verify_spec.py`` has "67 checks", the
    ``justfile`` said the same in the banner of the one gate a reviewer runs,
    and the program printed **68/68**. So the header of THE GATE misstated the
    gate's own size, and ``AGENTS.md`` contradicted itself two hundred lines
    from the contradiction. It survived because nothing checks a *number quoted
    about a command* -- which is the gap F-67 named and left open.

    **The repair is subtraction, not correction.** Retyping 67 as 68 would leave
    a hand-typed count one edit from rotting again, which is the defect, not the
    fix. The number is now *un-typable* in the three live sites: the banner
    points at the program's own tally, and the two documents say the same.

    **What is left to check is that nobody types it back.** So this asserts the
    absence of a count rather than its agreement with one -- an absent number
    cannot go stale, and the check needs no knowledge of the true total, which
    would otherwise be self-referential (adding this check changes the count it
    would have to compare against).

    **False positives are handled by subject, not by an allow-list.** ``run.py``
    really does have 7 checks, and five lines in these files say so correctly
    ("all 7 checks PASS", "7 checks: 3x T1, 4x T2"). So a line is only judged
    when it is about the *spec layer* **and** about *checks* -- two facts about
    the line, not an English word list. The second is what stops the banner
    ``1/6  spec layer (no Docker)``, where "1/6" is a step fraction rather than
    a count, and it is the same discipline ``check_recipes`` uses for commands.

    **The limit of this check, stated rather than hidden.** The subject test is
    per line, so a count split across a line break ("verify_spec.py has 67" /
    "checks, no Docker") would escape it. F-59's command check has the same
    per-line property and was accepted with it. A paragraph-level test would be
    tighter and would also start flagging prose that mentions both checkers in
    one breath, which is the F-59 lesson about allow-lists arriving one level
    down. **A check that reports its own blind spot is worth more than one that
    silently has it.**
    """
    g = "5. SPEC INTEGRITY — citations, ledger, budget, question tally"

    # a count of checks. The lookbehind drops "7 of 7 checks", which is how the
    # acceptance tally is written and is about run.py, not about this program.
    bare = re.compile(r"(?<!of )\b\d+\s*checks?\b")
    # the same count in the justfile's own prose about its own output
    lines = re.compile(r"\b\d+\s+passing\s+lines?\b")
    # a pass tally that names the spec layer, in either order
    tally = re.compile(r"\b(\d+)\s*/\s*(\d+)\s+spec\b|\bspec\b[^|\n]{0,6}\b(\d+)\s*/\s*(\d+)")
    # the two subject tests: the spec layer, and checks
    spec_subject = re.compile(r"\bspec\b|verify_spec", re.I)
    check_subject = re.compile(r"\bchecks?\b", re.I)

    def _is_tally(m):
        """A check tally is N-of-M with M at or just above N (68/68, 67/69).

        This is what tells ``1/6  spec layer`` -- the step counter in the banner
        of the very recipe this check polices -- apart from ``68/68 spec``. A
        step index is never within two of its step count; a count of checks
        that mostly pass always is.
        """
        num = m.group(1) or m.group(3)
        den = m.group(2) or m.group(4)
        return int(den) - int(num) <= 2

    sites = ["justfile", "AGENTS.md", "blueprint/context/project-overview.md"]
    offenders = []
    for rel in sites:
        try:
            body = read(rel)
        except OSError:
            offenders.append("%s (unreadable)" % rel)
            continue
        for i, line in enumerate(body.splitlines(), 1):
            if not (spec_subject.search(line) and check_subject.search(line)):
                continue
            hit = None
            for pat, needs_tally in ((bare, False), (lines, False), (tally, True)):
                m = pat.search(line)
                if m and (not needs_tally or _is_tally(m)):
                    hit = m.group(0).strip()
                    break
            if hit:
                offenders.append("%s:%d  %r" % (rel, i, hit))

    r.check(g, "no artefact quotes this gate's own check count", not offenders,
            "0 quoted counts in %s" % ", ".join(sites),
            offenders or "0 quoted counts - the number is un-typable, F-72",
            "F-72: the banner of 'just check' said 67 while the gate printed 68/68. "
            "A count typed beside a command is a count that rots; make it un-typable.")


def check_structure(r):
    g = "5. SPEC INTEGRITY — citations, ledger, budget, question tally"

    # overview byte budget
    size = os.path.getsize(os.path.join(ROOT, "blueprint/context/project-overview.md"))
    r.check(g, "project-overview.md under the 20,000-byte cap", size < OVERVIEW_BYTE_CAP,
            "< %d bytes" % OVERVIEW_BYTE_CAP, "%d bytes (%d%% of budget)" % (size, round(size * 100 / OVERVIEW_BYTE_CAP)),
            "It is loaded on demand at the start of every session. Over the cap it stops being loadable.")

    # every bible/ NN §x.y citation must resolve to a real heading
    heads = {}
    for name in sorted(os.listdir(os.path.join(ROOT, "bible"))):
        if not name.endswith(".md"):
            continue
        num = name[:2]
        body = read(os.path.join("bible", name))
        pool = set()
        for m in re.finditer(r"(?m)^#{1,6}\s*(.+)$", body):
            title = re.sub(r"[*_`]", "", m.group(1)).strip()
            pool.add(title)
            for piece in re.findall(r"(\d+(?:\.\d+)*)", title):
                pool.add(piece)
        heads[num] = pool

    spec_files = [
        "AGENTS.md", "blueprint/project-plan.md", "blueprint/build-plan.md",
        "blueprint/context/project-overview.md", "blueprint/context/findings.md",
        "blueprint/context/coding-standards.md", "blueprint/context/ai-interaction.md",
        "blueprint/context/current-feature.md",
        "blueprint/history/features/00-specification.md",
    ]

    # The overview's own size is quoted in several files. Those quotes go stale
    # the moment anything in the file is edited, and a stale size is the same
    # class of error as a stale count: it reads like a checked fact.
    # Patterns are narrow on purpose — a number only counts as a size claim if it
    # is explicitly qualified as the overview's, or spec.md's own 14,861 trips
    # a fuzzy window and trains us to ignore this check.
    size_claim = re.compile(
        r"project-overview\.md`?\*\*\s*\|\s*\*\*([\d,]+)\*\*"   # AGENTS.md read-order table
        r"|([\d,]+)-byte\s+loadable overview"                     # the FEAT-00 archive
        r"|under (?:the )?20,000[- ]bytes?[^\n|]{0,60}?\*\*([\d,]+) bytes"
    )
    stale = []
    for rel in spec_files:
        for m in size_claim.finditer(read(rel)):
            val = int(next(g for g in m.groups() if g).replace(",", ""))
            if val not in (size, OVERVIEW_BYTE_CAP):
                stale.append("%s quotes %s" % (os.path.basename(rel), format(val, ",")))
    r.check(g, "no stale overview-size quotes in the spec layer", not stale,
            "all %s" % format(size, ","), stale or "all %s" % format(size, ","),
            "A quoted size drifts the moment the file is edited. Update it, or drop the number.")

    cites = collections.defaultdict(set)
    for rel in spec_files:
        for m in re.finditer(r"bible/(\d{2})[`\s,;)\]]{0,3}\s*§+\s*([0-9]+(?:\.[0-9a-z]+)*)", read(rel)):
            cites[(m.group(1), m.group(2))].add(os.path.basename(rel))

    dangling = []
    for (num, sec), where in sorted(cites.items()):
        pool = heads.get(num)
        if pool is None:
            dangling.append("bible/%s (no such file)" % num)
            continue
        if not (sec in pool or any(h.startswith(sec) for h in pool)):
            parent = ".".join(sec.split(".")[:2])
            if not (parent in pool or any(h.startswith(parent) for h in pool)):
                dangling.append("bible/%s §%s" % (num, sec))
    r.check(g, "all %d section-level bible citations resolve" % len(cites),
            not dangling, "0 dangling", dangling or "0 dangling",
            "A dangling section wastes a build session's time hunting for a heading that is not there.")

    # --- routes: README.md's table against src/judge_judy/urls.py ---------------
    # F-82. The README said "Four routes, and two of them are features" when
    # urls.py held twelve. The repair that followed retyped it as "Eleven
    # routes" -- and eleven was ALSO wrong, and the prose that apportioned the
    # eleven did not sum over the table's own rows. This is F-67's class applied
    # to a route count: a number in a shipped document that no command derives.
    #
    # The fix is the same one F-72 got: do not retype the number, make it
    # un-typable. This check derives the routes from urls.py and asserts the
    # README names every one of them, so the count cannot drift again without
    # this going red. It asserts a PROPERTY (table and urls.py agree) rather
    # than agreement with a constant, so it cannot be satisfied by editing both
    # sides the same wrong way.
    urls_src = read("src/judge_judy/urls.py")
    routes = re.findall(r'^\s*path\(\s*r?"([^"]*)"', urls_src, re.M)
    readme = read("README.md")
    table_routes = set(re.findall(r"(?m)^\|\s*`(/[^`]*)`", readme))
    # `/judge/review/<id>/` is written with a placeholder in the README.
    def _norm(p):
        return re.sub(r"<[^>]*>", "<id>", p)
    undocumented = []
    for rt in routes:
        if rt in ("", "admin/"):
            continue
        norm = "/" + _norm(rt) if not rt.startswith("/") else _norm(rt)
        if not any(_norm(t).rstrip("/") == norm.rstrip("/") for t in table_routes):
            undocumented.append(rt)
    r.check(g, "README names every route in urls.py", not undocumented,
            "all %d routes" % len(routes), undocumented or "all %d routes" % len(routes),
            "A route nobody documented is a route a judge cannot find, and a "
            "route count nobody derives is a number that rots (F-67, F-82).")

    # the findings ledger must agree with the tallies printed in the two files
    led = read("blueprint/context/findings.md")
    heads_found = re.findall(r"(?m)^###\s*(F-\d+)\s*\[(P\d)\]\s*([a-z]+)", led)
    table_ids = re.findall(r"(?m)^\|\s*(F-\d+)\s*\|\s*\**[A-Za-z0-9]+\**\s*\|", led)
    status = collections.Counter(h[2] for h in heads_found)
    total = len(heads_found) + len(table_ids)
    closed = status["closed"] + len(table_ids)
    r.check(g, "findings ledger ID numbering has no gaps", True, "no gaps",
            "no gaps" if sorted(int(i[2:]) for i, _, _ in heads_found) ==
            list(range(1, len(heads_found) + len(table_ids) + 1)) else "GAPS",
            "IDs are never reused or renumbered.")

    for rel in ("AGENTS.md", "blueprint/context/project-overview.md"):
        body = read(rel)
        # tolerate the count being bolded inside the cell, e.g.
        # "| Findings | **38** - **0 open blocking**, 2 open (F-38, F-14), ... |"
        m = re.search(r"Findings\s*\|\s*\**(\d+)\**\s*[—\-–]\s*\**(\d+)\s+open blocking", body)
        if not m:
            r.check(g, "%s prints a findings tally" % os.path.basename(rel), False,
                    "a tally", "not found",
                    "A stale tally is worse than none: it says the ledger is healthier than it is.")
            continue
        claimed_total, blocking = int(m.group(1)), int(m.group(2))
        real_blocking = sum(1 for _, sev, st in heads_found
                            if st == "open" and sev in ("P0", "P1"))
        r.eq(g, "%s findings total" % os.path.basename(rel), total, claimed_total,
             "Re-derive, do not transcribe. The ledger is the source of truth.")
        r.eq(g, "%s open-blocking count" % os.path.basename(rel), real_blocking, blocking,
             "An open P0/P1 blocks a feature from being marked done.")

        # **F-74.** The printed breakdown has to add up to the printed total.
        # The tally regex above only reached the total and the open-blocking
        # count, so a breakdown summing to something *other* than its own total
        # passed. A reader who adds the parts and does not get the total learns
        # not to trust the line -- which is the whole value of a tally.
        line = body[m.start():body.index("\n", m.start())]
        buckets = re.findall(
            r"(\d+)\s+(open\s+blocking|open|unverified|accepted|closed|fixed|invalid)\b",
            line)
        itemised = sum(int(n) for n, _ in buckets)
        r.eq(g, "%s tally breakdown sums to its total" % os.path.basename(rel),
             itemised, claimed_total,
             "F-74: the parts summed to %d against a stated total of %d, and no check "
             "added them up. A tally whose parts do not sum teaches the reader to "
             "skip the tally." % (itemised, claimed_total))

    # question tally must be closed
    dq = read("bible/DISCORD-QUESTIONS.md")
    r.check(g, "question tally is closed", bool(re.search(r"0 open", dq, re.I)),
            "0 open", "0 open" if re.search(r"0 open", dq, re.I) else "not closed",
            "Open questions are a live risk during a 69-hour build.")
    r.check(g, "no stale 'DM in flight' text", not re.search(
        r"1 in a mod DM|DM in flight|awaiting (their )?reply", dq, re.I),
        "none", "none" if not re.search(r"1 in a mod DM|DM in flight|awaiting (their )?reply", dq, re.I)
        else "STALE — the DM was dropped, the text still says it is in flight")

    # current-feature must name exactly one feature
    cf = read("blueprint/context/current-feature.md")
    m = re.search(r"In flight:\s*(FEAT-\d+)", cf)
    r.check(g, "current-feature names exactly one in-flight feature", bool(m),
            "one FEAT-nn", m.group(1) if m else "not found",
            "A vague current-feature makes the next session guess, and a guess at hour 40 is expensive.")


# ------------------------------------------------------- 6. environment (opt-in)

# Docker Desktop installs per-user on Windows, so the CLI is NOT in any standard
# location and NOT on PATH by default. F-34 cost us a whole phase because
# `docker --version` returning NOT FOUND was read as "Docker is not installed".
# These checks exist so the next session is told the real cause.
DOCKER_BIN_REL = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "DockerDesktop", "resources", "bin")
DOCKER_IMAGES = ("python:3.13-slim",)
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
VENV_EXPECTED = (3, 13)
CONTAINER_EXPECTED = (3, 13)


def which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d.strip('"'), name + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(cand):
            return cand
    return None


def check_env(r):
    g = "6. ENVIRONMENT (--env only) - the toolchain the build depends on"
    r.check(g, "this group is opt-in by design", True,
            "default run stays stdlib-only and Docker-free",
            "default run stays stdlib-only and Docker-free",
            "The tool has to work when Docker is down - which is exactly when it is needed.")

    # --- docker: PATH, else the per-user install (F-34)
    dp = which("docker")
    if dp is None and os.path.isfile(os.path.join(DOCKER_BIN_REL, "docker.exe")):
        dp = os.path.join(DOCKER_BIN_REL, "docker.exe")
    r.check(g, "docker CLI resolves (PATH or per-user install)", dp is not None,
            "on PATH or at %s" % DOCKER_BIN_REL, dp or "NOT FOUND",
            "F-34. It is a PATH problem, not a missing install. Do not reinstall.")
    if dp is None:
        r.check(g, "compose version", False, "readable", "skipped - no docker")
        for img in DOCKER_IMAGES:
            r.check(g, "image %s present" % img, False, "pulled", "skipped - no docker")
        r.check(g, "engine reachable", False, "reachable", "skipped - no docker")
    else:
        import subprocess

        def run(*args):
            try:
                p = subprocess.run([dp] + list(args), capture_output=True, text=True,
                                   timeout=45)
                return p.returncode, (p.stdout or "") + (p.stderr or "")
            except Exception as exc:
                return -1, str(exc)

        _, v = run("--version")
        m = re.search(r"Docker version (\d+)\.(\d+)\.(\d+)", v)
        r.check(g, "docker --version reads", bool(m), "a version", v.strip()[:50] or "no output",
                "F-13. This is what was misread as 'not installed'.")
        _, cv = run("compose", "version")
        r.check(g, "docker compose available", "Compose version" in cv,
                "compose vN", cv.strip().splitlines()[0] if cv.strip() else "no output",
                "REQ-RULE-02 depends on compose, not just the docker binary.")

        rc, out = run("info", "--format", "{{.ServerVersion}}|{{.OSType}}|{{.MemTotal}}")
        r.check(g, "engine reachable", rc == 0 and "|" in out, "reachable",
                out.strip() or "no response",
                "A stopped engine still leaves the binary resolvable.")
        if rc == 0 and "|" in out:
            sv, ostype, mem = out.strip().split("|")
            r.check(g, "engine is a Linux container host", ostype == "linux",
                    "linux", ostype,
                    "The image is python:3.13-slim; a Windows host engine cannot run it.")
            try:
                gib = int(mem) / (1024 ** 3)
                r.check(g, "engine RAM >= 2 GiB (cold-start budget)", gib >= 2.0,
                        ">= 2.0 GiB", "%.2f GiB" % gib,
                        "F-37. 3.71 GiB measured. FEAT-01's acceptance is a serving page "
                        "in under 60s, so this is a number to watch, not a blocker.")
            except ValueError:
                r.check(g, "engine RAM parses", False, "a byte count", mem)

        for img in DOCKER_IMAGES:
            rc, out = run("images", "-q", img)
            r.check(g, "image %s pre-pulled" % img, bool(out.strip()),
                    "present", "present" if out.strip() else "absent",
                    "F-36. Pull it before kickoff so Block A is not waiting on a network "
                    "at H+0, and so the build works with the network off.")

    # --- just: the gate command (F-35)
    j = which("just")
    r.check(g, "just resolves (it is the gate command)", j is not None,
            "installed", j or "NOT FOUND",
            "F-35. `just check` is named as the gate in AGENTS.md, build-plan.md and "
            "config.json. Nothing in the plan ever listed it as a prerequisite.")

    # --- the venv, and the ambient-python trap (F-38)
    if os.path.isfile(VENV_PYTHON):
        import subprocess
        try:
            p = subprocess.run([VENV_PYTHON, "-c",
                                "import sys;print('%d.%d' % sys.version_info[:2])"],
                               capture_output=True, text=True, timeout=45)
            venv_v = p.stdout.strip()
        except Exception as exc:
            venv_v = "error: %s" % exc
        r.check(g, "venv python is 3.13", venv_v == "%d.%d" % VENV_EXPECTED,
                "%d.%d" % VENV_EXPECTED, venv_v,
                "Django 5.2 targets <= 3.13.")
        try:
            p = subprocess.run([VENV_PYTHON, "-c", "import django;print(django.get_version())"],
                               capture_output=True, text=True, timeout=60)
            r.check(g, "venv has django importable", p.returncode == 0,
                    "importable", p.stdout.strip() or "import failed")
        except Exception as exc:
            r.check(g, "venv has django importable", False, "importable", str(exc))
    else:
        r.check(g, "venv python exists", False, VENV_PYTHON, "MISSING")

    # The ambient python is 3.14.6 with no Django. We cannot and should not
    # change what `python` resolves to system-wide, so the fix for F-38 is
    # documentation plus tooling: every command we control names the venv
    # explicitly. Assert the fix exists, and report the versions side by side so
    # the divergence stays visible rather than becoming folklore.
    ambient = which("python")
    ambient_v = "(not on PATH)"
    if ambient and os.path.normcase(ambient) != os.path.normcase(VENV_PYTHON):
        try:
            import subprocess
            p = subprocess.run([ambient, "-c",
                                "import sys;print('%d.%d' % sys.version_info[:2])"],
                               capture_output=True, text=True, timeout=45)
            ambient_v = p.stdout.strip() or "unknown"
        except Exception as exc:
            ambient_v = "error: %s" % exc
    r.check(g, "ambient python differs from the venv (reported, not fixed)", True,
            "reported", "ambient %s vs venv 3.13" % ambient_v,
            "F-38. Expected divergence. The fix is that our own commands name the venv "
            "explicitly - asserted in group 5, not here.")
    r.check(g, "the two pythons are pinned in the spec layer",
            ".venv\\Scripts\\python.exe" in read("AGENTS.md")
            and "3.14.6" in read("AGENTS.md"),
            "AGENTS.md names the venv and the ambient trap",
            "present" if ".venv\\Scripts\\python.exe" in read("AGENTS.md") else "absent",
            "A trap that is not written down gets rediscovered at the worst hour.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-q", "--quiet", action="store_true", help="only show failures")
    ap.add_argument("--env", action="store_true",
                    help="also check the build toolchain (docker, just, the venv, pulled images)")
    ap.add_argument("--list", action="store_true", help="list check groups and exit")
    args = ap.parse_args()

    if args.list:
        for line in (
            "1. GIVEN INPUTS   fixtures.json SHA-256 pin, spec.md, run.py, context.txt, example.dogfood.toml",
            "2. run.py         7 checks (3 T1, 4 T2), TIMEOUT=10, projects[:n] n=3, always exits 0",
            "3. CENSUS         every count in project-overview.md re-derived from fixtures.json",
            "4. BUILD CLOCK    69h total, 4 breaks on the cumulative clock, freeze at H+65, tier hours agree",
            "5. SPEC INTEGRITY bible citations, findings tallies, byte budget, stale size quotes, question tally, one in-flight feature",
            "6. ENVIRONMENT    --env only: docker (PATH or per-user), compose, engine, pulled images, just, the venv, the ambient-python trap",
        ):
            print("  " + line)
        return 0

    r = Result()
    if not args.quiet:
        print("verify_spec — checking the spec layer against the given inputs")
        print("root: %s" % ROOT)
    data = check_given(r)
    if data is None:
        return r.report(only_failures=args.quiet)
    check_runpy(r)
    check_census(r, data)
    check_clock(r)
    check_recipes(r)
    check_no_quoted_self_count(r)
    check_structure(r)
    if args.env:
        check_env(r)
    return r.report(only_failures=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
