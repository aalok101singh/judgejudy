# Feature Archive Template

> Copy to `NN-slug.md` and fill it in when a feature is **verified done**.
> This is the durable record of *what was built and how* — the Write Up Quest
> material, and the first thing a new session reads to work out where the
> project actually is.

---

# FEAT-NN — Name

**Completed:** YYYY-MM-DD · **Planned:** Nh · **Actual:** Nh · **Gate:** T-n

## What was built

Three to six bullets. Concrete nouns, not intentions. Name the files, the
endpoints and the commands — this is what a new session reads to find out
whether something already exists.

## How it was built

The design that actually shipped, and **the decision that changed while
building.** One paragraph plus anything worth a diagram.

> This is the section the Write Up Quest is built on. "We built X, then Y told
> us Z, so we changed it" is worth more than a clean architecture diagram.

## How it was verified

The command that proves it, and the result. Paste the real output, never a
summary of it.

```bash
just check
```

| | |
|---|---|
| Acceptance line from `build-plan.md` | pass / fail |
| Requirement IDs covered | REQ-Tn-nn |
| Findings opened | F-nn |
| Findings closed | F-nn |

## What was cut or deferred

Anything dropped during the feature, with the reason and the regret. **Move it
to the cut ledger in `bible/08` §13.**

| Item | Reason | Regret |
|---|---|---|
| | | |

## What the next session should know

The three things that would otherwise be re-derived the hard way. The trap, the
surprise, the thing that looks wrong but is right.

1.
2.
3.
