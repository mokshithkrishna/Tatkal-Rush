/**
 * TATKAL RUSH — Official Railway Reservation Application Logic
 * Concurrency-Safe Booking Engine, Max 3 Tickets Limit,
 * Backend-First Atomic Seat Claim, Dynamic Multi-Passenger Binding,
 * Official Digital E-Tickets, and Distributed Architecture Dashboard.
 */

// ── API Helpers ────────────────────────────────────────────────────────────
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, data };
  return data;
}

async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw { status: res.status, data };
  return data;
}

// ── Toast Alerts (Clean & Accessible) ──────────────────────────────────────
class Toast {
  constructor() {
    this.container = document.getElementById('toastContainer');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toastContainer';
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  }

  show(type, title, msg, duration = 4500) {
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const el = document.createElement('div');
    el.className = `toast ${type} fade-in`;
    el.innerHTML = `
      <span style="font-size:1.2rem;line-height:1;">${icons[type] || 'ℹ️'}</span>
      <div style="flex:1;">
        <div class="toast-title">${title}</div>
        ${msg ? `<div class="toast-msg">${msg}</div>` : ''}
      </div>
    `;
    this.container.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(20px)';
      el.style.transition = 'all 0.25s';
      setTimeout(() => el.remove(), 250);
    }, duration);
  }

  success(title, msg) { this.show('success', title, msg); }
  error(title, msg) { this.show('error', title, msg); }
  warning(title, msg) { this.show('warning', title, msg); }
  info(title, msg) { this.show('info', title, msg); }
}
const toast = new Toast();

// ── Real-time WebSocket Feed ───────────────────────────────────────────────
class LiveFeed {
  constructor(onMetrics, onSeatUpdate, onSimComplete) {
    this.onMetrics = onMetrics;
    this.onSeatUpdate = onSeatUpdate;
    this.onSimComplete = onSimComplete;
    this.ws = null;
    this.connect();
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'metrics' && this.onMetrics) this.onMetrics(msg.data);
        if (msg.type === 'seat_update' && this.onSeatUpdate) this.onSeatUpdate(msg);
        if (msg.type === 'simulation_complete' && this.onSimComplete) this.onSimComplete(msg.data);
      } catch (_) {}
    };

    this.ws.onclose = () => setTimeout(() => this.connect(), 2500);
    this.ws.onerror = () => this.ws && this.ws.close();
  }
}

