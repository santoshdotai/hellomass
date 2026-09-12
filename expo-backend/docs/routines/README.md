# Souveno Expo Agent — routine prompts

These are the exact prompts behind the five scheduled routines. If a routine has to be re-created in the claude.ai Routines screen (to attach the Gmail and Google Calendar connectors and the hellomass repository), paste the matching prompt.

| Routine | Schedule (IST) | Cron (UTC) | File |
|---|---|---|---|
| Souveno expo: 00:01 organiser replies, best stall and price negotiation | 00:01 daily | `31 18 * * *` | [0001-organiser-replies-negotiation.md](0001-organiser-replies-negotiation.md) |
| Souveno expo: 11pm stall enquiries to organisers | 23:00 daily | `30 17 * * *` | [2300-stall-enquiries.md](2300-stall-enquiries.md) |
| Souveno expo: 3-day subsidy, early-bird and confirmation follow-up | 09:30 every 3rd day | `0 4 */3 * *` | [3day-subsidy-followup.md](3day-subsidy-followup.md) |
| Souveno expo: 8pm evening brief for tomorrow | 20:00 daily | `30 14 * * *` | [2000-evening-brief.md](2000-evening-brief.md) |
| Souveno Expo Agent — Monday booking check | 09:00 Monday | `30 3 * * 1` | [monday-booking-check.md](monday-booking-check.md) |
