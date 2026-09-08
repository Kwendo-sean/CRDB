document.addEventListener('DOMContentLoaded', () => {
 const root = document.querySelector('.quiz-stage'); if (!root) return;
 const pendingKey = `pendingQuizAnswer:${root.dataset.quizId}`;
 const result = document.getElementById('answer-result');
 const choices = () => root.querySelectorAll('[data-choice]');
 const csrf = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
 const say = text => { if (result) result.textContent = text; };
 const lock = () => choices().forEach(b => b.disabled = true);
 const unlock = () => choices().forEach(b => b.disabled = false);

 // What the participant is told when the server refuses a submission. These are
 // real answers from the server, not connection problems, so the pending answer
 // is discarded rather than retried forever.
 const REJECTIONS = {
  question_closed_or_already_answered: 'TIME UP / THIS QUESTION IS CLOSED',
  invalid_submission: 'THAT ANSWER COULD NOT BE READ / REFRESH AND TRY AGAIN',
  too_many_submissions: 'TOO MANY TAPS / WAIT A MOMENT',
  quiz_not_open: 'THIS ROUND IS NOT OPEN',
  not_found: 'THIS ROUND IS NO LONGER AVAILABLE'
 };

 const syncState = async () => {
  try {
   const response = await fetch(root.dataset.stateUrl, { headers: { Accept: 'application/json' } });
   if (!response.ok) return null;
   const state = await response.json();
   if (state.answered) localStorage.removeItem(pendingKey);
   const questionId = state.question?.id ? String(state.question.id) : '';
   if (state.state !== root.dataset.quizState || questionId !== (root.dataset.questionId || '')) location.reload();
   return state;
  } catch { return null; }
 };

 const submit = async body => {
  lock();
  let response;
  try {
   response = await fetch(root.dataset.answerUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
    body: JSON.stringify(body)
   });
  } catch {
   // The request never reached the server. This is the only case worth retrying:
   // keep the answer with its original submission id so the retry is idempotent.
   say('CONNECTION INTERRUPTED / ANSWER SAVED, RETRYING');
   unlock();
   setTimeout(() => { if (localStorage.getItem(pendingKey)) submit(body); }, 3000);
   return;
  }

  let data = {};
  try { data = await response.json(); } catch { /* non-JSON error page */ }

  if (response.ok) {
   localStorage.removeItem(pendingKey);
   say(data.status === 'correct' ? `CORRECT ✓ / +${data.competition_points} PTS` : 'ANSWER LOCKED / 0 PTS');
   return;
  }

  // The server answered and refused. Never retry: the outcome will not change.
  localStorage.removeItem(pendingKey);
  const state = await syncState();
  if (response.status === 409 && state?.answered) { say('ANSWER / LOCKED'); return; }
  say(REJECTIONS[data.error] || (response.status === 403
   ? 'SESSION EXPIRED / REFRESH THIS PAGE'
   : 'THAT ANSWER WAS NOT ACCEPTED / REFRESH AND TRY AGAIN'));
 };

 const started = Date.now();
 choices().forEach(button => button.addEventListener('click', () => {
  const body = {
   question_id: +button.dataset.question,
   choice_id: +button.dataset.choice,
   submission_id: crypto.randomUUID(),
   response_duration_ms: Date.now() - started
  };
  localStorage.setItem(pendingKey, JSON.stringify(body));
  submit(body);
 }));

 // Resume an answer that was interrupted, but only for the question on screen.
 const pending = localStorage.getItem(pendingKey);
 if (pending) {
  try {
   const body = JSON.parse(pending);
   if (String(body.question_id) === (root.dataset.questionId || '')) submit(body);
   else localStorage.removeItem(pendingKey);
  } catch { localStorage.removeItem(pendingKey); }
 }

 // An auto-run round advances on the clock, so there is no host action to push
 // over the socket. Polling therefore always runs; the server answers it from a
 // shared cache, so the cost does not grow with the number of players. The socket
 // stays on top of it purely to make host actions land instantly.
 setInterval(syncState, 2000);
 const connect = () => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${location.host}/ws/quizzes/${root.dataset.quizId}/`);
  socket.onmessage = syncState;
  socket.onclose = () => setTimeout(connect, 3000);
  socket.onerror = () => socket.close();
 };
 connect();

 // Between questions the page shows a countdown to the next one opening.
 const lobby = document.getElementById('lobby-countdown');
 if (lobby) {
  let left = Number(lobby.dataset.seconds || 0);
  const tick = () => { lobby.textContent = left > 0 ? left : 'STARTING'; if (left-- > 0) setTimeout(tick, 1000); else syncState(); };
  tick();
 }

 const timer = document.getElementById('timer');
 if (timer && timer.dataset.deadline) {
  const tick = () => {
   const left = Math.max(0, Math.ceil((new Date(timer.dataset.deadline) - Date.now()) / 1000));
   timer.textContent = `00:${String(left).padStart(2, '0')}`;
   if (left) { setTimeout(tick, 250); return; }
   // The deadline has passed. Stop offering buttons the server will refuse.
   timer.textContent = 'TIME UP';
   lock();
   if (!localStorage.getItem(pendingKey) && result && !result.textContent) say('TIME UP / ANSWERS CLOSED');
   syncState();
   setTimeout(syncState, 1500);
  };
  tick();
 }
});