// ── Coach B1 Seat Map Builder (Clean Light Railway Theme) ───────────────────
function renderCoachLayout(seats, containerId, selectedSeatsList, maxAllowed, onToggleSeat) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const seatMap = {};
  seats.forEach(s => { seatMap[s.seat_number] = s; });

  const bays = [
    {
      title: "BAY 1 — General Berths (Booked)",
      left: ["1A", "1B", "1C"],
      right: ["1D", "1E", "1F"],
      isTatkal: false,
    },
    {
      title: "BAY 2 — General Berths (Booked)",
      left: ["2A", "2B", "2C"],
      right: ["2D", "2E", "2F"],
      isTatkal: false,
    },
    {
      title: "BAY 3 — Tatkal Special Quota (Available for Booking)",
      left: ["12A", "12B", "12C"],
      right: ["12D", "12E"],
      isTatkal: true,
    }
  ];

  let html = `<div class="coach-roof">
    <div>
      <div class="coach-title">🚆 COACH B1 — AC 3-TIER (3A)</div>
      <div style="font-size:0.82rem;color:var(--text-muted);margin-top:2px;">
        Tatkal Special Quota &bull; Max 3 Berths per Booking
      </div>
    </div>
    <span class="coach-tag">${selectedSeatsList.length} / ${maxAllowed || 3} Selected</span>
  </div>
  <div class="coach-interior">`;

  // Render Bay 1 & Bay 2 (General Booked)
  html += renderBayHtml(bays[0], seatMap, selectedSeatsList);
  html += renderBayHtml(bays[1], seatMap, selectedSeatsList);

  // Render Bay 3 (Tatkal Quota: 12A, 12B, 12C | AISLE | 12D, 12E)
  html += `<div class="coach-bay" style="border: 2px solid #fdba74; background: #fffaf5;">
    <span class="bay-label" style="color:var(--secondary);border-color:#fdba74;font-weight:900;">⭐ BAY 3 — TATKAL SPECIAL QUOTA (12A, 12B, 12C, 12D, 12E)</span>
    <div style="margin-bottom:0.75rem;font-size:0.8rem;color:var(--text-muted);">
      ⚡ Authoritative Tatkal Inventory. Select up to 3 berths (e.g. 12A + 12C + 12E).
    </div>
    <div class="bay-grid" style="grid-template-columns: repeat(3, 1fr) 40px repeat(2, 1fr);">
      ${bays[2].left.map(sNum => renderSeatTile(seatMap[sNum] || { seat_number: sNum, status: 'AVAILABLE', berth_type: sNum === '12A' ? 'Lower' : (sNum === '12B' ? 'Middle' : 'Upper'), quota: 'Tatkal' }, selectedSeatsList)).join('')}
      <div class="aisle-gap">AISLE</div>
      ${bays[2].right.map(sNum => renderSeatTile(seatMap[sNum] || { seat_number: sNum, status: 'AVAILABLE', berth_type: sNum === '12D' ? 'Side Lower' : 'Side Upper', quota: 'Tatkal' }, selectedSeatsList)).join('')}
    </div>
  </div>`;

  html += `</div>
  <div class="seat-legend-bar">
    <div class="legend-pill"><div class="legend-dot dot-avail"></div> 🟢 Available (Tatkal)</div>
    <div class="legend-pill"><div class="legend-dot dot-selected"></div> 🔵 Selected (${selectedSeatsList.length}/${maxAllowed || 3})</div>
    <div class="legend-pill"><div class="legend-dot dot-held"></div> 🟠 Held (5-Min Lock)</div>
    <div class="legend-pill"><div class="legend-dot dot-booked"></div> ⚪ Booked (General)</div>
  </div>`;

  container.innerHTML = html;

  container.querySelectorAll('.seat-tile').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      const sNum = el.dataset.seat;
      const status = el.dataset.status;
      if (status === 'AVAILABLE' || selectedSeatsList.includes(sNum)) {
        if (onToggleSeat) onToggleSeat(sNum, seatMap[sNum] || { seat_number: sNum, status: 'AVAILABLE' });
      } else if (status === 'HELD') {
        toast.warning('Seat Held', `Seat ${sNum} is currently held by another user.`);
      } else if (status === 'BOOKED') {
        toast.info('Seat Booked', `Seat ${sNum} is already booked in general quota.`);
      }
    });
  });
}

function renderBayHtml(bay, seatMap, selectedSeatsList) {
  return `<div class="coach-bay">
    <span class="bay-label">${bay.title}</span>
    <div class="bay-grid" style="grid-template-columns: repeat(3, 1fr) 40px repeat(3, 1fr);">
      ${bay.left.map(sNum => renderSeatTile(seatMap[sNum] || { seat_number: sNum, status: 'BOOKED', berth_type: 'Berth', quota: 'General' }, selectedSeatsList)).join('')}
      <div class="aisle-gap">AISLE</div>
      ${bay.right.map(sNum => renderSeatTile(seatMap[sNum] || { seat_number: sNum, status: 'BOOKED', berth_type: 'Berth', quota: 'General' }, selectedSeatsList)).join('')}
    </div>
  </div>`;
}

function renderSeatTile(seat, selectedSeatsList) {
  const isSelected = selectedSeatsList.includes(seat.seat_number);
  const statusClass = isSelected ? 'selected' : (seat.status ? seat.status.toLowerCase() : 'available');
  const berth = seat.berth_type || 'Berth';

  return `
    <div class="seat-tile ${statusClass}" data-seat="${seat.seat_number}" data-status="${seat.status || 'AVAILABLE'}" title="Seat ${seat.seat_number} (${berth}) - ${isSelected ? 'SELECTED' : seat.status}">
      <span class="seat-tile-num">${seat.seat_number}</span>
      <span class="seat-tile-berth">${berth}</span>
      <span class="seat-tile-status">${isSelected ? 'SELECTED' : (seat.status || 'AVAILABLE')}</span>
    </div>
  `;
}

