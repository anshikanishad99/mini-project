const $ = s => document.querySelector(s);
let map, marker, pos = null, timer = null;

function getPos() {
  return new Promise(res => {
    if (!navigator.geolocation) return res(null);
    navigator.geolocation.getCurrentPosition(
      p => res({ lat: p.coords.latitude, lng: p.coords.longitude }), () => res(null),
      { enableHighAccuracy: true, timeout: 8000 });
  });
}

async function refreshLocation() {
  pos = await getPos();
  if (pos) {
    $('#loc').textContent = `Live location: ${pos.lat.toFixed(5)}, ${pos.lng.toFixed(5)}`;
    $('#hosp-link').href = `https://www.google.com/maps/search/hospitals/@${pos.lat},${pos.lng},14z`;
    showOnMap();
  } else {
    $('#loc').textContent = 'Location unavailable - please allow location access in your browser.';
  }
}

// Google Maps callback (script tag only loads when an API key is configured)
window.initMap = function () {
  map = new google.maps.Map($('#map'), { center: { lat: 28.6692, lng: 77.4538 }, zoom: 13 });
  showOnMap();
};

function showOnMap() {
  if (!map || !pos) return;
  map.setCenter(pos); map.setZoom(14);
  if (marker) marker.setMap(null);
  marker = new google.maps.Marker({ position: pos, map, title: 'You are here' });
  try {   // nearby hospitals via Places (needs Places API enabled on the key)
    new google.maps.places.PlacesService(map).nearbySearch(
      { location: pos, radius: 5000, type: 'hospital' }, (results, status) => {
        const ul = $('#hospitals'); ul.innerHTML = '';
        if (status !== 'OK' || !results) return;
        results.slice(0, 5).forEach(h => {
          new google.maps.Marker({ position: h.geometry.location, map, title: h.name });
          const li = document.createElement('li'); li.textContent = '🏥 ' + h.name; ul.appendChild(li);
        });
      });
  } catch (e) { console.warn('Places unavailable', e); }
}

async function sendSOS(reason) {
  await refreshLocation();
  const r = await fetch('/api/sos', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat: pos && pos.lat, lng: pos && pos.lng, reason }) });
  const j = await r.json();
  const box = $('#sos-box'); box.hidden = false; box.className = 'card alert';
  box.innerHTML = '<b>✅ SOS alert sent</b><br>Delivery status: ' + Object.entries(j.delivery || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
}

function startCountdown(reason) {
  let n = 10; const box = $('#sos-box'); box.hidden = false; box.className = 'card alert';
  box.innerHTML = `<b>🚨 Emergency detected.</b> SOS will be sent automatically in <b id="cd">${n}</b>s.<br>
    <button class="btn red" id="now">Send now</button> <button class="btn ghost" id="cancel">Cancel</button>`;
  $('#now').onclick = () => { clearInterval(timer); sendSOS(reason); };
  $('#cancel').onclick = () => { clearInterval(timer); box.hidden = true; };
  timer = setInterval(() => {
    n--; const cd = $('#cd'); if (cd) cd.textContent = n;
    if (n <= 0) { clearInterval(timer); sendSOS(reason); }
  }, 1000);
}

function render(j) {
  const box = $('#result'); box.hidden = false;
  box.className = 'card' + (j.emergency ? ' alert' : '');
  const tone = j.wellness_score >= 70 ? 'good' : j.wellness_score >= 40 ? 'mid' : 'bad';
  box.innerHTML = `<h2>Step 3-4 · AI Result (based on the details you just entered)</h2>
    <div class="score-row"><div class="score ${tone}"><b>${j.wellness_score}</b><small>Wellness<br>score</small></div>
    <div><h3 style="margin:0">Most likely: ${j.prediction} (${j.confidence}%)</h3>
    ${j.bmi ? `<p class="muted-p" style="margin:6px 0 0">BMI ${j.bmi} · ${j.bmi_category}</p>` : ''}
    ${j.low_confidence ? '<p class="muted-p" style="margin:6px 0 0">Model confidence is low - several conditions look similar. Please consult a doctor.</p>' : ''}</div></div>` +
    j.probabilities.map(p => `<div class="bar"><i style="width:${p.pct}%"></i><span>${p.label} ${p.pct}%</span></div>`).join('') +
    `<h3>Why this result</h3><ul>${j.factors.map(x => `<li>${x}</li>`).join('')}</ul>` +
    `<h3>Personalised recommendations</h3><ul>${j.recommendations.map(x => `<li>${x}</li>`).join('')}</ul>` +
    (j.emergency ? `<p><b>⚠ Emergency indicators:</b> ${j.reasons.join('; ')}</p>` : '') +
    `<p><a class="btn ghost" href="/records">View my health records</a></p>` +
    `<p class="muted">Screening aid only - not a diagnosis. Consult a doctor if unsure.</p>`;
  if (j.emergency) startCountdown(j.reasons.join('; '));
}

function showErrors(msg, fields) {
  const box = $('#form-error'); box.hidden = false; box.textContent = msg;
  document.querySelectorAll('#assess-form input').forEach(i => {
    i.classList.toggle('invalid', !!(fields && fields[i.name]));
    const old = i.parentElement.querySelector('.ferr'); if (old) old.remove();
    if (fields && fields[i.name]) {
      const m = document.createElement('span'); m.className = 'ferr'; m.textContent = fields[i.name];
      i.parentElement.appendChild(m);
    }
  });
  const first = document.querySelector('#assess-form input.invalid'); if (first) first.focus();
}

$('#assess-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  // client-side check: every required field must be filled (no defaults are assumed)
  const missing = {};
  form.querySelectorAll('input[required]').forEach(i => { if (i.value.trim() === '') missing[i.name] = 'This field is required.'; });
  if (Object.keys(missing).length) return showErrors('Please fill in all required details before we can predict.', missing);

  const d = Object.fromEntries(new FormData(form).entries());
  form.querySelectorAll('input[type=checkbox]').forEach(c => d[c.name] = c.checked ? 1 : 0);
  const btn = $('#submit-btn'); btn.disabled = true;
  try {
    const r = await fetch('/api/assess', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) });
    const j = await r.json();
    if (!r.ok) return showErrors(j.error || 'Something went wrong.', j.fields);
    $('#form-error').hidden = true; showErrors_clear();
    render(j);
    form.reset();                                   // next check-up starts blank, never pre-filled
    $('#result').scrollIntoView({ behavior: 'smooth' });
  } finally { btn.disabled = false; }
});

function showErrors_clear() {
  document.querySelectorAll('#assess-form input').forEach(i => {
    i.classList.remove('invalid'); const old = i.parentElement.querySelector('.ferr'); if (old) old.remove();
  });
}

$('#sos-btn').addEventListener('click', () => { if (confirm('Send an emergency SOS alert now?')) sendSOS('Manual SOS pressed by student'); });
refreshLocation();
