# Security Policy

## Reporting a vulnerability

**Please do not open a public issue.** A public issue is the fastest way to turn
a vulnerability into a published one.

Report it privately via **GitHub Security Advisories**: on this repository, go to
`Security` → `Report a vulnerability`. If that is unavailable to you, open an
issue that says only *"private security report, please contact me"* and nothing
else, and we will move it somewhere private.

Please include: what you did, what you expected, the version or commit, and a
reproduction if you have one. **You do not need a working exploit** — a
description of the shape of the problem is enough for us to start.

### What to expect

- An acknowledgement within a few days.
- An assessment, and an honest estimate, once we have reproduced it.
- A fix, and a note in the release describing the class of problem without
  publishing anything that would help someone build the next one.

We will not pursue legal action over good-faith research, and we will credit you
if you would like to be named.

---

## The threat model, in one paragraph

Judge Judy holds other people's competitive work before it holds their scores,
and it publishes a ranking that affects real outcomes. So the properties that
matter are **confidentiality between judges**, **integrity of the published
result**, and **availability of a self-hosted deployment with no third party in
the loop**. Everything below follows from those three.

## What is defended, and how

| Property | Mechanism |
|---|---|
| A judge cannot read a peer's reviews | `Review.objects.for_actor(actor)`. Isolation is a property of the data-access layer, enforced by lint rule JJ01, so a view cannot forget to apply it. |
| Denials are not mistaken for success | Every refusal is a **403 with an empty body** from one shared function. Never a redirect: a redirect returns 200 to any client that follows it. |
| A judge's own standing cannot be inferred | While results are published, a judge sees a ranking over **their own reviews only**. |
| The audit trail cannot be quietly rewritten | Entries are hash-chained; `AuditEntry.delete()` raises; a chain entry and the change it describes commit in one transaction. |
| The published result cannot be altered after the fact | `results_hash` covers the ranking, mixed with an input digest of the scores behind it, and the audit chain head is replicated into every judge's signed record — so equivocation is detectable from outside the organizer's database. |
| A judge's scores cannot be read by the organizer in the clear | Signed records commit to **digests of reviews, never scores**. |
| Signing keys cannot be destroyed by a routine reset | Keys live on their own volume, separate from the database. |
| No outbound traffic | The container is proved to boot and serve under `--network none`. There is no CDN, hosted database, external API, or API key. |

## What is deliberately **not** defended

Stated plainly, because a threat model that lists only wins is marketing.

- **Anonymous comment rate limiting is weak by design.** An anonymous poster is
  keyed by a hash of their session, so **clearing cookies resets the budget**.
  IP was the alternative and this project refuses it everywhere else: it is a
  poor identity that gets innocent people in trouble. A limit a private window
  resets is still a limit against the naive case; the strong case is reachable by
  giving people accounts.
- **A signed-in poster is keyed by account, not by IP.** Moving between networks
  does not reset their budget, and neither does a new browser.
- **Judges can collude.** Nothing here stops two judges agreeing on scores. The
  influence report surfaces *concentration*; it deliberately carries no threshold
  and never says "brigaded", because a report that accuses a table of friends on
  a number alone is a machine for making enemies.
- **Randomised ballot order makes position bias zero-*mean*, not zero.** Anyone
  claiming the bias was *removed* is overstating it.
- **No webhook delivery ships.** Models and a `501` stub exist; delivery, retries
  and HMAC verification do not. A webhook URL is also a live SSRF bug class, and
  it is better absent than half-built.
- **Demo credentials are not secrets.** They are HMAC-signed tokens derived from
  a key published in this repository, because anyone holding the repository can
  mint one — which is the point of a demo. Never point a real deployment at them.
- **This is a self-hosted portal, not a hardened multi-tenant service.** One
  deployment runs one event, by design. Do not put several organizers' events in
  one instance.
- **No rate limiting on login beyond a per-account lockout.** Five failures in
  five minutes locks that account for fifteen minutes, keyed per-email so one
  attacker cannot lock every judge out at once. That is a lockout, not a
  distributed-attack defence. Put a reverse proxy in front of a public
  deployment.

## Supported versions

Judge Judy is pre-1.0 and has one supported line: `main` at the latest commit.
Fixes are not backported to old commits.

## Dependencies

Runtime dependencies are six, each commented in `requirements.txt` with why it is
there and what was deliberately left out. Dependabot is configured; if you see a
dependency bump PR, it is automated and worth reading, because a supply-chain
change to a judging portal is worth reading.