// ── Official Digital Railway E-Ticket Renderer ─────────────────────────────
function renderDigitalTicket(ticket, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const pnr = ticket.pnr || 'TR8264917352';
  const fareFormatted = typeof ticket.total_fare === 'number' ? ticket.total_fare.toLocaleString('en-IN') : '1,245';
  const passengers = ticket.passengers || [
    { index: 1, name: ticket.passenger_name || 'Demo Passenger', age: 28, gender: 'Male', coach: 'B1', seat_number: ticket.seat_number || '12A', fare: 1245 }
  ];

  container.innerHTML = `
    <div class="ticket-wrapper fade-in" id="printableTicket">
      <div class="ticket-header">
        <div class="ticket-logo">
          <span>🚆</span>
          <div>
            <div style="font-size:1.15rem;font-weight:900;letter-spacing:0.5px;">INDIAN RAILWAYS ELECTRONIC RESERVATION SLIP</div>
            <div style="font-size:0.75rem;color:#fcd34d;font-weight:700;">TATKAL RUSH CONCURRENCY ENGINE &bull; GOVT. OF INDIA DEMO</div>
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:0.7rem;color:rgba(255,255,255,0.8);font-weight:700;">PNR NUMBER</div>
          <div class="ticket-pnr-badge">${pnr}</div>
        </div>
      </div>

      <div class="ticket-body">
        <div class="ticket-route-box">
          <div class="station-box">
            <div class="ticket-station-time">${ticket.departure_time || '10:00 AM'}</div>
            <div class="ticket-station-name">${ticket.source || 'Chennai Central (MAS)'}</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:1.1rem;font-weight:900;color:var(--primary);">${ticket.train_number || '12608'} — ${ticket.train_name || 'LALBAGH SUPERFAST EXPRESS'}</div>
            <div style="font-size:0.85rem;color:var(--text-muted);font-weight:600;margin-top:2px;">📅 Journey Date: ${ticket.journey_date || '15 October 2026'}</div>
            <div style="font-size:0.75rem;color:var(--success-dark);font-weight:800;margin-top:2px;">
              CLASS: ${ticket.seat_class || '3A'} &bull; QUOTA: ${ticket.quota || 'TATKAL SPECIAL'}
            </div>
          </div>
          <div class="station-box">
            <div class="ticket-station-time">${ticket.arrival_time || '03:00 PM'}</div>
            <div class="ticket-station-name">${ticket.destination || 'KSR Bengaluru (SBC)'}</div>
          </div>
        </div>

        <h4 style="font-size:0.95rem;font-weight:900;color:var(--primary);margin-bottom:0.75rem;">
          PASSENGER &amp; SEAT ASSIGNMENTS (${passengers.length} Passenger${passengers.length > 1 ? 's' : ''})
        </h4>
        <div style="display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1.5rem;">
          ${passengers.map((p, idx) => `
            <div style="background:var(--surface2);border:1px solid var(--border-light);border-radius:6px;padding:0.75rem 1.25rem;display:grid;grid-template-columns:30px 2fr 1fr 1fr 1fr;align-items:center;font-size:0.85rem;">
              <span style="font-weight:900;color:var(--text-muted);">${p.index || idx + 1}</span>
              <div>
                <strong>${p.name}</strong>
                <div style="font-size:0.75rem;color:var(--text-muted);">${p.gender}, ${p.age} yrs</div>
              </div>
              <div>Coach: <strong style="color:var(--primary);">${p.coach || 'B1'}</strong></div>
              <div>Berth: <strong style="font-size:1.15rem;color:var(--secondary);font-family:var(--mono);">${p.seat_number}</strong></div>
              <div style="text-align:right;">
                <span class="avail-chip avail-green" style="font-size:0.7rem;padding:0.2rem 0.55rem;">CONFIRMED ✓</span>
              </div>
            </div>
          `).join('')}
        </div>

        <div class="ticket-bottom-bar">
          <div style="display:flex;align-items:center;gap:1.25rem;">
            <div class="ticket-qr">
              <svg viewBox="0 0 100 100" width="100%" height="100%">
                <rect width="100" height="100" fill="#fff" />
                <path d="M10,10 h30 v30 h-30 z M15,15 v20 h20 v-20 z M20,20 h10 v10 h-10 z" fill="#0f3460" />
                <path d="M60,10 h30 v30 h-30 z M65,15 v20 h20 v-20 z M70,20 h10 v10 h-10 z" fill="#0f3460" />
                <path d="M10,60 h30 v30 h-30 z M15,65 v20 h20 v-20 z M20,70 h10 v10 h-10 z" fill="#0f3460" />
                <rect x="45" y="10" width="8" height="30" fill="#0f3460" />
                <rect x="45" y="55" width="45" height="8" fill="#0f3460" />
                <rect x="60" y="70" width="15" height="20" fill="#0f3460" />
                <rect x="80" y="80" width="10" height="10" fill="#0f3460" />
              </svg>
            </div>
            <div>
              <div style="font-size:0.85rem;font-weight:800;color:var(--primary);">TOTAL FARE: ₹${fareFormatted} (${ticket.payment_status || 'PAID'} &bull; ${ticket.payment_method || 'UPI'})</div>
              <div style="font-size:0.75rem;color:var(--text-muted);margin-top:2px;">Transaction Reference: <code>${ticket.payment_ref || 'PAY92841029'}</code></div>
              <div style="font-size:0.75rem;color:var(--text-muted);">Timestamp: <strong>${ticket.booking_time || '10:00:00 AM'}</strong> &bull; Zero Double Booking Verified</div>
            </div>
          </div>
          <div class="ticket-status-stamp">CONFIRMED ✓</div>
        </div>
      </div>
    </div>

    <div style="display:flex;gap:1rem;justify-content:center;margin-top:1.5rem;flex-wrap:wrap;">
      <button type="button" class="btn btn-primary btn-lg" onclick="window.print()">🖨️ PRINT TICKET</button>
      <button type="button" class="btn btn-success btn-lg" onclick="downloadTicketHtml('${pnr}')">📥 DOWNLOAD TICKET (HTML)</button>
      <a href="/booking" class="btn btn-outline btn-lg">📋 VIEW MY BOOKINGS</a>
    </div>
  `;
}

