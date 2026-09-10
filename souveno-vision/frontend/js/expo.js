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
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const starStr = (s) => '★'.repeat(Math.floor(s)) + (s % 1 ? '½' : '') + '☆'.repeat(5 - Math.ceil(s));

  const state = { catalog: null, playbook: null, leads: [], collabs: [] };

  // ---------------------------------------------------------------- nav
  $$('#expoNav .nav-btn').forEach((b) => b.addEventListener('click', () => {
    $$('#expoNav .nav-btn').forEach((x) => x.classList.toggle('active', x === b));
    $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + b.dataset.view));
    if (b.dataset.view === 'funnel') loadFunnel();
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
    $('#eventGrid').innerHTML = evs.map((e) => {
      const ev = e.evaluation, f = ev.funnel, b = ev.budget, p = e.plan;
      return `<div class="event-card s${Math.floor(ev.stars)}" data-id="${e.id}">
        <div><span class="stars" title="${ev.total_score}/100">${starStr(ev.stars)}</span> <b>${ev.stars.toFixed(1)}</b>
          <span class="pill ${e.mode}">${e.mode}</span>${e.tentative ? '<span class="pill tentative">dates TBA</span>' : ''}</div>
        <h4>${esc(e.name)}</h4>
        <div class="meta">${e.start} → ${e.end} · ${esc(e.city)} · ${esc(e.venue)}</div>
        <div class="meta">${esc(e.category)} · ICP ${e.icp.join(', ')}</div>
        <div class="meta">Footfall (prev): ${e.footfall_history[0].visitors.toLocaleString('en-IN')} visitors · ${e.footfall_history[0].exhibitors} exhibitors</div>
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
  $('#funnelEvent').addEventListener('change', loadFunnel);

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
  })().catch((e) => { document.body.insertAdjacentHTML('afterbegin', `<div class="panel card" style="margin:20px">Failed to load: ${esc(e.message)}</div>`); });
})();
