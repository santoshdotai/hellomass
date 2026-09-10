# How the Expo Agent scores a show (1 to 5 stars)

Prepared 10 September 2026 for Souveno AI. Every number below is the agent's estimate from public organiser figures and Souveno's own strategy documents (Barakah Systems market validation report, Souveno AI overview, ICP definition). Change any component in `data/expo/events.json` and the stars recompute.

## The six components (total 100 points)

| Component | Max | What it measures | How it is judged |
|---|---|---|---|
| ICP fit | 40 | Share of the floor that is a quote-heavy B2B manufacturer, distributor or industrial trader (Souveno's ideal customer). Exhibitors count as prospects too, because at industrial shows the exhibitors are the buyers. | 40 = pure ICP (fasteners, pipes, electrical dealers). 20-30 = adjacent (packaging, pharma distributors). 10 = ecosystem shows where visitors are investors, students and IT companies. |
| Footfall | 15 | Realistic trade-visitor count, log-scaled. Organiser claims are discounted (an organiser's '350,000' is treated as ~120,000). | 15 = 100k+ verified trade visitors. 11-13 = 25k-75k. 8 = 10k-15k. 6 = under 10k. |
| Decision makers | 15 | Density of owners, directors and purchase heads on the floor, versus staff, students and general public. | 15 = owner-led shows (ELECRAMA dealer halls). 8 = delegate/tech crowds. |
| Geography and cost | 10 | Travel burden from Hyderabad. | 10 = home city (HITEX). 7 = domestic metro (one flight). 5-6 = poor connectivity (Surat, Greater Noida). 3 = Gulf. |
| Competition noise | 10 | How many WhatsApp-automation / CRM SaaS vendors will be on the same floor shouting the same message. Fewer = higher. | 9 = Souveno would be the only software vendor. 2-3 = every WhatsApp SaaS competitor exhibits (GITEX, tech summits). |
| Timing fit | 10 | Fit with the 90-day validation plan, date clashes with better shows, travel fatigue, and whether the show is once-in-years (bonus) or clashes (penalty). | 10 = perfect slot. 4-6 = clashes with a higher-scoring show or sits in a low-priority period. |

**Stars** = total ÷ 20, rounded to the nearest half star, floor 1.0, cap 5.0. So 95-100 = 5.0, 85-94 = 4.5, 75-84 = 4.0, 65-74 = 3.5, 55-64 = 3.0, 45-54 = 2.5.

## Worked example: Bengaluru Tech Summit 2026 = 2.5 stars

17-19 November 2026, BIEC Bengaluru. Organiser figures: 1,800+ exhibitors, 25,000 delegates, 1,000 startups, theme 'AI & Beyond'.

| Component | Points | Why |
|---|---|---|
| ICP fit | 10 / 40 | The crowd is IT companies, government, students, investors and other startups. Almost nobody on that floor runs a fastener, pipe, cable or packaging business with 30-300 WhatsApp quote requests a day. That is the single biggest reason the score is low. |
| Footfall | 11 / 15 | 25,000 delegates is a large crowd, so this component scores well. |
| Decision makers | 8 / 15 | Plenty of CXOs, but of tech companies, not of manufacturing SMEs. Useful for partners, not for customers. |
| Geography and cost | 7 / 10 | One short flight from Hyderabad, hotel near Yeshwantpur with a metro to BIEC. |
| Competition noise | 3 / 10 | Every WhatsApp-automation and AI-agent vendor in India exhibits here. Souveno's message would be one of fifty identical ones. |
| Timing fit | 6 / 10 | Sits two days before EngiExpo Pune (4.5 stars), which needs the same people and budget. |
| **Total** | **45 / 100** | 45 ÷ 20 = 2.25 → rounds to **2.5 stars** |

What that means in practice: visiting for one day, walking 60 stands a day, the model expects 11-22 usable leads and 0.6-1.2 paid pilots, for a budget of ₹48,000-64,000. The same money at EngiExpo Ahmedabad is expected to return 7-14 paid pilots.

**When BTS still makes sense:** partner hunting (Tally/ERP consultants, BSPs, resellers), investor meetings, or a speaking slot. That is why it stays on the calendar as a 1-day visit, not a stall. If you decide to exhibit anyway, set the event to *exhibit* in the dashboard and the agent proposes a stall advance.

## Contrast: why Plastivision India 2027 = 5.0 stars

ICP fit 40/40 (HDPE/PVC pipe and duct makers are Souveno's live vertical), footfall 15/15 (150,000 in 2023), decision makers 14/15 (owner-led plastics SMEs), geography 7/10 (Mumbai), competition 9/10 (no WhatsApp SaaS vendor exhibits), timing 10/10 (once every four years) = 95/100 → 5.0.

## Client probability and expected leads

Separately from the stars, each show gets an expected funnel using Souveno's own conversion targets: exhibiting captures 0.5% of ICP-relevant visitors (reach capped at 60,000); visiting means 60 booths a day for up to 3 days with 50% sharing details; then 35% qualify, 50% of those take a demo, and 30% of demos become paid pilots (the validation report's target). The low estimate is half the high. 'Client probability' is the chance of at least one paid pilot from the low estimate: 1 − e^(−expected pilots).

## All 23 shows, ranked

| Show | City | Start | ICP /40 | Footfall /15 | Decision makers /15 | Geography /10 | Low competition /10 | Timing /10 | Total | Stars | Mode |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Plastivision India 2027 | Mumbai | 2027-01-21 | 40 | 15 | 14 | 7 | 9 | 10 | **95** | **5.0** | exhibit |
| ELECRAMA 2027 | Greater Noida | 2027-02-20 | 40 | 15 | 15 | 6 | 9 | 10 | **95** | **5.0** | exhibit |
| Fastener Fair India 2027 | Mumbai | 2027-04-22 | 40 | 8 | 13 | 7 | 9 | 9 | **86** | **4.5** | exhibit |
| EngiExpo Pune 2026 | Pune | 2026-11-21 | 38 | 12 | 12 | 7 | 8 | 8 | **85** | **4.5** | exhibit |
| EngiExpo Ahmedabad 2026 | Ahmedabad | 2026-12-19 | 38 | 12 | 12 | 7 | 8 | 8 | **85** | **4.5** | exhibit |
| Indexpo Hyderabad 2027 (Industrial & Engineering Expo) | Hyderabad | 2027-09-03 | 36 | 9 | 11 | 10 | 8 | 9 | **83** | **4.0** | exhibit |
| ACETECH Hyderabad 2027 | Hyderabad | 2027-01-22 | 34 | 11 | 11 | 10 | 8 | 7 | **81** | **4.0** | exhibit |
| International Hardware Fair India 2026 | New Delhi | 2026-10-23 | 36 | 9 | 12 | 7 | 8 | 8 | **80** | **4.0** | visit |
| EngiExpo Surat 2027 | Surat | 2027-02-06 | 36 | 11 | 11 | 5 | 8 | 8 | **79** | **4.0** | exhibit |
| Indexpo Mumbai 2027 (Industrial & Engineering Expo) | Mumbai | 2027-06-03 | 34 | 9 | 11 | 7 | 8 | 9 | **78** | **4.0** | visit |
| IMTEX 2027 + Tooltech + Digital Manufacturing | Bengaluru | 2027-01-21 | 30 | 13 | 13 | 7 | 8 | 6 | **77** | **4.0** | visit |
| Automation Expo 2027 | Mumbai | 2027-06-02 | 30 | 13 | 12 | 7 | 7 | 8 | **77** | **4.0** | exhibit |
| EngiExpo Jaipur 2027 | Jaipur | 2027-08-28 | 34 | 11 | 11 | 6 | 8 | 7 | **77** | **4.0** | visit |
| PAPEXPO 2026 | Hyderabad | 2026-10-01 | 30 | 8 | 10 | 10 | 8 | 9 | **75** | **4.0** | visit |
| India Automation & Robotics Expo 2027 | Bengaluru | 2027-04-09 | 26 | 8 | 11 | 7 | 7 | 8 | **67** | **3.5** | visit |
| India Pharma Expo 2027 | Hyderabad | 2027-03-11 | 22 | 8 | 10 | 10 | 8 | 7 | **65** | **3.5** | visit |
| WAREMAT Expo 2026 | Hyderabad | 2026-10-08 | 22 | 6 | 9 | 10 | 8 | 8 | **63** | **3.0** | visit |
| Big 5 Global 2026 | Dubai | 2026-11-23 | 26 | 13 | 11 | 3 | 6 | 4 | **63** | **3.0** | visit |
| Convergence India 2027 + INDELXPO 2027 | New Delhi | 2027-03-23 | 20 | 11 | 9 | 7 | 4 | 7 | **58** | **3.0** | visit |
| Gulf Print & Pack 2027 | Dubai | 2027-01-12 | 20 | 8 | 10 | 3 | 7 | 5 | **53** | **2.5** | visit |
| Startup Mahakumbh 6.0 | New Delhi | 2027-03-12 | 10 | 14 | 8 | 7 | 3 | 6 | **48** | **2.5** | visit |
| GITEX Global 2026 | Dubai | 2026-12-07 | 12 | 15 | 10 | 3 | 2 | 5 | **47** | **2.5** | visit |
| Bengaluru Tech Summit 2026 | Bengaluru | 2026-11-17 | 10 | 11 | 8 | 7 | 3 | 6 | **45** | **2.5** | visit |

## ICP segments used

- **A** — Industrial components / fasteners / hardware
- **B** — Building materials / tiles / sanitary / electrical
- **C** — Packaging / printing / labels
- **D** — Auto parts / auto ancillary / job work
- **E** — Machinery / equipment / fabrication
- **P** — Pipes / HDPE / PVC / ducts (flagship live client vertical)
- **X** — Partners, investors, ecosystem (not buyers)

## How to change a score

Edit the `score` block of the event in `data/expo/events.json` (six integers within the maxima above). Stars, client probability, budgets, the calendar `.ics`, the dashboards and the booking proposals all recompute from that file. Replace the modelled footfall figures with your own counts after each show; the agent's numbers for Indexpo Hyderabad are placeholders until you enter what you saw on 4-6 September 2026.
