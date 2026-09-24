# Organiser desk — 23:00 IST, 24 September 2026

**Third firing with no Gmail, second for this desk.** The connector still
answers "needs you to sign in again". Nothing can be sent, drafted or read.
File fallback again; the commit is prefixed "[no Gmail connector]".

Two nudges are now waiting in the repo rather than in anyone's inbox. Both
texts are below, ready to paste.

## Why re-authorising may not be enough, now confirmed

The 00:01 desk suspected this morning that re-authorising would not reach
this session. Reading the Routine itself confirms it. `trig_01EiSjTdFDEQTeYPeSGrAjaW`
holds:

    persist_session:        true
    persistent_session_id:  session_0187kiZSpMrARQMMN9shzTmj
    mcp_connections:        []

So every firing lands in one long-lived session whose connector grants were
fixed when that session started on 12 September, and the Routine itself
carries no connectors of its own. Re-authorising in the claude.ai settings
refreshes the account, not this session's stale grant.

The durable fix is to give the Routine its own Gmail grant and let each
firing start fresh, so it picks up current credentials. That is a change to
how Santosh's Routines are configured, so the desk has not made it. The
same applies to the 00:01 and 20:00 desks, which are hitting the same wall.

## 1. Gulfood Manufacturing — held since 23 Sep, now 8 days silent

Text unchanged from yesterday's brief,
`docs/briefs/2026-09-23-stall-enquiries.md`. Send it in thread
`1a0ab4b7c34f2507` to `gfm@dwtc.com`. The show opens on **3 November**, and
this answer is what decides whether the Gulfood flights are worth booking.

## 2. Telangana Rising — 7 days silent today

The 17 September request to T-Hub for a showcase pod reached seven days of
silence. Send in thread `1a0b0727ef4c4e5e`.

    To:      events@t-hub.co
    Cc:      valuepartners@t-hub.co
    Subject: Re: Telangana Rising Global Summit 2026 — startup showcase pod
             through T-Hub

Dear T-Hub events team,

May I follow up on my note of 17 September about a startup showcase pod at
the Telangana Rising Global Summit (7 to 9 December, Hyderabad)?

Two things would help us most. First, whether T-Hub is in fact curating a
startup showcase at this summit, because if the pods sit with TGIC or
another state body we would rather approach them directly than keep waiting
here. Second, if T-Hub is curating it, the application route and the last
date.

We are a Hyderabad AI startup and registered MSME building Vision AI for
attendance, stock and vehicle-gate counting, and a WhatsApp AI quote desk
for manufacturers and distributors. We are a short drive from your campus
and glad to come in person.

Regards,
Santosh Padmaa
Founder & CEO, Souveno AI Solutions (Souveno AI)
GSTIN 36BDNPP2011D2ZV · Hyderabad · +91 86393 32232 · souveno30@gmail.com
https://souveno.ai

## After either goes out

Set `nudgeCount: 1` and `lastNudgeAt` on the plan, and add the message to
the conversation as `kind: "nudge"`. Second nudges are the last, no earlier
than seven days later.

**Check each thread before sending.** No organiser mail has been read since
the morning of 22 September, so "silent" here means only that nothing is
recorded in Conversations. That is how Informa's Middle East Energy
handover sat unnoticed for six days.

## Nothing else was due

Plastivision is 6 days from its first nudge, Startup Mahakumbh, Intersec
and TiE 5, Hardware Fair and ELECRAMA 4, ACETECH 3. Nineteen threads are
live and Santosh's. TechSparks still has no usable address and GITEX stays
skipped. No first contact is outstanding.
