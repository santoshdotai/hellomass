"""The 0-to-1 exhibition playbook for Souveno: how to pick a stall, where to
stand, how to convert, and the taxonomy of outcomes the dashboard tracks."""
from __future__ import annotations

LEAD_STATUSES = [
    {"key": "new", "label": "Lead captured", "order": 1},
    {"key": "qualified", "label": "Qualified (score >= 25/50)", "order": 2},
    {"key": "demo_booked", "label": "Demo booked", "order": 3},
    {"key": "pilot", "label": "Paid pilot", "order": 4},
    {"key": "converted", "label": "Converted (paying)", "order": 5},
    {"key": "not_converted", "label": "Not converted", "order": 6},
    {"key": "left_midway", "label": "Left midway", "order": 7},
]

DROP_REASONS = [
    "Price too high vs WATI/AiSensy",
    "Too few WhatsApp quote requests per day",
    "Wants ERP/Tally integration first",
    "Wants free trial, not paid pilot",
    "Decision-maker not on the call",
    "Chose competitor (QuotesMill / other)",
    "Catalogue / price data not ready",
    "Trust concern: AI quoting wrong price",
    "Timing: busy season, revisit later",
    "No response after 3 follow-ups",
    "Not the ICP (retail / D2C / bespoke)",
    "Other",
]

QUALIFICATION_SCORECARD = [
    {"key": "whatsapp_primary", "q": "WhatsApp is the primary sales channel", "max": 5},
    {"key": "quote_volume", "q": "20+ quote requests a day", "max": 5},
    {"key": "manual_pain", "q": "Staff manually checks Excel/ERP and builds PDFs", "max": 5},
    {"key": "catalog_repeat", "q": "Standardised SKU / product list", "max": 5},
    {"key": "response_pain", "q": "Quotes commonly take > 30 minutes", "max": 5},
    {"key": "followup_leak", "q": "No systematic follow-up", "max": 5},
    {"key": "decision_access", "q": "Owner/director on the demo", "max": 5},
    {"key": "data_ready", "q": "Clean catalogue + prices available", "max": 5},
    {"key": "payment_ready", "q": "Willing to connect Razorpay/UPI", "max": 5},
    {"key": "budget_urgency", "q": "Willing to pay for a pilot this month", "max": 5},
]

STALL_SELECTION = {
    "principles": [
        "Corner stall (two open sides) beats an inline stall of twice the size: 40-60% more walk-ins.",
        "Be on the path between the registration desk and the largest anchor exhibitor; that aisle carries 3-5x the traffic of a side row.",
        "Within 30 metres of an entrance, a café or the washrooms: dwell traffic, not transit traffic.",
        "Avoid dead-end rows, back walls, pillars, and stalls behind machinery that makes noise or blocks sight lines.",
        "At industrial shows ask for the 'Industry 4.0 / software / automation' pavilion; buyers looking for digitisation walk there deliberately.",
        "9 sqm (3x3) shell scheme is enough for a two-person software demo; 12-18 sqm only if you host a seating corner for demos.",
    ],
    "favourable_numbers": [
        "Stall numbering runs from the entrance at most Indian venues: the lowest numbers in a hall (A-01..A-05) sit nearest the gate.",
        "Numbers that end a row (x-01 and the last number of the row) are corners; ask for those first.",
        "Odd/even sides: the side facing the main cross-aisle is the favourable one; check the floor plan, not the number.",
        "Hall 1 or the hall that hosts the inaugural stage is where VIPs and press walk on day one.",
    ],
    "where_to_stand": [
        "Stand at the front edge of the stall, never behind a table; the table goes at the back with the screen.",
        "Face the direction traffic comes from (registration side) and keep the demo phone unlocked on the WhatsApp voice-note demo.",
        "One person greets and qualifies (3 questions, 90 seconds); the other runs the 5-minute demo and scans the card.",
        "At conferences sit in the aisle seat of rows 3-5: easy to leave, visible to speakers, and next to the people who arrive early (decision-makers).",
    ],
}

HOW_TO_GET_CLIENTS = [
    {"step": "Before", "items": [
        "Publish the expo on Calendly (booth-meeting event type) and mail the exhibitor list 10 days before: 'We are at stall X; 10-minute WhatsApp quote demo'.",
        "Load the pre-filled registration answers from /api/expo/events/{id} into the organiser form (bookmarklet).",
        "Print 300 cards with the QR to /expo/card; every scan captures their details and gives them yours.",
        "Prepare a 90-second script: 'How many rate enquiries reach your WhatsApp every day? Who answers them after 7pm?'",
    ]},
    {"step": "During", "items": [
        "Target: 60 booths a day when visiting, 40 qualified cards a day when exhibiting.",
        "Demo the messy voice note -> GST quotation PDF in under 60 seconds; do not open the dashboard first.",
        "Score every lead on the 10-question card (0-50); 35+ books a demo on the spot via Calendly.",
        "Log the outcome and the reason before you leave the stall; unlogged conversations do not exist.",
    ]},
    {"step": "After", "items": [
        "Same-evening WhatsApp: personalised quotation demo using a product from their own card/catalogue.",
        "Day 2, day 7, day 14 follow-ups; mark not_converted with a reason on day 21.",
        "Review the dashboard: cost per converted client per event decides which shows you repeat next year.",
    ]},
]

CHECKLIST = [
    "Stall booked + floor-plan position confirmed in writing",
    "Flights booked (arrive evening before)", "Hotel booked (<= 20 min from venue)",
    "Organiser registration submitted; exhibitor badges", "QR cards printed (300)",
    "Demo phone + backup phone with WhatsApp Business", "Portable 4G router", "Roll-up banner with one line: 'Your best salesperson now lives on WhatsApp'",
    "Pilot pricing sheet (Growth plan) laminated", "Lead scorecard on the tablet (this dashboard)",
    "Calendly booth-meeting link on the banner", "Follow-up templates ready (SOUVENO_NOTIFICATION_TEMPLATES)",
]


def playbook() -> dict:
    return {
        "lead_statuses": LEAD_STATUSES,
        "drop_reasons": DROP_REASONS,
        "qualification_scorecard": QUALIFICATION_SCORECARD,
        "stall_selection": STALL_SELECTION,
        "how_to_get_clients": HOW_TO_GET_CLIENTS,
        "checklist": CHECKLIST,
    }