function downloadTicketHtml(pnr) {
  const el = document.getElementById('printableTicket');
  if (!el) return;
  const content = `<!DOCTYPE html><html><head><title>Railway_Ticket_${pnr}</title><link rel="stylesheet" href="/static/styles.css"></head><body style="padding:2rem;background:#fff;">${el.outerHTML}</body></html>`;
  const blob = new Blob([content], { type: 'text/html' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `Railway_Ticket_${pnr}.html`;
  a.click();
  toast.success('Ticket Downloaded', `Official Ticket ${pnr} saved.`);
}

function formatCountdown(secs) {
  const m = Math.floor(secs / 60).toString().padStart(2, '0');
  const s = (secs % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

// ── Station Autocomplete Helper ────────────────────────────────────────────
function initStationAutocomplete(inputElId, dropdownElId, onSelect) {
  const input = document.getElementById(inputElId);
  const dropdown = document.getElementById(dropdownElId);
  if (!input || !dropdown) return;

  let debounceTimer = null;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length === 0) {
      dropdown.classList.remove('active');
      dropdown.innerHTML = '';
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const res = await apiGet(`/api/stations?q=${encodeURIComponent(q)}`);
        const stations = res.stations || [];
        if (stations.length === 0) {
          dropdown.innerHTML = `<div style="padding:0.75rem 1rem;color:var(--text-muted);font-size:0.85rem;">No matching railway stations found</div>`;
          dropdown.classList.add('active');
          return;
        }

        dropdown.innerHTML = stations.map(s => `
          <div class="autocomplete-item" data-display="${s.name} (${s.code})" data-code="${s.code}" data-name="${s.name}">
            <div>
              <div style="font-weight:700;font-size:0.9rem;color:var(--text);">${s.name}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${s.city}, ${s.state}</div>
            </div>
            <span class="autocomplete-code">${s.code}</span>
          </div>
        `).join('');
        dropdown.classList.add('active');

        dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
          item.addEventListener('click', (e) => {
            e.preventDefault();
            const displayVal = item.dataset.display;
            input.value = displayVal;
            dropdown.classList.remove('active');
            if (onSelect) onSelect(displayVal, item.dataset.code, item.dataset.name);
          });
        });
      } catch (_) {
        dropdown.classList.remove('active');
      }
    }, 180);
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.remove('active');
    }
  });
}

