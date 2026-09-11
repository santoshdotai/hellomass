/* SOUVENO Expo Agent dashboard */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const api = async (path, opts = {}) => {
    const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.status === 204 ? null : r.json();
  };
  const inr = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  const subsidyBox = (sb) => {
    if (!sb) return '';
    const sch = (sb.schemes || []).map((x) => `<li><b>${esc(x.name)}</b> — ${esc(x.benefit)}${x.estimated_refund_inr ? ` · est. ${inr(x.estimated_refund_inr[0])}–${inr(x.estimated_refund_inr[1])}` : ''}${x.apply_by ? ` · <span class="${x.urgency === 'late' ? 'late' : x.urgency === 'soon' ? 'soon' : ''}">apply by ${x.apply_by}${x.days_to_apply != null ? ` (${x.days_to_apply} days)` : ''}</span>` : ' · apply after the show'} · <a target="_blank" rel="noopener" href="${x.link}">${x.status === 'confirmed' ? 'confirmed scheme' : x.status === 'needs_membership' ? 'needs EPC membership' : 'being verified'}</a></li>`).join('');
    const eb = sb.early_bird || {};
    return `<div class="subbox"><b>💰 Subsidy / money back: ${esc(sb.headline)}</b>${sch ? `<ul>${sch}</ul>` : ''}<div class="ff">Early-bird / last date to book with discount: ${eb.deadline ? `<b>${eb.deadline}</b> (${eb.days_left} days)` : 'not published yet'} — ${esc(eb.note || '')}</div><div class="meta">Agent re-checks every 3 days · last checked ${esc(sb.last_checked || '—')} · next ${esc(sb.next_check || '')}${sb.notes ? ' · ' + esc(sb.notes) : ''}</div></div>`;
  };
  // ---------------------------------------------------------------- navigation + view styles
  function goToEvent(id) {
    const btn = $('.nav-btn[data-view="events"]'); if (btn) btn.click();
    const fm = $('#filterMode'); if (fm && fm.value) { fm.value = ''; renderEvents(); }
    setTimeout(() => { const el = document.getElementById('ev-' + id); if (!el) return; el.scrollIntoView({ behavior: 'smooth', block: 'start' }); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }, 60);
  }
  document.addEventListener('click', (e) => { const a = e.target.closest('.golink'); if (!a) return; e.preventDefault(); goToEvent(a.dataset.ev); });
  const evName = (id) => { const e = (state.catalog && state.catalog.events || []).find((x) => x.id === id); return e ? e.name : id; };
  const evLink = (id, text) => `<a class="golink" data-ev="${id}" href="#ev-${id}">${esc(text || evName(id))}</a>`;
  const VIEWS = {};
  const viewOf = (key, def) => { if (VIEWS[key]) return VIEWS[key]; try { VIEWS[key] = localStorage.getItem('sx.view.' + key) || def; } catch { VIEWS[key] = def; } return VIEWS[key]; };
  const viewBar = (key, opts, def) => { const cur = viewOf(key, def); return `<span class="views" data-key="${key}">${opts.map((o) => `<button type="button" class="${o === cur ? 'on' : ''}" data-v="${o}">${o}</button>`).join('')}</span>`; };
  const VIEW_RENDER = {};
  document.addEventListener('click', (e) => { const b = e.target.closest('.views button'); if (!b) return; const key = b.parentElement.dataset.key; VIEWS[key] = b.dataset.v; try { localStorage.setItem('sx.view.' + key, b.dataset.v); } catch {} if (VIEW_RENDER[key]) VIEW_RENDER[key](); });
  const kanban = (cols) => `<div class="kanban">${cols.map((c) => `<div class="kcol"><h4>${c.title} <span class="muted">(${c.items.length})</span></h4>${c.items.join('') || '<div class="muted">—</div>'}</div>`).join('')}</div>`;


  const linkify = (t) => esc(t).replace(/(https?:\/\/[^\s)]+)/g, (u) => `<a target="_blank" rel="noopener" href="${u}">${u.replace(/^https?:\/\//, '').slice(0, 48)}…</a>`);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const starStr = (s) => '★'.repeat(Math.floor(s)) + (s % 1 ? '½' : '') + '☆'.repeat(5 - Math.ceil(s));

  const state = { catalog: null, playbook: null, leads: [], collabs: [] };

  // ---------------------------------------------------------------- nav
  $$('#expoNav .nav-btn').forEach((b) => b.addEventListener('click', () => {
    $$('#expoNav .nav-btn').forEach((x) => x.classList.toggle('active', x === b));
    $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + b.dataset.view));
    if (b.dataset.view === 'funnel') { loadFunnel(); loadActuals(); }
    if (b.dataset.view === 'approvals') loadApprovals();
    if (b.dataset.view === 'travel') loadTravellers();
    if (b.dataset.view === 'finance') loadFinance();
    if (b.dataset.view === 'settings') loadSettings();
    if (b.dataset.view === 'stalls') loadFloorplan();
    if (b.dataset.view === 'leads') loadLeads();
    if (b.dataset.view === 'collab') loadCollabs();
  }));

  // ---------------------------------------------------------------- events
  async function loadCatalog() {
    state.catalog = await api('/api/expo/events');
    const evs = state.catalog.events;
    const exhibit = evs.filter((e) => e.mode === 'exhibit');
    const lo = evs.reduce((a, e) => a + e.evaluation.budget.total_inr[0], 0);
    const hi = evs.reduce((a, e) => a + e.evaluation.budget.total_inr[1], 0);
    const pilots = evs.reduce((a, e) => a + e.evaluation.funnel.paid_pilots[0], 0);
    const leads = evs.reduce((a, e) => a + e.lead_count, 0);
    $('#kpiRow').innerHTML = [
      ['Events tracked', evs.length], ['Exhibit / visit', `${exhibit.length} / ${evs.length - exhibit.length}`],
      ['5-star shows', evs.filter((e) => e.evaluation.stars >= 5).length],
      ['Budget, all shows', `${inr(lo)}–${inr(hi)}`], ['Expected paid pilots (low)', Math.round(pilots)],
      ['Leads captured so far', leads], ['Date clashes', state.catalog.clashes.length],
    ].map(([l, v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
    renderEvents();
    renderItinerary();
    renderTravel();
    const opts = evs.slice().sort((a, b) => a.start.localeCompare(b.start)).map((e) => `<option value="${e.id}">${esc(e.name)} (${e.start})</option>`).join('');
    ['#funnelEvent', '#leadEvent'].forEach((s) => ($(s).innerHTML += opts));
    $('#scanEvent').innerHTML = opts + '<option value="walk-in">Walk-in / other</option>';
  }

  function renderEvents() {
    const sort = $('#sortEvents').value, mode = $('#filterMode').value;
    let evs = state.catalog.events.filter((e) => !mode || e.mode === mode);
    if (sort === 'date') evs = evs.slice().sort((a, b) => a.start.localeCompare(b.start));
    if (sort === 'cost') evs = evs.slice().sort((a, b) => (a.evaluation.cost_per_expected_client_inr || 9e9) - (b.evaluation.cost_per_expected_client_inr || 9e9));
    VIEW_RENDER.events = renderEvents;
    const vb = $('#evViews'); if (vb) vb.innerHTML = viewBar('events', ['cards', 'list', 'kanban'], 'cards');
    const view = viewOf('events', 'cards');
    if (view !== 'cards') {
      const stage = (e) => { const p = e.plan || {}; if (p.stall_status === 'booked' || p.flight_status === 'booked') return 'Booked'; if (p.stall_status === 'enquired' || p.flight_status === 'searching' || p.hotel_status === 'searching') return 'In progress'; return 'Not started'; };
      const mini = (e) => `<div class="kcard">${evLink(e.id, e.name)}<b>${starStr(e.evaluation.stars)} ${e.evaluation.stars.toFixed(1)} · ${e.mode}</b><span class="muted">${e.start} · ${esc(e.city)}</span><br><span class="muted">${e.evaluation.lead_product === 'vision_ai' ? 'Vision AI' : e.evaluation.lead_product === 'both' ? 'both' : 'quote desk'} · clients ${e.evaluation.funnel.paid_pilots[0]}–${e.evaluation.funnel.paid_pilots[1]}</span>${e.plan && e.plan.stall_number ? `<br><span class="muted">stall ${esc(e.plan.stall_number)}</span>` : ''}</div>`;
      if (view === 'list') { $('#eventGrid').innerHTML = `<div class="tablewrap"><table class="fin"><thead><tr><th>Show</th><th>Dates</th><th>City</th><th>Mode</th><th>★</th><th>Lead with</th><th>Cost</th><th>Clients</th><th>Stall</th><th>Flights</th><th>Hotel</th><th>Leads</th></tr></thead><tbody>${evs.map((e) => { const ev = e.evaluation, p = e.plan || {}; return `<tr><td>${evLink(e.id, e.name)}</td><td>${e.start} → ${e.end}</td><td>${esc(e.city)}</td><td>${e.mode}</td><td>${ev.stars.toFixed(1)}</td><td>${ev.lead_product === 'vision_ai' ? 'Vision AI' : ev.lead_product === 'both' ? 'both' : 'quote desk'}</td><td>${Array.isArray(ev.budget.total_inr) ? inr(ev.budget.total_inr[0]) + ' – ' + inr(ev.budget.total_inr[1]) : inr(ev.budget.total_inr)}</td><td>${ev.funnel.paid_pilots[0]}–${ev.funnel.paid_pilots[1]}</td><td>${p.stall_status || '—'} ${esc(p.stall_number || '')}</td><td>${p.flight_status || '—'}</td><td>${p.hotel_status || '—'}</td><td>${e.lead_count || 0}</td></tr>`; }).join('')}</tbody></table></div>`; return; }
      $('#eventGrid').innerHTML = kanban(['Not started', 'In progress', 'Booked'].map((t) => ({ title: t, items: evs.filter((e) => stage(e) === t).sort((a, b) => a.start.localeCompare(b.start)).map(mini) }))); return;
    }
    $('#eventGrid').innerHTML = evs.map((e) => {
      const ev = e.evaluation, f = ev.funnel, b = ev.budget, p = e.plan;
      return `<div class="event-card s${Math.floor(ev.stars)}" data-id="${e.id}" id="ev-${e.id}">
        <div><span class="stars" title="${ev.total_score}/100">${starStr(ev.stars)}</span> <b>${ev.stars.toFixed(1)}</b>
          <span class="pill ${e.mode}">${e.mode}</span>${e.tentative ? '<span class="pill tentative">dates TBA</span>' : ''} <span class="pill" title="quote desk ${ev.quote_fit}/40 · Vision AI ${ev.vision_fit}/40">lead with: ${ev.lead_product === 'both' ? 'both products' : ev.lead_product === 'vision_ai' ? 'Vision AI' : 'WhatsApp quote desk'}</span></div>
        <h4>${esc(e.name)}</h4>
        <div class="meta">${e.start} → ${e.end} · ${esc(e.city)} · ${esc(e.venue)}</div>
        <div class="meta">${esc(e.category)} · ICP ${e.icp.join(', ')}</div>
        <div class="whybox"><b>${esc(ev.explain.headline)}</b><ul>${ev.explain.lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul><div class="ff">${esc(ev.explain.footfall_expected)}</div><div class="ff">${esc(ev.explain.reach)}</div></div>
        ${subsidyBox(e.subsidy_info)}
        <div class="bar-row"><span>Client probability</span><div class="bar"><i style="width:${f.client_probability_pct}%"></i></div><b>${f.client_probability_pct}%</b></div>
        <div class="meta">Leads ${f.leads[0]}–${f.leads[1]} · demos ${f.demos[0]}–${f.demos[1]} · paid pilots ${f.paid_pilots[0]}–${f.paid_pilots[1]}</div>
        <div class="meta">Budget ${inr(b.total_inr[0])}–${inr(b.total_inr[1])}${ev.cost_per_expected_client_inr ? ' · ' + inr(ev.cost_per_expected_client_inr) + ' per expected client' : ''}</div>
        <div><span class="pill ${p.stall_status}">stall: ${p.stall_status}</span><span class="pill ${p.flight_status}">flights: ${p.flight_status}</span><span class="pill ${p.hotel_status}">hotel: ${p.hotel_status}</span><span class="pill">${e.lead_count} leads</span></div>
        <div class="row-actions"><button class="btn secondary open-event">Details, stall &amp; booking</button><a class="btn ghost" target="_blank" href="${e.website}">Site</a></div>
      </div>`;
    }).join('');
    $$('.open-event').forEach((b) => b.addEventListener('click', () => openEvent(b.closest('.event-card').dataset.id)));
  }
  $('#sortEvents').addEventListener('change', renderEvents);
  $('#filterMode').addEventListener('change', renderEvents);

  async function openEvent(id) {
    const d = await api('/api/expo/events/' + id);
    const ev = d.evaluation, p = d.plan, tp = d.travel_plan, comp = ev.components;
    const sel = (name, val, opts) => `<select name="${name}">${opts.map((o) => `<option ${o === val ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
    const st = ['not_started', 'enquired', 'searching', 'booked', 'form_filled', 'confirmed'];
    $('#modalBox').innerHTML = `
      <h2>${esc(d.name)} <span class="stars">${starStr(ev.stars)}</span></h2>
      <p class="muted">${esc(d.why)}</p>
      <div class="grid2">
        <div><h3>Score breakdown (${ev.total_score}/100)</h3>${Object.entries(comp).map(([k, v]) => `<div class="score-row"><span>${k.replace(/_/g, ' ')}</span><div class="bar"><i style="width:${(100 * v.score) / v.max}%"></i></div><b>${v.score}/${v.max}</b></div>`).join('')}</div>
        <div><h3>Expected funnel (${ev.funnel.mode})</h3>
          <div class="meta">Leads ${ev.funnel.leads.join('–')} · qualified ${ev.funnel.qualified.join('–')} · demos ${ev.funnel.demos.join('–')} · paid pilots ${ev.funnel.paid_pilots.join('–')}</div>
          <div class="meta">If you ${ev.funnel_alt.mode} instead: leads ${ev.funnel_alt.leads.join('–')}, pilots ${ev.funnel_alt.paid_pilots.join('–')}</div>
          <h3>Budget</h3><div class="meta">Stall ${ev.budget.stall_sqm} sqm ${inr(ev.budget.stall_inr)} + fabrication ${inr(ev.budget.fabrication_inr)} · flights ${inr(ev.budget.flights_inr[0])}–${inr(ev.budget.flights_inr[1])} · hotel ${ev.budget.hotel_nights} nights ${inr(ev.budget.hotel_inr[0])}–${inr(ev.budget.hotel_inr[1])} (${esc(ev.budget.hotel_pick || 'home')}) · per diem ${inr(ev.budget.per_diem_inr)}</div>
          <div class="meta"><b>Total ${inr(ev.budget.total_inr[0])}–${inr(ev.budget.total_inr[1])}</b> · ${ev.budget.label}</div></div>
      </div>
      <h3>Stall</h3><div class="meta">${esc(d.stall.recommend)}<br/>${esc(d.stall.hall_hint)} · shell scheme ≈ ${inr(d.stall.shell_rate_inr_sqm)}/sqm</div>${d.exhibitor_contact ? `<h3>Book space with the organiser</h3><div class="meta">${esc(d.exhibitor_contact.org)} · ${d.exhibitor_contact.email ? `<a href="mailto:${d.exhibitor_contact.email}">${d.exhibitor_contact.email}</a>` : ''} ${esc(d.exhibitor_contact.phone)}<br/>${esc(d.exhibitor_contact.how)}</div>` : ''}
      <h3>Travel</h3>${tp.needs_travel ? `<div class="meta detail-links">Out ${tp.outbound.date} ${tp.outbound.route}: <a target="_blank" href="${tp.outbound.links.google_flights}">Google Flights</a><a target="_blank" href="${tp.outbound.links.makemytrip}">MakeMyTrip</a><a target="_blank" href="${tp.outbound.links.ixigo}">ixigo</a><br/>
        Return ${tp.return.date} ${tp.return.route}: <a target="_blank" href="${tp.return.links.google_flights}">Google Flights</a><a target="_blank" href="${tp.return.links.makemytrip}">MakeMyTrip</a><br/>
        Hotel ${tp.hotel.checkin} → ${tp.hotel.checkout} (${tp.hotel.nights} nights): <a target="_blank" href="${tp.hotel.links.google_hotels}">Google Hotels</a><a target="_blank" href="${tp.hotel.links.makemytrip}">MakeMyTrip</a>
        <ul>${tp.hotel.picks.map((h) => `<li>${esc(h.name)} · ${esc(h.area)} · ${h.tier} · ${inr(h.inr_night[0])}–${inr(h.inr_night[1])}/night · ${h.km_to_venue} km · ${esc(h.why)}</li>`).join('')}</ul></div>` : '<div class="meta">Home city: no flight or hotel.</div>'}
      <h3>Registration auto-fill</h3><div class="meta">Open the organiser's form, then run the bookmarklet (copied from Leads &amp; Cards) — or copy these answers:</div>
      <pre class="scan-result">${esc(Object.entries(d.registration_answers).map(([k, v]) => k + ': ' + v).join('\n'))}</pre>
      <form id="planForm"><h3>My plan for this event</h3><div class="grid2">
        <label>Decision ${sel('decision', p.decision, ['attend', 'exhibit', 'skip'])}</label>
        <label>Stall number <input name="stall_number" value="${esc(p.stall_number)}" placeholder="e.g. H9-01" /></label>
        <label>Hall <input name="hall" value="${esc(p.hall)}" /></label>
        <label>Team <input name="team" value="${esc(p.team)}" /></label>
        <label>Stall status ${sel('stall_status', p.stall_status, st)}</label>
        <label>Flight status ${sel('flight_status', p.flight_status, st)}</label>
        <label>Hotel status ${sel('hotel_status', p.hotel_status, st)}</label>
        <label>Registration ${sel('registration_status', p.registration_status, st)}</label>
        <label>Budget approved (INR) <input name="budget_approved_inr" type="number" value="${p.budget_approved_inr}" /></label>
        <label>Notes <textarea name="notes" rows="2">${esc(p.notes)}</textarea></label>
      </div><div class="row-actions"><button class="btn primary" type="submit">Save plan</button><button class="btn ghost" type="button" id="closeModal">Close</button></div></form>`;
    $('#modal').classList.remove('hidden');
    $('#closeModal').addEventListener('click', () => $('#modal').classList.add('hidden'));
    $('#planForm').addEventListener('submit', async (ev2) => {
      ev2.preventDefault();
      const body = Object.fromEntries(new FormData(ev2.target).entries());
      body.budget_approved_inr = Number(body.budget_approved_inr || 0);
      await api('/api/expo/plans/' + id, { method: 'PUT', body: JSON.stringify(body) });
      $('#modal').classList.add('hidden');
      loadCatalog();
    });
  }

  // ---------------------------------------------------------------- itinerary / travel
  function renderItinerary() {
    const c = state.catalog;
    $('#clashList').innerHTML = c.clashes.map((x) => `<span class="pill">${x.a} ↔ ${x.b} (${x.overlap_start}→${x.overlap_end})</span>`).join('') || '<span class="muted">No clashes</span>';
    $('#itinerary').innerHTML = c.itinerary.map((d) => `<div class="day ${d.travel_day_before ? 'travel' : ''}"><div class="d">${d.date} ${d.weekday}</div>${esc(d.event)}<div class="meta">${esc(d.city)}${d.travel_day_before ? ' · ✈ fly in the evening before' : ''}${d.also_running.length ? '<br/>also on: ' + d.also_running.join(', ') : ''}</div></div>`).join('');
  }
  function renderTravel() {
    const rows = state.catalog.events.slice().sort((a, b) => a.start.localeCompare(b.start)).map((e) => {
      const tp = e.travel_plan, p = e.plan;
      if (!tp.needs_travel) return `<tr><td>${e.start}</td><td>${esc(e.name)}</td><td colspan="4" class="muted">Home city (HITEX): no booking needed</td><td>stall: ${p.stall_status}</td></tr>`;
      return `<tr><td>${e.start}</td><td>${esc(e.name)}</td>
        <td>${tp.outbound.route}<br/>${tp.outbound.date} · <a target="_blank" href="${tp.outbound.links.google_flights}">search</a></td>
        <td>${tp.return.route}<br/>${tp.return.date} · <a target="_blank" href="${tp.return.links.google_flights}">search</a></td>
        <td>${esc(tp.hotel.picks[0] ? tp.hotel.picks[0].name : '—')}<br/>${tp.hotel.nights} nights · <a target="_blank" href="${tp.hotel.links.google_hotels}">search</a></td>
        <td>${inr(e.evaluation.budget.flights_inr[0])}–${inr(e.evaluation.budget.flights_inr[1])} flights<br/>${inr(e.evaluation.budget.hotel_inr[0])}–${inr(e.evaluation.budget.hotel_inr[1])} hotel</td>
        <td>flights: <span class="pill ${p.flight_status}">${p.flight_status}</span><br/>hotel: <span class="pill ${p.hotel_status}">${p.hotel_status}</span></td></tr>`;
    }).join('');
    $('#travelTable').innerHTML = `<table class="grid"><thead><tr><th>Date</th><th>Event</th><th>Outbound</th><th>Return</th><th>Hotel</th><th>Estimate (2 pax)</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ---------------------------------------------------------------- funnel
  async function loadFunnel() {
    const eid = $('#funnelEvent').value;
    const d = await api('/api/expo/dashboard' + (eid ? '?event_id=' + eid : ''));
    const order = state.playbook.lead_statuses;
    const max = Math.max(1, ...Object.values(d.by_status));
    $('#funnelBars').innerHTML = order.map((s) => `<div class="bar-row"><span>${s.label}</span><div class="bar"><i style="width:${(100 * (d.by_status[s.key] || 0)) / max}%"></i></div><b>${d.by_status[s.key] || 0}</b></div>`).join('') +
      `<div class="meta">Leads ${d.leads_generated} · clients met ${d.clients_met} · demos ${d.demos} · pilots ${d.pilots} · converted ${d.converted} (${d.conversion_rate_pct}%) · not converted ${d.not_converted} · left midway ${d.left_midway}</div>`;
    const rmax = Math.max(1, ...d.reasons.map((r) => r.count));
    $('#reasonBars').innerHTML = d.reasons.length ? d.reasons.map((r) => `<div class="bar-row"><span>${esc(r.reason)}</span><div class="bar"><i style="width:${(100 * r.count) / rmax};background:var(--critical)"></i></div><b>${r.count}</b></div>`).join('') : '<div class="muted">No drop-offs logged yet.</div>';
    const pmax = Math.max(1, ...d.leads_per_day.map((r) => r.count));
    $('#perDay').innerHTML = d.leads_per_day.length ? d.leads_per_day.map((r) => `<div class="bar-row"><span>${r.date}</span><div class="bar"><i style="width:${(100 * r.count) / pmax}%"></i></div><b>${r.count}</b></div>`).join('') : '<div class="muted">No leads yet.</div>';
    $('#expectedBox').innerHTML = d.expected ? `<div class="meta">Expected (${d.expected.mode}): leads ${d.expected.leads.join('–')} · qualified ${d.expected.qualified.join('–')} · demos ${d.expected.demos.join('–')} · paid pilots ${d.expected.paid_pilots.join('–')}</div>
      <div class="bar-row"><span>Leads vs expected (low)</span><div class="bar"><i style="width:${Math.min(100, (100 * d.leads_generated) / Math.max(1, d.expected.leads[0]))}%"></i></div><b>${d.leads_generated}/${d.expected.leads[0]}</b></div>
      <div class="bar-row"><span>Pilots+converted vs expected</span><div class="bar"><i style="width:${Math.min(100, (100 * (d.pilots + d.converted)) / Math.max(1, d.expected.paid_pilots[0]))}%"></i></div><b>${d.pilots + d.converted}/${d.expected.paid_pilots[0]}</b></div>` : '<div class="muted">Pick an event to compare against its forecast.</div>';
    $('#developments').innerHTML = d.developments.length ? `<table class="grid"><tbody>${d.developments.map((x) => `<tr><td>${(x.happened_at || '').slice(0, 16).replace('T', ' ')}</td><td>${x.kind}</td><td>${esc(x.summary)}</td><td>${x.outcome}</td></tr>`).join('')}</tbody></table>` : '<div class="muted">Log demos, calls and meetings from the lead row.</div>';
  }
  $('#refreshFunnel').addEventListener('click', loadFunnel);
  $('#funnelEvent').addEventListener('change', () => { loadFunnel(); loadActuals(); });

  // ---------------------------------------------------------------- leads & cards
  async function loadLeads() {
    const q = new URLSearchParams();
    if ($('#leadSearch').value) q.set('q', $('#leadSearch').value);
    if ($('#leadEvent').value) q.set('event_id', $('#leadEvent').value);
    if ($('#leadStatus').value) q.set('status', $('#leadStatus').value);
    state.leads = await api('/api/expo/leads?' + q.toString());
    const statuses = state.playbook.lead_statuses, reasons = state.playbook.drop_reasons;
    $('#leadTable').innerHTML = `<table class="grid"><thead><tr><th>When</th><th>Who</th><th>Company</th><th>Contact</th><th>Event</th><th>Score</th><th>Status</th><th>Reason</th><th></th></tr></thead><tbody>` +
      state.leads.map((l) => `<tr data-id="${l.id}"><td>${(l.created_at || '').slice(0, 10)}</td><td>${esc(l.name)}<br/><span class="muted">${esc(l.designation)}</span></td><td>${esc(l.company)}<br/><span class="muted">${esc(l.segment)} ${esc(l.industry)}</span></td>
        <td>${l.phone ? `<a href="https://wa.me/${l.phone.replace(/[^\d]/g, '')}" target="_blank">${esc(l.phone)}</a>` : ''}<br/>${esc(l.email)}</td><td>${esc(l.event_id)}</td>
        <td><input class="fit" type="number" min="0" max="50" value="${l.fit_score}" style="width:52px" /></td>
        <td><select class="status">${statuses.map((s) => `<option value="${s.key}" ${s.key === l.status ? 'selected' : ''}>${s.label}</option>`).join('')}</select></td>
        <td><select class="reason"><option value="">—</option>${reasons.map((r) => `<option ${r === l.reason ? 'selected' : ''}>${r}</option>`).join('')}</select></td>
        <td><button class="btn ghost log">+ log</button></td></tr>`).join('') + '</tbody></table>';
    $$('#leadTable tr[data-id]').forEach((tr) => {
      const id = tr.dataset.id;
      const save = async () => {
        try {
          await api('/api/expo/leads/' + id, { method: 'PATCH', body: JSON.stringify({ status: $('.status', tr).value, reason: $('.reason', tr).value, fit_score: Number($('.fit', tr).value) }) });
        } catch (e) { alert(e.message); loadLeads(); }
      };
      $('.status', tr).addEventListener('change', save); $('.reason', tr).addEventListener('change', save); $('.fit', tr).addEventListener('change', save);
      $('.log', tr).addEventListener('click', async () => {
        const summary = prompt('What happened? (meeting / demo / call / whatsapp)');
        if (!summary) return;
        const kind = (prompt('Kind: meeting, demo, call, whatsapp, email, followup', 'meeting') || 'meeting').toLowerCase();
        const outcome = (prompt('Outcome: positive / neutral / negative', 'positive') || '').toLowerCase();
        await api(`/api/expo/leads/${id}/interactions`, { method: 'POST', body: JSON.stringify({ kind, summary, outcome }) });
        alert('Logged.');
      });
    });
  }
  ['#leadSearch', '#leadEvent', '#leadStatus'].forEach((s) => $(s).addEventListener('change', loadLeads));
  $('#leadSearch').addEventListener('keyup', (e) => e.key === 'Enter' && loadLeads());

  $('#scanBtn').addEventListener('click', async () => {
    const eid = $('#scanEvent').value, file = $('#cardImage').files[0], text = $('#cardText').value.trim();
    if (!file && !text) return alert('Take a photo of the card or paste its text.');
    $('#scanStatus').textContent = 'Extracting…';
    try {
      let res;
      if (file) {
        const fd = new FormData(); fd.append('event_id', eid); fd.append('create_lead', 'true'); fd.append('image', file); if (text) fd.append('text', text);
        const r = await fetch('/api/expo/cards/scan', { method: 'POST', body: fd }); res = await r.json();
      } else {
        res = await api('/api/expo/cards/parse', { method: 'POST', body: JSON.stringify({ event_id: eid, text, create_lead: true }) });
      }
      $('#scanResult').classList.remove('hidden');
      $('#scanResult').textContent = JSON.stringify(res.extracted, null, 1);
      $('#scanStatus').textContent = res.lead ? `Saved lead #${res.lead.id} (${res.extracted.method}, confidence ${res.extracted.confidence})` : (res.extracted.hint || 'Nothing recognisable — type the card text.');
      $('#cardText').value = ''; $('#cardImage').value = '';
      loadLeads();
    } catch (e) { $('#scanStatus').textContent = 'Error: ' + e.message; }
  });

  $('#newLeadBtn').addEventListener('click', async () => {
    const name = prompt('Name'); if (!name) return;
    const company = prompt('Company') || ''; const phone = prompt('Phone') || '';
    await api('/api/expo/leads', { method: 'POST', body: JSON.stringify({ event_id: $('#leadEvent').value || $('#scanEvent').value, name, company, phone, source: 'manual' }) });
    loadLeads();
  });

  function renderQr() {
    const url = location.origin + '/expo/card?event=' + encodeURIComponent($('#scanEvent').value || 'walk-in');
    $('#qr').innerHTML = ''; $('#qrUrl').textContent = url;
    if (window.QRCode) new QRCode($('#qr'), { text: url, width: 160, height: 160 });
  }
  $('#scanEvent').addEventListener('change', renderQr);
  $('#copyBookmarklet').addEventListener('click', async () => {
    const js = await (await fetch('/api/expo/profile/autofill.js' + ($('#scanEvent').value && $('#scanEvent').value !== 'walk-in' ? '?event_id=' + $('#scanEvent').value : ''))).text();
    const bm = 'javascript:' + encodeURIComponent(js);
    try { await navigator.clipboard.writeText(bm); alert('Copied. Create a bookmark and paste this as its URL; click it on any organiser registration form to fill it.'); }
    catch { prompt('Copy this bookmarklet URL:', bm); }
  });

  // ---------------------------------------------------------------- collaborations
  async function loadCollabs() {
    state.collabs = await api('/api/expo/collaborations');
    const stages = ['idea', 'discussed', 'proposal_sent', 'agreed', 'dropped'];
    $('#collabTable').innerHTML = `<table class="grid"><thead><tr><th>Event</th><th>Partner</th><th>Company</th><th>Type</th><th>Stage</th><th>Value</th><th>Notes</th></tr></thead><tbody>` +
      state.collabs.map((c) => `<tr data-id="${c.id}"><td>${esc(c.event_id)}</td><td>${esc(c.partner)}</td><td>${esc(c.company)}</td><td>${esc(c.kind)}</td>
        <td><select class="stage">${stages.map((s) => `<option ${s === c.stage ? 'selected' : ''}>${s}</option>`).join('')}</select></td><td>${esc(c.value)}</td><td>${esc(c.notes)}</td></tr>`).join('') + '</tbody></table>';
    $$('#collabTable tr[data-id]').forEach((tr) => $('.stage', tr).addEventListener('change', () => api('/api/expo/collaborations/' + tr.dataset.id, { method: 'PATCH', body: JSON.stringify({ stage: $('.stage', tr).value }) })));
  }
  $('#newCollabBtn').addEventListener('click', async () => {
    const partner = prompt('Partner / person'); if (!partner) return;
    const company = prompt('Company') || '';
    const kind = prompt('Type: reseller, erp_consultant, bsp, association, integration, investor, co_marketing, other', 'reseller') || 'reseller';
    const event_id = prompt('Event id (e.g. elecrama-2027)', $('#scanEvent').value) || 'walk-in';
    await api('/api/expo/collaborations', { method: 'POST', body: JSON.stringify({ event_id, partner, company, kind }) });
    loadCollabs();
  });

  // ---------------------------------------------------------------- approvals
  async function loadTravellers() {
    const host = $('#travellersPanel'); if (!host) return;
    const st = await api('/api/expo/settings');
    const rows = (st.travellers && st.travellers.length) ? st.travellers : [{ given_name: 'Santosh', family_name: '', born_on: '', gender: 'm', phone_number: '+91 86393 32232', email: 'santoshdotai@gmail.com', loyalty: {} }, { given_name: '', family_name: '', born_on: '', gender: 'm', phone_number: '', email: '', loyalty: {} }];
    const air = [['6E', 'IndiGo BluChip'], ['AI', 'Air India Flying Returns'], ['QP', 'Akasa'], ['EK', 'Emirates Skywards'], ['FZ', 'flydubai OPEN'], ['G9', 'Air Arabia']];
    host.innerHTML = `<h3>Travellers & frequent-flyer numbers (asked once, saved for every booking)</h3><div class="hint">Used to pre-fill airline bookings and, in automate mode, to ticket via Duffel with your loyalty numbers. Passport fields are only needed for Gulf trips. Never enter card numbers or portal passwords here.</div>
      ${rows.map((t, i) => `<div class="trav" data-i="${i}"><b>Traveller ${i + 1}</b><div class="grid3">
        <label>First name <input name="given_name" value="${esc(t.given_name || '')}"></label><label>Last name <input name="family_name" value="${esc(t.family_name || '')}"></label><label>Date of birth <input name="born_on" type="date" value="${esc(t.born_on || '')}"></label>
        <label>Gender <select name="gender"><option value="m" ${t.gender === 'm' ? 'selected' : ''}>M</option><option value="f" ${t.gender === 'f' ? 'selected' : ''}>F</option></select></label><label>Phone <input name="phone_number" value="${esc(t.phone_number || '')}"></label><label>E-mail <input name="email" value="${esc(t.email || '')}"></label>
        <label>Passport no. <input name="passport_number" value="${esc(t.passport_number || '')}"></label><label>Passport expiry <input name="passport_expiry" type="date" value="${esc(t.passport_expiry || '')}"></label><label>Nationality <input name="nationality" value="${esc(t.nationality || 'IN')}"></label>
        ${air.map(([c, n]) => `<label>${n} # <input name="loyalty.${c}" value="${esc((t.loyalty || {})[c] || '')}"></label>`).join('')}</div></div>`).join('')}
      <button class="btn primary" id="saveTrav">Save travellers</button> <span class="hint" id="travMsg"></span>`;
    $('#saveTrav').onclick = async () => {
      const out = $$('#travellersPanel .trav').map((div) => { const o = { loyalty: {} }; $$('input,select', div).forEach((inp) => { if (inp.name.startsWith('loyalty.')) { if (inp.value) o.loyalty[inp.name.slice(8)] = inp.value; } else o[inp.name] = inp.value; }); return o; }).filter((o) => o.given_name);
      await api('/api/expo/settings/travellers', { method: 'PUT', body: JSON.stringify(out) }); $('#travMsg').textContent = `Saved ${out.length} traveller(s).`;
    };
  }
  // ---------------------------------------------------------------- finance
  const rng = (a, u = inr) => Array.isArray(a) ? `${u(a[0])} – ${u(a[1])}` : u(a);
  const usd = (n) => '$' + Number(n || 0).toLocaleString('en-US');
  const pct = (a) => Array.isArray(a) ? `${a[0] == null ? '—' : a[0] + '%'} – ${a[1] == null ? '—' : a[1] + '%'}` : (a == null ? '—' : a + '%');
  function finTable(rows, title) {
    if (!rows.length) return `<h3>${title}</h3><div class="muted">No ${title.toLowerCase()} start in this window.</div>`;
    return `<h3>${title} (${rows.length})</h3><div class="tablewrap"><table class="fin"><thead><tr><th>Show</th><th>Starts</th><th>★</th><th>Lead with</th><th>Total cost</th><th>Subsidy back</th><th>Leads</th><th>Pipeline worth</th><th>Conversions</th><th>Conv. %</th><th>Conversion worth ₹</th><th>Worth $</th><th>P&amp;L ₹</th><th>ROI</th><th>Best bets</th></tr></thead><tbody>
      ${rows.map((r) => `<tr class="${r.verdict === 'loss' ? 'loss' : ''}"><td><b>${evLink(r.id, r.name)}</b><br><span class="muted">${esc(r.city)}</span></td><td>${r.start}<br><span class="muted">${r.days_away} days</span></td><td>${r.stars.toFixed(1)}</td><td>${r.lead_product === 'both' ? 'both' : r.lead_product === 'vision_ai' ? 'Vision AI' : 'quote desk'}</td><td>${rng(r.cost_inr)}</td><td>${rng(r.subsidy_refund_inr)}</td><td>${r.leads[0]}–${r.leads[1]}</td><td>${rng(r.pipeline_inr)}</td><td>${r.conversions[0]}–${r.conversions[1]} clients</td><td>${r.conversion_pct}%<br><span class="muted">≥1 client: ${r.client_probability_pct}%</span></td><td>${rng(r.revenue_inr)}</td><td>${rng(r.revenue_usd, usd)}</td><td><b>${rng(r.pl_inr)}</b></td><td>${pct(r.roi_pct)}</td><td><span class="muted">${r.best_bets.segments.map((x) => esc(x.name)).join(' · ')}</span><br>${esc(r.best_bets.who)}</td></tr>`).join('')}
    </tbody></table></div>`;
  }
  function kpi(t, label) {
    return `<div class="fin-kpis"><b>${label}</b><span>${t.shows} shows</span><span>Cost ${rng(t.cost_inr)}</span><span>Subsidy back ${rng(t.subsidy_refund_inr)}</span><span>Leads ${t.leads[0]}–${t.leads[1]}</span><span>Pipeline ${rng(t.pipeline_inr)}</span><span>Conversions ${t.conversions[0]}–${t.conversions[1]} (${t.conversion_pct}%)</span><span>Revenue ${rng(t.revenue_inr)} / ${rng(t.revenue_usd, usd)}</span><span class="${t.pl_inr[0] < 0 ? 'bad' : 'good'}">P&amp;L ${rng(t.pl_inr)} / ${rng(t.pl_usd, usd)}</span><span>ROI ${pct(t.roi_pct)}</span></div>`;
  }
  function finBody(r) {
    const view = viewOf('finance', 'table'); const rows = (r.exhibits || []).concat(r.visits || []).sort((a, b) => a.start.localeCompare(b.start));
    const fcard = (x) => `<div class="kcard">${evLink(x.id, x.name)}<b>${rng(x.pl_inr)} P&amp;L</b><span class="muted">${x.start} · ${esc(x.city)} · ${x.mode} · ${x.stars.toFixed(1)}★</span><br><span class="muted">cost ${rng(x.cost_inr)} · ${x.leads[0]}–${x.leads[1]} leads · ${x.conversions[0]}–${x.conversions[1]} clients · ROI ${pct(x.roi_pct)}</span><br><span class="muted">best bets: ${x.best_bets.segments.map((z) => esc(z.name.split(':')[0])).join(', ')}</span></div>`;
    if (view === 'cards') return `<h3>Exhibits</h3><div class="kgrid">${(r.exhibits || []).map(fcard).join('') || '<div class="muted">none</div>'}</div><h3>Visits</h3><div class="kgrid">${(r.visits || []).map(fcard).join('') || '<div class="muted">none</div>'}</div>`;
    if (view === 'kanban') return kanban([['profit', 'Profit (even at the low case)'], ['profit at the high case', 'Profit only at the high case'], ['loss', 'Loss']].map(([k, t]) => ({ title: t, items: rows.filter((x) => x.verdict === k).map(fcard) })));
    if (view === 'timeline') { const months = {}; rows.forEach((x) => { const m = x.start.slice(0, 7); (months[m] = months[m] || []).push(x); }); return Object.entries(months).map(([m, xs]) => { const dt = new Date(m + '-01T00:00:00'); const c = [xs.reduce((a, x) => a + x.cost_inr[0], 0), xs.reduce((a, x) => a + x.cost_inr[1], 0)], p = [xs.reduce((a, x) => a + x.pl_inr[0], 0), xs.reduce((a, x) => a + x.pl_inr[1], 0)]; return `<div class="tl-row"><div><b>${dt.toLocaleString('en-IN', { month: 'short', year: 'numeric' })}</b><br><span class="muted">${xs.length} show(s)<br>cost ${rng(c)}<br>P&amp;L ${rng(p)}</span></div><div>${xs.map((x) => `<div>${x.start.slice(8)} · ${evLink(x.id, x.name)} <span class="muted">${x.mode} · P&amp;L ${rng(x.pl_inr)}</span></div>`).join('')}</div></div>`; }).join('') || '<div class="muted">No show starts in this window.</div>'; }
    return finTable(r.exhibits, 'Exhibits') + finTable(r.visits, 'Visits');
  }

  async function loadFinance() {
    const sel = $('#finHorizon'); const h = sel.value || '1m';
    const r = await api(`/api/expo/finance?horizon=${h}`);
    if (!sel.options.length) { r.horizons.forEach((x) => { const o = document.createElement('option'); o.value = x.key; o.textContent = x.label; sel.appendChild(o); }); sel.value = h; sel.onchange = loadFinance; }
    $('#finWindow').textContent = `${r.today} → ${r.window_end}. ${r.disclaimer}`;
    const a = r.assumptions;
    VIEW_RENDER.finance = loadFinance; const fv = $('#finViews'); if (fv) fv.innerHTML = viewBar('finance', ['table', 'cards', 'kanban', 'timeline'], 'table');
    $('#finance').innerHTML = kpi(r.totals.all, 'Everything') + kpi(r.totals.exhibits, 'Exhibits') + kpi(r.totals.visits, 'Visits')
      + `<div class="whybox"><b>Best bets in this window (by high-case P&amp;L)</b><ol>${r.best_bets.map((b) => `<li>${evLink(b.id, b.name)} — ${b.mode} · ${b.lead_product === 'vision_ai' ? 'Vision AI' : b.lead_product === 'both' ? 'both products' : 'quote desk'} · P&amp;L ${rng(b.pl_inr)} · ROI ${pct(b.roi_pct)}</li>`).join('')}</ol></div>`
      + finBody(r)
      + `<div class="meta">Assumptions (edit in data/expo/events.json → _meta.deal_economics): ${esc(a.quote_desk.label)} = ${inr(a.quote_desk.first_year_value_inr)} first year · ${esc(a.vision_ai.label)} = ${inr(a.vision_ai.first_year_value_inr)} first year · ${Math.round(a.lead_to_client_probability * 10000) / 100}% of captured leads become clients (${esc(a.lead_to_client_note || '')}) · USD at ₹${a.fx_inr_per_usd}. Subsidy shown is the best single scheme; P&amp;L uses cost net of subsidy.</div>`;
  }
  // ---------------------------------------------------------------- actuals (after the show) + voice
  async function loadActuals() {
    const host = $('#actualsPanel'); if (!host) return;
    const evId = $('#funnelEvent').value;
    const all = await api('/api/expo/actuals');
    const fx = all.calibration;
    const existing = evId ? all.items.find((x) => x.event_id === evId) : null;
    const segs = Object.entries(state.catalog.meta.icp_segments || {});
    const a = existing || {};
    host.innerHTML = `<h3>After the show: actual figures (the AI learns from these)</h3>
      <div class="hint">${esc(fx.note)}${fx.n_actuals ? ` Exhibit factors — leads ×${fx.by_mode.exhibit.leads.factor}, clients ×${fx.by_mode.exhibit.paid_pilots.factor}, cost ×${fx.by_mode.exhibit.cost.factor}; visit factors — leads ×${fx.by_mode.visit.leads.factor}, clients ×${fx.by_mode.visit.paid_pilots.factor}.` : ''}</div>
      ${evId ? `<div class="grid3">
        <label>Actual total cost (INR) <input name="actual_cost_inr" type="number" value="${a.actual_cost_inr || ''}"></label>
        <label>Footfall you saw / organiser closing figure <input name="footfall_visitors" type="number" value="${a.footfall_visitors || ''}"></label>
        <label>Leads captured (blank = cards scanned here) <input name="leads" type="number" value="${a.leads || ''}"></label>
        <label>Qualified <input name="qualified" type="number" value="${a.qualified || ''}"></label>
        <label>Demos <input name="demos" type="number" value="${a.demos || ''}"></label>
        <label>Paid pilots / clients won <input name="paid_pilots" type="number" value="${a.paid_pilots || ''}"></label>
        <label>Revenue won, first year (INR) <input name="revenue_inr" type="number" value="${a.revenue_inr || ''}"></label>
        <label>Subsidy received (INR) <input name="subsidy_received_inr" type="number" value="${a.subsidy_received_inr || ''}"></label>
        <label>Stall number <input name="stall_number" value="${esc(a.stall_number || '')}"></label>
        <label>Segments that actually converted <select name="best_segments" multiple size="4">${segs.map(([k, n]) => `<option value="${k}" ${(a.best_segments || []).includes(k) ? 'selected' : ''}>${k} — ${esc(n)}</option>`).join('')}</select></label>
        <label style="grid-column:1/-1">Notes (what worked, what did not, where the crowd was) <textarea name="notes" rows="2">${esc(a.notes || '')}</textarea></label>
      </div><button class="btn primary" id="saveActuals">Save actuals</button> <span class="hint" id="actMsg"></span>
      ${a.estimate ? `<div class="whybox" style="margin-top:8px"><b>Estimate vs actual</b><ul><li>Leads: estimated ${a.estimate.leads[0]}–${a.estimate.leads[1]}, actual ${a.leads} (×${a.variance.leads_ratio ?? '—'})</li><li>Clients: estimated ${a.estimate.paid_pilots[0]}–${a.estimate.paid_pilots[1]}, actual ${a.paid_pilots} (×${a.variance.pilots_ratio ?? '—'})</li><li>Cost: estimated ${inr(a.estimate.cost_inr[0])}–${inr(a.estimate.cost_inr[1])}, actual ${inr(a.actual_cost_inr)} (×${a.variance.cost_ratio ?? '—'})</li><li>Footfall: estimated ${a.estimate.footfall_visitors || '—'}, actual ${a.footfall_visitors || '—'}</li><li><b>Actual P&amp;L: ${inr(a.pl_actual_inr)}</b> (revenue + subsidy − cost)</li></ul></div>` : ''}`
      : `<div class="muted">Pick an event above to enter what really happened.</div>`}
      ${all.items.length ? `<h4>Recorded so far</h4><ul>${all.items.map((x) => `<li>${esc(x.event_name)}: ${x.leads} leads, ${x.paid_pilots} clients, cost ${inr(x.actual_cost_inr)}, P&amp;L ${inr(x.pl_actual_inr)}</li>`).join('')}</ul>` : ''}`;
    const sb = $('#saveActuals'); if (sb) sb.onclick = async () => {
      const body = {}; $$('#actualsPanel input,#actualsPanel textarea,#actualsPanel select').forEach((el) => { if (el.name === 'best_segments') body.best_segments = Array.from(el.selectedOptions).map((o) => o.value); else if (el.type === 'number') body[el.name] = Number(el.value || 0); else body[el.name] = el.value; });
      await api(`/api/expo/actuals/${evId}`, { method: 'PUT', body: JSON.stringify(body) }); $('#actMsg').textContent = 'Saved. Future estimates are now calibrated.'; loadActuals();
    };
  }
  function speak(text) { try { const u = new SpeechSynthesisUtterance(text); u.lang = 'en-IN'; speechSynthesis.cancel(); speechSynthesis.speak(u); } catch {} }
  async function runVoice(text) {
    $('#micSay').textContent = `“${text}” …`;
    try {
      const r = await api('/api/expo/voice', { method: 'POST', body: JSON.stringify({ text }) });
      $('#micSay').textContent = r.reply; speak(r.reply);
      if (r.open_url) window.open(r.open_url, '_blank', 'noopener');
      if (r.action === 'open_finance' || r.action === 'approve' || r.action === 'mark_done' || r.action === 'open_approvals') { const v = r.action === 'open_finance' ? 'finance' : 'approvals'; const btn = $(`.nav-btn[data-view="${v}"]`); if (btn) btn.click(); if (r.action === 'open_finance' && r.horizon) { const sel = $('#finHorizon'); if (sel) { sel.value = r.horizon; loadFinance(); } } }
    } catch (e) { $('#micSay').textContent = e.message; }
  }
  (() => {
    const btn = $('#micBtn'); if (!btn) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { btn.onclick = () => { const t = prompt('Voice is not available in this browser. Type the command instead:'); if (t) runVoice(t); }; return; }
    const rec = new SR(); rec.lang = 'en-IN'; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (e) => runVoice(e.results[0][0].transcript);
    rec.onerror = (e) => { $('#micSay').textContent = 'Mic error: ' + e.error; };
    rec.onend = () => btn.classList.remove('primary');
    btn.onclick = () => { btn.classList.add('primary'); $('#micSay').textContent = 'Listening…'; try { rec.start(); } catch (e) { $('#micSay').textContent = e.message; } };
  })();
  function renderModeSeg(d) {
    const m = d.payment_mode || 'manual';
    for (const id of ['#modeSeg', '#modeSegAp']) { const seg = $(id); if (!seg) continue; $$('button', seg).forEach((b) => { b.classList.toggle('on', b.dataset.m === m); b.onclick = async () => { if (b.dataset.m === m) return; if (!confirm(`Switch to ${b.dataset.m.toUpperCase()} mode?`)) return; await api('/api/expo/settings/payment-mode', { method: 'PUT', body: JSON.stringify({ mode: b.dataset.m }) }); loadSettings(); loadApprovals(); }; }); }
    const info = $('#modeInfo'); if (info) info.textContent = m === 'manual' ? 'Manual: you approve, then pay from the Souveno bank app or open the pre-filled Skyscanner / Booking.com link, book with the Souveno e-mail, and tap Done with the UTR / PNR / confirmation number.' : 'Automate: you approve; the agent books flights via Duffel with your saved frequent-flyer numbers when DUFFEL_ACCESS_TOKEN is set, otherwise opens the pre-filled Skyscanner / Booking.com link; then it reads the confirmation e-mail and marks the item Done. Nothing is charged without your Approve tap.';
  }
  async function loadSettings() {
    const st = await api('/api/expo/settings'); renderModeSeg(st);
    const c = $('#connections'); if (!c) return;
    const rows = [['Skyscanner', 'Flights: every flight proposal opens a Skyscanner round trip from Hyderabad, pre-filled with dates and 2 adults. No login needed; you pay on the airline site with the Souveno e-mail.', 'ready'],
      ['Booking.com', 'Hotels: every hotel proposal opens Booking.com pre-filled with the hotel, dates and 2 adults. No login stored; you pay on the site.', 'ready'],
      ['Gmail (Souveno inbox)', 'The 3-day routine reads e-tickets, Booking.com confirmations and organiser invoices and marks approvals Done.', 'routine'],
      ['Google Calendar', 'All shows, flights, booking and visa reminders are on the calendar; santoshdotai@gmail.com is invited to each.', 'connected'],
      ['Duffel (airline ticketing)', 'Lets AUTOMATE mode issue tickets with your frequent-flyer numbers. Needs DUFFEL_ACCESS_TOKEN.', st.connectors.duffel ? 'connected' : 'not connected'],
      ['RazorpayX payouts', 'Lets AUTOMATE mode pay stall advances by NEFT. Needs RAZORPAYX_* keys. Not needed in manual mode.', st.connectors.razorpayx ? 'connected' : 'not connected'],
      ['Frequent-flyer numbers', `${(st.travellers || []).length} traveller(s) saved in Travel & Booking.`, (st.travellers || []).length ? 'ready' : 'fill in Travel & Booking']];
    c.innerHTML = `<table class="conn">${rows.map(([n, d, x]) => `<tr><td><b>${n}</b></td><td class="muted">${d}</td><td><span class="pill ${x === 'ready' || x === 'connected' ? 'booked' : x === 'routine' ? 'searching' : ''}">${x}</span></td></tr>`).join('')}</table>`;
  }




  async function loadApprovals() {
    const d = await api('/api/expo/approvals');
    const r = d.rails;
    renderModeSeg(d);
    $('#railsInfo').textContent = d.payment_mode === 'manual'
      ? `Manual mode: the agent proposes, you approve, then you pay from the Souveno bank app or book on the airline/hotel site and tap Done with the UTR / PNR. No card or payout key is stored. · Flight policy: ${d.policy.flights}`
      : `Automate mode: Duffel ticketing ${r.duffel ? 'on' : 'off (no key: you get the Skyscanner link, agent reads the e-ticket e-mail)'} · RazorpayX payouts ${r.razorpayx ? 'on' : 'off'} · travellers saved ${d.travellers_saved || 0} · Flight policy: ${d.policy.flights}`;
    const pending = d.items.filter((i) => i.status === 'proposed').length;
    $('#apBadge').textContent = pending; $('#apBadge').classList.toggle('hidden', !pending);
    const evOf = (i) => state.catalog.events.find((e) => e.id === i.event_id) || null;
    const starStrOf = (e) => e ? `${starStr(e.evaluation.stars)} ${e.evaluation.stars.toFixed(1)}` : '';
    const stallVerdict = (e) => !e ? '' : (e.mode === 'exhibit' ? `<span class="pill exhibit">stall: YES — exhibit</span> ${esc(e.stall.recommend)}` : `<span class="pill visit">stall: NO — visit only</span> ${esc(e.stall.recommend)}`);
    const order = { proposed: 0, approved: 1, failed: 2, executed: 3, rejected: 4 };
    const sortMode = $('#apSort') ? $('#apSort').value : 'urgency';
    const urg = (i) => (i.kind === 'flight' && i.details.booking_window && i.details.booking_window.status !== 'ideal' && i.status === 'proposed') ? 0 : 1;
    const stars = (i) => { const e = evOf(i); return e ? e.evaluation.stars : 0; };
    const items = d.items.slice().sort((a, b) => order[a.status] - order[b.status] || (sortMode === 'priority' ? (stars(b) - stars(a)) : 0) || urg(a) - urg(b) || (a.deadline || '').localeCompare(b.deadline || ''));
    VIEW_RENDER.approvals = loadApprovals; const apv = $('#apViews'); if (apv) apv.innerHTML = viewBar('approvals', ['list', 'kanban'], 'list');
    const apCard = (i) => `<div class="ap ${i.status}" data-id="${i.id}">
        <div><div class="status muted">${i.status} · ${i.kind.replace('_', ' ')} · ${i.executor}${i.deadline ? ' · decide by ' + i.deadline.slice(0, 10) : ''}</div>
          <div><span class="stars" title="Souveno priority">${starStrOf(evOf(i))}</span> <span class="meta">priority for Souveno</span> · ${stallVerdict(evOf(i))}</div>
          <div class="amt">${inr(i.amount_inr)} <span class="muted" style="font-size:12px">to ${esc(i.payee)}</span></div>
          <div>${evLink(i.event_id, i.event_name)} · ${esc(i.title)}</div>
          <div class="meta">${i.kind === 'stall_advance' ? `${i.details.sqm} sqm × ${inr(i.details.rate_inr_sqm)} = ${inr(i.details.base_inr)} + 18% GST = ${inr(i.details.total_inr)} · advance 50% · balance ${inr(i.details.balance_inr)} · <i>${esc(i.details.rate_status || '')}</i>` : ''}
          ${i.kind === 'flight' ? `${i.details.origin} → ${i.details.destination} ${i.details.depart} / back ${i.details.return} · ${i.details.travellers} pax · ${esc(i.details.preference)} · <a target="_blank" href="${i.details.links.outbound.google_flights}">search</a>${i.details.booking_window ? `<br/><span class="pill ${i.details.booking_window.status === 'ideal' ? 'booked' : 'searching'}">${i.details.booking_window.status === 'ideal' ? (i.details.international ? '90-day' : '60-day') + ' window open' : i.details.booking_window.status === 'urgent' ? 'inside the window — book now' : 'past the hard deadline — book immediately'}${i.details.international ? ' · international' : ''}</span> ${esc(i.details.booking_window.advice)} · ${i.details.booking_window.days_to_departure} days to departure` : ''}` : ''}
          ${i.kind === 'visa' ? `${esc(i.details.visa_type)} · apply by ${i.details.apply_by} (${i.details.lead_days} working days) · ${esc(i.details.note)}<br/>Documents: ${i.details.documents.join(', ')}` : ''}
          ${i.kind === 'hotel' ? `${esc(i.details.hotel.name)} · ${i.details.checkin} → ${i.details.checkout} · ${inr(i.details.hotel.inr_night[0])}–${inr(i.details.hotel.inr_night[1])}/night · <a target="_blank" href="${i.details.links.google_hotels}">search</a>` : ''}</div>
          ${i.status === 'approved' && i.executor === 'manual' ? `<div class="steps"><b>Do this now, then tap Done:</b><ol>${(i.manual_steps || []).map((st) => `<li>${linkify(st)}</li>`).join('')}</ol><button class="btn ghost act" data-act="copyref" title="Copy the reference for the payment remarks">Copy reference ${esc(i.approval_uid)}</button></div>` : ''}
          ${i.status === 'executed' ? `<div class="meta">Done${i.execution.reference || i.execution.note ? ' · ref ' + esc(i.execution.reference || i.execution.note) : ''} · ${(i.executed_at || '').slice(0, 10)}</div>` : ''}
          ${i.status === 'failed' || (i.status === 'approved' && i.executor !== 'manual') ? `<div class="meta">${esc(i.execution.instruction || i.execution.reason || (i.execution.ok ? 'Executed ' + (i.execution.mode || '') : ''))}${i.execution.error ? ' · ' + esc(i.execution.error) : ''}</div>` : ''}
          ${i.notes ? `<div class="meta">Note: ${esc(i.notes)}</div>` : ''}
        </div>
        <div class="actions">
          ${i.status === 'proposed' ? `<button class="btn primary act" data-act="approve">Approve</button><button class="btn ghost act" data-act="edit">Edit amount</button><button class="btn ghost act" data-act="reject">Reject</button>` : ''}
          ${i.status === 'approved' ? `${i.executor !== 'manual' ? '<button class="btn secondary act" data-act="execute">Execute now</button>' : ''}<button class="btn primary act" data-act="done">Done (paid/booked)</button>` : ''}
          ${i.status === 'failed' ? `<button class="btn secondary act" data-act="approve">Retry</button><button class="btn primary act" data-act="done">Done manually</button>` : ''}
        </div></div>`;
    $('#approvalList').innerHTML = !items.length ? '<div class="muted">Nothing proposed yet. Tap "Propose bookings" or set an event to exhibit in its details.</div>' : viewOf('approvals', 'list') === 'kanban' ? kanban([['proposed', 'Waiting for your tap'], ['approved', 'Approved — to pay/book'], ['executed', 'Done'], ['failed', 'Failed'], ['rejected', 'Rejected']].map(([k, t]) => ({ title: t, items: d.items.filter((i) => i.status === k).map(apCard) }))) : items.map(apCard).join('');
    $$('#approvalList .act').forEach((b) => b.addEventListener('click', async () => {
      const id = b.closest('.ap').dataset.id, act = b.dataset.act;
      try {
        if (act === 'copyref') { const uid = b.textContent.replace('Copy reference ', '').trim(); try { await navigator.clipboard.writeText(uid); b.textContent = 'Copied ' + uid; } catch { prompt('Copy this reference', uid); } return; }
        if (act === 'approve') { if (!confirm('Approve this booking? Nothing is paid automatically: you get a step-by-step checklist to pay or book yourself, then tap Done.')) return; await api(`/api/expo/approvals/${id}/decide`, { method: 'POST', body: JSON.stringify({ decision: 'approve', execute: true }) }); }
        if (act === 'reject') { const notes = prompt('Reason (optional)') || ''; await api(`/api/expo/approvals/${id}/decide`, { method: 'POST', body: JSON.stringify({ decision: 'reject', notes }) }); }
        if (act === 'edit') { const v = prompt('Corrected amount in INR (from the organiser rate card / actual fare)'); if (!v) return; await api(`/api/expo/approvals/${id}`, { method: 'PATCH', body: JSON.stringify({ amount_inr: Number(v), details: { rate_status: 'corrected by you' } }) }); }
        if (act === 'execute') await api(`/api/expo/approvals/${id}/execute`, { method: 'POST' });
        if (act === 'done') { const ref = prompt('Reference (UTR for a payment, PNR for a flight, confirmation number for a hotel, visa number)'); if (ref === null) return; await api(`/api/expo/approvals/${id}/mark-done?reference=${encodeURIComponent(ref)}&note=${encodeURIComponent(ref)}`, { method: 'POST' }); }
      } catch (e) { alert(e.message); }
      loadApprovals(); loadCatalog();
    }));
  }
  $('#apSort').addEventListener('change', loadApprovals);
  $('#proposeBtn').addEventListener('click', async () => { const r = await api('/api/expo/approvals/propose?horizon_days=90', { method: 'POST' }); alert(`${r.created.length} new proposals`); loadApprovals(); });

  // ---------------------------------------------------------------- stall picker
  const fp = { img: null, marks: [], stalls: [] };
  function fpList(r, el) {
    el.innerHTML = `<div class="fp-list"><b>Ask the organiser for, in this order:</b><ol>${r.top.map((t) => `<li><span class="n">${esc(t.number)}</span> · ${t.score}/100 · ${t.pros.join(', ')}${t.cons.length ? ' · <span class="muted">but ' + t.cons.join(', ') + '</span>' : ''}</li>`).join('')}</ol>
      <b>Avoid:</b> ${r.avoid.map((t) => `<span class="n">${esc(t.number)}</span> (${t.score})`).join(', ')} <span class="muted">· ${r.stall_count} stalls scored · ${esc(r.note)}</span></div>`;
  }
  async function loadFloorplan() {
    if (!$('#fpEvent').options.length) {
      $('#fpEvent').innerHTML = state.catalog.events.slice().sort((a, b) => a.start.localeCompare(b.start)).map((e) => `<option value="${e.id}">${esc(e.name)} (${e.start})</option>`).join('');
      const first = state.catalog.events.find((e) => e.mode === 'exhibit'); if (first) $('#fpEvent').value = first.id;
    }
    try {
      const r = await api('/api/expo/floorplans/' + $('#fpEvent').value);
      $('#fpSvg').innerHTML = r.svg; fpList(r, $('#fpTop'));
    } catch (e) { $('#fpSvg').innerHTML = ''; $('#fpTop').innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
  }
  $('#fpEvent').addEventListener('change', loadFloorplan);
  const cv = $('#fpCanvas'), cx = cv.getContext('2d');
  function fpDraw() {
    cx.clearRect(0, 0, cv.width, cv.height);
    if (fp.img) cx.drawImage(fp.img, 0, 0, cv.width, cv.height); else { cx.fillStyle = '#1b2438'; cx.fillRect(0, 0, cv.width, cv.height); cx.fillStyle = '#8b96b3'; cx.font = '14px sans-serif'; cx.fillText('Load the organiser floor plan image, then click to mark', 20, 40); }
    const col = { entrance: '#25d366', registration: '#3ba7ff', food_court: '#f5a623', washroom: '#6c8fff', anchor: '#ff5b5b', noisy: '#c9a000', pillar: '#ffffff' };
    fp.marks.forEach((m) => { cx.fillStyle = col[m.kind]; cx.beginPath(); cx.arc(m.x, m.y, 6, 0, 7); cx.fill(); cx.fillStyle = '#fff'; cx.font = '11px sans-serif'; cx.fillText(m.kind === 'anchor' ? 'anchor ' + m.name : m.kind, m.x + 8, m.y + 4); });
    fp.stalls.forEach((s) => { cx.strokeStyle = '#3ba7ff'; cx.lineWidth = 2; cx.strokeRect(s.x - 10, s.y - 10, 20, 20); cx.fillStyle = '#3ba7ff'; cx.font = 'bold 11px sans-serif'; cx.fillText(s.number, s.x - 9, s.y - 13); });
  }
  fpDraw();
  $('#fpImage').addEventListener('change', () => { const f = $('#fpImage').files[0]; if (!f) return; const img = new Image(); img.onload = () => { cv.width = Math.min(900, img.width); cv.height = Math.round(cv.width * img.height / img.width); fp.img = img; fp.marks = []; fp.stalls = []; fpDraw(); }; img.src = URL.createObjectURL(f); });
  cv.addEventListener('click', (ev) => {
    const r = cv.getBoundingClientRect(); const x = (ev.clientX - r.left) * cv.width / r.width, y = (ev.clientY - r.top) * cv.height / r.height;
    const kind = $('#fpMarker').value;
    if (kind === 'stall') { const number = prompt('Stall number as printed on the plan'); if (!number) return; const open = Number(prompt('Open sides (1 inline, 2 corner, 3 peninsula)', '2') || 1); const main = confirm('Is it on the MAIN aisle from the entrance? OK = yes'); fp.stalls.push({ number, x, y, open_sides: open, on_main_aisle: main }); }
    else if (kind === 'anchor') { const name = prompt('Anchor exhibitor name') || 'anchor'; fp.marks.push({ kind, x, y, name }); }
    else fp.marks.push({ kind, x, y });
    fpDraw();
  });
  $('#fpUndo').addEventListener('click', () => { if (fp.stalls.length && (!fp.marks.length || fp.stalls.at(-1))) fp.stalls.pop(); else fp.marks.pop(); fpDraw(); });
  $('#fpClear').addEventListener('click', () => { fp.marks = []; fp.stalls = []; fpDraw(); });
  $('#fpScore').addEventListener('click', async () => {
    const pick = (k) => fp.marks.filter((m) => m.kind === k).map((m) => [m.x, cv.height - m.y]);
    const body = { name: 'organiser floor plan (' + $('#fpEvent').selectedOptions[0].text + ')', width: cv.width, height: cv.height, units: 'px',
      entrances: pick('entrance'), registration: pick('registration')[0] || null, food_court: pick('food_court'), washrooms: pick('washroom'),
      anchors: fp.marks.filter((m) => m.kind === 'anchor').map((m) => ({ name: m.name, x: m.x, y: cv.height - m.y })), noisy: pick('noisy'), pillars: pick('pillar'),
      stalls: fp.stalls.map((s) => ({ number: s.number, x: s.x - 10, y: cv.height - s.y - 10, w: 20, h: 20, open_sides: s.open_sides, on_main_aisle: s.on_main_aisle })) };
    try { const r = await api('/api/expo/floorplans/score', { method: 'POST', body: JSON.stringify(body) }); fpList(r, $('#fpCustom'));
      const best = r.top[0]; if (best && confirm(`Best stall on your plan: ${best.number} (${best.score}/100). Save it as the stall request for this event?`)) { await api('/api/expo/plans/' + $('#fpEvent').value, { method: 'PUT', body: JSON.stringify({ stall_number: best.number, stall_status: 'enquired' }) }); loadCatalog(); }
    } catch (e) { alert(e.message); }
  });

  // ---------------------------------------------------------------- playbook
  function renderPlaybook() {
    const p = state.playbook, li = (a) => a.map((x) => `<li>${esc(x)}</li>`).join('');
    $('#playbook').innerHTML = `
      <div class="panel"><h3>How to get clients (0 → 1)</h3>${p.how_to_get_clients.map((s) => `<h4>${s.step}</h4><ul>${li(s.items)}</ul>`).join('')}</div>
      <div class="panel"><h3>Which stall to book</h3><ul>${li(p.stall_selection.principles)}</ul><h4>Favourable stall numbers</h4><ul>${li(p.stall_selection.favourable_numbers)}</ul></div>
      <div class="panel"><h3>Where to stand / sit</h3><ul>${li(p.stall_selection.where_to_stand)}</ul><h4>Pre-event checklist</h4><ul>${li(p.checklist)}</ul></div>
      <div class="panel"><h3>Qualification scorecard (0-50)</h3><ul>${p.qualification_scorecard.map((q) => `<li>${esc(q.q)} <span class="muted">(0-${q.max})</span></li>`).join('')}</ul><div class="meta">35+ → book a demo on the spot · 25-34 → nurture · &lt;25 → not now.</div><h4>Drop-off reasons tracked</h4><ul>${li(p.drop_reasons)}</ul></div>`;
    $('#leadStatus').innerHTML += p.lead_statuses.map((s) => `<option value="${s.key}">${s.label}</option>`).join('');
  }

  (async function boot() {
    state.playbook = await api('/api/expo/playbook');
    renderPlaybook();
    await loadCatalog();
    renderQr();
    api('/api/expo/approvals').then((d) => { const n = d.items.filter((i) => i.status === 'proposed').length; $('#apBadge').textContent = n; $('#apBadge').classList.toggle('hidden', !n); }).catch(() => {});
  })().catch((e) => { document.body.insertAdjacentHTML('afterbegin', `<div class="panel card" style="margin:20px">Failed to load: ${esc(e.message)}</div>`); });
})();
