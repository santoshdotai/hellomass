# Organiser desk — blocked status (one file, kept current)

**Last rewritten: 00:01 IST, 6 October 2026 — fourteenth consecutive
night with no Gmail.**

This replaces the per-night copies `2026-09-23-organiser-desk.md` through
`2026-09-27-organiser-desk.md`, which said the same thing five times. Those
are left in place for the record; this is the one to read. The desk will
rewrite this file each blocked night instead of adding another, and the
one-line-per-firing audit trail continues in `routine-log.md`.

## State

Gmail has answered "needs you to sign in again" on every attempt since
**22 September 18:31 UTC** — fourteen nights, both this desk and the 23:00 desk,
plus three extra retries on the first night. A non-interactive session
cannot run the OAuth flow.

**No organiser mail has been read for fifteen days.** Nineteen threads are
live. Nothing in the repo, the db or the dashboard is broken; only the
mailbox link. The desks can compute and record but cannot see or speak.

When Gmail returns, sweep (b) — by thread, every
`conversations/<eventId>.threadIds` re-read for inbound newer than the last
recorded `at` — recovers the entire gap. Use a window wide enough to cover
it (`newer_than:10d` or more).

## Open items, in the order they matter

**1. IFSEC India 2026 — the live one.** S08 (7 sqm, two sides open,
Rs 2,05,084 all-in) is not held until the signed and stamped contract form
and the advance both arrive. Informa chased on 21 September; the form was
promised on the 18th. The DC-MSME PMS question, worth about Rs 1.2 lakh,
has never been asked — one line in the same mail. The form was promised
on 18 September, eighteen days ago. This item has **no external deadline**,
which is exactly why it keeps slipping while dated items get attention.

**2. Gulfood Manufacturing 2026.** Silent since the 16 September enquiry,
twenty days, and with the show on 3 November this one is
now past the point where a reply would leave time to build and ship;
show opens **3 November**, so the answer gates the flights. Draft ready in
`PENDING-OUTBOX.md`.

**3. WAREMAT 2026 — closed, pending verification.** The DC-MSME scheme
application closed 26 September with the advance approval never tapped
(`approvals/waremat-2026--stall_advance`, status still `proposed`). The
desk cannot verify the lapse: it has been blind since the 22nd and Santosh
may have sent the form and advance himself on his own thread
(`1a0970f80320b77e`). The first firing with Gmail must read that thread and
correct the record either way. If it did lapse, the forgone claim is
Rs 72,216. The stall may still be buyable at Rs 90,270, but without the
subsidy that is Rs 10,030/sqm against a Rs 6,000 ceiling — a fresh
decision, not this approval. The desk has stopped raising it.

**4. Everything else unsent.** `PENDING-OUTBOX.md`, kept current by the
23:00 desk.

## The fix

Re-authorise Gmail at https://claude.ai/customize/connectors. That may not
be sufficient on its own: connectors are bound when a session starts and
these desks fire into a long-running session, which would explain fourteen
identical nights. The durable fix is a fresh session per firing, which
cannot be done with `update_trigger` — it would mean recreating the
Routines and losing their run history — so it remains the user's call. The
desks are self-contained (all state in the repo and the dashboard db), so
nothing would be lost by it.

Nothing booked, paid or confirmed. No mail sent or drafted to anyone.