// ── Train Details Modal Renderer (5 Tabs) ──────────────────────────────────
function renderTrainDetailsModal(details, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const schedule = details.schedule || [];
  const classes = details.classes || [];
  const tatkal = details.tatkal_stats || { available: 5, held: 0, booked: 0, total: 5 };

  container.innerHTML = `
    <div style="background:#fff;border-radius:12px;padding:2rem;box-shadow:var(--shadow-lg);border:1px solid var(--border-light);max-width:850px;margin:0 auto;" class="fade-in">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem;border-bottom:1.5px solid var(--border-light);padding-bottom:1rem;">
        <div>
          <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
            <span style="font-size:1.4rem;font-weight:900;color:var(--primary);font-family:var(--mono);">${details.train_number}</span>
            <span style="font-size:1.3rem;font-weight:800;color:var(--text);">${details.name}</span>
            <span class="train-type-badge">${details.train_type}</span>
          </div>
          <div style="font-size:0.85rem;color:var(--text-muted);margin-top:4px;">
            ${details.source} (${details.source_code}) → ${details.destination} (${details.destination_code}) &bull; Distance: <strong>${details.distance_km} km</strong> &bull; Duration: <strong>${details.duration}</strong>
          </div>
        </div>
        <button type="button" class="btn btn-outline" style="padding:0.35rem 0.85rem;font-size:0.85rem;" onclick="closeTrainDetailsModal()">✕ Close</button>
      </div>

      <!-- Navigation Tabs -->
      <div class="modal-tabs" id="trainModalTabs">
        <div class="modal-tab active" onclick="switchTrainModalTab('tabSchedule', this, event)">📅 Schedule &amp; Halts</div>
        <div class="modal-tab" onclick="switchTrainModalTab('tabClasses', this, event)">🛋️ Classes &amp; Fares</div>
        <div class="modal-tab" onclick="switchTrainModalTab('tabSeatAvail', this, event)">🟢 Live Availability</div>
        <div class="modal-tab" onclick="switchTrainModalTab('tabFare', this, event)">💳 Fare Breakdown</div>
        <div class="modal-tab" onclick="switchTrainModalTab('tabRoute', this, event)">🗺️ Route Timeline</div>
      </div>

      <!-- Tab: Schedule -->
      <div id="tabSchedule" class="tab-pane active fade-in">
        <div style="margin-bottom:0.75rem;font-size:0.82rem;color:var(--text-muted);">
          <strong>Running Days:</strong> ${details.running_days} &bull; <strong>Coach Composition:</strong> <code style="font-size:0.75rem;background:var(--surface2);padding:2px 6px;border-radius:4px;">${details.coach_composition}</code>
        </div>
        <div style="max-height:300px;overflow-y:auto;border:1px solid var(--border-light);border-radius:8px;">
          <table style="width:100%;border-collapse:collapse;font-size:0.85rem;text-align:left;">
            <thead>
              <tr style="background:var(--surface2);border-bottom:1.5px solid var(--border-light);">
                <th style="padding:0.6rem 0.85rem;">#</th>
                <th style="padding:0.6rem 0.85rem;">Station Name</th>
                <th style="padding:0.6rem 0.85rem;">Code</th>
                <th style="padding:0.6rem 0.85rem;">Arrival</th>
                <th style="padding:0.6rem 0.85rem;">Departure</th>
                <th style="padding:0.6rem 0.85rem;">Halt</th>
                <th style="padding:0.6rem 0.85rem;">Distance</th>
              </tr>
            </thead>
            <tbody>
              ${schedule.map(s => `
                <tr style="border-bottom:1px solid var(--border-light);">
                  <td style="padding:0.6rem 0.85rem;font-weight:700;color:var(--text-muted);">${s.stop_number}</td>
                  <td style="padding:0.6rem 0.85rem;font-weight:700;">${s.station_name}</td>
                  <td style="padding:0.6rem 0.85rem;"><span class="autocomplete-code">${s.station_code}</span></td>
                  <td style="padding:0.6rem 0.85rem;">${s.arrival_time}</td>
                  <td style="padding:0.6rem 0.85rem;">${s.departure_time}</td>
                  <td style="padding:0.6rem 0.85rem;">${s.halt_duration_min > 0 ? `${s.halt_duration_min} min` : '--'}</td>
                  <td style="padding:0.6rem 0.85rem;">${s.distance_km} km</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab: Classes -->
      <div id="tabClasses" class="tab-pane fade-in" style="display:none;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:1rem;">
          ${classes.map(c => `
            <div style="background:var(--surface2);border:1.5px solid var(--border-light);border-radius:10px;padding:1rem;text-align:center;">
              <div style="font-size:1.2rem;font-weight:900;color:var(--primary);">${c.class_code}</div>
              <div style="font-size:0.8rem;color:var(--text-muted);">${c.class_name}</div>
              <div style="font-size:1.3rem;font-weight:900;color:var(--secondary);margin:0.5rem 0;">₹${c.fare}</div>
              <span class="avail-chip ${c.tatkal_available > 0 ? 'avail-green' : 'avail-red'}" style="font-size:0.75rem;">
                ${c.tatkal_available > 0 ? `🟢 ${c.tatkal_available} Seats` : '🔴 WL'}
              </span>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Tab: Seat Availability -->
      <div id="tabSeatAvail" class="tab-pane fade-in" style="display:none;">
        <div style="background:var(--surface2);border-radius:10px;padding:1.25rem;border:1px solid var(--border-light);margin-bottom:1rem;">
          <h4 style="font-weight:800;color:var(--primary);margin-bottom:0.5rem;">Coach B1 — Tatkal Quota Real-Time Status</h4>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(140px, 1fr));gap:1rem;text-align:center;">
            <div style="background:#fff;padding:0.75rem;border-radius:8px;border:1px solid var(--border-light);">
              <div style="font-size:1.6rem;font-weight:900;color:var(--success-dark);">${tatkal.available}</div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);">AVAILABLE</div>
            </div>
            <div style="background:#fff;padding:0.75rem;border-radius:8px;border:1px solid var(--border-light);">
              <div style="font-size:1.6rem;font-weight:900;color:var(--accent);">${tatkal.held}</div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);">HELD (5-MIN LOCK)</div>
            </div>
            <div style="background:#fff;padding:0.75rem;border-radius:8px;border:1px solid var(--border-light);">
              <div style="font-size:1.6rem;font-weight:900;color:var(--text-muted);">${tatkal.booked}</div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);">BOOKED</div>
            </div>
          </div>
        </div>
        <p style="font-size:0.82rem;color:var(--text-muted);">
          ⚡ Tatkal Special Quota seats (12A, 12B, 12C, 12D, 12E) in Coach B1 are atomically allocated with zero double booking guarantees.
        </p>
      </div>

      <!-- Tab: Fare -->
      <div id="tabFare" class="tab-pane fade-in" style="display:none;">
        <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
          <thead>
            <tr style="background:var(--surface2);border-bottom:1px solid var(--border-light);">
              <th style="padding:0.6rem;">Class</th>
              <th style="padding:0.6rem;">Base Fare</th>
              <th style="padding:0.6rem;">Tatkal Charge</th>
              <th style="padding:0.6rem;">Total Amount</th>
            </tr>
          </thead>
          <tbody>
            ${classes.map(c => `
              <tr style="border-bottom:1px solid var(--border-light);text-align:center;">
                <td style="padding:0.6rem;font-weight:800;color:var(--primary);">${c.class_code} (${c.class_name})</td>
                <td style="padding:0.6rem;">₹${Math.round(c.fare * 0.85)}</td>
                <td style="padding:0.6rem;">₹${Math.round(c.fare * 0.15)}</td>
                <td style="padding:0.6rem;font-weight:900;color:var(--secondary);">₹${c.fare}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <!-- Tab: Route Timeline -->
      <div id="tabRoute" class="tab-pane fade-in" style="display:none;">
        <div class="timeline-container">
          ${schedule.map((s, idx) => `
            <div class="timeline-stop ${idx === 0 ? 'first' : (idx === schedule.length - 1 ? 'last' : '')}">
              <div class="timeline-dot"></div>
              <div style="display:flex;justify-content:space-between;width:100%;align-items:center;background:var(--surface2);padding:0.6rem 1rem;border-radius:8px;border:1px solid var(--border-light);">
                <div>
                  <div style="font-weight:800;color:var(--primary);font-size:0.95rem;">${s.station_name} (${s.station_code})</div>
                  <div style="font-size:0.75rem;color:var(--text-muted);">${s.distance_km} km from source &bull; Day ${s.day_number}</div>
                </div>
                <div style="text-align:right;">
                  <div style="font-weight:800;color:var(--text);font-family:var(--mono);">${s.arrival_time !== '--' ? `Arr: ${s.arrival_time}` : 'Starts'}</div>
                  <div style="font-size:0.75rem;color:var(--secondary);font-family:var(--mono);">${s.departure_time !== '--' ? `Dep: ${s.departure_time}` : 'Terminates'}</div>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>

      <div style="margin-top:1.5rem;display:flex;justify-content:flex-end;gap:1rem;">
        <button type="button" class="btn btn-outline" onclick="closeTrainDetailsModal()">Close Window</button>
        <button type="button" class="btn btn-accent" onclick="selectTrainAndCloseModal(${details.id})">SELECT THIS TRAIN →</button>
      </div>
    </div>
  `;
}

function switchTrainModalTab(tabId, el, e) {
  if (e) {
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (typeof e.stopPropagation === 'function') e.stopPropagation();
  }
  document.querySelectorAll('#trainModalTabs .modal-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => { p.style.display = 'none'; p.classList.remove('active'); });

  el.classList.add('active');
  const target = document.getElementById(tabId);
  if (target) {
    target.style.display = 'block';
    target.classList.add('active');
  }
}

// ── Auth Navigation State Handler ──────────────────────────────────────────
function initAuthNav() {
  const userJson = localStorage.getItem('tatkal_user');
  const navContainer = document.querySelector('.nav');
  if (!navContainer) return;

  let authItem = document.getElementById('navAuthItem');
  if (!authItem) {
    authItem = document.createElement('div');
    authItem.id = 'navAuthItem';
    navContainer.appendChild(authItem);
  }

  if (userJson) {
    try {
      const user = JSON.parse(userJson);
      authItem.innerHTML = `
        <span class="user-badge-nav">
          👤 ${user.username || 'demo_user'}
        </span>
        <button type="button" onclick="logoutUser()" class="btn-logout-nav">
          Logout
        </button>
      `;
    } catch (_) {
      authItem.innerHTML = `<a href="/login" class="btn btn-outline" style="padding:0.35rem 0.75rem;font-size:0.8rem;">🔑 Login</a>`;
    }
  } else {
    authItem.innerHTML = `<a href="/login" class="btn btn-outline" style="padding:0.35rem 0.75rem;font-size:0.8rem;">🔑 Login</a>`;
  }
}

function logoutUser() {
  localStorage.removeItem('tatkal_token');
  localStorage.removeItem('tatkal_user');
  toast.info('Logged Out', 'You have been logged out.');
  setTimeout(() => { window.location.href = '/login'; }, 400);
}

document.addEventListener('DOMContentLoaded', () => {
  initAuthNav();
});
