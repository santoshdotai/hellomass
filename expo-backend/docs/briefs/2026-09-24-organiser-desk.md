# Organiser desk — 00:01 IST, 24 September 2026

**Second night with no Gmail.** The connector answered "needs you to sign
in again" again tonight, as it did at 00:01, 01:04 and 04:05 yesterday and
at the 23:00 desk. No organiser mail has been read since the morning of
22 September. File fallback again; this commit is prefixed
"[no Gmail connector]".

## Why re-authorising alone may not be enough

Connectors are read **when a session starts**. This desk runs as a
persistent host session, so its Gmail grant was fixed at session start and
has since gone stale — re-authorising in the claude.ai connector settings
will not necessarily reach *this* session. Every further firing into it is
likely to fail the same way.

Two fixes, and the second is the durable one:

1. Re-authorise Gmail at https://claude.ai/customize/connectors.
2. Consider switching this routine (and the 23:00 and 20:00 desks) to
   **start a fresh session on each firing** (`create_new_session_on_fire`).
   Each firing then picks up the current connector grants. The desks do not
   depend on conversation history — the prompt is self-contained and all
   state lives in the repo and the dashboard db — so nothing is lost by it.
   This is the user's call to make; the desk has not changed it.

## WAREMAT 2026 — the approval deadline is TODAY

`approvals/waremat-2026--stall_advance` is **still `status: proposed`**,
unchanged since 21 September. Its deadline is **24 September — today**.
The MSME scheme application closes on the **26th**.

    MSME package, 9 sqm shell   Rs 90,270 all-inclusive (Rs 8,500/sqm ex-GST)
    50% advance to release      Rs 45,135
    MSME claim back (80%)       Rs 72,216   (100% for women/SC/ST)
    Net cost                    about Rs 18,054 — Rs 2,006/sqm — in the home city

Midaas Touch need the signed and sealed booking contract form, the advance,
the Udyam certificate and the payment receipt before the 26th. Nothing in
this desk's gap changes the recommendation: **accept without bargaining**.
What the gap does change is the margin for error — there is now none.

If the decision is yes, it does not need this desk: the form and the
transfer are Santosh's to do directly, and the thread
(`1a0970f80320b77e`) is his. If it is no, it is worth saying so to Midaas
Touch before the 26th rather than letting it lapse silently.

## IFSEC India 2026 — unchanged, still waiting on us

Informa chased on 21 September for the signed and stamped contract form
promised on the 18th. S08 (7 sqm, two sides open, Rs 2,05,084 all-in) is
not held until the form and the advance both arrive. The DC-MSME PMS
question — worth roughly Rs 1.2 lakh — has still never been asked.

## What is not known

Anything an organiser sent on 22 or 23 September. Nineteen threads are
live. The thread sweep will recover all of it on the first firing that has
Gmail, but until then "no news" means only that this desk is blind, not
that nobody wrote. The 23:00 desk carries the same warning about its
Gulfood nudge.

Nothing has been booked, paid or confirmed. No mail has been sent or
drafted to any organiser.

Dashboard: https://claude.ai/artifact/E14Qtzzdhu7gXPCJ78w9HY
