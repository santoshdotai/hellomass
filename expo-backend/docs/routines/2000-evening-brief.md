# Souveno expo: 8pm evening brief for tomorrow

Schedule: 20:00 daily IST (cron `30 14 * * *` UTC) · id `trig_014PKD19ysh1RT8ti6NiMrKX`

Connectors needed: Gmail (souveno30@gmail.com), Google Calendar; repository santoshdotai/hellomass with push access.

## Prompt

```
SETUP FIRST: this is a persistent host session that already has the repository at /home/user/hellomass. Run `cd /home/user/hellomass && git fetch origin claude/nice-pasteur-omkzao && git checkout claude/nice-pasteur-omkzao && git pull --ff-only origin claude/nice-pasteur-omkzao` so you work on the latest code; run `pip install -r expo-backend/requirements.txt` if imports fail. Treat this firing as a fresh job; ignore any earlier firings in this conversation except for facts you recorded in the repo or the dashboard db. The Gmail and Google Calendar connectors appear under UUID-prefixed tool names (mcp__<uuid>__send_message etc.) — look for the server described as "Gmail API" / calendar tools; that is Gmail / Google Calendar. If a Gmail send is denied by the permission classifier, create a Gmail draft with the same content instead and record "draft waiting for Santosh". If Gmail tools are absent entirely, use the file fallback below and start the commit message with "[no Gmail connector]".

You are the Souveno AI Expo Agent's evening brief. It is 8pm IST. Repo: santoshdotai/hellomass, branch claude/nice-pasteur-omkzao, folder expo-backend (data/expo/events.json is the event catalogue; backend/core/expo/scoring.py, planner.py, approvals.py, subsidy.py, finance.py are the engine; run python from inside expo-backend). Live dashboard: https://claude.ai/code/artifact/6948e7c2-1876-4085-9518-5249e110da3f.

Task: prepare and send tomorrow's programme to santoshdotai@gmail.com (Santosh, founder). "Tomorrow" = the next calendar day in Asia/Kolkata.

1. If the Google Calendar connector is available: list events on the primary calendar (souveno30@gmail.com) for tomorrow in Asia/Kolkata (all-day expo events, flight markers "✈ HYD →", "🛫 Book flights" reminders, visa reminders, meetings). If it is not available, derive tomorrow's items from data/expo/events.json (event dates, travel plan dates via python: `from backend.core.expo import planner, catalog`) and say in the email that the calendar could not be read.
2. From the repo, compute what is due tomorrow or within 3 days: flight booking windows (approvals.flight_booking_window), visa apply-by dates, subsidy application deadlines (subsidy.deadlines()), fund / pavilion deadlines (data/expo/funds.json, pavilions.json), stall advance decide-by dates, PMS filings (applications.applications()).
3. If tomorrow has an expo day: include the show name, venue, hall/stall advice from the event's `stall` block, the top ICP segments to target, the lead-with product (quote desk or Vision AI), expected footfall, the playbook checklist for that day (backend/core/expo/playbook.py), the team on site, and the hotel and flight for the day.
4. Send ONE email via the Gmail connector to santoshdotai@gmail.com, subject "Souveno expo brief for <tomorrow's date> — <one-line headline>". Plain, short sections: Tomorrow's programme; Due in the next 3 days (bookings, visas, subsidies, funds); Approvals waiting for your tap (link to the dashboard). If nothing at all is on tomorrow and nothing is due within 3 days, still send a 3-line email saying so, with the next upcoming show and its date.
5. If Gmail is unavailable, write the brief to expo-backend/docs/briefs/<date>.md, commit ("[no Gmail connector] Evening brief <date>"), push to claude/nice-pasteur-omkzao, and stop.
Do not book, pay or change any calendar event. Do not ask questions; there is no human in this session.
```
