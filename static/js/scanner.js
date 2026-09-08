// Staff QR scanner: pick a game or session once, then scan passes continuously.
(() => {
 const target = document.querySelector('#scan-target');
 const result = document.querySelector('#scan-result');
 if (!result) return;

 const REMEMBER = 'scannerTarget';
 if (target) {
  try { if (localStorage.getItem(REMEMBER)) target.value = localStorage.getItem(REMEMBER); } catch {}
  target.addEventListener('change', () => { try { localStorage.setItem(REMEMBER, target.value); } catch {} });
 }

 const csrf = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

 // A scan may deliver the full pass URL or just the token; both must work.
 const tokenFrom = value => {
  const raw = String(value || '').trim();
  try { return new URL(raw).pathname.split('/').filter(Boolean).pop(); } catch { return raw; }
 };

 const show = html => { result.innerHTML = html; };

 const award = async value => {
  if (!target || !target.value) {
   show('<div class="alert error"><strong>CHOOSE A GAME FIRST</strong><p>Select what you are scanning for at the top of this page.</p></div>');
   return;
  }
  show('<p>VERIFYING…</p>');
  let response, data;
  try {
   response = await fetch('/api/scan/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
    body: JSON.stringify({ qr_token: tokenFrom(value), target: target.value })
   });
   data = await response.json();
  } catch {
   show('<div class="alert error"><strong>NO CONNECTION</strong><p>Check the network and scan again.</p></div>');
   return;
  }
  if (!response.ok) {
   show(`<div class="alert error"><strong>NOT AWARDED</strong><p>${data.detail || 'That scan was not accepted.'}</p></div>`);
   return;
  }
  const label = target.options[target.selectedIndex].text;
  const fresh = data.status === 'awarded';
  show(`
   <p class="${fresh ? 'signal' : ''}">${fresh ? '✓ POINTS AWARDED' : 'ALREADY AWARDED'}</p>
   <h2>${data.participant.name}</h2>
   <p>${data.participant.department || 'CRDB PARTICIPANT'}</p>
   <p class="scan-what">${label}</p>
   ${fresh && data.points ? `<p class="scan-points">+${data.points} XP</p>` : ''}
   ${!fresh ? '<p class="scan-hint">This pass was already scanned for this. No double points.</p>' : ''}
   <p class="scan-hint">TOTAL XP / ${data.total_points}</p>
   <p class="scan-hint">Ready for the next pass.</p>
  `);
 };

 document.querySelector('#confirm-checkin')?.addEventListener('click', () => {
  award(document.querySelector('#manual-token')?.value);
 });

 document.querySelector('#start-scanner')?.addEventListener('click', async () => {
  if (!target || !target.value) { alert('Choose a game or session first.'); return; }
  if (!window.Html5Qrcode) { alert('Camera module unavailable — reload with a network connection.'); return; }
  const scanner = new Html5Qrcode('reader');
  document.querySelector('#start-scanner')?.remove();
  let busy = false;
  // Stay running between people: a stand scans a queue, not one pass.
  await scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 250, height: 250 } },
   async text => {
    if (busy) return;
    busy = true;
    await award(text);
    setTimeout(() => { busy = false; }, 1500);
   }, () => {});
 });
})();
