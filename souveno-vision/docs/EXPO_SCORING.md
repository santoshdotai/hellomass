# How the Expo Agent scores a show (1 to 5 stars)

Prepared 10 September 2026 for Souveno AI. Every number below is the agent's estimate from public organiser figures and Souveno's own strategy documents (Barakah Systems market validation report, Souveno AI overview, ICP definition). Change any component in `data/expo/events.json` and the stars recompute.

## Souveno sells two products, so every show is scored for both

| Product line | What it does | Who buys it on a show floor |
|---|---|---|
| **WhatsApp AI quote desk** | Enquiry → stock check → GST quotation PDF → payment, all inside WhatsApp | Quote-heavy B2B manufacturers, distributors and industrial traders (segments A-E, P below) |
| **Vision AI** | Camera-based employee attendance and performance reports, stock and dispatch-stock counting, vehicle entry/exit logging, safety compliance | Factories, warehouses and 3PL hubs, construction sites and developers, logistics yards and fleets, retail/showrooms, plus CCTV dealers and security integrators as channel partners (segments F, W, K, L, R, S) |

Each event carries two ICP scores, `icp_fit` (quote desk) and `vision_fit` (Vision AI), both out of 40. **The ICP component that counts toward the total is the better of the two**, because on the day the team leads with whichever product the floor wants. The dashboard shows a *lead with* badge: Quote desk, Vision AI, or Both (when the two fits are within 4 points of each other and at least 24/40).

## The six components (total 100 points)

| Component | Max | What it measures | How it is judged |
|---|---|---|---|
| ICP fit | 40 | max(quote-desk fit, Vision AI fit). Quote desk: share of the floor that is a quote-heavy B2B manufacturer, distributor or industrial trader. Vision AI: share that runs factories, warehouses, sites, yards or gates with cameras already installed. Exhibitors count as prospects too, because at industrial shows the exhibitors are the buyers. | 40 = pure ICP (fasteners, pipes, electrical dealers; or a warehousing/security floor for Vision AI). 20-30 = adjacent (packaging, pharma distributors; construction developers). 10 = ecosystem shows where visitors are investors, students and IT companies. |
| Footfall | 15 | Realistic trade-visitor count, log-scaled. Organiser claims are discounted (an organiser's '350,000' is treated as ~120,000). | 15 = 100k+ verified trade visitors. 11-13 = 25k-75k. 8 = 10k-15k. 6 = under 10k. |
| Decision makers | 15 | Density of owners, directors, plant heads and purchase heads on the floor, versus staff, students and general public. | 15 = owner-led shows (ELECRAMA dealer halls). 8 = delegate/tech crowds. |
| Geography and cost | 10 | Travel burden from Hyderabad (all flights depart from and return to HYD). | 10 = home city (HITEX). 7 = domestic metro (one flight). 5-6 = poor connectivity (Surat, Greater Noida). 3-5 = Gulf. |
| Competition noise | 10 | How many WhatsApp-automation / CRM SaaS or video-analytics vendors will be on the same floor shouting the same message. Fewer = higher. | 9 = Souveno would be the only software vendor. 2-3 = every WhatsApp SaaS or AI-camera competitor exhibits (GITEX, tech summits, IFSEC). |
| Timing fit | 10 | Fit with the 90-day validation plan, date clashes with better shows, travel fatigue, and whether the show is once-in-years (bonus) or clashes (penalty). | 10 = perfect slot. 4-6 = clashes with a higher-scoring show or sits in a low-priority period. |

**Stars** = total ÷ 20, rounded to the nearest half star, floor 1.0, cap 5.0. So 95-100 = 5.0, 85-94 = 4.5, 75-84 = 4.0, 65-74 = 3.5, 55-64 = 3.0, 45-54 = 2.5.

## Worked example: Bengaluru Tech Summit 2026 = 2.5 stars

17-19 November 2026, BIEC Bengaluru. Organiser figures: 1,800+ exhibitors, 25,000 delegates, 1,000 startups, theme 'AI & Beyond'.

| Component | Points | Why |
|---|---|---|
| ICP fit | 14 / 40 | Quote desk 10/40: the crowd is IT companies, government, students, investors and other startups. Almost nobody on that floor runs a fastener, pipe, cable or packaging business with 30-300 WhatsApp quote requests a day. Vision AI 14/40: a few smart-city, retail-tech and security-integrator stands, so Vision AI leads here, but it is still a thin slice. That is the single biggest reason the score is low. |
| Footfall | 11 / 15 | 25,000 delegates is a large crowd, so this component scores well. |
| Decision makers | 8 / 15 | Plenty of CXOs, but of tech companies, not of manufacturing SMEs or warehouse operators. Useful for partners, not for customers. |
| Geography and cost | 7 / 10 | One short flight from Hyderabad, hotel near Yeshwantpur with a metro to BIEC. |
| Competition noise | 3 / 10 | Every WhatsApp-automation, AI-agent and computer-vision vendor in India exhibits here. Souveno's message would be one of fifty identical ones. |
| Timing fit | 6 / 10 | Sits two days before EngiExpo Pune (4.5 stars), which needs the same people and budget. |
| **Total** | **49 / 100** | 49 ÷ 20 = 2.45 → rounds to **2.5 stars** |

What that means in practice: visiting for one day, walking 60 stands a day, the model expects 16-31 usable leads and 0.8-1.7 paid pilots, for a budget of ₹48,000-64,000. The same money at EngiExpo Ahmedabad is expected to return several times as many paid pilots.

**When BTS still makes sense:** partner hunting (Tally/ERP consultants, BSPs, CCTV integrators, resellers), investor meetings, or a speaking slot. That is why it stays on the calendar as a 1-day visit, not a stall. If you decide to exhibit anyway, set the event to *exhibit* in the dashboard and the agent proposes a stall advance.

## Why Big 5 Global (construction) is 3.5 stars but Hardware Fair India is 4.0

| | Big 5 Global 2026, Dubai | International Hardware Fair India 2026, Delhi |
|---|---|---|
| Quote-desk fit | 26/40 (building-material and electrical dealers, but a third of the floor is contractors and architects) | 36/40 (hardware, fastener and tool traders: almost pure ICP) |
| Vision AI fit | 32/40 (construction sites, developers, logistics yards with cameras) | 16/40 |
| ICP counted | 32 (lead with Vision AI) | 36 (lead with quote desk) |
| Footfall | 13/15 (80,000 visitors, bigger crowd) | 9/15 (about 12,000 trade visitors) |
| Decision makers | 11/15 | 12/15 |
| Geography and cost | 5/10 (visa, 4-hour flight from HYD, ₹70k+ air fare for two) | 7/10 (one domestic flight) |
| Low competition | 6/10 (several automation and site-camera vendors) | 8/10 |
| Timing | 4/10 (sits between EngiExpo Pune and GITEX) | 8/10 |
| **Total** | **71 → 3.5 stars** | **80 → 4.0 stars** |

Big 5 has the bigger crowd, but the crowd is less Souveno-shaped, it costs three times as much to reach, and it lands in a crowded fortnight. Hardware Fair is smaller but almost every stand is a buyer.

## Contrast: why Plastivision India 2027 = 5.0 stars

ICP fit 40/40 (HDPE/PVC pipe and duct makers are Souveno's live vertical), footfall 15/15 (150,000 in 2023), decision makers 14/15 (owner-led plastics SMEs), geography 7/10 (Mumbai), competition 9/10 (no WhatsApp SaaS vendor exhibits), timing 10/10 (once every four years) = 95/100 → 5.0.

## Client probability and expected leads

Separately from the stars, each show gets an expected funnel using Souveno's own conversion targets: exhibiting captures 0.5% of ICP-relevant visitors (reach capped at 60,000); visiting means 60 booths a day for up to 3 days with 50% sharing details; then 35% qualify, 50% of those take a demo, and 30% of demos become paid pilots (the validation report's target). The low estimate is half the high. 'Client probability' is the chance of at least one paid pilot from the low estimate: 1 − e^(−expected pilots). The funnel is computed for the lead product; the dashboard also shows the alternative product's funnel.

## All 29 shows, ranked

| Show | City | Start | Quote fit /40 | Vision fit /40 | ICP counted /40 | Footfall /15 | Decision makers /15 | Geography /10 | Low competition /10 | Timing /10 | Total | Stars | Lead with | Mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Plastivision India 2027 | Mumbai | 2027-01-21 | 40 | 30 | 40 | 15 | 14 | 7 | 9 | 10 | **95** | **5.0** | Quote desk | exhibit |
| ELECRAMA 2027 | Greater Noida | 2027-02-20 | 40 | 28 | 40 | 15 | 15 | 6 | 9 | 10 | **95** | **5.0** | Quote desk | exhibit |
| Fastener Fair India 2027 | Mumbai | 2027-04-22 | 40 | 26 | 40 | 8 | 13 | 7 | 9 | 9 | **86** | **4.5** | Quote desk | exhibit |
| EngiExpo Pune 2026 | Pune | 2026-11-21 | 38 | 30 | 38 | 12 | 12 | 7 | 8 | 8 | **85** | **4.5** | Quote desk | exhibit |
| EngiExpo Ahmedabad 2026 | Ahmedabad | 2026-12-19 | 38 | 30 | 38 | 12 | 12 | 7 | 8 | 8 | **85** | **4.5** | Quote desk | exhibit |
| Automation Expo 2027 | Mumbai | 2027-06-02 | 30 | 36 | 36 | 13 | 12 | 7 | 7 | 8 | **83** | **4.0** | Vision AI | exhibit |
| Indexpo Hyderabad 2027 (Industrial & Engineering Expo) | Hyderabad | 2027-09-03 | 36 | 30 | 36 | 9 | 11 | 10 | 8 | 9 | **83** | **4.0** | Quote desk | exhibit |
| Middle East Energy 2027 | Dubai | 2027-05-11 | 36 | 26 | 36 | 12 | 13 | 5 | 8 | 8 | **82** | **4.0** | Quote desk | exhibit |
| India Warehousing Show 2027 | New Delhi | 2027-06-24 | 24 | 38 | 38 | 9 | 12 | 7 | 8 | 8 | **82** | **4.0** | Vision AI | exhibit |
| IMTEX 2027 + Tooltech + Digital Manufacturing | Bengaluru | 2027-01-21 | 30 | 34 | 34 | 13 | 13 | 7 | 8 | 6 | **81** | **4.0** | Both | visit |
| ACETECH Hyderabad 2027 | Hyderabad | 2027-01-22 | 34 | 26 | 34 | 11 | 11 | 10 | 8 | 7 | **81** | **4.0** | Quote desk | exhibit |
| International Hardware Fair India 2026 | New Delhi | 2026-10-23 | 36 | 16 | 36 | 9 | 12 | 7 | 8 | 8 | **80** | **4.0** | Quote desk | visit |
| WAREMAT Expo 2026 | Hyderabad | 2026-10-08 | 22 | 38 | 38 | 6 | 9 | 10 | 8 | 8 | **79** | **4.0** | Vision AI | visit |
| EngiExpo Surat 2027 | Surat | 2027-02-06 | 36 | 30 | 36 | 11 | 11 | 5 | 8 | 8 | **79** | **4.0** | Quote desk | exhibit |
| Indexpo Mumbai 2027 (Industrial & Engineering Expo) | Mumbai | 2027-06-03 | 34 | 30 | 34 | 9 | 11 | 7 | 8 | 9 | **78** | **4.0** | Both | visit |
| Gulfood Manufacturing 2026 | Dubai | 2026-11-03 | 26 | 34 | 34 | 12 | 11 | 5 | 7 | 8 | **77** | **4.0** | Vision AI | visit |
| EngiExpo Jaipur 2027 | Jaipur | 2027-08-28 | 34 | 28 | 34 | 11 | 11 | 6 | 8 | 7 | **77** | **4.0** | Quote desk | visit |
| PAPEXPO 2026 | Hyderabad | 2026-10-01 | 30 | 18 | 30 | 8 | 10 | 10 | 8 | 9 | **75** | **4.0** | Quote desk | visit |
| Intersec Dubai 2027 | Dubai | 2027-01-12 | 6 | 34 | 34 | 12 | 11 | 5 | 5 | 8 | **75** | **4.0** | Vision AI | visit |
| India Automation & Robotics Expo 2027 | Bengaluru | 2027-04-09 | 26 | 34 | 34 | 8 | 11 | 7 | 7 | 8 | **75** | **4.0** | Vision AI | visit |
| IFSEC India 2026 | New Delhi | 2026-12-03 | 8 | 34 | 34 | 9 | 11 | 7 | 5 | 8 | **74** | **3.5** | Vision AI | visit |
| India Pharma Expo 2027 | Hyderabad | 2027-03-11 | 22 | 30 | 30 | 8 | 10 | 10 | 8 | 7 | **73** | **3.5** | Vision AI | visit |
| Big 5 Global 2026 | Dubai | 2026-11-23 | 26 | 32 | 32 | 13 | 11 | 5 | 6 | 4 | **71** | **3.5** | Vision AI | visit |
| Big 5 Saudi 2027 (formerly Big 5 Construct Saudi) | Riyadh | 2027-04-19 | 26 | 32 | 32 | 12 | 11 | 3 | 7 | 5 | **70** | **3.5** | Vision AI | visit |
| Convergence India 2027 + INDELXPO 2027 | New Delhi | 2027-03-23 | 20 | 26 | 26 | 11 | 9 | 7 | 4 | 7 | **64** | **3.0** | Vision AI | visit |
| GITEX Global 2026 | Dubai | 2026-12-07 | 12 | 24 | 24 | 15 | 10 | 5 | 2 | 5 | **61** | **3.0** | Vision AI | visit |
| Gulf Print & Pack 2027 | Dubai | 2027-01-12 | 20 | 18 | 20 | 8 | 10 | 5 | 7 | 5 | **55** | **3.0** | Quote desk | visit |
| Startup Mahakumbh 6.0 | New Delhi | 2027-03-12 | 10 | 12 | 12 | 14 | 8 | 7 | 3 | 6 | **50** | **2.5** | Vision AI | visit |
| Bengaluru Tech Summit 2026 | Bengaluru | 2026-11-17 | 10 | 14 | 14 | 11 | 8 | 7 | 3 | 6 | **49** | **2.5** | Vision AI | visit |

## ICP segments used

- **A** — Industrial components / fasteners / hardware
- **B** — Building materials / tiles / sanitary / electrical
- **C** — Packaging / printing / labels
- **D** — Auto parts / auto ancillary / job work
- **E** — Machinery / equipment / fabrication
- **P** — Pipes / HDPE / PVC / ducts (flagship live client vertical)
- **X** — Partners, investors, ecosystem (not buyers)
- **F** — Factories & plants: workforce attendance/performance, line activity, safety
- **W** — Warehouses, 3PL & distribution hubs: stock count, dispatch verification, vehicle gates
- **K** — Construction sites & developers: workforce, vehicle entry/exit, safety compliance
- **L** — Logistics yards, fleets, gate operations: vehicle entry/exit, dwell time
- **R** — Retail, cafés, showrooms: footfall, queue, staff activity
- **S** — Security system integrators & CCTV dealers: Vision AI channel partners

## How to change a score

Edit the `score` block of the event in `data/expo/events.json` (seven integers: `icp_fit` and `vision_fit` out of 40, then the five others within the maxima above). Stars, lead product, client probability, budgets, the calendar `.ics`, the dashboards and the booking proposals all recompute from that file. Replace the modelled footfall figures with your own counts after each show; the agent's numbers for Indexpo Hyderabad are placeholders until you enter what you saw on 4-6 September 2026.
